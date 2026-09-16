"""Hold refresher: an owned room is held only by its own occupant (spec 24 §1a).

Once a room is owned, scored evidence counts only while the near band has been
active within ``grace_s`` - a neighbour beyond the wall can produce the score,
but not the approach that attributes it to the occupant.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..presence.arming import CrossingArming
from ..presence.ownership import Ownership
from ..roles import ROLE_HOLD_REFRESHER, Stage, StageEnv

if TYPE_CHECKING:
    from ..context import DetectorContext


class AttributedHold(Stage):
    """Refreshes hold on scored evidence attributable to an owned room's occupant."""

    __slots__ = ("_arming", "_ownership")

    role = ROLE_HOLD_REFRESHER
    requires = ("ownership", "crossing_arming")

    def __init__(
        self, env: StageEnv, *, ownership: Ownership, crossing_arming: CrossingArming
    ) -> None:
        """Build the refresher over the ownership it attributes evidence to."""
        super().__init__(env)
        self._ownership = ownership
        self._arming = crossing_arming

    def refreshes(self, context: DetectorContext) -> bool:
        """Whether this frame's score is the occupant's own."""
        return (
            self._ownership.owned
            and context.score >= self._config.exit_score
            and self._arming.near_recent(context.ts_mono)
        )
