"""Causal motion anchored still footprint.

This small stateful primitive pairs a current still-channel residual with the
strongest recent motion-assisted footprint.  Floor and spread are supplied by
the caller so this class does not learn, age, or otherwise own baseline state.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING, Sequence

from ..roles import ADMIT, ROLE_ENTRY_FILTER, EntryVerdict, Stage, StageEnv
from ..types import CHANNEL_STILL

if TYPE_CHECKING:
    from ..context import DetectorContext


GATE_START = 2
GATE_STOP = 9
GATE_COUNT = GATE_STOP - GATE_START


@dataclass(frozen=True, slots=True)
class MotionAnchorResult:
    """The causal result for one frame."""

    anchored: bool
    score: float
    template: tuple[float, ...] | None

    @property
    def active(self) -> bool:
        """Whether the current still footprint supports the anchor."""
        return self.anchored

    def __bool__(self) -> bool:
        """Allow callers to use an update result directly in a condition."""
        return self.anchored


class MotionAnchor:
    """Track a still footprint introduced by sufficiently strong motion."""

    __slots__ = (
        "motion_threshold",
        "retention",
        "max_gap_s",
        "_template",
        "_previous_ts",
        "_score",
        "_anchored",
    )

    def __init__(
        self,
        motion_threshold: float = 40.0,
        retention: float = 0.4,
        max_gap_s: float = 0.55,
    ) -> None:
        """Create an empty anchor with the experiment's default thresholds."""
        if not all(
            isfinite(float(x)) for x in (motion_threshold, retention, max_gap_s)
        ):
            raise ValueError("thresholds must be finite")
        if retention < 0.0 or max_gap_s < 0.0:
            raise ValueError("retention and max_gap_s must be non-negative")
        self.motion_threshold = float(motion_threshold)
        self.retention = float(retention)
        self.max_gap_s = float(max_gap_s)
        self._template: tuple[float, ...] | None = None
        self._previous_ts: float | None = None
        self._score = 0.0
        self._anchored = False

    @property
    def anchored(self) -> bool:
        """Whether the last valid frame supports a live template."""
        return self._anchored

    @property
    def score(self) -> float:
        """Least-squares support score from the last valid frame."""
        return self._score

    @property
    def template(self) -> tuple[float, ...] | None:
        """The current motion-derived footprint, if one exists."""
        return self._template

    def update(
        self,
        ts_mono: float,
        move: Sequence[float],
        still: Sequence[float],
        floor: Sequence[float],
        spread: Sequence[float],
    ) -> MotionAnchorResult:
        """Fold one frame and return its causal support result.

        ``move``, ``still``, ``floor`` and ``spread`` may be full nine-gate
        arrays or the already-selected seven gates.  Full arrays use gates
        2..8; seven-element arrays are accepted for experiment adapters.
        Invalid input is ignored without changing learned state.
        """
        values = self._select(move, still, floor, spread)
        timestamp = self._finite(ts_mono)
        if values is None or timestamp is None:
            return self._result(False, 0.0)
        m, s, f, d = values

        previous = self._previous_ts
        self._previous_ts = timestamp
        if previous is not None and (
            timestamp < previous or timestamp - previous > self.max_gap_s
        ):
            self._clear_template()

        residual = tuple(
            max(value - base, 0.0) / scale for value, base, scale in zip(s, f, d)
        )
        peak = max(m)
        candidate = tuple(
            value * (motion / max(peak, 1.0)) for value, motion in zip(residual, m)
        )
        norm = sum(value * value for value in candidate)
        if peak >= self.motion_threshold and norm >= 1.0:
            old_norm = self._template_norm() if self._template is not None else 0.0
            if self._template is None or norm > old_norm:
                self._template = candidate

        if self._template is None:
            self._score = 0.0
            self._anchored = False
            return self._result(False, 0.0)
        denominator = self._template_norm()
        score = (
            sum(value * anchor for value, anchor in zip(residual, self._template))
            / denominator
        )
        self._score = score
        self._anchored = score >= self.retention
        if not self._anchored:
            self._clear_template()
        return self._result(self._anchored, score)

    def reset(self) -> None:
        """Forget the template and timestamp."""
        self._clear_template()
        self._previous_ts = None

    def rebase(self) -> None:
        """Restart timestamp continuity while forgetting the template."""
        self.reset()

    def _template_norm(self) -> float:
        assert self._template is not None
        return sum(value * value for value in self._template)

    def _clear_template(self) -> None:
        self._template = None
        self._score = 0.0
        self._anchored = False

    def _result(self, anchored: bool, score: float) -> MotionAnchorResult:
        return MotionAnchorResult(anchored, score, self._template)

    @staticmethod
    def _finite(value: float) -> float | None:
        try:
            value = float(value)
        except TypeError, ValueError:
            return None
        return value if isfinite(value) else None

    @staticmethod
    def _select(*arrays: Sequence[float]) -> tuple[tuple[float, ...], ...] | None:
        selected: list[tuple[float, ...]] = []
        for array in arrays:
            try:
                length = len(array)
                if length == 9:
                    values = tuple(float(x) for x in array[GATE_START:GATE_STOP])
                elif length == GATE_COUNT:
                    values = tuple(float(x) for x in array)
                else:
                    return None
            except TypeError, ValueError:
                return None
            if not all(isfinite(x) for x in values):
                return None
            selected.append(values)
        if any(value <= 0.0 for value in selected[3]):
            return None
        return tuple(selected)  # type: ignore[return-value]


class MotionAnchorStage(Stage):
    """Qualify entry and hold occupancy using an anchored still footprint."""

    role = ROLE_ENTRY_FILTER

    def __init__(self, env: StageEnv) -> None:
        super().__init__(env)
        self.tracker = MotionAnchor()
        self.supported = False

    def accumulate(self, context: DetectorContext) -> None:
        frame = context.frame
        baseline = context.baseline
        result = self.tracker.update(
            frame.ts_mono,
            frame.move_gates,
            frame.still_gates,
            tuple(baseline.floor(g, CHANNEL_STILL) for g in range(9)),
            tuple(baseline.spread(g, CHANNEL_STILL) for g in range(9)),
        )
        self.supported = result.anchored

    def verdict(self, context: DetectorContext) -> EntryVerdict:
        return ADMIT if self.supported else EntryVerdict("rejected_motion_anchor")

    def refreshes(self, context: DetectorContext) -> bool:
        return self.supported
