"""Everything the detector knows about the occupant it is already holding.

Three stages that only work together: the signed retention statistic says
somebody is still here, ownership says whose evidence this is, and the arming
sequence says whether the occupant has been seen leaving. This module is the
plumbing that holds whichever of them a config named, and the state they
persist together.
"""

from __future__ import annotations

from typing import Any

from ..roles import (
    ROLE_ARMING,
    ROLE_OWNERSHIP,
    ROLE_RETENTION,
    Stage,
    StageEnv,
    build_stages,
)
from ..types import GATE_COUNT, OWNERSHIP_ARMED, OWNERSHIP_DISARMED, DetectorConfig
from .arming import CrossingArming
from .ownership import Ownership
from .retention import SignedRetention

SCHEMA_VERSION = 1
"""Serialisation version of the presence state."""

STAGES: dict[str, type[Stage]] = {
    "retention": SignedRetention,
    "ownership": Ownership,
    "crossing_arming": CrossingArming,
}
"""The presence stages, by the name a config lists them under."""


class Presence:
    """The presence stages of one sensor, and the state they persist together."""

    __slots__ = ("_arming", "_ownership", "_retention", "_stages")

    def __init__(self, stages: dict[str, Stage]) -> None:
        """Hold the presence stages the pipeline built."""
        self._stages = stages
        self._retention: SignedRetention | None = _by_role(stages, ROLE_RETENTION)
        self._ownership: Ownership | None = _by_role(stages, ROLE_OWNERSHIP)
        self._arming: CrossingArming | None = _by_role(stages, ROLE_ARMING)

    @property
    def stages(self) -> dict[str, Stage]:
        """The stages this presence is made of, by config name."""
        return self._stages

    @property
    def owned(self) -> bool:
        """Whether a qualifying entry currently owns the room."""
        return self._ownership is not None and self._ownership.owned

    @property
    def armed(self) -> bool:
        """Whether the occupant has demonstrably re-crossed the entry band."""
        return self._arming is not None and self._arming.armed

    @property
    def state(self) -> str | None:
        """Ownership as reported to consumers, or ``None`` when unowned."""
        if not self.owned:
            return None
        return OWNERSHIP_ARMED if self.armed else OWNERSHIP_DISARMED

    @property
    def values(self) -> tuple[float, ...]:
        """Normalized retention per gate."""
        if self._retention is None:
            return (0.0,) * GATE_COUNT
        return self._retention.values

    @property
    def level(self) -> float:
        """Retention at the occupancy's gates, or over the band when unowned."""
        if self._retention is None:
            return 0.0
        gates = self._ownership.gates if self.owned and self._ownership else ()
        return self._retention.level(gates or None)

    def reconfigure(self, config: DetectorConfig) -> None:
        """Adopt new tuning knobs across every presence stage."""
        for stage in self._stages.values():
            stage.reconfigure(config)

    def update(self, ts_mono: float, still_gates: tuple[int, ...]) -> None:
        """Fold one frame's still channel into the retention statistic."""
        if self._retention is not None:
            self._retention.update(ts_mono, still_gates)

    def observe_lead(self, ts_mono: float, leading_gate: int | None) -> None:
        """Record whether this frame's activity led inside the entry band."""
        if self._arming is not None:
            self._arming.observe_lead(ts_mono, leading_gate)

    def claim(self, gates: tuple[int, ...], leading_gate: int | None) -> None:
        """Take ownership of a fresh occupancy if the entry qualifies."""
        if self._ownership is not None and self._ownership.claim(gates, leading_gate):
            self._restart()

    def enter(self, gates: tuple[int, ...]) -> None:
        """Take ownership of a fresh occupancy over ``gates``."""
        if self._ownership is not None:
            self._ownership.enter(gates)
            self._restart()

    def include(self, gates: tuple[int, ...]) -> None:
        """Extend the occupancy's gate set over gates it has now reached."""
        if self._ownership is not None:
            self._ownership.include(gates)

    def step_arming(self, ts_mono: float) -> None:
        """Advance the sequence that arms release."""
        if self._arming is not None:
            self._arming.step(ts_mono)

    def release(self) -> None:
        """Drop ownership when the occupancy ends."""
        if self._ownership is not None:
            self._ownership.release()
        self._restart()

    def rebase(self) -> None:
        """Forget timings left over from a timebase that has restarted."""
        for stage in (self._retention, self._arming):
            if stage is not None:
                stage.rebase()

    def to_dict(self) -> dict[str, Any]:
        """Serialise every presence stage, JSON-safe."""
        state: dict[str, Any] = {"version": SCHEMA_VERSION}
        for stage in self._stages.values():
            state.update(stage.to_dict())
        return state

    @classmethod
    def build(cls, env: StageEnv, names: tuple[str, ...]) -> Presence:
        """Build the presence stages ``names`` asks for."""
        return cls(build_stages(env, names, STAGES))

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: DetectorConfig) -> Presence:
        """Rebuild the presence stages from :meth:`to_dict` output."""
        version = int(data["version"])
        if version != SCHEMA_VERSION:
            raise ValueError(f"unsupported presence schema version {version}")
        presence = cls.build(StageEnv(config), config.stages)
        presence.restore(data)
        return presence

    def restore(self, data: dict[str, Any]) -> None:
        """Restore every presence stage from :meth:`to_dict` output."""
        for stage in self._stages.values():
            stage.restore(data)

    def _restart(self) -> None:
        """Start the arming sequence and the retention hold over."""
        if self._arming is not None:
            self._arming.reset()
        if self._retention is not None:
            self._retention.reset()


def _by_role(stages: dict[str, Stage], role: str) -> Any:
    return next((stage for stage in stages.values() if stage.role == role), None)
