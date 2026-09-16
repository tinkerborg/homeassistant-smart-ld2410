"""Fixed frame-time buckets, the tier every baseline statistic reads.

Raw samples accumulate into buckets keyed by ``Frame.ts_utc``; a bucket that
closes contributes one summary and its samples are dropped, which is what makes
hours of 10Hz data affordable. No wall-clock time is read anywhere.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def quantile(ordered: Sequence[float], q: float) -> float:
    """Return the linearly interpolated ``q`` quantile of a sorted sequence."""
    last = len(ordered) - 1
    if last <= 0:
        return float(ordered[0])
    position = q * last
    lower = int(position)
    upper = min(lower + 1, last)
    fraction = position - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction)


class BucketWindow:
    """Rolls raw samples into fixed frame-time buckets over a bounded window."""

    __slots__ = ("_bucket_s", "_max_buckets", "_open_index", "_open_samples")

    def __init__(self, *, bucket_s: float, max_buckets: int) -> None:
        """Start an empty window."""
        self._bucket_s = bucket_s
        self._max_buckets = max_buckets
        self._open_index: int | None = None
        self._open_samples: list[int] = []

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
        """Throw away the in-progress bucket, which cannot stand in for a whole one."""
        self._open_index = None
        self._open_samples.clear()

    def resize(self, max_buckets: int) -> None:
        """Change the window capacity."""
        self._max_buckets = max_buckets

    def summarise(self, ordered: list[int]) -> None:
        """Fold one closed bucket's sorted samples into the statistic."""
        raise NotImplementedError

    def open_state(self) -> dict[str, Any]:
        """Return the in-progress bucket, JSON-safe."""
        return {
            "open_index": self._open_index,
            "open_samples": list(self._open_samples),
        }

    def restore_open(self, data: dict[str, Any]) -> None:
        """Restore the in-progress bucket from :meth:`open_state` output."""
        open_index = data.get("open_index")
        self._open_index = None if open_index is None else int(open_index)
        self._open_samples = [int(value) for value in data.get("open_samples", ())]

    def _close_open_bucket(self) -> None:
        if self._open_samples:
            self.summarise(sorted(self._open_samples))
        self._open_samples = []
