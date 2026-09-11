"""Occupancy detection on baseline residuals.

The detector replaces the LD2410's own occupancy decision. Every frame is
turned into per-channel z-scores against the learned noise baseline, hot gates
are grouped into spatially contiguous runs, and a hysteresis state machine
converts the strongest run's score into an occupancy bit.

Two failure modes drive the design:

* A single hot gate with quiet neighbours is physical nonsense for a person, so
  it is suppressed. That kills the "stuck gate 0" case that pins occupancy on
  for hours.
* Occupancy is entered at ``enter_score`` but only released after the score has
  stayed under the lower ``exit_score`` for ``hold_s`` continuously, which stops
  noise grazing a threshold from flapping the output.

Layered on top of that, the detector segments each gate's smoothed residual
into episodes and feeds them to the dwell-character classifier (see
:mod:`.episodes` and :mod:`.classifier`). Gates the classifier has learned are
bleed - only ever brief sweeps, never a dwell - stop counting toward *entry*,
which is what rejects a hallway pass-by seen through a wall before hysteresis
ever has to. They keep counting toward holding: once someone is in the room,
every gate helps keep them there. The same exclusion carries the spec 21
energy-ceiling boundary once it is both confirmed and enabled.

Entry is gated once more by the candidate's own raw energy: attenuated
through-wall activity is weak in the move *and* still channels at once, while
genuine presence keeps one of them strong however motionless it gets.

A last entry test asks for arrival-scale motion: someone walking into the room
drives the moving channel near whatever ceiling that sensor has learned, and a
wall attenuates activity too far to reach it. Both energy tests are entry-only
for the same reason the exclusion is.

All timing is derived from frame timestamps (``ts_mono`` for intervals,
``ts_utc`` for baseline bucketing, episode boundaries and statistics decay);
nothing here reads a clock, so a recorded stream replays identically.
"""

from __future__ import annotations

from math import exp
from typing import Any

from .baseline import (
    DEFAULT_BUCKET_S,
    DEFAULT_MIN_BUCKETS,
    BaselineModel,
)
from .classifier import GateClassifier
from .episodes import EpisodeTracker
from .types import (
    GATE_COUNT,
    DetectorConfig,
    DetectorOutput,
    Frame,
    GateTransition,
)

_CONFIDENCE_SLOPE = 4.0
"""Logistic slope factor; see :meth:`Detector._confidence`."""

_ZERO_RESIDUALS: tuple[float, ...] = (0.0,) * GATE_COUNT

GATE_STATS_KEY = "gate_stats"
"""Key the classifier state occupies inside the persisted detector state."""


def _never_excluded(gate: int) -> bool:
    """Exclusion predicate for the unmasked (holding) scoring pass."""
    del gate
    return False


