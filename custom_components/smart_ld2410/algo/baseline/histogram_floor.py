"""The learned empty-room energy level, read as the peak of the distribution.

An occupied gate's energy distribution is a sharp ambient peak with an activity
tail hanging off it: quiet frames keep arriving in long blocks between
movements, so the peak sits where the empty room is however much of the window
the tail covers. Reading the peak instead of a time quantile is what lets a
gate learn its floor from a window that was never once unoccupied.

Until a gate has observed ``mode_min_s`` of samples its peak is untrusted: a
freshly power-cycled channel reads saturated, and a mode estimator follows it
straight to the top of the scale.

All timing comes from ``Frame.ts_utc``; nothing here reads a clock.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from typing import Any

from ..roles import ROLE_FLOOR, Stage, StageEnv
from ..types import CHANNEL_MOVE, CHANNEL_STILL, CHANNELS, GATE_COUNT, Frame
from .window import BucketWindow


class _HistogramChannel(BucketWindow):
    """One channel's window of per-bucket energy histograms."""

    __slots__ = (
        "_buckets",
        "_last_ts",
        "_mode",
        "_observed_s",
        "_open_counts",
        "_totals",
        "_trusted",
    )

    def __init__(self, *, bucket_s: float, max_buckets: int) -> None:
        super().__init__(bucket_s=bucket_s, max_buckets=max_buckets)
        self._buckets: deque[dict[int, int]] = deque()
        self._totals: dict[int, int] = {}
        self._open_counts: dict[int, int] = {}
        self._observed_s = 0.0
        self._last_ts: float | None = None
        self._mode: float | None = None
        self._trusted: float | None = None

    @property
    def bucket_count(self) -> int:
        return len(self._buckets)

    @property
    def counts(self) -> Mapping[int, int]:
        return self._totals

    @property
    def mode(self) -> float | None:
        if self._mode is None and self._totals:
            self._mode = float(
                min(self._totals.items(), key=lambda item: (-item[1], item[0]))[0]
            )
        return self._mode

    def floor(self, min_observed_s: float) -> float:
        mode = self.mode
        if mode is not None and self._observed_s >= min_observed_s:
            self._trusted = mode
        return self._trusted if self._trusted is not None else 0.0

    def add_sample(self, ts_utc: float, value: int) -> None:
        super().add_sample(ts_utc, value)
        self._open_counts[value] = self._open_counts.get(value, 0) + 1
        self._totals[value] = self._totals.get(value, 0) + 1
        if self._last_ts is not None:
            # A dropout is time nobody observed, so a gap contributes at most
            # the bucket it interrupted - otherwise hours of downtime would
            # satisfy the saturation guard with seconds of samples.
            self._observed_s += min(max(ts_utc - self._last_ts, 0.0), self._bucket_s)
        self._last_ts = ts_utc
        self._mode = None

    def discard_open_bucket(self) -> None:
        self._subtract(self._open_counts)
        self._open_counts = {}
        self._mode = None
        super().discard_open_bucket()

    def resize(self, max_buckets: int) -> None:
        super().resize(max_buckets)
        self._evict_beyond_capacity()

    def summarise(self, ordered: list[int]) -> None:
        del ordered
        self._buckets.append(self._open_counts)
        self._open_counts = {}
        self._evict_beyond_capacity()

    def to_dict(self) -> dict[str, Any]:
        return {
            "histograms": [sorted(counts.items()) for counts in self._buckets],
            "histogram_observed_s": self._observed_s,
            "histogram_mode": self._trusted,
            **self.open_state(),
        }

    def restore(self, data: dict[str, Any], *, max_buckets: int) -> None:
        histograms = data.get("histograms")
        if histograms is None:
            return
        self._buckets = deque(
            {int(value): int(count) for value, count in counts}
            for counts in histograms
        )
        self._open_counts = {}
        self.restore_open(data)
        for value in self._open_samples:
            self._open_counts[value] = self._open_counts.get(value, 0) + 1
        self._totals = {}
        for counts in (*self._buckets, self._open_counts):
            for value, count in counts.items():
                self._totals[value] = self._totals.get(value, 0) + count
        self._observed_s = float(data.get("histogram_observed_s", 0.0))
        mode = data.get("histogram_mode")
        self._trusted = None if mode is None else float(mode)
        self._last_ts = None
        self._mode = None
        self.resize(max_buckets)

    def _evict_beyond_capacity(self) -> None:
        while len(self._buckets) > self._max_buckets:
            self._subtract(self._buckets.popleft())

    def _subtract(self, counts: dict[int, int]) -> None:
        for value, count in counts.items():
            remaining = self._totals[value] - count
            if remaining > 0:
                self._totals[value] = remaining
            else:
                del self._totals[value]
        self._mode = None


class HistogramFloor(Stage):
    """Per-channel noise floor: the dominant low mode of the energy histogram."""

    __slots__ = ("_channels", "_max_buckets")

    role = ROLE_FLOOR

    def __init__(self, env: StageEnv) -> None:
        """Start an empty floor over the window ``env`` describes."""
        super().__init__(env)
        self._max_buckets = max(1, round(env.config.baseline_window_s / env.bucket_s))
        self._channels = {
            channel: [
                _HistogramChannel(bucket_s=env.bucket_s, max_buckets=self._max_buckets)
                for _ in range(GATE_COUNT)
            ]
            for channel in CHANNELS
        }

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
        """The learned empty-room level of one channel (0.0 while untrusted)."""
        return self._channels[channel][gate].floor(self._config.mode_min_s)

    def counts(self, channel: str, gate: int) -> Mapping[int, int]:
        """How often each energy value occurs across the window."""
        return self._channels[channel][gate].counts

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
