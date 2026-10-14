"""The per-sensor raw moving energy an arrival must reach, learned from motion bursts.

A burst is a run of frames whose moving channel exceeds its floor by ``k``
spreads at any of gates ``FIRST_GATE``..``LAST_GATE``, with gaps of up to
``BURST_MERGE_S`` merged. Each burst contributes its peak raw move to a
histogram that decays with observed time over the baseline window. A
three-class Otsu split separates ambient flicker, through-wall activity and the
occupant's own motion; the bar is the lower edge of the strongest class.

All timing comes from ``Frame.ts_utc``; nothing here reads a clock.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import accumulate
from math import exp, inf
from typing import Any

from ..roles import ROLE_ARRIVAL_BAR, Stage, StageEnv
from ..types import MAX_GATE_ENERGY, Frame

ARRIVAL_BAR_FALLBACK = 40.0
"""Raw moving energy an arrival must reach before the bar is learned."""

FIRST_GATE = 2
LAST_GATE = 8
"""Gates whose moving energy forms bursts."""

BURST_MERGE_S = 1.0
"""Longest quiet gap that still continues a burst."""

MIN_STRONG_BURSTS = 20
"""Bursts the strongest class must hold before its edge is trusted as the bar."""

OBSERVED_GAP_S = 5.0
"""Longest frame gap counted as observed time for the histogram's decay."""

_BINS = MAX_GATE_ENERGY + 1


class ArrivalBar(Stage):
    """Decayed histogram of motion-burst peaks, and the bar its upper split gives."""

    __slots__ = (
        "_bar",
        "_burst_last",
        "_burst_peak",
        "_counts",
        "_last_ts",
        "_undecayed_s",
        "_weights",
    )

    role = ROLE_ARRIVAL_BAR

    def __init__(self, env: StageEnv) -> None:
        """Start with no bursts seen."""
        super().__init__(env)
        self._weights = [0.0] * _BINS
        self._counts = [0] * _BINS
        self._bar: float | None = None
        self._undecayed_s = 0.0
        self._last_ts: float | None = None
        self._burst_peak: float | None = None
        self._burst_last = 0.0

    @property
    def learned(self) -> bool:
        """Whether the strongest class has held enough bursts to set the bar."""
        return self._bar is not None

    @property
    def value(self) -> float:
        """The bar in raw energy units, or the fallback while unlearned."""
        return ARRIVAL_BAR_FALLBACK if self._bar is None else self._bar

    def add_frame(self, frame: Frame) -> None:
        """Accept a frame; bursts are folded in by :meth:`observe`."""
        del frame

    def observe(
        self, frame: Frame, move_model: Sequence[tuple[float, float]] | None
    ) -> None:
        """Fold one frame into the burst in progress.

        ``move_model`` is each gate's moving-channel ``(floor, spread)``, or
        ``None`` while the baseline is not ready.
        """
        ts = frame.ts_utc
        if self._last_ts is not None and 0.0 < ts - self._last_ts <= OBSERVED_GAP_S:
            self._undecayed_s += ts - self._last_ts
        self._last_ts = ts
        if self._burst_peak is not None and ts - self._burst_last > BURST_MERGE_S:
            self._close_burst(self._burst_peak)
        if move_model is None:
            return
        move = frame.move_gates
        k = self._config.k
        if not any(
            move[gate] > move_model[gate][0] + k * move_model[gate][1]
            for gate in range(FIRST_GATE, LAST_GATE + 1)
        ):
            return
        peak = float(max(move[FIRST_GATE : LAST_GATE + 1]))
        self._burst_peak = peak if self._burst_peak is None else max(self._burst_peak, peak)
        self._burst_last = ts

    def resize(self, max_buckets: int) -> None:
        """Accept a resize; the decay follows the configured window instead."""
        del max_buckets

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe snapshot."""
        return {
            "weights": list(self._weights),
            "counts": list(self._counts),
            "bar": self._bar,
            "undecayed_s": self._undecayed_s,
            "last_ts": self._last_ts,
            "burst_peak": self._burst_peak,
            "burst_last": self._burst_last,
        }

    def restore(self, data: dict[str, Any]) -> None:
        """Restore from :meth:`to_dict` output."""
        weights = data["weights"]
        counts = data["counts"]
        if len(weights) != _BINS or len(counts) != _BINS:
            raise ValueError("arrival bar histogram has the wrong bin count")
        self._weights = [float(value) for value in weights]
        self._counts = [int(value) for value in counts]
        self._bar = None if data["bar"] is None else float(data["bar"])
        self._undecayed_s = float(data["undecayed_s"])
        self._last_ts = None if data["last_ts"] is None else float(data["last_ts"])
        self._burst_peak = (
            None if data["burst_peak"] is None else float(data["burst_peak"])
        )
        self._burst_last = float(data["burst_last"])

    def _close_burst(self, peak: float) -> None:
        self._burst_peak = None
        decay = exp(-self._undecayed_s / self._config.baseline_window_s)
        self._undecayed_s = 0.0
        self._weights = [weight * decay for weight in self._weights]
        index = int(round(peak))
        self._weights[index] += 1.0
        self._counts[index] += 1
        split = _upper_split(self._weights)
        if split is not None and sum(self._counts[split + 1 :]) >= MIN_STRONG_BURSTS:
            self._bar = split + 1.0


def _upper_split(weights: Sequence[float]) -> int | None:
    cumulative = list(accumulate(weights))
    moments = list(accumulate(weight * float(bin_) for bin_, weight in enumerate(weights)))
    total, total_moment = cumulative[-1], moments[-1]
    if total <= 0:
        return None
    offset = total * (total_moment / total) ** 2
    best_value = -inf
    best: int | None = None
    for lower in range(len(weights)):
        w0 = cumulative[lower]
        if w0 <= 0:
            continue
        head = moments[lower] ** 2 / w0
        for upper in range(lower + 1, len(weights)):
            w1 = cumulative[upper] - w0
            w2 = total - cumulative[upper]
            if w1 <= 0 or w2 <= 0:
                continue
            value = (
                head
                + (moments[upper] - moments[lower]) ** 2 / w1
                + (total_moment - moments[upper]) ** 2 / w2
                - offset
            )
            if value > best_value:
                best_value = value
                best = upper
    return best
