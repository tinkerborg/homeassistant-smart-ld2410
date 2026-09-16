"""Hold refresher: the coherent run alone holds a room nobody owns (spec 20 §4).

Every gate counts here, bleed included: a person who walked into a corner the
sensor sees through a wall is still a person who is in the room.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..presence.ownership import Ownership
from ..roles import ROLE_HOLD_REFRESHER, Stage, StageEnv

if TYPE_CHECKING:
    from ..context import DetectorContext


class ScoreHold(Stage):
    """Refreshes hold while an unowned room's score stays at or above ``exit_score``."""

    __slots__ = ("_ownership",)

    role = ROLE_HOLD_REFRESHER
    optional = ("ownership",)

    def __init__(self, env: StageEnv, *, ownership: Ownership | None = None) -> None:
        """Build the refresher, over the ownership stage where one is listed."""
        super().__init__(env)
        self._ownership = ownership

    def refreshes(self, context: DetectorContext) -> bool:
        """Whether this frame's score holds an unowned occupancy."""
        owned = self._ownership is not None and self._ownership.owned
        return not owned and context.score >= self._config.exit_score
