"""The shared per-frame state every detector stage reads.

One context lives for the detector's lifetime and is stepped once per frame.
It owns the quantities more than one stage needs - the baseline residuals, the
time-smoothed per-gate support, the coherent run's score and band, and where
the activity in progress began - plus the composites a stage may consult: the
baseline, the gate model, the episode tracker and the presence stages.

All timing comes from ``Frame.ts_mono`` for intervals and ``Frame.ts_utc`` for
anything persisted; nothing here reads a clock.
"""

from __future__ import annotations

from math import exp
from typing import TYPE_CHECKING

from .scoring.runs import admit_every_gate
from .types import GATE_COUNT, DetectorConfig, Frame

if TYPE_CHECKING:
    from .baseline import Baseline
    from .episodes import EpisodeTracker
    from .gates import GateModel
    from .pipeline import Pipeline
    from .presence import Presence

ZERO_RESIDUALS: tuple[float, ...] = (0.0,) * GATE_COUNT

_NO_FRAME = Frame(
    ts_utc=0.0,
    ts_mono=0.0,
    move_gates=(0,) * GATE_COUNT,
    still_gates=(0,) * GATE_COUNT,
    target_distance_cm=0,
    device_occupancy=False,
)
"""Stands in until the first frame arrives, so a stage never reads a ``None``."""


class DetectorContext:
    """Everything a stage may read about the frame being processed."""

    __slots__ = (
        "_alpha",
        "_last_mono",
        "active_gates",
        "activity",
        "config",
        "episodes",
        "frame",
        "frame_leading_gate",
        "leading_gate",
        "occupied",
        "peaks",
        "pipeline",
        "residuals_move",
        "residuals_still",
        "score",
        "support",
    )

    def __init__(
        self,
        config: DetectorConfig,
        *,
        pipeline: Pipeline,
        episodes: EpisodeTracker,
    ) -> None:
        """Create a context over the pipeline the detector assembled."""
        self.config = config
        self.pipeline = pipeline
        self.episodes = episodes
        self.frame = _NO_FRAME
        self.occupied = False
        self.activity = False
        self.score = 0.0
        self.active_gates: tuple[int, ...] = ()
        self.peaks = ZERO_RESIDUALS
        self.residuals_move = ZERO_RESIDUALS
        self.residuals_still = ZERO_RESIDUALS
        self.support = [0.0] * GATE_COUNT
        self.leading_gate: int | None = None
        self.frame_leading_gate: int | None = None
        self._alpha = 1.0
        self._last_mono: float | None = None

    @property
    def ts_mono(self) -> float:
        """Frame time of the frame in progress."""
        return self.frame.ts_mono

    @property
    def baseline(self) -> Baseline:
        """The learned noise model."""
        return self.pipeline.baseline

    @property
    def gates(self) -> GateModel:
        """What the sensor has learned about each gate."""
        return self.pipeline.gates

    @property
    def presence(self) -> Presence:
        """Retention, ownership and the arming sequence."""
        return self.pipeline.presence

    def reconfigure(self, config: DetectorConfig) -> None:
        """Adopt new tuning knobs."""
        self.config = config

    def timebase_restarted(self, ts_mono: float) -> bool:
        """Whether ``ts_mono`` jumped backwards, i.e. a new process's clock."""
        previous = self._last_mono
        return previous is not None and ts_mono < previous

    def rebase(self) -> None:
        """Forget timings left over from a timebase that has restarted."""
        self.presence.rebase()

    def begin_frame(self, frame: Frame) -> None:
        """Start a frame: derive its smoothing weight and fold in the still channel."""
        self.frame = frame
        self._alpha = self._support_alpha(frame.ts_mono)
        self.presence.update(frame.ts_mono, frame.still_gates)

    def decay_support(self) -> None:
        """Relax the neighbour-support estimate towards zero."""
        for gate in range(GATE_COUNT):
            self.support[gate] -= self._alpha * self.support[gate]

    def measure(self, *, occupied: bool) -> None:
        """Derive this frame's residuals, score, and candidate evidence.

        ``occupied`` is the occupancy in force while the frame is scored: entry
        is scored over in-room gates only, holding over all of them, so masking
        on ``not occupied`` is exactly the rule that a bleed gate can never help
        enter the room and can always help keep it occupied.
        """
        self.occupied = occupied
        frame = self.frame
        self.residuals_move, self.residuals_still = self.baseline.residuals(frame)
        # Negative residuals mean "quieter than the noise floor"; they carry no
        # evidence of presence, so they clamp to zero for scoring while the
        # signed values stay in the output for diagnostics.
        self.peaks = tuple(
            max(0.0, self.residuals_move[gate], self.residuals_still[gate])
            for gate in range(GATE_COUNT)
        )
        for gate in range(GATE_COUNT):
            self.support[gate] += self._alpha * (self.peaks[gate] - self.support[gate])
        self.score, self.active_gates = self.pipeline.score(
            self.peaks,
            self.support,
            excluded=self.gates.excluded if not occupied else admit_every_gate,
        )
        self.activity = bool(self.active_gates or self.episodes.open_gates)
        self._track_leading_edge()
        self.pipeline.observe_entry(self)
        self.presence.observe_lead(frame.ts_mono, self.frame_leading_gate)

    def _track_leading_edge(self) -> None:
        """Record where the activity in progress began.

        The leading edge outlives the candidate window on purpose - it stays
        readable for the whole visit it opened, and only a fully quiet band
        clears it.
        """
        if not self.activity:
            self.leading_gate = None
        leading = self.pipeline.leading_gate(self.residuals_move, self.support)
        self.frame_leading_gate = leading
        if leading is not None and (
            self.leading_gate is None or leading < self.leading_gate
        ):
            self.leading_gate = leading

    def _support_alpha(self, ts_mono: float) -> float:
        """Return the EMA weight for this frame, derived from the frame gap.

        Deriving alpha from the elapsed frame time rather than a fixed
        per-frame constant keeps the smoothing identical under 10Hz streaming
        and under a gappy or decimated replay.
        """
        previous = self._last_mono
        self._last_mono = ts_mono
        tau = self.config.support_tau_s
        if previous is None or tau <= 0.0:
            return 1.0
        elapsed = ts_mono - previous
        if elapsed <= 0.0:
            return 0.0
        return 1.0 - exp(-elapsed / tau)
