"""Which gate classes are barred from entry (spec 20 §4, 21 §3).

Exclusion is an entry-side rule only. A bleed gate can never help enter the
room; once the room is occupied every gate contributes to holding it, because a
person who walked into a corner the sensor sees through a wall is still a
person who is in the room.

The manual ``max_gate`` cap belongs here too: it is configuration rather than
evidence, so it is applied on read and never stored, and dropping the cap later
restores whatever the gate had actually learned instead of making it start
over.
"""

from __future__ import annotations

from ..roles import ROLE_GATE_MASK, Stage
from ..types import CLASS_BLEED, CLASS_OUT


class GateExclusion(Stage):
    """Masks bleed and out-of-room gates out of entry scoring and support."""

    __slots__ = ()

    role = ROLE_GATE_MASK

    def capped(self, gate: int) -> bool:
        """Whether the manual ``max_gate`` override puts ``gate`` out of the room."""
        max_gate = self._config.max_gate
        return max_gate is not None and gate > max_gate

    def excluded(self, gate_class: str) -> bool:
        """Whether a gate of this class is barred from entry evidence."""
        return gate_class in (CLASS_BLEED, CLASS_OUT)
