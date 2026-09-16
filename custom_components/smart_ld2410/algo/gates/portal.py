"""Doorway gates, told from hallway gates by what follows (spec 20 §3a).

A brief episode viewed alone cannot distinguish a doorway transit from a
pass-by outside the room. The discriminator is what happens next on the same
sensor: a brief episode is *leading* if a sustained episode opens within
``lead_window_s`` of its close, on either side of it - a person walking through
a doorway lights the gate they are heading for before the doorway gate falls
quiet - and *dead-end* otherwise.

The outcome signal is raw episode segmentation only, never the detector's
occupancy output: the detector's decisions depend on these classes, and
feeding them back as training signal would let the classifier eat its own tail.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..roles import (
    RANK_PORTAL,
    ROLE_GATE_CLASS,
    GateVerdict,
    Stage,
    StageEnv,
)
from ..types import CLASS_PORTAL, GATE_COUNT, Episode
from .decay import decay_factor
from .dwell import DwellClass


class _GateOutcomes:
    """One gate's decayed leading and dead-end counts."""

    __slots__ = ("n_dead", "n_lead", "updated_ts")

    def __init__(self) -> None:
        self.n_lead = 0.0
        self.n_dead = 0.0
        self.updated_ts: float | None = None


class _PendingBrief:
    """A closed brief episode still waiting to be called leading or dead-end."""

    __slots__ = ("close_ts", "gate")

    def __init__(self, gate: int, close_ts: float) -> None:
        self.gate = gate
        self.close_ts = close_ts


class PortalClass(Stage):
    """Resolves brief episodes into doorway evidence, and names PORTAL gates."""

    __slots__ = ("_dwell", "_gates", "_pending", "_sustained_starts")

    role = ROLE_GATE_CLASS
    requires = ("dwell_class",)

    def __init__(self, env: StageEnv, *, dwell_class: DwellClass) -> None:
        """Start with no brief episodes waiting on an outcome."""
        super().__init__(env)
        self._dwell = dwell_class
        self._gates = [_GateOutcomes() for _ in range(GATE_COUNT)]
        self._pending: list[_PendingBrief] = []
        self._sustained_starts: list[float] = []

    def advance(self, gate: int, ts: float) -> None:
        """Decay one gate's outcome counts forward to ``ts``."""
        stat = self._gates[gate]
        stat.n_lead, stat.n_dead = self.decayed(gate, ts)
        stat.updated_ts = ts

    def decayed(self, gate: int, ts: float) -> tuple[float, float]:
        """Return ``(n_lead, n_dead)`` as of ``ts``, without mutating."""
        stat = self._gates[gate]
        factor = decay_factor(stat.updated_ts, ts, self._config.stats_half_life_s)
        return stat.n_lead * factor, stat.n_dead * factor

    def observe(self, episode: Episode) -> None:
        """Record a sustained episode's start, or queue a brief one's outcome."""
        gate = episode.gate
        if gate is None:
            return
        if self._dwell.is_sustained(episode):
            self._sustained_starts.append(episode.t0)
        elif episode.duration_s <= self._config.t_brief_s:
            self._pending.append(_PendingBrief(gate, episode.t1))

    def due(
        self, ts: float, open_starts: tuple[float, ...]
    ) -> tuple[tuple[int, bool], ...]:
        """Call every brief episode past its lead window leading or dead-end.

        One whose window holds a still-open episode waits: a dwell is a minute
        long, so its verdict cannot exist yet.
        """
        if not self._pending:
            self._sustained_starts.clear()
            return ()
        window = self._config.lead_window_s
        unresolved: list[_PendingBrief] = []
        resolved: list[tuple[int, bool]] = []
        for pending in self._pending:
            if ts < pending.close_ts + window:
                unresolved.append(pending)
                continue
            if _within(self._sustained_starts, pending.close_ts, window):
                leading = True
            elif _within(open_starts, pending.close_ts, window):
                unresolved.append(pending)
                continue
            else:
                leading = False
            resolved.append((pending.gate, leading))
        self._pending = unresolved
        oldest = min((pending.close_ts for pending in unresolved), default=None)
        if oldest is None:
            self._sustained_starts.clear()
        else:
            self._sustained_starts = [
                start for start in self._sustained_starts if start >= oldest - window
            ]
        return tuple(resolved)

    def credit(self, gate: int, leading: bool) -> None:
        """Count one resolved brief episode."""
        stat = self._gates[gate]
        if leading:
            stat.n_lead += 1.0
        else:
            stat.n_dead += 1.0

    def classify(self, gate: int, ts: float, current: str) -> GateVerdict | None:
        """This gate's doorway verdict as of ``ts``, or ``None`` for no opinion."""
        del current
        config = self._config
        n_lead, n_dead = self.decayed(gate, ts)
        if n_lead >= config.n_portal_min and n_lead >= config.portal_lead_frac * (
            n_lead + n_dead
        ):
            return GateVerdict(RANK_PORTAL, CLASS_PORTAL)
        return None

    def gate_state(self, gate: int) -> dict[str, Any]:
        """Return one gate's outcome counts, JSON-safe."""
        stat = self._gates[gate]
        return {"n_lead": stat.n_lead, "n_dead": stat.n_dead}

    def restore_gate(self, gate: int, data: dict[str, Any]) -> None:
        """Restore one gate from :meth:`gate_state` output."""
        stat = self._gates[gate]
        stat.n_lead = float(data.get("n_lead", 0.0))
        stat.n_dead = float(data.get("n_dead", 0.0))
        updated = data.get("updated_ts")
        stat.updated_ts = None if updated is None else float(updated)


def _within(starts: Sequence[float], ts: float, window: float) -> bool:
    """Whether any of ``starts`` falls within ``window`` seconds of ``ts``.

    Symmetric: a doorway transit lights the gate it is heading for before the
    doorway gate falls quiet.
    """
    return any(abs(start - ts) <= window for start in starts)
