"""Entry filter: a candidate must be strong in at least one channel (spec 23).

Attenuated through-wall activity is uniformly weak in the move *and* still
channels at once, while genuine presence, however motionless, keeps one of them
strong. The peak is taken over the whole candidate rather than one frame: a
person's strongest return is a single moment of a dwell.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..roles import ADMIT, ROLE_ENTRY_FILTER, EntryVerdict, Stage, StageEnv
from ..types import RESULT_REJECTED_ENERGY_FLOOR

if TYPE_CHECKING:
    from ..context import DetectorContext


class EnergyFloor(Stage):
    """Refuses entry while the candidate's raw move+still peak is under the floor."""

    __slots__ = ("_combo_peak",)

    role = ROLE_ENTRY_FILTER

    def __init__(self, env: StageEnv) -> None:
        """Start with no candidate in progress."""
        super().__init__(env)
        self._combo_peak = 0.0

    def accumulate(self, context: DetectorContext) -> None:
        """Fold this frame's energy into the candidate in progress.

        Energy is read over the entry-scored gates only, so an excluded gate
        can never lift a candidate past the floor.
        """
        if context.occupied or not context.activity:
            self._combo_peak = 0.0
        frame = context.frame
        for gate in context.active_gates:
            combined = float(frame.move_gates[gate] + frame.still_gates[gate])
            self._combo_peak = max(self._combo_peak, combined)

    def verdict(self, context: DetectorContext) -> EntryVerdict:
        """Judge the candidate against ``energy_floor``."""
        del context
        floor = self._config.energy_floor
        if floor > 0.0 and self._combo_peak < floor:
            return EntryVerdict(RESULT_REJECTED_ENERGY_FLOOR)
        return ADMIT
