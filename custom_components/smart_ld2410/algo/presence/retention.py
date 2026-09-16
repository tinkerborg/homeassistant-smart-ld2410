"""The signed still-presence retention statistic (spec 24 §2).

A fast EMA of the still channel minus a slow one, negative part discarded,
normalized by the gate's own frame-to-frame noise and peak-held. The sign is
what separates "a person is sitting here" from "a person just left": a
departure drives the unsigned difference to its maximum, while the signed form
reads ~0 through every vacancy and stays elevated through stillness. The
peak-hold carries a genuine sit across the sub-threshold gaps inside it.

All timing comes from frame ``ts_mono``; nothing here reads a clock.
"""

from __future__ import annotations

from collections.abc import Iterable
from math import exp
from typing import Any

from ..roles import ROLE_RETENTION, Stage, StageEnv
from ..types import GATE_COUNT

_NOISE_TAU_S = 10.0
_NOISE_MIN = 0.1
"""Lower bound on the normalizer, so a dead-quiet gate cannot divide by ~0."""

_NOISE_CLAMP_SLOPE = 4.0
_NOISE_CLAMP_OFFSET = 0.5
"""Robustness clamp: one transient step must not inflate the normalizer."""

_MAX_FRAME_GAP_S = 2.0
"""Longest step any EMA here advances by, so a dropout cannot wipe the state."""


class SignedRetention(Stage):
    """Per-gate normalized still-presence retention, peak-held."""

    __slots__ = (
        "_blocking",
        "_fast",
        "_noise",
        "_peak",
        "_prev_mono",
        "_prev_still",
        "_slow",
        "_started",
    )

    role = ROLE_RETENTION

    def __init__(self, env: StageEnv) -> None:
        """Start with an unseeded statistic."""
        super().__init__(env)
        self._fast = [0.0] * GATE_COUNT
        self._slow = [0.0] * GATE_COUNT
        self._noise = [_NOISE_MIN * 3.0] * GATE_COUNT
        self._peak = [0.0] * GATE_COUNT
        self._prev_still = [0.0] * GATE_COUNT
        self._prev_mono: float | None = None
        self._started = False
        self._blocking = False

    @property
    def values(self) -> tuple[float, ...]:
        """Normalized retention per gate."""
        return tuple(self._peak)

    def level(self, gates: Iterable[int] | None = None) -> float:
        """Highest retention over ``gates``, or over the whole band."""
        return max(self._peak[gate] for gate in (gates or range(GATE_COUNT)))

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

    def blocks(self, gates: Iterable[int] | None = None) -> bool:
        """Whether retention is elevated enough to keep a room held."""
        config = self._config
        if config.retention_off <= 0.0:
            return False
        level = self.level(gates)
        if level >= config.retention_on:
            self._blocking = True
        elif level < config.retention_off:
            self._blocking = False
        return self._blocking

    def reset(self) -> None:
        """Forget whether retention was holding a room that has just changed."""
        self._blocking = False

    def rebase(self) -> None:
        """Forget timings left over from a timebase that has restarted."""
        self._prev_mono = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise the statistic, JSON-safe."""
        return {
            "fast": list(self._fast),
            "slow": list(self._slow),
            "noise": list(self._noise),
            "peak": list(self._peak),
            "prev_still": list(self._prev_still),
            "prev_mono": self._prev_mono,
            "started": self._started,
            "blocking": self._blocking,
        }

    def restore(self, data: dict[str, Any]) -> None:
        """Restore the statistic from :meth:`to_dict` output."""
        self._fast = [float(value) for value in data["fast"]]
        self._slow = [float(value) for value in data["slow"]]
        self._noise = [float(value) for value in data["noise"]]
        self._peak = [float(value) for value in data["peak"]]
        self._prev_still = [float(value) for value in data["prev_still"]]
        prev_mono = data["prev_mono"]
        self._prev_mono = None if prev_mono is None else float(prev_mono)
        self._started = bool(data["started"])
        self._blocking = bool(data["blocking"])

    def _seed(self, ts_mono: float, still_gates: tuple[int, ...]) -> None:
        """Start both EMAs at the first still reading, so neither ramps in."""
        self._started = True
        self._prev_mono = ts_mono
        for gate in range(GATE_COUNT):
            value = float(still_gates[gate])
            self._fast[gate] = value
            self._slow[gate] = value
            self._prev_still[gate] = value


def _alpha(elapsed: float, tau: float) -> float:
    """EMA weight for a step of ``elapsed`` seconds at time constant ``tau``."""
    if tau <= 0.0:
        return 1.0
    return 1.0 - exp(-elapsed / tau)
