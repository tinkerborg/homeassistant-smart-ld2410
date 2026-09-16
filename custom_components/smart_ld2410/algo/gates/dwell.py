"""Dwell-character gate classification (spec 20 §2-3).

A gate where people regularly settle - one unbroken minute of elevation, a
thing no sweep can produce - is in the room, and one such episode is enough: a
guest bedroom used twice a year must work the first time it is used. A gate
that has only ever seen dozens of three-second sweeps and never a dwell is
bleed: a hallway behind a wall, seen through it.

Demotion is deliberately asymmetric. Promotion to IN_ROOM is instant; IN_ROOM
leaves only through the decayed bleed rule. A wrongly-permissive gate costs a
false positive; a wrongly-strict gate loses a real person.
"""

from __future__ import annotations

from typing import Any

from ..roles import (
    RANK_BLEED,
    RANK_STALE_IN_ROOM,
    RANK_SUSTAINED,
    ROLE_GATE_CLASS,
    GateVerdict,
    Stage,
    StageEnv,
)
from ..types import CLASS_BLEED, CLASS_IN_ROOM, GATE_COUNT, Episode
from .decay import decay_factor

_IN_ROOM_SUSTAINED = 1.0
"""Decayed sustained count at which a gate is in-room."""

_BLEED_SUSTAINED_MAX = 0.5
"""Decayed sustained count a gate must be under to be demotable to bleed."""


class _GateDwell:
    """One gate's decayed dwell counts."""

    __slots__ = ("last_sustained_ts", "n_brief", "n_sustained", "updated_ts")

    def __init__(self) -> None:
        self.n_sustained = 0.0
        self.n_brief = 0.0
        self.last_sustained_ts: float | None = None
        self.updated_ts: float | None = None


class DwellClass(Stage):
    """Counts sustained and brief episodes per gate, and the class they imply."""

    __slots__ = ("_gates",)

    role = ROLE_GATE_CLASS

    def __init__(self, env: StageEnv) -> None:
        """Start with every gate unseen."""
        super().__init__(env)
        self._gates = [_GateDwell() for _ in range(GATE_COUNT)]

    def advance(self, gate: int, ts: float) -> None:
        """Decay one gate's counts forward to ``ts``."""
        stat = self._gates[gate]
        stat.n_sustained, stat.n_brief = self.decayed(gate, ts)
        stat.updated_ts = ts

    def decayed(self, gate: int, ts: float) -> tuple[float, float]:
        """Return ``(n_sustained, n_brief)`` as of ``ts``, without mutating."""
        stat = self._gates[gate]
        factor = decay_factor(stat.updated_ts, ts, self._config.stats_half_life_s)
        return stat.n_sustained * factor, stat.n_brief * factor

    def is_sustained(self, episode: Episode) -> bool:
        """Whether an episode is long and unbroken enough to prove a body."""
        config = self._config
        return (
            episode.duration_s >= config.t_dwell_s
            and episode.active_frac >= config.active_frac_min
        )

    def observe(self, episode: Episode) -> None:
        """Fold one closed per-gate episode into its gate's counts.

        Episodes between the two lengths, and long ones too gappy to be a
        dwell, count toward neither class.
        """
        gate = episode.gate
        if gate is None:
            return
        stat = self._gates[gate]
        if self.is_sustained(episode):
            stat.n_sustained += 1.0
            stat.last_sustained_ts = episode.t1
        elif episode.duration_s <= self._config.t_brief_s:
            stat.n_brief += 1.0

    def classify(self, gate: int, ts: float, current: str) -> GateVerdict | None:
        """This gate's dwell verdict as of ``ts``, or ``None`` for no opinion."""
        config = self._config
        stat = self._gates[gate]
        n_sustained, n_brief = self.decayed(gate, ts)
        if n_sustained >= _IN_ROOM_SUSTAINED:
            return GateVerdict(RANK_SUSTAINED, CLASS_IN_ROOM)
        stale = (
            stat.last_sustained_ts is None
            or ts - stat.last_sustained_ts > config.stats_half_life_s
        )
        if (
            n_brief >= config.n_bleed_min
            and n_sustained < _BLEED_SUSTAINED_MAX
            and stale
        ):
            return GateVerdict(RANK_BLEED, CLASS_BLEED)
        if current == CLASS_IN_ROOM:
            # Falling back to UNKNOWN the instant the decayed count slips under
            # 1.0 - the very next frame after the episode that promoted it -
            # would make the class flap without changing any behaviour.
            return GateVerdict(RANK_STALE_IN_ROOM, CLASS_IN_ROOM)
        return None

    def gate_state(self, gate: int) -> dict[str, Any]:
        """Return one gate's counts, JSON-safe."""
        stat = self._gates[gate]
        return {
            "n_sustained": stat.n_sustained,
            "n_brief": stat.n_brief,
            "last_sustained_ts": stat.last_sustained_ts,
            "updated_ts": stat.updated_ts,
        }

    def restore_gate(self, gate: int, data: dict[str, Any]) -> None:
        """Restore one gate from :meth:`gate_state` output."""
        stat = self._gates[gate]
        stat.n_sustained = float(data["n_sustained"])
        stat.n_brief = float(data["n_brief"])
        last = data.get("last_sustained_ts")
        stat.last_sustained_ts = None if last is None else float(last)
        updated = data.get("updated_ts")
        stat.updated_ts = None if updated is None else float(updated)
