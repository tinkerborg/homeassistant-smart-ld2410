"""Per-gate noise baseline for the radar feature pipeline.

The baseline models the environmental noise floor of every gate channel
(9 gates x move/still = 18 channels) as a *low quantile* of the recent past
plus an upper-tail spread, and it learns unconditionally - it is never told
that the room is occupied.

Two tiers keep hours of 10Hz data affordable:

* Bucket tier: raw samples accumulate into fixed buckets (60s by default,
  keyed by ``Frame.ts_utc``). When a bucket closes it contributes two numbers
  and the samples are dropped: the bucket's sample median ``q50``, and the
  bucket's upper-tail spread ``q90 - q50``.
* Window tier: two index-aligned deques of those pairs spanning ``window_s``.
  ``floor`` is the 25th percentile of the bucket ``q50``s; ``spread`` is the
  25th percentile of the bucket spreads, floored at the configured minimum.

Residuals are ``(energy - floor) / spread``.

Why a low quantile instead of a median
--------------------------------------
A person only ever *adds* energy to a gate. Vacant buckets therefore sit at
the bottom of the distribution, so a low quantile reads the empty-room level
even when the room was occupied for much of the window. That is what lets the
baseline be learned with people in the room, and it is why adaptation no
longer has to be frozen during detection.

Freezing adaptation while occupied - the previous design - created a death
spiral: any noise source strong enough to trigger detection froze the very
learning that would have absorbed it, so the sensor latched occupied forever.
:meth:`BaselineModel.add_frame` still accepts ``frozen`` for call-site
compatibility, and ignores it.

Why an upper-tail spread instead of a MAD
-----------------------------------------
Real idle gates are not Gaussian. A live gate measured at 10Hz sits at 15 for
most samples and excursions to 25-35 several times a minute; its MAD is 1-2
while its tail reaches +17. Dividing by a MAD turns an utterly ordinary noise
excursion into a z-score of 15, and two adjacent gates doing it at once clear
any sane entry threshold. ``q90 - q50`` measures how high a channel routinely
reaches, which is exactly what a detection threshold has to clear, and on the
recorded hardware it takes the worst idle-noise score in an empty room from
5.6 (well past the 3.0 entry threshold) to 1.3.

The 25th percentile is applied to the spreads too: a bucket that contained a
person is wide as well as high, and taking a low quantile keeps such buckets
from inflating the divisor and desensitising the gate.

The tradeoff, stated honestly
-----------------------------
If a room is occupied for more than ~75% of the learning window, the 25th
percentile starts to absorb the occupant and the gate goes numb until the
window turns over. The default 12h window makes that rare, and the detector's
freeze no longer protects against it. That is accepted: a baseline that
occasionally desensitises after a 9-hour vigil is strictly better than one
that can never unlearn a noise source it mistook for a person.

No wall-clock time is read anywhere: all timing comes from frame timestamps.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from typing import Any

from .types import GATE_COUNT, DetectorConfig, Frame

SCHEMA_VERSION = 3
"""Bumped to 3 for the quantile estimator.

Version 1 stored bucket medians, version 2 added per-bucket MADs. Neither
carries the per-bucket upper-tail spread this estimator divides by, and it
cannot be reconstructed from summaries that never recorded it, so
:meth:`BaselineModel.from_dict` refuses both rather than misreading them.
"""

DEFAULT_BUCKET_S = 60.0
"""Width of one accumulation bucket, in seconds of frame time."""

DEFAULT_MIN_BUCKETS = 5
"""Closed buckets needed before the baseline is usable (5 minutes by default)."""

FLOOR_QUANTILE = 0.25
"""Window quantile of the bucket medians that defines the noise floor."""

SPREAD_QUANTILE = 0.25
"""Window quantile of the bucket spreads that defines the residual divisor."""

BUCKET_TAIL_QUANTILE = 0.90
"""Sample quantile within a bucket whose distance above ``q50`` is its spread."""

_SPREAD_FLOOR = 1e-6
"""Absolute minimum divisor, regardless of the configured minimum.

