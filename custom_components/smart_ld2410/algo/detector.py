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

All timing is derived from frame timestamps (``ts_mono`` for intervals,
``ts_utc`` for baseline bucketing); nothing here reads a clock, so a recorded
stream replays identically.
"""

from __future__ import annotations

from math import exp

from .baseline import (
    DEFAULT_BUCKET_S,
    DEFAULT_MIN_BUCKETS,
    BaselineModel,
)
from .types import GATE_COUNT, DetectorConfig, DetectorOutput, Frame

_CONFIDENCE_SLOPE = 4.0
"""Logistic slope factor; see :meth:`Detector._confidence`."""

_ZERO_RESIDUALS: tuple[float, ...] = (0.0,) * GATE_COUNT


class Detector:
    """Frame-driven occupancy state machine over a :class:`BaselineModel`."""

    __slots__ = (
        "_baseline",
        "_config",
        "_freeze_until_mono",
        "_hold_until_mono",
        "_last_mono",
        "_occupied",
        "_support",
    )

    def __init__(
        self,
        config: DetectorConfig | None = None,
        *,
        baseline: BaselineModel | None = None,
        bucket_s: float = DEFAULT_BUCKET_S,
        min_buckets: int = DEFAULT_MIN_BUCKETS,
    ) -> None:
        """Create a detector, optionally over a restored baseline model."""
        self._config = config or DetectorConfig()
        self._baseline = baseline or BaselineModel.from_config(
            self._config, bucket_s=bucket_s, min_buckets=min_buckets
        )
        self._occupied = False
        self._hold_until_mono: float | None = None
        self._freeze_until_mono: float | None = None
        self._support = [0.0] * GATE_COUNT
        self._last_mono: float | None = None

    @property
    def baseline(self) -> BaselineModel:
        """The baseline model this detector owns."""
        return self._baseline

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
        score, active_gates = self._score(peaks)
        self._advance(score, frame.ts_mono)

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
        )

    def _score(self, peaks: tuple[float, ...]) -> tuple[float, tuple[int, ...]]:
        """Score the strongest spatially coherent run of hot gates."""
        k = self._config.k
        partial = k / 2.0
        best_score = 0.0
        best_run: tuple[int, ...] = ()

        run: list[int] = []
        for gate in range(GATE_COUNT + 1):
            hot = gate < GATE_COUNT and peaks[gate] >= k
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
                left = self._support[only - 1] if only > 0 else 0.0
                right = self._support[only + 1] if only + 1 < GATE_COUNT else 0.0
                if left < partial and right < partial:
                    run = []
                    continue
            run_score = sum(peaks[index] for index in run) / k
            if run_score > best_score:
                best_score = run_score
                best_run = tuple(run)
            run = []

        return best_score, best_run

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

    def _advance(self, score: float, ts_mono: float) -> None:
        """Step the hysteresis state machine using frame time only."""
        config = self._config
        if not self._occupied:
            if score >= config.enter_score:
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
