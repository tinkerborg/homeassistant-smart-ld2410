"""Entry filter: occupancy begins on arrival-scale motion (spec 22 §2).

Someone walking into the room drives the moving channel near whatever ceiling
that sensor has learned; a wall attenuates activity too far to reach it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..baseline.ceiling import MoveCeiling
from ..roles import ADMIT, ROLE_ENTRY_FILTER, EntryVerdict, Stage, StageEnv
from ..types import RESULT_REJECTED_ARRIVAL

if TYPE_CHECKING:
    from ..context import DetectorContext


class ArrivalGate(Stage):
    """Refuses entry until the candidate has shown arrival-scale moving energy."""

    __slots__ = ("_ceiling", "_frames")

    role = ROLE_ENTRY_FILTER
    requires = ("move_ceiling",)

    def __init__(self, env: StageEnv, *, move_ceiling: MoveCeiling) -> None:
        """Start with no candidate in progress, over the learned ceiling."""
        super().__init__(env)
        self._ceiling = move_ceiling
        self._frames = 0

    def accumulate(self, context: DetectorContext) -> None:
        """Count this frame if an admitted gate reached the arrival threshold."""
        if context.occupied or not context.activity:
            self._frames = 0
        arrival = self._config.arrival_frac * self._ceiling.value
        frame = context.frame
        reached = any(
            frame.move_gates[gate] >= arrival for gate in context.active_gates
        )
        self._frames += int(reached)

    def verdict(self, context: DetectorContext) -> EntryVerdict:
        """Judge the candidate against the learned move ceiling.

        An unlearned ceiling leaves the rule inactive: it may only ever tighten
        a sensor that has seen what strong motion looks like, never block a
        fresh install.
        """
        del context
        config = self._config
        if (
            config.arrival_frac > 0.0
            and self._ceiling.learned
            and self._frames < config.arrival_min_frames
        ):
            return EntryVerdict(RESULT_REJECTED_ARRIVAL)
        return ADMIT
