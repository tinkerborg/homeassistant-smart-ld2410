"""Signed still-presence retention and room ownership (spec 24 §1a, §2).

Two mechanics that only work together. The retention statistic is a *signed*
change detector over the still channel - a fast EMA minus a slow one, negative
part discarded, normalized by the gate's own frame-to-frame noise and
peak-held. A departure drives the unsigned difference to its maximum, which is
why the sign is what separates "a person is sitting here" from "a person just
left"; the peak-hold is what carries a genuine sit across the sub-threshold
gaps inside it.

Ownership is the claim that the occupancy belongs to this room, earned by an
entry that led at the room's own entry gates - something activity beyond a
wall can never do. It begins disarmed, where retention refreshes hold and
stillness therefore cannot release: there is no way out of a room that does
not produce motion. Only the occupant re-crossing the entry band arms release,
and from then on nothing but their own attributed evidence holds the door.

All timing comes from frame ``ts_mono``; nothing here reads a clock.
"""

from __future__ import annotations

from collections import deque
from math import exp
from typing import Any

from .types import (
    GATE_COUNT,
    OWNERSHIP_ARMED,
    OWNERSHIP_DISARMED,
    DetectorConfig,
)

SCHEMA_VERSION = 1
"""Serialisation version of the retention/ownership state."""

_NOISE_TAU_S = 10.0
_NOISE_MIN = 0.1
"""Lower bound on the normalizer, so a dead-quiet gate cannot divide by ~0."""

_NOISE_CLAMP_SLOPE = 4.0
_NOISE_CLAMP_OFFSET = 0.5
"""Robustness clamp: one transient step must not inflate the normalizer."""

_MAX_FRAME_GAP_S = 2.0
"""Longest step any EMA here advances by, so a dropout cannot wipe the state."""

_CROSS_WINDOW_S = 20.0
"""Span the arming burst of near-band frames must fall inside."""


