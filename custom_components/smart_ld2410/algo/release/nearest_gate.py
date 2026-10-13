"""Release path: the nearest in-room gate has gone dark relative to this visit.

The nearest gate that is both learned in-room and still-capable sits between
the sensor and everything deeper in the room, so an occupant anywhere in the
room keeps some of its own still energy there. Its trailing median is compared
with its plateau over the visit, and a ratio under ``release_fraction`` for
``hold_s`` releases the room even while through-wall activity keeps the deeper
gates, and so the score, elevated.
"""

from __future__ import annotations

from collections import deque
from statistics import median
from typing import TYPE_CHECKING

from ..baseline.in_room import STILL_LIT_SPREADS, InRoomGates
from ..presence.motion_anchor import MotionAnchorStage
from ..roles import ROLE_RELEASE, Stage, StageEnv
from ..types import CHANNEL_STILL, GATE_COUNT

if TYPE_CHECKING:
    from ..context import DetectorContext

MEDIAN_WINDOW_S = 5.0
"""Trailing window the still median is taken over."""

PLATEAU_HALF_LIFE_S = 600.0
"""Decay half-life of the visit's plateau, so a long visit's peak does not rule forever."""

_PLATEAU_FLOOR = 1e-9


class NearestGateRelease(Stage):
    """Releases when the watched gate's still median stays under a fraction of its plateau."""

    __slots__ = (
        "_counting_since",
        "_gates",
        "_last_ts",
        "_lit",
        "_median",
        "_motion",
        "_plateau",
        "_window",
    )

    role = ROLE_RELEASE
    requires = ("in_room_gates", "motion_anchor")

    def __init__(
        self,
        env: StageEnv,
        *,
        in_room_gates: InRoomGates,
        motion_anchor: MotionAnchorStage,
    ) -> None:
        """Build the release over the learned in-room gates and the anchor."""
        super().__init__(env)
        self._gates = in_room_gates
        self._motion = motion_anchor
        self._window: deque[tuple[float, tuple[int, ...]]] = deque()
        self._median = [0.0] * GATE_COUNT
        self._plateau = [0.0] * GATE_COUNT
        self._lit = [False] * GATE_COUNT
        self._counting_since: float | None = None
        self._last_ts: float | None = None

    def rebase(self) -> None:
        """Forget timings left over from a timebase that has restarted."""
        self._window.clear()
        self._counting_since = None
        self._last_ts = None

    def observe(self, context: DetectorContext) -> None:
        """Fold this frame into the trailing still median."""
        t = context.ts_mono
        window = self._window
        window.append((t, context.frame.still_gates))
        while window[0][0] <= t - MEDIAN_WINDOW_S:
            window.popleft()
        self._median = [
            float(median(still[gate] for _, still in window)) for gate in range(GATE_COUNT)
        ]

    def enter(self, context: DetectorContext) -> None:
        """Seed the visit's plateau from the arrival."""
        levels = _lit_levels(context)
        self._plateau = list(self._median)
        self._lit = [value > level for value, level in zip(self._median, levels)]
        self._counting_since = None
        self._last_ts = context.ts_mono

    def releases(self, context: DetectorContext) -> bool:
        """Whether the watched gate has stayed dark for the whole hold window."""
        t = context.ts_mono
        decay = 1.0 if self._last_ts is None else 2.0 ** (-(t - self._last_ts) / PLATEAU_HALF_LIFE_S)
        self._last_ts = t
        levels = _lit_levels(context)
        for gate, value in enumerate(self._median):
            self._plateau[gate] = max(self._plateau[gate] * decay, value)
            self._lit[gate] = self._lit[gate] or value > levels[gate]
        watched = self._gates.watched_gate
        if (
            watched is None
            or not self._lit[watched]
            or self._motion.admitted
            or self._median[watched] / max(self._plateau[watched], _PLATEAU_FLOOR)
            >= self._config.release_fraction
        ):
            self._counting_since = None
            return False
        if self._counting_since is None:
            self._counting_since = t
        return t - self._counting_since >= self._config.hold_s


def _lit_levels(context: DetectorContext) -> list[float]:
    baseline = context.baseline
    return [
        baseline.floor(gate, CHANNEL_STILL)
        + STILL_LIT_SPREADS * baseline.spread(gate, CHANNEL_STILL)
        for gate in range(GATE_COUNT)
    ]
