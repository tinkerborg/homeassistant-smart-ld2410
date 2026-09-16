"""The reference level an arrival is measured against (spec 22 §1).

One bucket contributes the level its moving channel routinely reached while it
was open; the ceiling is the strongest such level still inside the window, so
it converges towards the strongest motion the sensor ever sees and relearns
once those buckets age out.

It is deliberately sensor-global rather than per-gate: attenuation is absolute
on a 0-100 scale, and a per-gate reference would normalise a bleed-only gate
into passing its own bleed.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from ..roles import ROLE_CEILING, Stage, StageEnv
from ..types import Frame
from .window import BucketWindow, quantile

CEILING_BUCKET_QUANTILE = 0.90
"""Sample quantile within a bucket that summarises it for the ceiling."""


class _CeilingWindow(BucketWindow):
    """The bucket levels the ceiling is the maximum of."""

    __slots__ = ("levels",)

    def __init__(self, *, bucket_s: float, max_buckets: int) -> None:
        super().__init__(bucket_s=bucket_s, max_buckets=max_buckets)
        self.levels: deque[float] = deque(maxlen=max_buckets)

    def resize(self, max_buckets: int) -> None:
        super().resize(max_buckets)
        self.levels = deque(self.levels, maxlen=max_buckets)

    def summarise(self, ordered: list[int]) -> None:
        self.levels.append(quantile(ordered, CEILING_BUCKET_QUANTILE))


class MoveCeiling(Stage):
    """Sensor-global reference level for arrival-scale moving energy."""

    __slots__ = ("_max_buckets", "_window")

    role = ROLE_CEILING

    def __init__(self, env: StageEnv) -> None:
        """Start an unlearned ceiling over the window ``env`` describes."""
        super().__init__(env)
        self._max_buckets = max(1, round(env.config.baseline_window_s / env.bucket_s))
        self._window = _CeilingWindow(
            bucket_s=env.bucket_s, max_buckets=self._max_buckets
        )

    @property
    def learned(self) -> bool:
        """Whether any bucket has closed, i.e. whether :attr:`value` means anything."""
        return bool(self._window.levels)

    @property
    def value(self) -> float:
        """The reference level, in raw energy units (0.0 while unlearned)."""
        levels = self._window.levels
        return max(levels) if levels else 0.0

    def add_frame(self, frame: Frame) -> None:
        """Ingest one frame's strongest moving return."""
        self._window.add_sample(frame.ts_utc, max(frame.move_gates))

    def resize(self, max_buckets: int) -> None:
        """Change the window capacity, truncating the oldest buckets if shrinking."""
        self._max_buckets = max_buckets
        self._window.resize(max_buckets)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe snapshot of the ceiling."""
        return {"levels": list(self._window.levels), **self._window.open_state()}

    def restore(self, data: dict[str, Any]) -> None:
        """Restore the ceiling from :meth:`to_dict` output."""
        self._window.levels = deque(
            (float(value) for value in data["levels"]), maxlen=self._max_buckets
        )
        self._window.restore_open(data)