class OwnershipRetention:
    """Per-gate retention statistic and the ownership state machine over it."""

    __slots__ = (
        "_armed",
        "_blocking",
        "_config",
        "_crossings",
        "_fast",
        "_gates",
        "_last_near",
        "_noise",
        "_owned",
        "_peak",
        "_prev_mono",
        "_prev_still",
        "_quiet_gap",
        "_slow",
        "_started",
    )

    def __init__(self, config: DetectorConfig) -> None:
        """Create an unowned tracker with an unseeded statistic."""
        self._config = config
        self._fast = [0.0] * GATE_COUNT
        self._slow = [0.0] * GATE_COUNT
        self._noise = [_NOISE_MIN * 3.0] * GATE_COUNT
        self._peak = [0.0] * GATE_COUNT
        self._prev_still = [0.0] * GATE_COUNT
        self._prev_mono: float | None = None
        self._started = False
        self._owned = False
        self._armed = False
        self._quiet_gap = False
        self._blocking = False
        self._gates: set[int] = set()
        self._last_near: float | None = None
        self._crossings: deque[float] = deque()

    def reconfigure(self, config: DetectorConfig) -> None:
        """Adopt new tuning knobs without disturbing the statistic."""
        self._config = config

    @property
    def owned(self) -> bool:
        """Whether a qualifying entry currently owns the room."""
        return self._owned

    @property
    def armed(self) -> bool:
        """Whether the occupant has demonstrably re-crossed the entry band."""
        return self._armed

    @property
    def state(self) -> str | None:
        """Ownership as reported to consumers, or ``None`` when unowned."""
        if not self._owned:
            return None
        return OWNERSHIP_ARMED if self._armed else OWNERSHIP_DISARMED

    @property
    def values(self) -> tuple[float, ...]:
        """Normalized retention per gate."""
        return tuple(self._peak)

    @property
    def level(self) -> float:
        """Retention at the occupancy's gates, or over the band when unowned."""
        gates = self._gates if self._owned and self._gates else range(GATE_COUNT)
        return max(self._peak[gate] for gate in gates)

    def update(self, ts_mono: float, still_gates: tuple[int, ...]) -> None:
        """Fold one frame's still channel into the per-gate statistic."""
        if not self._started:
            self._seed(ts_mono, still_gates)
            return
        previous = self._prev_mono
        self._prev_mono = ts_mono
        elapsed = _MAX_FRAME_GAP_S
        if previous is not None:
            elapsed = min(max(ts_mono - previous, 0.0), _MAX_FRAME_GAP_S)
        config = self._config
        alpha_fast = _alpha(elapsed, config.tau_fast)
        alpha_slow = _alpha(elapsed, config.tau_slow)
        alpha_noise = _alpha(elapsed, _NOISE_TAU_S)
        decay = exp(-elapsed / config.tau_peak) if config.tau_peak > 0.0 else 0.0
        for gate in range(GATE_COUNT):
            value = float(still_gates[gate])
            self._fast[gate] += alpha_fast * (value - self._fast[gate])
            self._slow[gate] += alpha_slow * (value - self._slow[gate])
            step = min(
                abs(value - self._prev_still[gate]),
                _NOISE_CLAMP_SLOPE * self._noise[gate] + _NOISE_CLAMP_OFFSET,
            )
            self._noise[gate] += alpha_noise * (step - self._noise[gate])
            rise = (self._fast[gate] - self._slow[gate]) / max(
                self._noise[gate], _NOISE_MIN
            )
            self._peak[gate] = max(self._peak[gate] * decay, max(rise, 0.0))
            self._prev_still[gate] = value

    def observe_lead(self, ts_mono: float, leading_gate: int | None) -> None:
        """Record whether this frame's activity led inside the entry band."""
        if leading_gate is not None and leading_gate <= self._config.lead_gate_max:
            self._last_near = ts_mono
            if self._owned:
                self._crossings.append(ts_mono)
        while self._crossings and ts_mono - self._crossings[0] > _CROSS_WINDOW_S:
            self._crossings.popleft()

    def enter(self, gates: tuple[int, ...]) -> None:
        """Take ownership of a fresh, disarmed occupancy over ``gates``."""
        self._owned = True
        self._armed = False
        self._quiet_gap = False
        self._blocking = False
        self._gates = set(gates)
        self._crossings.clear()

    def include(self, gates: tuple[int, ...]) -> None:
        """Extend the occupancy's gate set over gates it has now reached."""
        self._gates.update(gates)

    def rebase(self) -> None:
        """Forget timings left over from a timebase that has restarted."""
        self._prev_mono = None
        self._last_near = None
        self._crossings.clear()

    def release(self) -> None:
        """Drop ownership when the occupancy ends."""
        self._owned = False
        self._armed = False
        self._quiet_gap = False
        self._blocking = False
        self._gates = set()
        self._crossings.clear()

    def refreshes_hold(self, ts_mono: float, scored: bool) -> bool:
        """Whether this frame's evidence keeps an owned room occupied."""
        self._step_arming(ts_mono)
        near_recent = (
            self._last_near is not None
            and ts_mono - self._last_near <= self._config.grace_s
        )
        attributed = scored and near_recent
        if self._armed:
            return attributed
        return attributed or self._retention_blocks()

    def to_dict(self) -> dict[str, Any]:
        """Serialise the statistic and ownership, JSON-safe."""
        return {
            "version": SCHEMA_VERSION,
            "fast": list(self._fast),
            "slow": list(self._slow),
            "noise": list(self._noise),
            "peak": list(self._peak),
            "prev_still": list(self._prev_still),
            "prev_mono": self._prev_mono,
            "started": self._started,
            "owned": self._owned,
            "armed": self._armed,
            "quiet_gap": self._quiet_gap,
            "blocking": self._blocking,
            "gates": sorted(self._gates),
            "last_near": self._last_near,
            "crossings": list(self._crossings),
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], config: DetectorConfig
    ) -> OwnershipRetention:
        """Rebuild a tracker from :meth:`to_dict` output."""
        version = int(data["version"])
        if version != SCHEMA_VERSION:
            raise ValueError(f"unsupported retention schema version {version}")
        tracker = cls(config)
        tracker._fast = [float(value) for value in data["fast"]]
        tracker._slow = [float(value) for value in data["slow"]]
        tracker._noise = [float(value) for value in data["noise"]]
        tracker._peak = [float(value) for value in data["peak"]]
        tracker._prev_still = [float(value) for value in data["prev_still"]]
        prev_mono = data["prev_mono"]
        tracker._prev_mono = None if prev_mono is None else float(prev_mono)
        tracker._started = bool(data["started"])
        tracker._owned = bool(data["owned"])
        tracker._armed = bool(data["armed"])
        tracker._quiet_gap = bool(data["quiet_gap"])
        tracker._blocking = bool(data["blocking"])
        tracker._gates = {int(gate) for gate in data["gates"]}
        last_near = data["last_near"]
        tracker._last_near = None if last_near is None else float(last_near)
        tracker._crossings = deque(float(value) for value in data["crossings"])
        return tracker

    def _seed(self, ts_mono: float, still_gates: tuple[int, ...]) -> None:
        """Start both EMAs at the first still reading, so neither ramps in."""
        self._started = True
        self._prev_mono = ts_mono
        for gate in range(GATE_COUNT):
            value = float(still_gates[gate])
            self._fast[gate] = value
            self._slow[gate] = value
            self._prev_still[gate] = value

    def _step_arming(self, ts_mono: float) -> None:
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

    def _retention_blocks(self) -> bool:
        """Whether retention is elevated enough to keep a disarmed room held."""
        config = self._config
        if config.retention_off <= 0.0:
            return False
        level = self.level
        if level >= config.retention_on:
            self._blocking = True
        elif level < config.retention_off:
            self._blocking = False
        return self._blocking


def _alpha(elapsed: float, tau: float) -> float:
    """EMA weight for a step of ``elapsed`` seconds at time constant ``tau``."""
    if tau <= 0.0:
        return 1.0
    return 1.0 - exp(-elapsed / tau)
