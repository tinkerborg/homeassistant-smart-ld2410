"""The residual divisor, measured on the quiet population alone.

A whole-window spread is inflated by an activity tail far more than a floor is,
which is what erases the detection margin of a gate someone is sitting in front
of. The median absolute deviation of the samples within ``mode_band`` of the
floor's mode measures the width of the quiet peak instead, which is the width
exceedance scoring is asking about.

The histogram floor already holds the counts this reads, so this stage
accumulates nothing of its own and persists nothing of its own.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..roles import ROLE_SPREAD, Stage, StageEnv
from ..types import Frame
from .histogram_floor import HistogramFloor

_SPREAD_FLOOR = 1e-6
"""Absolute minimum divisor, regardless of the configured minimum.

A pathological ``min_mad=0`` config combined with a perfectly flat noise floor
would otherwise divide by zero.
"""


class ModeSpread(Stage):
    """Per-channel residual divisor: the mode-local median absolute deviation."""

    __slots__ = ("_floor",)

    role = ROLE_SPREAD

    requires = ("histogram_floor",)

    def __init__(self, env: StageEnv, histogram_floor: HistogramFloor) -> None:
        """Read the spread off the counts the histogram floor accumulates."""
        super().__init__(env)
        self._floor = histogram_floor

    @property
    def minimum(self) -> float:
        """Lower bound on the divisor."""
        return max(self._config.min_mad, _SPREAD_FLOOR)

    def value(self, channel: str, gate: int) -> float:
        """The divisor one channel's residuals are taken over."""
        mode = self._floor.value(channel, gate)
        band = self._config.mode_band
        deviations = sorted(
            (abs(value - mode), count)
            for value, count in self._floor.counts(channel, gate).items()
            if abs(value - mode) <= band
        )
        return max(_weighted_median(deviations), self.minimum)

    def add_frame(self, frame: Frame) -> None:
        """Accept a frame; the histogram floor is what accumulates it."""
        del frame

    def resize(self, max_buckets: int) -> None:
        """Accept a resize; the histogram floor is what holds the window."""
        del max_buckets

    def channel_state(self, channel: str, gate: int) -> dict[str, Any]:
        """Return one channel's snapshot, JSON-safe."""
        del channel, gate
        return {}

    def restore_channel(self, channel: str, gate: int, data: dict[str, Any]) -> None:
        """Restore one channel from :meth:`channel_state` output."""
        del channel, gate, data


def _weighted_median(ordered: Sequence[tuple[float, int]]) -> float:
    total = sum(count for _, count in ordered)
    if not total:
        return 0.0
    seen = 0
    for deviation, count in ordered:
        seen += count
        if seen * 2 >= total:
            return deviation
    return ordered[-1][0]
