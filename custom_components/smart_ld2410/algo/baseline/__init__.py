"""The learned noise model one sensor keeps: floor, spread, and arrival ceiling.

Residuals are ``(energy - floor) / spread``, and the floor, the spread and the
move ceiling are three separate stages over the same bucket tier - each can be
replaced or left out of the stage list on its own. This module is the plumbing
that holds whichever of them a config named, and the persistence they share.

All timing comes from ``Frame.ts_utc``; nothing here reads a clock.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ..roles import (
    ROLE_CEILING,
    ROLE_FLOOR,
    ROLE_SPREAD,
    Stage,
    StageEnv,
    build_stages,
)
from ..types import (
    CHANNEL_MOVE,
    CHANNEL_STILL,
    CHANNELS,
    GATE_COUNT,
    DetectorConfig,
    Frame,
)
from .ceiling import MoveCeiling
from .floor import QuantileFloor
from .histogram_floor import HistogramFloor
from .mode_spread import ModeSpread
from .spread import TailSpread

SCHEMA_VERSION = 5
"""Current persisted-state layout.

Versions 1 and 2 stored bucket medians and MADs, neither of which carries the
upper-tail spread the quantile estimator divides by, so
:meth:`Baseline.from_dict` refuses them rather than misreading them. Versions 3
and 4 are read as-is: they hold the bucket summaries a quantile floor and a
tail spread are made of, and every statistic they do not carry - a move
ceiling, a gate's energy histograms - simply starts unlearned.

