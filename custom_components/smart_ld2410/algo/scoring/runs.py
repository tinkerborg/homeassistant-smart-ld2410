"""Spatial-run scoring: the strongest contiguous band of hot gates wins.

A person lights a contiguous run of gates, so the score is the summed
elevation of the strongest such run, normalised by the exceedance threshold.
The same scan answers where activity *began*, which is the leading edge an
entry is judged on.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from ..roles import ROLE_SCORER, Stage, StageEnv
from ..types import GATE_COUNT
from .suppression import LoneGateSuppression


def admit_every_gate(gate: int) -> bool:
    """Exclusion predicate that admits every gate."""
    del gate
    return False


class RunScorer(Stage):
    """Scores the strongest coherent run, and names the nearest run's first gate."""

    __slots__ = ("_suppression",)

    role = ROLE_SCORER
    optional = ("lone_gate_suppression",)

    def __init__(
        self, env: StageEnv, *, lone_gate_suppression: LoneGateSuppression | None = None
    ) -> None:
        """Build the scorer, over a suppression stage where one is listed."""
        super().__init__(env)
        self._suppression = lone_gate_suppression

    def best_run(
        self,
        peaks: Sequence[float],
        support: Sequence[float],
        *,
        excluded: Callable[[int], bool] = admit_every_gate,
    ) -> tuple[float, tuple[int, ...]]:
        """Return the score of the strongest coherent run, and the run itself.

        An excluded gate is invisible: it neither carries score itself nor lends
        a lone neighbour the elevation that would rescue it.
        """
        k = self._config.k
        best_score = 0.0
        strongest: tuple[int, ...] = ()
        run: list[int] = []
        for gate in range(GATE_COUNT + 1):
            if gate < GATE_COUNT and peaks[gate] >= k and not excluded(gate):
                run.append(gate)
                continue
            if not run:
                continue
            if len(run) == 1 and not self._credible(support, run[0], excluded=excluded):
                run = []
                continue
            score = sum(peaks[index] for index in run) / k
            if score > best_score:
                best_score = score
                strongest = tuple(run)
            run = []
        return best_score, strongest

    def leading_gate(
        self, residuals: Sequence[float], support: Sequence[float]
    ) -> int | None:
        """Return the nearest gate of the first coherent run, or ``None``.

        Read unmasked: a gate the classifier has learned is bleed still says
        where the activity began.
        """
        k = self._config.k
        run: list[int] = []
        for gate in range(GATE_COUNT + 1):
            if gate < GATE_COUNT and residuals[gate] >= k:
                run.append(gate)
                continue
            if not run:
                continue
            if len(run) > 1 or self._credible(
                support, run[0], excluded=admit_every_gate
            ):
                return run[0]
            run = []
        return None

    def _credible(
        self,
        support: Sequence[float],
        gate: int,
        *,
        excluded: Callable[[int], bool],
    ) -> bool:
        if self._suppression is None:
            return True
        return self._suppression.supported(support, gate, excluded=excluded)
