"""Hold refresher: still-presence retention holds a disarmed room (spec 24 §2).

There is no way out of a room that does not produce motion, so until the
occupant has demonstrably re-crossed the entry band their stillness alone keeps
the room occupied. Retention never refreshes hold for gates the current
occupancy never included: a neighbour's through-wall activity elevates the
statistic more than a genuine still occupant does, so it is trusted only inside
an owned visit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..presence.arming import CrossingArming
from ..presence.ownership import Ownership
from ..presence.retention import SignedRetention
from ..roles import ROLE_HOLD_REFRESHER, Stage, StageEnv

if TYPE_CHECKING:
    from ..context import DetectorContext


class RetentionHold(Stage):
    """Refreshes hold while retention is elevated at an owned occupancy's gates."""

    __slots__ = ("_arming", "_ownership", "_retention")

    role = ROLE_HOLD_REFRESHER
    requires = ("retention", "ownership", "crossing_arming")

    def __init__(
        self,
        env: StageEnv,
        *,
        retention: SignedRetention,
        ownership: Ownership,
        crossing_arming: CrossingArming,
    ) -> None:
        """Build the refresher over the statistic and the ownership it serves."""
        super().__init__(env)
        self._retention = retention
        self._ownership = ownership
        self._arming = crossing_arming

    def refreshes(self, context: DetectorContext) -> bool:
        """Whether retention keeps a disarmed owned room held."""
        del context
        if not self._ownership.owned or self._arming.armed:
            return False
        return self._retention.blocks(self._ownership.gates or None)
