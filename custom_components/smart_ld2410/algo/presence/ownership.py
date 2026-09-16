"""Room ownership: the claim that this room's own occupant is being seen.

Ownership is earned by an entry that led at the room's own entry gates,
something activity beyond a wall can never do. It is what separates evidence
from the occupant from evidence from a neighbour once the room is occupied,
when their per-frame signatures are indistinguishable.
"""

from __future__ import annotations

from typing import Any

from ..roles import ROLE_OWNERSHIP, Stage, StageEnv


class Ownership(Stage):
    """Which gates the current occupancy covers, and whether it is owned."""

    __slots__ = ("_gates", "_owned")

    role = ROLE_OWNERSHIP
    expects = ("run_score",)

    def __init__(self, env: StageEnv) -> None:
        """Start unowned."""
        super().__init__(env)
        self._owned = False
        self._gates: set[int] = set()

    @property
    def owned(self) -> bool:
        """Whether a qualifying entry currently owns the room."""
        return self._owned

    @property
    def gates(self) -> tuple[int, ...]:
        """The gates this occupancy has covered, ascending."""
        return tuple(sorted(self._gates))

    def claim(self, gates: tuple[int, ...], leading_gate: int | None) -> bool:
        """Take ownership if the entry led inside the room's own entry gates."""
        lead_gate_max = self._config.lead_gate_max
        if lead_gate_max < 0 or leading_gate is None or leading_gate > lead_gate_max:
            return False
        self.enter(gates)
        return True

    def enter(self, gates: tuple[int, ...]) -> None:
        """Take ownership of a fresh occupancy over ``gates``."""
        self._owned = True
        self._gates = set(gates)

    def include(self, gates: tuple[int, ...]) -> None:
        """Extend the occupancy's gate set over gates it has now reached."""
        self._gates.update(gates)

    def release(self) -> None:
        """Drop ownership when the occupancy ends."""
        self._owned = False
        self._gates = set()

    def to_dict(self) -> dict[str, Any]:
        """Serialise ownership, JSON-safe."""
        return {"owned": self._owned, "gates": sorted(self._gates)}

    def restore(self, data: dict[str, Any]) -> None:
        """Restore ownership from :meth:`to_dict` output."""
        self._owned = bool(data["owned"])
        self._gates = {int(gate) for gate in data["gates"]}
