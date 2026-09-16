"""Crossing-armed release: the occupant must be seen leaving (spec 24 §1a).

An owned room begins disarmed, where stillness alone cannot release it - there
is no way out of a room that does not produce motion. Once near-band activity
has been absent for ``quiet_s``, so the entry walk-in has settled, a fresh
burst of ``cross_n`` near-band frames marks a departure crossing and arms
release; from then on nothing but the occupant's own attributed evidence holds
the door.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from ..roles import ROLE_ARMING, Stage, StageEnv
from .ownership import Ownership

_CROSS_WINDOW_S = 20.0
"""Span the arming burst of near-band frames must fall inside."""


class CrossingArming(Stage):
    """Tracks near-band activity, and arms release on a departure crossing."""

    __slots__ = ("_armed", "_crossings", "_last_near", "_ownership", "_quiet_gap")

    role = ROLE_ARMING
    requires = ("ownership",)

    def __init__(self, env: StageEnv, *, ownership: Ownership) -> None:
        """Start disarmed, over the ownership a crossing belongs to."""
        super().__init__(env)
        self._ownership = ownership
        self._armed = False
        self._quiet_gap = False
        self._last_near: float | None = None
        self._crossings: deque[float] = deque()

    @property
    def armed(self) -> bool:
        """Whether the occupant has demonstrably re-crossed the entry band."""
        return self._armed

    def observe_lead(self, ts_mono: float, leading_gate: int | None) -> None:
        """Record whether this frame's activity led inside the entry band."""
        if leading_gate is not None and leading_gate <= self._config.lead_gate_max:
            self._last_near = ts_mono
            if self._ownership.owned:
                self._crossings.append(ts_mono)
        while self._crossings and ts_mono - self._crossings[0] > _CROSS_WINDOW_S:
            self._crossings.popleft()

    def step(self, ts_mono: float) -> None:
        """Advance the quiet-gap then re-crossing sequence that arms release."""
        config = self._config
        if self._armed:
            return
        if not self._quiet_gap:
            if self._last_near is None or ts_mono - self._last_near >= config.quiet_s:
                self._quiet_gap = True
                self._crossings.clear()
        elif len(self._crossings) >= config.cross_n:
            self._armed = True

    def near_recent(self, ts_mono: float) -> bool:
        """Whether near-band activity is recent enough to attribute evidence."""
        return (
            self._last_near is not None
            and ts_mono - self._last_near <= self._config.grace_s
        )

    def reset(self) -> None:
        """Start the arming sequence over for a fresh occupancy."""
        self._armed = False
        self._quiet_gap = False
        self._crossings.clear()

    def rebase(self) -> None:
        """Forget timings left over from a timebase that has restarted."""
        self._last_near = None
        self._crossings.clear()

    def to_dict(self) -> dict[str, Any]:
        """Serialise the arming sequence, JSON-safe."""
        return {
            "armed": self._armed,
            "quiet_gap": self._quiet_gap,
            "last_near": self._last_near,
            "crossings": list(self._crossings),
        }

    def restore(self, data: dict[str, Any]) -> None:
        """Restore the arming sequence from :meth:`to_dict` output."""
        self._armed = bool(data["armed"])
        self._quiet_gap = bool(data["quiet_gap"])
        last_near = data["last_near"]
        self._last_near = None if last_near is None else float(last_near)
        self._crossings = deque(float(value) for value in data["crossings"])