class Detector:
    """Frame-driven occupancy state machine over a :class:`BaselineModel`."""

    __slots__ = (
        "_arrival_frames",
        "_baseline",
        "_classifier",
        "_combo_peak",
        "_config",
        "_episodes",
        "_freeze_until_mono",
        "_hold_until_mono",
        "_last_mono",
        "_leading_gate",
        "_occupied",
        "_support",
    )

    def __init__(
        self,
        config: DetectorConfig | None = None,
        *,
        baseline: BaselineModel | None = None,
        classifier: GateClassifier | None = None,
        bucket_s: float = DEFAULT_BUCKET_S,
        min_buckets: int = DEFAULT_MIN_BUCKETS,
    ) -> None:
        """Create a detector, optionally over restored learned state."""
        self._config = config or DetectorConfig()
        self._baseline = baseline or BaselineModel.from_config(
            self._config, bucket_s=bucket_s, min_buckets=min_buckets
        )
        self._classifier = classifier or GateClassifier(self._config)
        self._episodes = EpisodeTracker(self._config)
        self._occupied = False
        self._hold_until_mono: float | None = None
        self._freeze_until_mono: float | None = None
        self._support = [0.0] * GATE_COUNT
        self._last_mono: float | None = None
        self._combo_peak = 0.0
        self._arrival_frames = 0
        self._leading_gate: int | None = None

    @property
    def baseline(self) -> BaselineModel:
        """The baseline model this detector owns."""
        return self._baseline

    @property
    def classifier(self) -> GateClassifier:
        """The dwell-character gate classifier this detector owns."""
        return self._classifier

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
        A changed ``baseline_window_s`` resizes the live :class:`BaselineModel`
        so what later gets persisted always carries the new window. Note
        ``min_mad`` - the lower bound on the residual divisor - is read from
        the model built at construction time, so changing it takes effect on
        the next restart rather than immediately.
        """
        if config.baseline_window_s != self._config.baseline_window_s:
            self._baseline.resize_window(config.baseline_window_s)
        self._config = config
        self._classifier.reconfigure(config)
        self._episodes.reconfigure(config)

    def process(self, frame: Frame) -> DetectorOutput:
        """Consume one frame and return the resulting decision."""
        self._rebase_on_backwards_mono(frame.ts_mono)
        alpha = self._support_alpha(frame.ts_mono)

        if not self._baseline.ready:
            # Cold start: a fresh install must not sit blind for hours, so the
            # device's own bit is passed through at neutral confidence while
            # the baseline fills.
            self._occupied = frame.device_occupancy
            self._hold_until_mono = None
            self._freeze_until_mono = None
            self._decay_support(alpha)
            self._baseline.add_frame(frame)
            return DetectorOutput(
                occupied=frame.device_occupancy,
                confidence=0.5,
                score=0.0,
                active_gates=(),
                residuals_move=_ZERO_RESIDUALS,
                residuals_still=_ZERO_RESIDUALS,
                adaptation_frozen=False,
                baseline_age_s=self._baseline.age_s,
                baseline_ready=False,
                gate_classes=self._classifier.classes,
                boundary_gate=self._classifier.boundary_gate,
                last_in_room_gate=self._classifier.last_in_room_gate,
            )

        residuals_move, residuals_still = self._baseline.residuals(frame)
        # Negative residuals mean "quieter than the noise floor"; they carry no
        # evidence of presence, so they clamp to zero for scoring while the
        # signed values stay in the output for diagnostics.
        peaks = tuple(
            max(0.0, residuals_move[gate], residuals_still[gate])
            for gate in range(GATE_COUNT)
        )
        for gate in range(GATE_COUNT):
            self._support[gate] += alpha * (peaks[gate] - self._support[gate])
        # Entry is scored over in-room gates only; holding is scored over all
        # of them (spec 20 §4). Masking on ``not occupied`` is exactly that
        # rule: a bleed gate can never help enter the room, and can always
        # help keep it occupied.
        score, active_gates = self._score(peaks, masked=not self._occupied)
        self._track_candidate(frame, active_gates, residuals_move)
        below_floor = self._below_energy_floor(active_gates)
        arrival_suppressed = not below_floor and self._below_arrival_threshold(
            active_gates
        )
        entry_suppressed = below_floor or arrival_suppressed
        self._advance(score, frame.ts_mono, entry_suppressed=entry_suppressed)

        episodes = self._episodes.process(
            ts=frame.ts_utc,
            peaks=peaks,
            support=self._support,
            residuals_move=residuals_move,
            residuals_still=residuals_still,
            move_raw=frame.move_gates,
            active_gates=active_gates,
            occupied=self._occupied,
            entry_suppressed=entry_suppressed,
            arrival_suppressed=arrival_suppressed,
            leading_gate=self._leading_gate,
        )
        transitions: list[GateTransition] = []
        for episode in episodes:
            transitions.extend(self._classifier.observe(episode))
        # The tracker is asked for its open gates *after* this frame's closes
        # have been applied, so a boundary retreat blocked by an episode is
        # unblocked on the same frame that episode ends.
        ticked, boundary_transitions = self._classifier.tick(
            frame.ts_utc,
            open_gates=self._episodes.open_gates,
            open_starts=self._episodes.open_starts,
        )
        transitions.extend(ticked)

        # The baseline learns unconditionally. ``frozen`` is still computed and
        # reported - it is what the adaptation_frozen entity shows, and the
        # hold/freeze state machine it comes from is unchanged - but it no
        # longer gates learning; see the BaselineModel module docstring.
        frozen = self._is_frozen(frame.ts_mono)
        self._baseline.add_frame(frame)

        return DetectorOutput(
            occupied=self._occupied,
            confidence=self._confidence(score),
            score=score,
            active_gates=active_gates,
            residuals_move=residuals_move,
            residuals_still=residuals_still,
            adaptation_frozen=frozen,
            baseline_age_s=self._baseline.age_s,
            baseline_ready=True,
            gate_classes=self._classifier.classes,
            boundary_gate=self._classifier.boundary_gate,
            last_in_room_gate=self._classifier.last_in_room_gate,
            leading_gate=self._leading_gate,
            episodes=episodes,
            gate_transitions=tuple(transitions),
            boundary_transitions=boundary_transitions,
        )

    def state_to_dict(self) -> dict[str, Any]:
        """Return everything this detector has learned, JSON-safe.

        Deliberately a superset of :meth:`BaselineModel.to_dict` rather than a
        new envelope around it: the classifier state rides along under
        :data:`GATE_STATS_KEY`, so a payload written by this version still
        loads in an older one (which ignores the extra key), and a payload
        written by an older one still loads here (the key is simply absent and
        every gate starts unknown - the permissive default). Callers that
        already persist ``detector.baseline.to_dict()`` need only swap in this
        method.
        """
        return {**self._baseline.to_dict(), GATE_STATS_KEY: self._classifier.to_dict()}

    @staticmethod
    def classifier_from_state(
        data: dict[str, Any] | None, config: DetectorConfig
    ) -> GateClassifier | None:
        """Rebuild the classifier out of :meth:`state_to_dict` output.

        Returns ``None`` when the payload carries no classification, which is
        the case for state written before this phase existed.
        """
        if not data:
            return None
        gate_stats = data.get(GATE_STATS_KEY)
        if not gate_stats:
            return None
        return GateClassifier.from_dict(gate_stats, config)

    def _score(
        self, peaks: tuple[float, ...], *, masked: bool
    ) -> tuple[float, tuple[int, ...]]:
        """Score the strongest spatially coherent run of hot gates.

        With ``masked`` set, gates the classifier has learned are bleed (or
        that the manual ``max_gate`` override has capped out) are invisible:
        they neither carry score themselves nor lend a lone neighbour the
        partial elevation that would rescue it.
        """
        k = self._config.k
        partial = k / 2.0
        excluded = self._classifier.excluded if masked else _never_excluded
        best_score = 0.0
        best_run: tuple[int, ...] = ()

        run: list[int] = []
        for gate in range(GATE_COUNT + 1):
            hot = gate < GATE_COUNT and peaks[gate] >= k and not excluded(gate)
            if hot:
                run.append(gate)
                continue
            if not run:
                continue
            if len(run) == 1:
                # An isolated hot gate is only credible if a neighbour shows at
                # least partial elevation — a still person concentrates energy
                # in one gate but always spills a little into the next.
                #
                # The neighbour test runs on time-smoothed elevation, not the
                # raw frame: a person's spill is sustained, whereas a single
                # noisy sample crossing k/2 would otherwise be enough to rescue
                # a permanently stuck gate ten times a minute.
                only = run[0]
                left = (
                    self._support[only - 1]
                    if only > 0 and not excluded(only - 1)
                    else 0.0
                )
                right = (
                    self._support[only + 1]
                    if only + 1 < GATE_COUNT and not excluded(only + 1)
                    else 0.0
                )
                if left < partial and right < partial:
                    run = []
                    continue
            run_score = sum(peaks[index] for index in run) / k
            if run_score > best_score:
                best_score = run_score
                best_run = tuple(run)
            run = []

        return best_score, best_run

    def _track_candidate(
        self,
        frame: Frame,
        active_gates: tuple[int, ...],
        residuals_move: tuple[float, ...],
    ) -> None:
        """Fold this frame into the entry evidence of the activity in progress.

        Energy is read over the entry-scored gates only, so an excluded gate
        can never lift a candidate past a threshold, and it accumulates over
        the whole candidate rather than one frame: a person's strongest return
        is a single moment of a dwell.

        The leading edge outlives the candidate window on purpose - it stays
        readable for the whole visit it opened, and only a fully quiet band
        clears it.
        """
        activity = bool(active_gates or self._episodes.open_gates)
        if self._occupied or not activity:
            self._combo_peak = 0.0
            self._arrival_frames = 0
        if not activity:
            self._leading_gate = None

        arrival = self._config.arrival_frac * self._baseline.move_ceiling
        reached_arrival = False
        for gate in active_gates:
            combo = float(frame.move_gates[gate] + frame.still_gates[gate])
            self._combo_peak = max(self._combo_peak, combo)
            reached_arrival |= frame.move_gates[gate] >= arrival
        self._arrival_frames += int(reached_arrival)

        for gate in range(GATE_COUNT):
            if residuals_move[gate] >= self._config.k:
                if self._leading_gate is None or gate < self._leading_gate:
                    self._leading_gate = gate
                break

    def _below_energy_floor(self, active_gates: tuple[int, ...]) -> bool:
        """Whether the candidate is still too faint in both channels to enter."""
        floor = self._config.energy_floor
        return (
            bool(active_gates)
            and not self._occupied
            and floor > 0.0
            and self._combo_peak < floor
        )

    def _below_arrival_threshold(self, active_gates: tuple[int, ...]) -> bool:
        """Whether the candidate has yet to show arrival-scale motion.

        An unlearned ceiling leaves the rule inactive: it may only ever
        tighten a sensor that has seen what strong motion looks like, never
        block a fresh install.
        """
        return (
            bool(active_gates)
            and not self._occupied
            and self._config.arrival_frac > 0.0
            and self._baseline.move_ceiling_learned
            and self._arrival_frames < self._config.arrival_min_frames
        )

    def _rebase_on_backwards_mono(self, ts_mono: float) -> None:
        """Rebase hold/freeze deadlines if ``ts_mono`` jumped backwards.

        ``ts_mono`` is a per-process monotonic clock, not wall time. A
        recorded dataset that spans an HA restart replays a ``ts_mono`` that
        drops back near zero partway through. Left alone, any active hold or
        freeze deadline - an absolute value in the old timebase - becomes
        unreachable, wedging the detector in its current occupancy state and
        freezing baseline adaptation forever. Restarting both countdowns from
        the new timebase is the conservative, bounded fix: it never extends a
        deadline beyond one full hold/freeze period from the jump.

        ``_last_mono`` itself needs no explicit reset here: ``_support_alpha``
        unconditionally overwrites it with this frame's ``ts_mono`` right
        after this runs, and a negative elapsed time there already yields a
        zero smoothing weight instead of corrupting the support estimate.
        """
        previous = self._last_mono
        if previous is None or ts_mono >= previous:
            return
        if self._hold_until_mono is not None:
            self._hold_until_mono = ts_mono + self._config.hold_s
        if self._freeze_until_mono is not None:
            self._freeze_until_mono = ts_mono + self._config.freeze_hold_s

    def _support_alpha(self, ts_mono: float) -> float:
        """Return the EMA weight for this frame, derived from the frame gap.

        Deriving alpha from the elapsed frame time rather than a fixed
        per-frame constant keeps the smoothing identical under 10Hz streaming
        and under a gappy or decimated replay.
        """
        previous = self._last_mono
        self._last_mono = ts_mono
        tau = self._config.support_tau_s
        if previous is None or tau <= 0.0:
            return 1.0
        elapsed = ts_mono - previous
        if elapsed <= 0.0:
            return 0.0
        return 1.0 - exp(-elapsed / tau)

    def _decay_support(self, alpha: float) -> None:
        """Relax the neighbour-support estimate towards zero."""
        for gate in range(GATE_COUNT):
            self._support[gate] -= alpha * self._support[gate]

    def _advance(
        self, score: float, ts_mono: float, *, entry_suppressed: bool = False
    ) -> None:
        """Step the hysteresis state machine using frame time only.

        ``entry_suppressed`` reads as "this frame did not score" for entry, and
        is deliberately ignored once occupied: exit stays score-driven so a
        person decaying to faint stillness is never dropped.
        """
        config = self._config
        if not self._occupied:
            if score >= config.enter_score and not entry_suppressed:
                self._occupied = True
                self._hold_until_mono = None
            return

        if score >= config.exit_score:
            # Recovered during the countdown: cancel it entirely.
            self._hold_until_mono = None
        elif self._hold_until_mono is None:
            self._hold_until_mono = ts_mono + config.hold_s
        elif ts_mono >= self._hold_until_mono:
            self._occupied = False
            self._hold_until_mono = None
            self._freeze_until_mono = ts_mono + config.freeze_hold_s

    def _is_frozen(self, ts_mono: float) -> bool:
        """Whether the detector is inside its occupied-plus-cooldown period.

        Reported as ``DetectorOutput.adaptation_frozen``. It no longer stops
        the baseline learning - see :class:`~.baseline.BaselineModel` - but the
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
        reads 0.5 exactly at ``enter_score`` — so anything short of entry sits
        in 0..0.5 — and saturates towards 1 for strong evidence.
        """
        enter = self._config.enter_score
        slope = _CONFIDENCE_SLOPE / enter if enter > 0.0 else _CONFIDENCE_SLOPE
        # Scores are non-negative, so the exponent is bounded by slope * enter
        # (4.0 by construction) and exp() cannot overflow here.
        return 1.0 / (1.0 + exp(-slope * (score - enter)))
