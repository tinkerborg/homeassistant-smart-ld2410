"""Occupancy decision over a pipeline of stages.

The detector replaces the LD2410's own occupancy decision. Every frame is
turned into per-channel z-scores against the learned noise baseline, hot gates
are grouped into spatially contiguous runs (:mod:`.coherence`), and a
hysteresis state machine converts the strongest run's score into an occupancy
bit: entry at ``enter_score``, release only after the score has stayed under
the lower ``exit_score`` for ``hold_s`` continuously, which stops noise grazing
a threshold from flapping the output.

What sits around that state machine is composed rather than hard-coded. The
stages named by ``DetectorConfig.stages`` are built into a :class:`.Pipeline`
and answer two questions: entry filters say whether a candidate may become an
occupancy, and hold refreshers say whether this frame's evidence keeps one
alive. The state they share - baseline residuals, per-gate statistics, the
candidate's accumulated evidence, the classifier, and the retention/ownership
tracker - lives in :class:`~.context.DetectorContext`.

Alongside the decision, the detector segments each gate's smoothed residual
into episodes and feeds them to the dwell-character classifier (see
:mod:`.episodes` and :mod:`.classifier`). Gates the classifier has learned are
bleed stop counting toward *entry*, which is what rejects a hallway pass-by
seen through a wall before hysteresis ever has to; they keep counting toward
holding, because once someone is in the room every gate helps keep them there.

All timing is derived from frame timestamps (``ts_mono`` for intervals,
``ts_utc`` for baseline bucketing, episode boundaries and statistics decay);
nothing here reads a clock, so a recorded stream replays identically.
"""

from __future__ import annotations

from math import exp
from typing import Any

from .baseline import Baseline
from .context import ZERO_RESIDUALS, DetectorContext
from .episodes import EpisodeTracker
from .gates import GateModel
from .pipeline import build_pipeline
from .presence import Presence
from .roles import StageEnv
from .types import (
    DEFAULT_BUCKET_S,
    DEFAULT_MIN_BUCKETS,
    DetectorConfig,
    DetectorOutput,
    Frame,
    GateTransition,
)

_CONFIDENCE_SLOPE = 4.0
"""Logistic slope factor; see :meth:`Detector._confidence`."""

GATE_STATS_KEY = "gate_stats"
"""Key the classifier state occupies inside the persisted detector state."""

RETENTION_KEY = "retention"
"""Key the retention/ownership state occupies inside the persisted state."""


