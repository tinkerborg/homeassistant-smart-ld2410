"""The residual divisor: how high a channel routinely reaches.

Real idle gates are not Gaussian. A live gate measured at 10Hz sits at 15 for
most samples and excursions to 25-35 several times a minute; its MAD is 1-2
while its tail reaches +17, so dividing by a MAD turns an utterly ordinary
noise excursion into a z-score of 15. ``q90 - q50`` measures what a detection
threshold actually has to clear.

The 25th percentile is applied to the spreads too: a bucket that contained a
person is wide as well as high, and a low quantile keeps such buckets from
inflating the divisor and desensitising the gate.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from ..roles import ROLE_SPREAD, Stage, StageEnv
from ..types import CHANNEL_MOVE, CHANNEL_STILL, CHANNELS, GATE_COUNT, Frame
from .window import BucketWindow, quantile

SPREAD_QUANTILE = 0.25
"""Window quantile of the bucket spreads that defines the residual divisor."""

BUCKET_TAIL_QUANTILE = 0.90
"""Sample quantile within a bucket whose distance above ``q50`` is its spread."""

_SPREAD_FLOOR = 1e-6
"""Absolute minimum divisor, regardless of the configured minimum.

A pathological ``min_mad=0`` config combined with a perfectly flat noise floor
would otherwise divide by zero.
"""


class _SpreadChannel(BucketWindow):
    """One channel's window of bucket upper-tail spreads."""

    __slots__ = ("_cache", "_minimum", "_spreads")

    def __init__(self, *, bucket_s: float, max_buckets: int, minimum: float) -> None:
        super().__init__(bucket_s=bucket_s, max_buckets=max_buckets)
        self._minimum = minimum
        self._spreads: deque[float] = deque(maxlen=max_buckets)
        self._cache: float | None = None

    @property
    def bucket_count(self) -> int:
        return len(self._spreads)

    @property
    def value(self) -> float:
        if self._cache is None:
            if self._spreads:
                self._cache = max(
                    quantile(sorted(self._spreads), SPREAD_QUANTILE), self._minimum
                )
            else:
                self._cache = self._minimum
        return self._cache

    def resize(self, max_buckets: int) -> None:
        super().resize(max_buckets)
        self._spreads = deque(self._spreads, maxlen=max_buckets)
        self._cache = None

    def summarise(self, ordered: list[int]) -> None:
        q50 = quantile(ordered, 0.5)
        self._spreads.append(max(0.0, quantile(ordered, BUCKET_TAIL_QUANTILE) - q50))
        self._cache = None

    def to_dict(self) -> dict[str, Any]:
        return {"spreads": list(self._spreads), **self.open_state()}

    def restore(self, data: dict[str, Any], *, max_buckets: int) -> None:
        if "spreads" not in data:
            return
        self._spreads = deque(
            (float(value) for value in data["spreads"]), maxlen=max_buckets
        )
        self.restore_open(data)
        self._cache = None


class TailSpread(Stage):
    """Per-channel residual divisor: the 25th percentile of ``q90 - q50``."""

    __slots__ = ("_channels", "_max_buckets", "_minimum")

    role = ROLE_SPREAD

    def __init__(self, env: StageEnv) -> None:
        """Start an empty spread over the window ``env`` describes."""
        super().__init__(env)
        self._minimum = max(env.config.min_mad, _SPREAD_FLOOR)
        self._max_buckets = max(1, round(env.config.baseline_window_s / env.bucket_s))
        self._channels = {
            channel: [
                _SpreadChannel(
                    bucket_s=env.bucket_s,
                    max_buckets=self._max_buckets,
                    minimum=self._minimum,
                )
                for _ in range(GATE_COUNT)
            ]
            for channel in CHANNELS
        }

    @property
    def minimum(self) -> float:
        """Lower bound on the divisor, as persisted with the model."""
        return self._minimum

    @property
    def bucket_count(self) -> int:
        """Closed buckets in the window, identical across channels."""
        return self._channels[CHANNEL_MOVE][0].bucket_count

    def add_frame(self, frame: Frame) -> None:
        """Ingest one frame into every channel."""
        for gate in range(GATE_COUNT):
            self._channels[CHANNEL_MOVE][gate].add_sample(
                frame.ts_utc, frame.move_gates[gate]
            )
            self._channels[CHANNEL_STILL][gate].add_sample(
                frame.ts_utc, frame.still_gates[gate]
            )

    def value(self, channel: str, gate: int) -> float:
        """The divisor one channel's residuals are taken over."""
        return self._channels[channel][gate].value

    def resize(self, max_buckets: int) -> None:
        """Change the window capacity, truncating the oldest buckets if shrinking."""
        self._max_buckets = max_buckets
        for channels in self._channels.values():
            for channel in channels:
                channel.resize(max_buckets)

    def channel_state(self, channel: str, gate: int) -> dict[str, Any]:
        """Return one channel's snapshot, JSON-safe."""
        return self._channels[channel][gate].to_dict()

    def restore_channel(self, channel: str, gate: int, data: dict[str, Any]) -> None:
        """Restore one channel from :meth:`channel_state` output."""
        self._channels[channel][gate].restore(data, max_buckets=self._max_buckets)