A pathological ``min_mad=0`` config combined with a perfectly flat noise
floor would otherwise make :meth:`BaselineModel.residuals` divide by zero.
"""


def _quantile(ordered: Sequence[float], q: float) -> float:
    """Return the linearly interpolated ``q`` quantile of a sorted sequence."""
    last = len(ordered) - 1
    if last <= 0:
        return float(ordered[0])
    position = q * last
    lower = int(position)
    upper = min(lower + 1, last)
    fraction = position - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction)


class GateBaseline:
    """Quantile floor/spread estimator for a single gate channel."""

    __slots__ = (
        "_bucket_s",
        "_cache",
        "_max_buckets",
        "_min_spread",
        "_open_index",
        "_open_samples",
        "_q50s",
        "_spreads",
    )

    def __init__(self, *, bucket_s: float, max_buckets: int, min_spread: float) -> None:
        """Initialise an empty baseline."""
        self._bucket_s = bucket_s
        self._max_buckets = max_buckets
        self._min_spread = min_spread
        self._q50s: deque[float] = deque(maxlen=max_buckets)
        self._spreads: deque[float] = deque(maxlen=max_buckets)
        self._open_index: int | None = None
        self._open_samples: list[int] = []
        self._cache: tuple[float, float] | None = None

    @property
    def bucket_count(self) -> int:
        """Number of closed buckets currently in the window."""
        return len(self._q50s)

    @property
    def floor(self) -> float:
        """The learned empty-room energy level (0.0 while empty).

        The 25th percentile of the closed buckets' sample medians.
        """
        return self._stats()[0]

    @property
    def spread(self) -> float:
        """The residual divisor: how high this channel routinely reaches.

        The 25th percentile of the closed buckets' ``q90 - q50``, floored.
        """
        return self._stats()[1]

    def _stats(self) -> tuple[float, float]:
        """Return the cached (floor, spread) pair, recomputing if stale."""
        if self._cache is None:
            minimum = max(self._min_spread, _SPREAD_FLOOR)
            if self._q50s:
                floor = _quantile(sorted(self._q50s), FLOOR_QUANTILE)
                spread = _quantile(sorted(self._spreads), SPREAD_QUANTILE)
                self._cache = (floor, max(spread, minimum))
            else:
                self._cache = (0.0, minimum)
        return self._cache

    def add_sample(self, ts_utc: float, value: int) -> None:
        """Accumulate one raw sample, closing the previous bucket if needed."""
        index = int(ts_utc // self._bucket_s)
        if self._open_index is None:
            self._open_index = index
        elif index != self._open_index:
            if index - self._open_index > 1:
                # The open bucket only partly covers time before a gap of
                # more than one bucket (a BLE dropout, or hours of HA
                # downtime for a restored open bucket): closing it into the
                # window would let a fragment stand in for the whole bucket,
                # so it is discarded instead - matching the rule that gaps
                # are never back-filled.
                self.discard_open_bucket()
            else:
                self._close_open_bucket()
            self._open_index = index
        self._open_samples.append(value)

    def discard_open_bucket(self) -> None:
        """Throw away the in-progress bucket.

        Used when a gap means the accumulated fragment cannot honestly stand
        in for a whole bucket's worth of time.
        """
        self._open_index = None
        self._open_samples.clear()

    def resize(self, max_buckets: int) -> None:
        """Change the window capacity, truncating the oldest buckets if shrinking.

        Growing keeps every existing bucket summary and simply allows more to
        accumulate; shrinking keeps only the newest ``max_buckets`` of both the
        median and the spread series, which stay index-aligned.
        """
        self._max_buckets = max_buckets
        self._q50s = deque(self._q50s, maxlen=max_buckets)
        self._spreads = deque(self._spreads, maxlen=max_buckets)
        self._cache = None

    def _close_open_bucket(self) -> None:
        """Move the in-progress bucket's median and tail spread into the window."""
        if self._open_samples:
            ordered = sorted(self._open_samples)
            q50 = _quantile(ordered, 0.5)
            self._q50s.append(q50)
            self._spreads.append(
                max(0.0, _quantile(ordered, BUCKET_TAIL_QUANTILE) - q50)
            )
            self._cache = None
        self._open_samples = []

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe snapshot of this channel."""
        return {
            "q50s": list(self._q50s),
            "spreads": list(self._spreads),
            "open_index": self._open_index,
            "open_samples": list(self._open_samples),
        }

    def restore(self, data: dict[str, Any]) -> None:
        """Restore this channel from :meth:`to_dict` output."""
        self._q50s = deque(
            (float(value) for value in data["q50s"]), maxlen=self._max_buckets
        )
        self._spreads = deque(
            (float(value) for value in data["spreads"]), maxlen=self._max_buckets
        )
        if len(self._spreads) != len(self._q50s):
            raise ValueError("baseline channel has mismatched bucket series")
        open_index = data.get("open_index")
        self._open_index = None if open_index is None else int(open_index)
        self._open_samples = [int(value) for value in data.get("open_samples", ())]
        self._cache = None


class BaselineModel:
    """The 18 per-channel baselines for one sensor, plus persistence."""

    __slots__ = (
        "_bucket_s",
        "_min_buckets",
        "_min_spread",
        "_move",
        "_still",
        "_window_s",
    )

    def __init__(
        self,
        *,
        window_s: float,
        min_spread: float,
        bucket_s: float = DEFAULT_BUCKET_S,
        min_buckets: int = DEFAULT_MIN_BUCKETS,
    ) -> None:
        """Initialise 18 empty channel baselines."""
        self._window_s = window_s
        self._min_spread = min_spread
        self._bucket_s = bucket_s
        self._min_buckets = min_buckets
        max_buckets = max(1, round(window_s / bucket_s))
        self._move = [
            GateBaseline(
                bucket_s=bucket_s, max_buckets=max_buckets, min_spread=min_spread
            )
            for _ in range(GATE_COUNT)
        ]
        self._still = [
            GateBaseline(
                bucket_s=bucket_s, max_buckets=max_buckets, min_spread=min_spread
            )
            for _ in range(GATE_COUNT)
        ]

    @classmethod
    def from_config(
        cls,
        config: DetectorConfig,
        *,
        bucket_s: float = DEFAULT_BUCKET_S,
        min_buckets: int = DEFAULT_MIN_BUCKETS,
    ) -> BaselineModel:
        """Build a model from the detector's tuning knobs.

        ``DetectorConfig.min_mad`` keeps its name for wiring compatibility; it
        is the lower bound on the residual divisor.
        """
        return cls(
            window_s=config.baseline_window_s,
            min_spread=config.min_mad,
            bucket_s=bucket_s,
            min_buckets=min_buckets,
        )

    @property
    def move(self) -> list[GateBaseline]:
        """Per-gate move-channel baselines."""
        return self._move

    @property
    def still(self) -> list[GateBaseline]:
        """Per-gate still-channel baselines."""
        return self._still

    @property
    def bucket_s(self) -> float:
        """Width of one accumulation bucket, in seconds."""
        return self._bucket_s

    @property
    def bucket_count(self) -> int:
        """Closed buckets in the window (identical across channels)."""
        return self._move[0].bucket_count

    @property
    def ready(self) -> bool:
        """Whether enough data has accumulated for residuals to mean anything."""
        return self.bucket_count >= self._min_buckets

    @property
    def age_s(self) -> float:
        """Seconds of data accumulated into the window."""
        return self.bucket_count * self._bucket_s

    def resize_window(self, window_s: float) -> None:
        """Resize the baseline window in place, keeping accumulated data.

        Used by :meth:`Detector.reconfigure` so that changing
        ``baseline_window_s`` at runtime resizes the live model instead of
        being silently ignored until the next restart. Shrinking truncates
        each channel to its newest buckets; growing keeps everything and
        simply raises the cap on future accumulation.
        """
        self._window_s = window_s
        max_buckets = max(1, round(window_s / self._bucket_s))
        for channel in self._move:
            channel.resize(max_buckets)
        for channel in self._still:
            channel.resize(max_buckets)

    def add_frame(self, frame: Frame, *, frozen: bool = False) -> None:
        """Ingest one frame into every channel.

        ``frozen`` is accepted so existing call sites keep working and is
        deliberately ignored: the quantile floor reads the empty-room level
        out of a partly occupied window on its own, and gating learning on
        the detector's own output is what allowed a noise source to latch
        occupancy permanently. See the module docstring.
        """
        del frozen
        for gate in range(GATE_COUNT):
            self._move[gate].add_sample(frame.ts_utc, frame.move_gates[gate])
            self._still[gate].add_sample(frame.ts_utc, frame.still_gates[gate])

    def residuals(self, frame: Frame) -> tuple[tuple[float, ...], tuple[float, ...]]:
        """Return signed z-scores ``(energy - floor) / spread`` for all channels."""
        move = tuple(
            (frame.move_gates[gate] - self._move[gate].floor) / self._move[gate].spread
            for gate in range(GATE_COUNT)
        )
        still = tuple(
            (frame.still_gates[gate] - self._still[gate].floor)
            / self._still[gate].spread
            for gate in range(GATE_COUNT)
        )
        return move, still

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe snapshot of the whole model."""
        return {
            "version": SCHEMA_VERSION,
            "window_s": self._window_s,
            "bucket_s": self._bucket_s,
            "min_spread": self._min_spread,
            "min_buckets": self._min_buckets,
            "move": [channel.to_dict() for channel in self._move],
            "still": [channel.to_dict() for channel in self._still],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaselineModel:
        """Rebuild a model from :meth:`to_dict` output.

        Any payload that is not exactly :data:`SCHEMA_VERSION` is rejected,
        older ones included, by raising ``ValueError``. Callers treat that as
        "no persisted baseline" and relearn, which is correct rather than
        merely safe: an older snapshot holds summaries from a different
        estimator and there is no honest way to convert them.
        """
        version = int(data["version"])
        if version != SCHEMA_VERSION:
            raise ValueError(f"unsupported baseline schema version {version}")
        model = cls(
            window_s=float(data["window_s"]),
            min_spread=float(data["min_spread"]),
            bucket_s=float(data["bucket_s"]),
            min_buckets=int(data["min_buckets"]),
        )
        for channel, channel_data in zip(model.move, data["move"], strict=True):
            channel.restore(channel_data)
        for channel, channel_data in zip(model.still, data["still"], strict=True):
            channel.restore(channel_data)
        return model
