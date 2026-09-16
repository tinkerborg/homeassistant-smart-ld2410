"""The learned empty-room energy level, per gate and channel.

A person only ever *adds* energy to a gate, so vacant buckets sit at the bottom
of the distribution and a low quantile reads the empty-room level even when the
room was occupied for much of the window. That is what lets the floor be
learned with people in the room, and why adaptation never has to be frozen.

The tradeoff, stated honestly: a room occupied for more than ~75% of the
learning window starts to absorb its occupant and the gate goes numb until the
window turns over. That is accepted - a baseline that occasionally desensitises
after a nine-hour vigil is strictly better than one that can never unlearn a
noise source it mistook for a person.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from ..roles import ROLE_FLOOR, Stage, StageEnv
from ..types import CHANNEL_MOVE, CHANNEL_STILL, CHANNELS, GATE_COUNT, Frame
from .window import BucketWindow, quantile

FLOOR_QUANTILE = 0.25
"""Window quantile of the bucket medians that defines the noise floor."""


class _FloorChannel(BucketWindow):
    """One channel's window of bucket medians."""

    __slots__ = ("_cache", "_medians")

    def __init__(self, *, bucket_s: float, max_buckets: int) -> None:
        super().__init__(bucket_s=bucket_s, max_buckets=max_buckets)
        self._medians: deque[float] = deque(maxlen=max_buckets)
        self._cache: float | None = None

    @property
    def bucket_count(self) -> int:
        return len(self._medians)

    @property
    def value(self) -> float:
        if self._cache is None:
            self._cache = (
                quantile(sorted(self._medians), FLOOR_QUANTILE)
                if self._medians
                else 0.0
            )
        return self._cache

    def resize(self, max_buckets: int) -> None:
        super().resize(max_buckets)
        self._medians = deque(self._medians, maxlen=max_buckets)
        self._cache = None

    def summarise(self, ordered: list[int]) -> None:
        self._medians.append(quantile(ordered, 0.5))
        self._cache = None

    def to_dict(self) -> dict[str, Any]:
        return {"q50s": list(self._medians), **self.open_state()}

    def restore(self, data: dict[str, Any], *, max_buckets: int) -> None:
        if "q50s" not in data:
            return
        self._medians = deque(
            (float(value) for value in data["q50s"]), maxlen=max_buckets
        )
        self.restore_open(data)
        self._cache = None


class QuantileFloor(Stage):
    """Per-channel noise floor: the 25th percentile of the bucket medians."""

    __slots__ = ("_channels", "_max_buckets")

    role = ROLE_FLOOR

    def __init__(self, env: StageEnv) -> None:
        """Start an empty floor over the window ``env`` describes."""
        super().__init__(env)
        self._max_buckets = max(1, round(env.config.baseline_window_s / env.bucket_s))
        self._channels = {
            channel: [
                _FloorChannel(bucket_s=env.bucket_s, max_buckets=self._max_buckets)
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
        """The learned empty-room level of one channel (0.0 while empty)."""
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