class Detector:
    """Frame-driven occupancy state machine over a configured stage pipeline."""

    __slots__ = (
        "_config",
        "_context",
        "_episodes",
        "_freeze_until_mono",
        "_hold_until_mono",
        "_occupied",
        "_pipeline",
    )

    def __init__(
        self,
        config: DetectorConfig | None = None,
        *,
        baseline: Baseline | None = None,
        gates: GateModel | None = None,
        presence: Presence | None = None,
        bucket_s: float = DEFAULT_BUCKET_S,
        min_buckets: int = DEFAULT_MIN_BUCKETS,
    ) -> None:
        """Create a detector, optionally over restored learned state."""
        self._config = config or DetectorConfig()
        self._episodes = EpisodeTracker(self._config)
        self._pipeline = build_pipeline(
            StageEnv(self._config, bucket_s=bucket_s, min_buckets=min_buckets),
            baseline=baseline,
            gates=gates,
            presence=presence,
        )
        self._context = DetectorContext(
            self._config, pipeline=self._pipeline, episodes=self._episodes
        )
        self._occupied = False
        self._hold_until_mono: float | None = None
        self._freeze_until_mono: float | None = None

    @property
    def baseline(self) -> Baseline:
        """The baseline model this detector owns."""
        return self._pipeline.baseline

    @property
    def gates(self) -> GateModel:
        """What this detector has learned about each gate."""
        return self._pipeline.gates

    @property
    def presence(self) -> Presence:
        """The retention, ownership and arming state this detector owns."""
        return self._pipeline.presence

    @property
    def config(self) -> DetectorConfig:
        """The tuning knobs in force."""
        return self._config

    @property
    def occupied(self) -> bool:
        """Current occupancy state."""
        return self._occupied

    def reconfigure(self, config: DetectorConfig) -> None:
        """Swap tuning knobs in place, keeping the baseline and hysteresis state.

        Lets HA options updates apply without a restart or a baseline reset.
        A changed ``baseline_window_s`` resizes the live :class:`~.baseline.Baseline`
        so what later gets persisted always carries the new window. Note
        ``min_mad`` - the lower bound on the residual divisor - is read from
        the model built at construction time, so changing it takes effect on
        the next restart rather than immediately.
        """
        if config.baseline_window_s != self._config.baseline_window_s:
            self.baseline.resize_window(config.baseline_window_s)
        self._config = config
        self._context.reconfigure(config)
        self._episodes.reconfigure(config)
        self._pipeline.reconfigure(config)

    def process(self, frame: Frame) -> DetectorOutput:
        """Consume one frame and return the resulting decision."""
        context = self._context
        if context.timebase_restarted(frame.ts_mono):
            context.rebase()
            self._rebase_deadlines(frame.ts_mono)
        context.begin_frame(frame)

        if not self.baseline.ready:
            return self._passthrough(frame)

        context.measure(occupied=self._occupied)
        verdict = self._pipeline.entry_verdict(context)
        self._advance(frame.ts_mono, admitted=verdict.admitted)

        episodes = self._episodes.process(
            ts=frame.ts_utc,
            peaks=context.peaks,
            support=context.support,
            residuals_move=context.residuals_move,
            residuals_still=context.residuals_still,
            move_raw=frame.move_gates,
            active_gates=context.active_gates,
            occupied=self._occupied,
            rejection=verdict.reason,
            leading_gate=context.leading_gate,
        )
        transitions: list[GateTransition] = []
        for episode in episodes:
            transitions.extend(self.gates.observe(episode))
        # The tracker is asked for its open gates *after* this frame's closes
        # have been applied, so a boundary retreat blocked by an episode is
        # unblocked on the same frame that episode ends.
        ticked, boundary_transitions = self.gates.tick(
            frame.ts_utc,
            open_gates=self._episodes.open_gates,
            open_starts=self._episodes.open_starts,
        )
        transitions.extend(ticked)

        # The baseline learns unconditionally. ``frozen`` is still computed and
        # reported - it is what the adaptation_frozen entity shows, and the
        # hold/freeze state machine it comes from is unchanged - but it no
        # longer gates learning; see the baseline package docstring.
        frozen = self._is_frozen(frame.ts_mono)
        self.baseline.add_frame(frame)

        return DetectorOutput(
            occupied=self._occupied,
            confidence=self._confidence(context.score),
            score=context.score,
            active_gates=context.active_gates,
            residuals_move=context.residuals_move,
            residuals_still=context.residuals_still,
            adaptation_frozen=frozen,
            baseline_age_s=self.baseline.age_s,
            baseline_ready=True,
            gate_classes=self.gates.classes,
            boundary_gate=self.gates.boundary_gate,
            last_in_room_gate=self.gates.last_in_room_gate,
            leading_gate=context.leading_gate,
            ownership=self.presence.state,
            retention_max=self.presence.level,
            episodes=episodes,
            gate_transitions=tuple(transitions),
            boundary_transitions=boundary_transitions,
        )

    def state_to_dict(self) -> dict[str, Any]:
        """Return everything this detector has learned, JSON-safe.

        Deliberately a superset of :meth:`Baseline.to_dict` rather than a
        new envelope around it: the classifier state rides along under
        :data:`GATE_STATS_KEY`, so a payload written by this version still
        loads in an older one (which ignores the extra key), and a payload
        written by an older one still loads here (the key is simply absent and
        every gate starts unknown - the permissive default). Callers that
        already persist ``detector.baseline.to_dict()`` need only swap in this
        method.
        """
        return {
            **self.baseline.to_dict(),
            GATE_STATS_KEY: self.gates.to_dict(),
            RETENTION_KEY: self.presence.to_dict(),
        }

    @staticmethod
    def presence_from_state(
        data: dict[str, Any] | None, config: DetectorConfig
    ) -> Presence | None:
        """Rebuild the presence stages out of :meth:`state_to_dict` output.

        Returns ``None`` when the payload predates this phase, which starts the
        statistic from the live stream again.
        """
        if not data:
            return None
        presence = data.get(RETENTION_KEY)
        if not presence:
            return None
        return Presence.from_dict(presence, config)

    @staticmethod
    def gates_from_state(
        data: dict[str, Any] | None, config: DetectorConfig
    ) -> GateModel | None:
        """Rebuild the gate model out of :meth:`state_to_dict` output.

        Returns ``None`` when the payload carries no classification, which is
        the case for state written before this phase existed.
        """
        if not data:
            return None
        gate_stats = data.get(GATE_STATS_KEY)
        if not gate_stats:
            return None
        return GateModel.from_dict(gate_stats, config)

    def _passthrough(self, frame: Frame) -> DetectorOutput:
        """Publish the device's own bit while the baseline fills.

        A fresh install must not sit blind for hours, so the device's decision
        stands at neutral confidence until residuals mean something.
        """
        self._occupied = frame.device_occupancy
        self._hold_until_mono = None
        self._freeze_until_mono = None
        self._context.decay_support()
        self.baseline.add_frame(frame)
        return DetectorOutput(
            occupied=frame.device_occupancy,
            confidence=0.5,
            score=0.0,
            active_gates=(),
            residuals_move=ZERO_RESIDUALS,
            residuals_still=ZERO_RESIDUALS,
            adaptation_frozen=False,
            baseline_age_s=self.baseline.age_s,
            baseline_ready=False,
            gate_classes=self.gates.classes,
            boundary_gate=self.gates.boundary_gate,
            last_in_room_gate=self.gates.last_in_room_gate,
        )

    def _rebase_deadlines(self, ts_mono: float) -> None:
        """Restart the hold and freeze countdowns in a fresh timebase.

        ``ts_mono`` is a per-process monotonic clock, not wall time. A recorded
        dataset that spans an HA restart replays a ``ts_mono`` that drops back
        near zero partway through. Left alone, any active deadline - an
        absolute value in the old timebase - becomes unreachable, wedging the
        detector in its current occupancy state and freezing baseline
        adaptation forever. Restarting both countdowns from the new timebase is
        the conservative, bounded fix: it never extends a deadline beyond one
        full hold/freeze period from the jump.
        """
        if self._hold_until_mono is not None:
            self._hold_until_mono = ts_mono + self._config.hold_s
        if self._freeze_until_mono is not None:
            self._freeze_until_mono = ts_mono + self._config.freeze_hold_s

    def _advance(self, ts_mono: float, *, admitted: bool) -> None:
        """Step the hysteresis state machine using frame time only.

        A rejected candidate reads as "this frame did not score" for entry, and
        entry filters are deliberately not consulted once occupied: exit stays
        score-driven so a person decaying to faint stillness is never dropped.
        An owned occupancy asks a harder question than the score alone - see
        :mod:`.presence`.
        """
        config = self._config
        context = self._context
        presence = self.presence
        if not self._occupied:
            if context.score >= config.enter_score and admitted:
                self._occupied = True
                self._hold_until_mono = None
                presence.claim(context.active_gates, context.leading_gate)
            return

        if presence.owned:
            presence.include(context.active_gates)
            presence.step_arming(ts_mono)

        if self._pipeline.refreshes_hold(context):
            # Recovered during the countdown: cancel it entirely.
            self._hold_until_mono = None
        elif self._hold_until_mono is None:
            self._hold_until_mono = ts_mono + config.hold_s
        elif ts_mono >= self._hold_until_mono:
            self._occupied = False
            self._hold_until_mono = None
            self._freeze_until_mono = ts_mono + config.freeze_hold_s
            presence.release()

    def _is_frozen(self, ts_mono: float) -> bool:
        """Whether the detector is inside its occupied-plus-cooldown period.

        Reported as ``DetectorOutput.adaptation_frozen``. It no longer stops
        the baseline learning - see :class:`~.baseline.Baseline` - but the
        state machine and the entity it feeds are unchanged.
        """
        if self._occupied:
            return True
        if self._freeze_until_mono is None:
            return False
        if ts_mono < self._freeze_until_mono:
            return True
        self._freeze_until_mono = None
        return False

    def _confidence(self, score: float) -> float:
        """Map a score to 0..1 through a logistic centred on ``enter_score``.

        ``confidence = 1 / (1 + exp(-a * (score - enter_score)))`` with
        ``a = 4 / enter_score``. It is continuous and strictly increasing,
        reads 0.5 exactly at ``enter_score`` - so anything short of entry sits
        in 0..0.5 - and saturates towards 1 for strong evidence.
        """
        enter = self._config.enter_score
        slope = _CONFIDENCE_SLOPE / enter if enter > 0.0 else _CONFIDENCE_SLOPE
        # Scores are non-negative, so the exponent is bounded by slope * enter
        # (4.0 by construction) and exp() cannot overflow here.
        return 1.0 / (1.0 + exp(-slope * (score - enter)))
