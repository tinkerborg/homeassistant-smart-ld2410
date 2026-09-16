"""Isolated-gate suppression: a lone hot gate needs a neighbour to be credible.

A person concentrates energy in one gate but always spills a little into the
next, so an exceedance with quiet neighbours is physical nonsense - which is
what kills the stuck-gate case that pins occupancy on for hours. The
neighbour's elevation is read from the time-smoothed support estimate rather
than the raw frame: a person's spill is sustained, whereas a single noisy
sample crossing the partial level would rescue a stuck gate ten times a minute.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from ..roles import ROLE_SUPPRESSION, Stage
from ..types import GATE_COUNT


class LoneGateSuppression(Stage):
    """Drops a single-gate run whose neighbours are not partly elevated."""

    __slots__ = ()

    role = ROLE_SUPPRESSION

    def supported(
        self,
        support: Sequence[float],
        gate: int,
        *,
        excluded: Callable[[int], bool],
    ) -> bool:
        """Whether a neighbour of ``gate`` carries at least partial elevation."""
        partial = self._config.k / 2.0
        left = support[gate - 1] if gate > 0 and not excluded(gate - 1) else 0.0
        right = (
            support[gate + 1]
            if gate + 1 < GATE_COUNT and not excluded(gate + 1)
            else 0.0
        )
        return left >= partial or right >= partial
