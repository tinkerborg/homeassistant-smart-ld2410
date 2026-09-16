"""What each gate is: in the room, a doorway, bleed through a wall, or unknown.

Three stages answer that from different evidence - dwell character, doorway
outcomes, and the energy-ceiling boundary - and a fourth turns the answer into
the mask entry scoring reads. Unknown is treated as in-room, so a fresh install
behaves exactly as it would without classification and only ever gets stricter
about a gate once that gate has earned it.

This module is the plumbing that holds whichever of those stages a config
named, resolves their verdicts by precedence, and persists what they learned.
All timing comes from ``Frame.ts_utc``, so a replay produces exactly the
classes the live run produced.
"""

from __future__ import annotations

from typing import Any

from ..roles import (
    ROLE_GATE_BOUNDARY,
    ROLE_GATE_CLASS,
    ROLE_GATE_MASK,
    GateVerdict,
    Stage,
    StageEnv,
    build_stages,
)
from ..types import (
    CLASS_IN_ROOM,
    CLASS_LETTERS,
    CLASS_OUT,
    CLASS_UNKNOWN,
    GATE_COUNT,
    SCOPE_GATE,
    BoundaryTransition,
    DetectorConfig,
    Episode,
    GateTransition,
)
from .boundary import EnergyCeilingBoundary
from .dwell import DwellClass
from .exclusion import GateExclusion
from .portal import PortalClass

SCHEMA_VERSION = 3
"""Serialisation version of the gate state."""

_SUPPORTED_VERSIONS = (1, 2, 3)
"""Versions :meth:`GateModel.from_dict` accepts.

An older payload restores with the fields it predates empty, keeping a month of
hard-won dwell statistics a version rejection would have thrown away.
"""

STAGES: dict[str, type[Stage]] = {
    "dwell_class": DwellClass,
    "portal_class": PortalClass,
    "energy_ceiling": EnergyCeilingBoundary,
    "gate_exclusion": GateExclusion,
}
"""The gate stages, by the name a config lists them under."""


class GateView:
    """Everything one gate has learned, across the stages that learned it."""

    __slots__ = ("_model", "gate")

    def __init__(self, model: GateModel, gate: int) -> None:
        """View gate ``gate`` of ``model``."""
        self._model = model
        self.gate = gate

    @property
    def gate_class(self) -> str:
        """The gate's learned class, before any override."""
        return self._model.learned_class(self.gate)

    @property
    def n_sustained(self) -> float:
        """Stored count of sustained episodes."""
        return self._model.dwell_state(self.gate)["n_sustained"]

    @property
    def n_brief(self) -> float:
        """Stored count of brief episodes."""
        return self._model.dwell_state(self.gate)["n_brief"]

    @property
    def last_sustained_ts(self) -> float | None:
        """When this gate last held a dwell."""
        return self._model.dwell_state(self.gate)["last_sustained_ts"]

    @property
    def updated_ts(self) -> float | None:
        """When this gate's counts were last decayed forward."""
        return self._model.dwell_state(self.gate)["updated_ts"]

    @property
    def n_lead(self) -> float:
        """Stored count of brief episodes that led to a dwell."""
        return self._model.portal_state(self.gate)["n_lead"]

    @property
    def n_dead(self) -> float:
        """Stored count of brief episodes that led nowhere."""
        return self._model.portal_state(self.gate)["n_dead"]

    @property
    def ceil_bins(self) -> dict[int, float]:
        """The gate's decayed histogram of episode peak raw move energy."""
        return self._model.ceil_bins(self.gate)

    def ceil_q(self) -> float | None:
        """Decayed upper quantile of episode peak raw energy, or ``None``."""
        return self._model.ceil_q(self.gate)

    def n_epi(self, ts: float) -> float:
        """Decayed count of episodes behind the ceiling, as of ``ts``."""
        return self._model.n_epi(self.gate, ts)

    def decayed(self, ts: float) -> tuple[float, float]:
        """``(n_sustained, n_brief)`` as of ``ts``."""
        return self._model.decayed_dwell(self.gate, ts)

    def decayed_outcomes(self, ts: float) -> tuple[float, float]:
        """``(n_lead, n_dead)`` as of ``ts``."""
        return self._model.decayed_outcomes(self.gate, ts)


