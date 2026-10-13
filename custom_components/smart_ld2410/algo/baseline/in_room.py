"""Which gates the room itself occupies, learned from arrival-scale motion.

Only a body inside the room drives a gate's moving channel to arrival scale;
a wall attenuates activity behind it too far. A gate whose decayed peak of raw
moving energy reaches ``IN_ROOM_MOVE`` is in-room, and stays so for weeks
after the motion that proved it. A gate is still-capable once its raw still
energy has exceeded the floor by ``STILL_LIT_SPREADS`` spreads: an in-room gate
that never shows still presence cannot carry a seated occupant.

Raw energy, not residuals, so the learned extent is independent of the floor.
All timing comes from ``Frame.ts_utc``; nothing here reads a clock.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..roles import ROLE_ROOM_GATES, Stage, StageEnv
from ..types import GATE_COUNT, Frame

IN_ROOM_MOVE = 90.0
"""Decayed raw moving energy that proves a gate in-room."""

STILL_LIT_SPREADS = 3.0
"""Spreads above the floor raw still energy must reach to count as lit."""


class InRoomGates(Stage):
    """Per-gate decayed move peak and still capability, and the watched gate."""

    __slots__ = ("_peaks", "_still_capable", "_watched")

    role = ROLE_ROOM_GATES

    def __init__(self, env: StageEnv) -> None:
        """Start with nothing learned."""
        super().__init__(env)
        self._peaks: list[tuple[float, float] | None] = [None] * GATE_COUNT
        self._still_capable = [False] * GATE_COUNT
        self._watched: int | None = None

    @property
    def watched_gate(self) -> int | None:
        """Nearest gate that is both in-room and still-capable, as of the last frame."""
        return self._watched

    @property
    def still_capable(self) -> tuple[bool, ...]:
        """Whether each gate's still channel has ever been lit."""
        return tuple(self._still_capable)

    def in_room(self, gate: int, ts_utc: float) -> bool:
        """Whether ``gate``'s decayed move peak at ``ts_utc`` proves it in-room."""
        peak = self._peaks[gate]
        if peak is None:
            return False
        level, at = peak
        return level * 2.0 ** (-(ts_utc - at) / self._config.in_room_half_life_s) >= IN_ROOM_MOVE

    def add_frame(self, frame: Frame) -> None:
        """Fold one frame's raw moving energy into the decayed peaks."""
        ts = frame.ts_utc
        for gate, move in enumerate(frame.move_gates):
            if move > 0 and not self._beats(gate, move, ts):
                self._peaks[gate] = (float(move), ts)

    def observe_still(
        self, frame: Frame, lit_levels: Sequence[float | None]
    ) -> None:
        """Mark gates whose still channel exceeds its lit level, then re-pick the watched gate.

        A ``None`` level is an untrusted floor and teaches nothing.
        """
        for gate, level in enumerate(lit_levels):
            if level is not None and frame.still_gates[gate] > level:
                self._still_capable[gate] = True
        self._watched = next(
            (
                gate
                for gate in range(GATE_COUNT)
                if self._still_capable[gate] and self.in_room(gate, frame.ts_utc)
            ),
            None,
        )

    def resize(self, max_buckets: int) -> None:
        """Accept a resize; nothing here is windowed."""
        del max_buckets

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe snapshot."""
        return {
            "move_peaks": [None if peak is None else list(peak) for peak in self._peaks],
            "still_capable": list(self._still_capable),
        }

    def restore(self, data: dict[str, Any]) -> None:
        """Restore from :meth:`to_dict` output."""
        peaks = data["move_peaks"]
        capable = data["still_capable"]
        if len(peaks) != GATE_COUNT or len(capable) != GATE_COUNT:
            raise ValueError("in-room gate state has the wrong gate count")
        self._peaks = [
            None if peak is None else (float(peak[0]), float(peak[1])) for peak in peaks
        ]
        self._still_capable = [bool(value) for value in capable]
        self._watched = None

    def _beats(self, gate: int, move: int, ts_utc: float) -> bool:
        peak = self._peaks[gate]
        if peak is None:
            return False
        level, at = peak
        return level * 2.0 ** (-(ts_utc - at) / self._config.in_room_half_life_s) > move
