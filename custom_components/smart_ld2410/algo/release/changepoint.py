"""Release path: a still-regime change in which every carrying gate lost its occupant.

The still channel of gates 2-8 is sampled onto a 10 Hz sample-and-hold grid
and watched by a Bayesian online changepoint detector. Each declared change is
judged by comparing the regime before it with the regime after it; when every
gate that carried presence before the change lost at least half its excess,
release is armed for ``hold_s`` after the change. Admitted motion or a rising
change disarms it, because both say someone is still moving in the room.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import deque
from statistics import median
from typing import TYPE_CHECKING

from ..presence.motion_anchor import MotionAnchorStage
from ..roles import ROLE_RELEASE, Stage, StageEnv
from ..types import CHANNEL_STILL
from .bocpd import TICK_S, RunLengthPosterior

if TYPE_CHECKING:
    from ..context import DetectorContext

STILL_GATES = range(2, 9)

PRE_S = 5.0
PRE_GUARD_S = 0.5
POST_S = 3.0
CARRY_SPREADS = 3.0
LOSS_SPREADS = 3.0
LOSS_FRACTION = 0.5

ENTRY_BURST_S = 5.0
"""Changes this soon after entry are the arrival settling, not a departure."""

ADMIT_LOOKBACK_S = 2.0
"""Changes this soon after admitted motion are that motion, not a departure."""

_PRE_TICKS = round(PRE_S / TICK_S)
_GUARD_TICKS = round(PRE_GUARD_S / TICK_S)
_POST_TICKS = round(POST_S / TICK_S)
_HISTORY_TICKS = 2 * (_PRE_TICKS + _POST_TICKS)
_ADMIT_MEMORY_S = 30.0
_TICK_EPSILON = 1e-9


class ChangepointRelease(Stage):
    """Arms release on a changepoint after which every carrying gate went dark."""

    __slots__ = (
        "_admits",
        "_anchor",
        "_armed_until",
        "_entry_ts",
        "_held",
        "_history",
        "_motion",
        "_next_tick",
        "_pending",
        "_posterior",
    )

    role = ROLE_RELEASE
    requires = ("motion_anchor",)

    def __init__(self, env: StageEnv, *, motion_anchor: MotionAnchorStage) -> None:
        """Start with an empty grid, over the anchor that reports admitted motion."""
        super().__init__(env)
        self._motion = motion_anchor
        self._entry_ts: float | None = None
        self._armed_until: float | None = None
        self.rebase()

    def rebase(self) -> None:
        """Forget the grid and every timing in a timebase that has restarted."""
        self._anchor: float | None = None
        self._next_tick = 0
        self._held: tuple[float, ...] = ()
        self._history: deque[tuple[int, tuple[float, ...], tuple[float, ...], tuple[float, ...]]] = deque(
            maxlen=_HISTORY_TICKS
        )
        self._pending: list[tuple[int, int]] = []
        self._admits: deque[float] = deque()
        self._posterior = RunLengthPosterior(self._config.changepoint_hazard_s)
        self._entry_ts = None
        self._armed_until = None

    def observe(self, context: DetectorContext) -> None:
        """Advance the grid to this frame and judge every change now decidable."""
        t = context.ts_mono
        if self._anchor is None:
            self._anchor = t
        else:
            baseline = context.baseline
            floor = tuple(baseline.floor(gate, CHANNEL_STILL) for gate in STILL_GATES)
            spread = tuple(
                max(baseline.spread(gate, CHANNEL_STILL), 1.0) for gate in STILL_GATES
            )
            while self._tick_ts(self._next_tick) + _TICK_EPSILON < t:
                for tau, decision in self._step(self._next_tick, floor, spread):
                    self._judge(context, tau, decision)
                self._next_tick += 1
        self._held = tuple(float(context.frame.still_gates[gate]) for gate in STILL_GATES)
        if self._motion.admitted:
            if context.occupied:
                self._armed_until = None
            self._admits.append(t)
        while self._admits and self._admits[0] < t - _ADMIT_MEMORY_S:
            self._admits.popleft()

    def enter(self, context: DetectorContext) -> None:
        """Start judging changes against a fresh occupancy."""
        self._entry_ts = context.ts_mono
        self._armed_until = None

    def releases(self, context: DetectorContext) -> bool:
        """Whether an armed release has come due."""
        return self._armed_until is not None and context.ts_mono >= self._armed_until

    def _tick_ts(self, tick: int) -> float:
        assert self._anchor is not None
        return self._anchor + TICK_S * tick

    def _step(
        self, tick: int, floor: tuple[float, ...], spread: tuple[float, ...]
    ) -> list[tuple[int, int]]:
        self._history.append((tick, self._held, floor, spread))
        ago = self._posterior.step(self._held, floor, spread)
        if ago is not None:
            tau = tick - ago
            if tau - _PRE_TICKS >= 0:
                self._pending.append((tau, max(tick, tau + _POST_TICKS)))
                self._pending.sort(key=lambda change: change[1])
        due = [change for change in self._pending if change[1] <= tick]
        self._pending = [change for change in self._pending if change[1] > tick]
        return due

    def _judge(self, context: DetectorContext, tau: int, decision: int) -> None:
        if not context.occupied or self._entry_ts is None:
            return
        verdict = self._compare(tau, decision)
        if verdict is None:
            return
        released, rising = verdict
        change_ts = self._tick_ts(tau)
        if change_ts < self._entry_ts + ENTRY_BURST_S:
            return
        if self._admitted_between(change_ts - ADMIT_LOOKBACK_S, change_ts):
            return
        if rising:
            self._armed_until = None
            return
        if not released:
            return
        if self._admitted_between(change_ts + _TICK_EPSILON, self._tick_ts(decision)):
            return
        if self._armed_until is None:
            self._armed_until = change_ts + self._config.hold_s

    def _compare(self, tau: int, decision: int) -> tuple[bool, bool] | None:
        by_tick = {entry[0]: entry for entry in self._history}
        window = [by_tick.get(tick) for tick in range(tau - _PRE_TICKS, tau + _POST_TICKS)]
        if decision not in by_tick or any(entry is None for entry in window):
            return None
        pre_rows = [entry[1] for entry in window[: _PRE_TICKS - _GUARD_TICKS] if entry]
        post_rows = [entry[1] for entry in window[_PRE_TICKS:] if entry]
        _, _, floor, spread = by_tick[decision]
        carrying_lost: list[bool] = []
        rising = False
        for gate in range(len(STILL_GATES)):
            pre = median(row[gate] for row in pre_rows)
            post = median(row[gate] for row in post_rows)
            excess = CARRY_SPREADS * spread[gate]
            if pre > floor[gate] + excess:
                carrying_lost.append(
                    post
                    < pre - max(LOSS_SPREADS * spread[gate], LOSS_FRACTION * (pre - floor[gate]))
                )
            if post - pre >= max(LOSS_SPREADS * spread[gate], LOSS_FRACTION * (post - floor[gate])):
                rising = True
        return bool(carrying_lost) and all(carrying_lost), rising

    def _admitted_between(self, low: float, high: float) -> bool:
        admits = self._admits
        return bisect_right(admits, high) > bisect_left(admits, low)