class GateModel:
    """The gate stages of one sensor, and the classes they agree on."""

    __slots__ = (
        "_boundary",
        "_classes",
        "_classifiers",
        "_config",
        "_dwell",
        "_last_eval_ts",
        "_mask",
        "_portal",
        "_stages",
        "_statistics",
    )

    def __init__(self, env: StageEnv, stages: dict[str, Stage]) -> None:
        """Hold the gate stages the pipeline built."""
        self._config = env.config
        self._stages = stages
        self._classifiers = [
            stage for stage in stages.values() if stage.role == ROLE_GATE_CLASS
        ]
        self._boundary: EnergyCeilingBoundary | None = _by_role(
            stages, ROLE_GATE_BOUNDARY
        )
        self._mask: GateExclusion | None = _by_role(stages, ROLE_GATE_MASK)
        self._statistics = [
            stage
            for stage in stages.values()
            if stage.role in (ROLE_GATE_CLASS, ROLE_GATE_BOUNDARY)
        ]
        self._dwell: DwellClass | None = _first(self._classifiers, DwellClass)
        self._portal: PortalClass | None = _first(self._classifiers, PortalClass)
        self._classes = [CLASS_UNKNOWN] * GATE_COUNT
        self._last_eval_ts: float | None = None

    @classmethod
    def build(cls, env: StageEnv, names: tuple[str, ...]) -> GateModel:
        """Build the gate stages ``names`` asks for."""
        return cls(env, build_stages(env, names, STAGES))

    @property
    def stages(self) -> dict[str, Stage]:
        """The stages this model is made of, by config name."""
        return self._stages

    @property
    def stats(self) -> tuple[GateView, ...]:
        """Per-gate views of the learned statistics, indexed by gate."""
        return tuple(GateView(self, gate) for gate in range(GATE_COUNT))

    @property
    def classes(self) -> str:
        """Diagnostic string like ``IIIPUBB...``, one letter per gate."""
        return "".join(
            CLASS_LETTERS[self.gate_class(gate)] for gate in range(GATE_COUNT)
        )

    @property
    def last_in_room_gate(self) -> int | None:
        """Highest gate proven to be in-room, or ``None`` if none is yet.

        Unknown gates are treated as in-room for *detection*, but they are not
        evidence of where the room ends, so they do not move this.
        """
        for gate in reversed(range(GATE_COUNT)):
            if self.gate_class(gate) == CLASS_IN_ROOM:
                return gate
        return None

    @property
    def boundary_gate(self) -> int | None:
        """The learned energy-ceiling boundary, or ``None``."""
        return None if self._boundary is None else self._boundary.boundary_gate

    @property
    def pending_boundary(self) -> int | None:
        """The candidate boundary the confirmation run is counting, if any."""
        return None if self._boundary is None else self._boundary.pending_boundary

    @property
    def confirmed_days(self) -> int:
        """Consecutive daily evaluations the pending boundary has survived."""
        return 0 if self._boundary is None else self._boundary.confirmed_days

    @property
    def ceil_profile(self) -> tuple[float | None, ...]:
        """Each gate's ceiling over what the sensor's falloff predicts for it."""
        if self._boundary is None:
            return (None,) * GATE_COUNT
        return self._boundary.ceil_profile

    def gate_class(self, gate: int) -> str:
        """Effective class of ``gate``: overrides, then boundary, then evidence.

        The manual cap is configuration and must never be second-guessed by
        something the sensor learned, so it is asked first.
        """
        if self._mask is not None and self._mask.capped(gate):
            return CLASS_OUT
        if self._boundary is not None:
            override = self._boundary.class_override(gate)
            if override is not None:
                return override
        return self._classes[gate]

    def learned_class(self, gate: int) -> str:
        """The class the evidence alone puts ``gate`` in."""
        return self._classes[gate]

    def excluded(self, gate: int) -> bool:
        """Whether ``gate`` is barred from entry scoring and neighbour support."""
        if self._mask is None:
            return False
        return self._mask.excluded(self.gate_class(gate))

    def reconfigure(self, config: DetectorConfig) -> None:
        """Adopt new thresholds; the learned statistics are untouched."""
        self._config = config
        for stage in self._stages.values():
            stage.reconfigure(config)

    def observe(self, episode: Episode) -> tuple[GateTransition, ...]:
        """Fold one closed per-gate episode in and reclassify.

        Detection-scope episodes are ignored: they describe a band, and the
        classification question is per gate.
        """
        if episode.scope != SCOPE_GATE or episode.gate is None:
            return ()
        ts = episode.t1
        self._advance(episode.gate, ts)
        for stage in self._statistics:
            stage.observe(episode)
        return self.evaluate(ts)

    def tick(
        self,
        ts: float,
        *,
        open_gates: tuple[int, ...] = (),
        open_starts: tuple[float, ...] = (),
    ) -> tuple[tuple[GateTransition, ...], tuple[BoundaryTransition, ...]]:
        """Re-evaluate on a schedule so decay alone can demote a gate.

        Classification is otherwise only recomputed when an episode closes,
        which would leave a gate that has simply gone quiet for months stuck at
        its last class forever. ``open_gates`` are the gates with an episode in
        progress; a boundary retreat that would suppress one of them is
        deferred. ``open_starts`` are those episodes' start times, which is what
        holds a brief episode unresolved while the dwell it may have led to
        still runs.
        """
        boundary_transitions: tuple[BoundaryTransition, ...] = ()
        if self._boundary is not None:
            boundary_transitions = self._boundary.tick(ts, open_gates)
        resolved = False
        if self._portal is not None:
            for gate, leading in self._portal.due(ts, open_starts):
                self._advance(gate, ts)
                self._portal.credit(gate, leading)
                resolved = True
        last = self._last_eval_ts
        interval = self._config.class_eval_interval_s
        if not resolved and last is not None and 0.0 <= ts - last < interval:
            return (), boundary_transitions
        return self.evaluate(ts), boundary_transitions

    def evaluate(self, ts: float) -> tuple[GateTransition, ...]:
        """Reclassify every gate as of ``ts`` and return the changes."""
        self._last_eval_ts = ts
        transitions: list[GateTransition] = []
        for gate in range(GATE_COUNT):
            previous = self._classes[gate]
            current = self._verdict(gate, ts, previous)
            if current != previous:
                transitions.append(
                    GateTransition(
                        gate=gate, ts=ts, previous=previous, current=current
                    )
                )
                self._classes[gate] = current
        return tuple(transitions)

    def dwell_state(self, gate: int) -> dict[str, Any]:
        """One gate's stored dwell counts, or zeros where nothing counts them."""
        if self._dwell is None:
            return {
                "n_sustained": 0.0,
                "n_brief": 0.0,
                "last_sustained_ts": None,
                "updated_ts": None,
            }
        return self._dwell.gate_state(gate)

    def portal_state(self, gate: int) -> dict[str, Any]:
        """One gate's stored doorway counts, or zeros where nothing counts them."""
        if self._portal is None:
            return {"n_lead": 0.0, "n_dead": 0.0}
        return self._portal.gate_state(gate)

    def decayed_dwell(self, gate: int, ts: float) -> tuple[float, float]:
        """``(n_sustained, n_brief)`` as of ``ts``."""
        if self._dwell is None:
            return (0.0, 0.0)
        return self._dwell.decayed(gate, ts)

    def decayed_outcomes(self, gate: int, ts: float) -> tuple[float, float]:
        """``(n_lead, n_dead)`` as of ``ts``."""
        if self._portal is None:
            return (0.0, 0.0)
        return self._portal.decayed(gate, ts)

    def ceil_bins(self, gate: int) -> dict[int, float]:
        """One gate's ceiling histogram, empty where nothing keeps one."""
        if self._boundary is None:
            return {}
        return {
            int(value): weight
            for value, weight in self._boundary.gate_state(gate)["ceil_bins"].items()
        }

    def ceil_q(self, gate: int) -> float | None:
        """One gate's decayed ceiling quantile, or ``None``."""
        return None if self._boundary is None else self._boundary.ceil_q(gate)

    def n_epi(self, gate: int, ts: float) -> float:
        """One gate's decayed episode count behind the ceiling."""
        return 0.0 if self._boundary is None else self._boundary.n_epi(gate, ts)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe snapshot of everything the gates have learned."""
        boundary = (
            self._boundary.to_dict()
            if self._boundary is not None
            else {
                "boundary_gate": None,
                "pending_boundary": None,
                "pending_evaluated": False,
                "confirm_count": 0,
                "last_boundary_eval_ts": None,
            }
        )
        return {
            "version": SCHEMA_VERSION,
            "last_eval_ts": self._last_eval_ts,
            "gates": [self._gate_state(gate) for gate in range(GATE_COUNT)],
            **boundary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: DetectorConfig) -> GateModel:
        """Rebuild the gate stages from :meth:`to_dict` output.

        Accepts the versions in :data:`_SUPPORTED_VERSIONS`; fields a payload
        predates start empty. Any other version raises ``ValueError``, which
        callers treat as "no persisted classification" and relearn - one
        permissive month rather than acting on counts whose meaning changed.
        """
        version = int(data["version"])
        if version not in _SUPPORTED_VERSIONS:
            raise ValueError(f"unsupported gate classifier schema version {version}")
        model = cls.build(StageEnv(config), config.stages)
        model.restore(data)
        return model

    def restore(self, data: dict[str, Any]) -> None:
        """Restore every gate stage from :meth:`to_dict` output."""
        gates = data["gates"]
        if len(gates) != GATE_COUNT:
            raise ValueError("gate classifier state has the wrong gate count")
        for gate, gate_data in enumerate(gates):
            gate_class = str(gate_data["class"])
            if gate_class not in CLASS_LETTERS:
                raise ValueError(f"unknown gate class {gate_class!r}")
            self._classes[gate] = gate_class
            for stage in self._statistics:
                stage.restore_gate(gate, gate_data)
        last_eval = data.get("last_eval_ts")
        self._last_eval_ts = None if last_eval is None else float(last_eval)
        if self._boundary is not None:
            self._boundary.restore(data)

    def _gate_state(self, gate: int) -> dict[str, Any]:
        state: dict[str, Any] = {"gate": gate}
        for stage in self._statistics:
            state.update(stage.gate_state(gate))
        state["class"] = self._classes[gate]
        return state

    def _advance(self, gate: int, ts: float) -> None:
        for stage in self._statistics:
            stage.advance(gate, ts)

    def _verdict(self, gate: int, ts: float, current: str) -> str:
        best: GateVerdict | None = None
        for stage in self._classifiers:
            verdict = stage.classify(gate, ts, current)
            if verdict is not None and (best is None or verdict.rank < best.rank):
                best = verdict
        return CLASS_UNKNOWN if best is None else best.gate_class


def _by_role(stages: dict[str, Stage], role: str) -> Any:
    return next((stage for stage in stages.values() if stage.role == role), None)


def _first(stages: list[Stage], kind: type[Stage]) -> Any:
    return next((stage for stage in stages if isinstance(stage, kind)), None)