A payload carries whatever the stages that wrote it had learned, so a stage
whose state is absent starts fresh rather than refusing the payload.
"""

_READABLE_VERSIONS = frozenset({3, 4, SCHEMA_VERSION})

STAGES: dict[str, type[Stage]] = {
    "quantile_floor": QuantileFloor,
    "tail_spread": TailSpread,
    "histogram_floor": HistogramFloor,
    "mode_spread": ModeSpread,
    "move_ceiling": MoveCeiling,
}
"""The baseline stages, by the name a config lists them under."""


class Baseline:
    """The baseline stages of one sensor, and the state they persist together."""

    __slots__ = (
        "_bucket_s",
        "_ceiling",
        "_floor",
        "_min_buckets",
        "_min_spread",
        "_spread",
        "_stages",
        "_window_s",
    )

    def __init__(
        self,
        env: StageEnv,
        stages: dict[str, Stage],
        names: tuple[str, ...] | None = None,
    ) -> None:
        """Hold the baseline stages the pipeline built, in the order it names them."""
        self._stages = stages
        order = env.config.stages if names is None else names
        self._window_s = env.config.baseline_window_s
        self._min_spread = env.config.min_mad
        self._bucket_s = env.bucket_s
        self._min_buckets = env.min_buckets
        self._floor: Any = _by_role(stages, ROLE_FLOOR, order)
        self._spread: Any = _by_role(stages, ROLE_SPREAD, order)
        self._ceiling: MoveCeiling | None = _by_role(stages, ROLE_CEILING, order)
        if self._floor is None or self._spread is None:
            raise ValueError("residuals need a floor stage and a spread stage")

    @classmethod
    def build(cls, env: StageEnv, names: tuple[str, ...]) -> Baseline:
        """Build the baseline stages ``names`` asks for."""
        return cls(env, build_stages(env, names, STAGES), names)

    @property
    def stages(self) -> dict[str, Stage]:
        """The stages this baseline is made of, by config name."""
        return self._stages

    @property
    def bucket_s(self) -> float:
        """Width of one accumulation bucket, in seconds."""
        return self._bucket_s

    @property
    def bucket_count(self) -> int:
        """Closed buckets in the window (identical across channels)."""
        return self._floor.bucket_count if self._floor is not None else 0

    @property
    def ready(self) -> bool:
        """Whether enough data has accumulated for residuals to mean anything."""
        return self.bucket_count >= self._min_buckets

    @property
    def age_s(self) -> float:
        """Seconds of data accumulated into the window."""
        return self.bucket_count * self._bucket_s

    @property
    def move_ceiling(self) -> float:
        """Raw moving energy level an arrival is measured against."""
        return self._ceiling.value if self._ceiling is not None else 0.0

    @property
    def move_ceiling_learned(self) -> bool:
        """Whether :attr:`move_ceiling` has any observation behind it yet."""
        return self._ceiling is not None and self._ceiling.learned

    def floor(self, gate: int, channel: str = CHANNEL_MOVE) -> float:
        """The learned empty-room level of one gate channel."""
        return self._floor.value(channel, gate) if self._floor is not None else 0.0

    def spread(self, gate: int, channel: str = CHANNEL_MOVE) -> float:
        """The residual divisor of one gate channel."""
        return self._spread.value(channel, gate) if self._spread is not None else 1.0

    def reconfigure(self, config: DetectorConfig) -> None:
        """Adopt new tuning knobs across every baseline stage."""
        for stage in self._stages.values():
            stage.reconfigure(config)

    def resize_window(self, window_s: float) -> None:
        """Resize the window in place, keeping accumulated data.

        Shrinking truncates each channel to its newest buckets; growing keeps
        everything and simply raises the cap on future accumulation.
        """
        self._window_s = window_s
        max_buckets = max(1, round(window_s / self._bucket_s))
        for stage in self._stages.values():
            stage.resize(max_buckets)

    def add_frame(self, frame: Frame, *, frozen: bool = False) -> None:
        """Ingest one frame into every stage.

        ``frozen`` is accepted so existing call sites keep working and is
        deliberately ignored: the quantile floor reads the empty-room level out
        of a partly occupied window on its own, and gating learning on the
        detector's own output is what allowed a noise source to latch occupancy
        permanently.
        """
        del frozen
        for stage in self._stages.values():
            stage.add_frame(frame)

    def residuals(self, frame: Frame) -> tuple[tuple[float, ...], tuple[float, ...]]:
        """Return signed z-scores ``(energy - floor) / spread`` for all channels."""
        move = tuple(
            (frame.move_gates[gate] - self.floor(gate, CHANNEL_MOVE))
            / self.spread(gate, CHANNEL_MOVE)
            for gate in range(GATE_COUNT)
        )
        still = tuple(
            (frame.still_gates[gate] - self.floor(gate, CHANNEL_STILL))
            / self.spread(gate, CHANNEL_STILL)
            for gate in range(GATE_COUNT)
        )
        return move, still

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe snapshot of the whole model."""
        return {
            "version": SCHEMA_VERSION,
            "window_s": self._window_s,
            "bucket_s": self._bucket_s,
            "min_spread": self._min_spread,
            "min_buckets": self._min_buckets,
            CHANNEL_MOVE: [
                self._channel_state(CHANNEL_MOVE, gate) for gate in range(GATE_COUNT)
            ],
            CHANNEL_STILL: [
                self._channel_state(CHANNEL_STILL, gate) for gate in range(GATE_COUNT)
            ],
            "move_ceiling": None
            if self._ceiling is None
            else self._ceiling.to_dict(),
        }

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], config: DetectorConfig | None = None
    ) -> Baseline:
        """Rebuild a model from :meth:`to_dict` output.

        Payloads older than :data:`_READABLE_VERSIONS` raise ``ValueError``.
        Callers treat that as "no persisted baseline" and relearn, which is
        correct rather than merely safe: such a snapshot holds summaries from a
        different estimator and there is no honest way to convert them.
        """
        version = int(data["version"])
        if version not in _READABLE_VERSIONS:
            raise ValueError(f"unsupported baseline schema version {version}")
        base = config or DetectorConfig()
        env = StageEnv(
            replace(
                base,
                baseline_window_s=float(data["window_s"]),
                min_mad=float(data["min_spread"]),
            ),
            bucket_s=float(data["bucket_s"]),
            min_buckets=int(data["min_buckets"]),
        )
        baseline = cls.build(env, base.stages)
        baseline.restore(data)
        return baseline

    def restore(self, data: dict[str, Any]) -> None:
        """Restore every stage from :meth:`to_dict` output."""
        for channel in CHANNELS:
            channels = data[channel]
            if len(channels) != GATE_COUNT:
                raise ValueError("baseline state has the wrong gate count")
            for gate, channel_data in enumerate(channels):
                q50s = channel_data.get("q50s")
                spreads = channel_data.get("spreads")
                if (
                    q50s is not None
                    and spreads is not None
                    and len(q50s) != len(spreads)
                ):
                    raise ValueError("baseline channel has mismatched bucket series")
                if self._floor is not None:
                    self._floor.restore_channel(channel, gate, channel_data)
                if self._spread is not None:
                    self._spread.restore_channel(channel, gate, channel_data)
        ceiling = data.get("move_ceiling")
        if ceiling is not None and self._ceiling is not None:
            self._ceiling.restore(ceiling)

    def _channel_state(self, channel: str, gate: int) -> dict[str, Any]:
        state: dict[str, Any] = {}
        if self._floor is not None:
            state.update(self._floor.channel_state(channel, gate))
        if self._spread is not None:
            state.update(self._spread.channel_state(channel, gate))
        return state


def _by_role(stages: dict[str, Stage], role: str, order: tuple[str, ...]) -> Any:
    named = [stages[name] for name in order if name in stages]
    return next((stage for stage in named if stage.role == role), None)
