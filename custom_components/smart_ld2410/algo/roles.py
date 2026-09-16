"""The roles a stage can fill, the verdicts they return, and what builds them.

Every detection mechanism is one stage filling one role, and a role is a
question the detector asks. The stages listed for a role answer it in the order
the config names them:

* floor and spread provide ``value(channel, gate)``, which residuals are taken
  against; the ceiling provides the level an arrival is measured against.
* a scorer turns a frame's elevations into a score and an active band, and a
  suppression stage says whether a lone hot gate is credible.
* gate classifiers return a :class:`GateVerdict` per gate, a gate boundary
  learns how far the room reaches, and a gate mask turns the class into the
  exclusion entry scoring reads.
* an entry filter returns an :class:`EntryVerdict`; a hold refresher answers
  yes or no. Release needs no role of its own: an occupancy ends when the hold
  window expires with nothing refreshing it, so refusing to release is
  refreshing.
* retention, ownership and arming carry what is known about the occupant a
  room is already holding.
"""

from __future__ import annotations

from dataclasses import dataclass

from .types import DEFAULT_BUCKET_S, DEFAULT_MIN_BUCKETS, DetectorConfig

ROLE_FLOOR = "floor"
ROLE_SPREAD = "spread"
ROLE_CEILING = "ceiling"
ROLE_SCORER = "scorer"
ROLE_SUPPRESSION = "suppression"
ROLE_GATE_CLASS = "gate_class"
ROLE_GATE_BOUNDARY = "gate_boundary"
ROLE_GATE_MASK = "gate_mask"
ROLE_ENTRY_FILTER = "entry_filter"
ROLE_RETENTION = "retention"
ROLE_OWNERSHIP = "ownership"
ROLE_ARMING = "arming"
ROLE_HOLD_REFRESHER = "hold_refresher"

RANK_SUSTAINED = 0
RANK_PORTAL = 1
RANK_BLEED = 2
RANK_STALE_IN_ROOM = 3
"""Precedence of the gate-class verdicts: a proven dwell outranks a doorway,
which outranks bleed, which outranks a gate coasting on an older dwell."""


@dataclass(frozen=True, slots=True)
class StageEnv:
    """What a stage is built from, whatever its role."""

    config: DetectorConfig
    bucket_s: float = DEFAULT_BUCKET_S
    min_buckets: int = DEFAULT_MIN_BUCKETS


@dataclass(frozen=True, slots=True)
class EntryVerdict:
    """An entry filter's answer: admitted, or rejected with a reason."""

    reason: str | None = None

    @property
    def admitted(self) -> bool:
        """Whether the candidate may enter as far as this filter is concerned."""
        return self.reason is None


ADMIT = EntryVerdict()
"""The verdict of a filter with nothing to say about this frame."""


@dataclass(frozen=True, slots=True)
class GateVerdict:
    """A gate classifier's opinion, and how strongly it outranks the others."""

    rank: int
    gate_class: str


class Stage:
    """Base of every stage: the tuning knobs in force, swappable in place."""

    __slots__ = ("_config",)

    role: str

    requires: tuple[str, ...] = ()
    """Stages this one is built over, handed to it by name."""

    expects: tuple[str, ...] = ()
    """Stages this one needs in the list but reads through the context instead."""

    optional: tuple[str, ...] = ()
    """Stages this one uses when they are listed, and works without when not."""

    def __init__(self, env: StageEnv) -> None:
        """Build the stage over the environment the pipeline assembled."""
        self._config = env.config

    def reconfigure(self, config: DetectorConfig) -> None:
        """Adopt new tuning knobs; anything learned is untouched."""
        self._config = config


def build_stages(
    env: StageEnv,
    names: tuple[str, ...],
    registry: dict[str, type[Stage]],
    built: dict[str, Stage] | None = None,
) -> dict[str, Stage]:
    """Instantiate the stages ``registry`` covers, wiring declared dependencies.

    Stages are built in dependency order whatever order the config lists them
    in; a stage whose required dependency is not in the list is refused by
    name, which is what makes a stage list checkable rather than merely
    permissive.
    """
    known = {name: registry[name] for name in names if name in registry}
    stages = dict(built or {})
    pending = [name for name in known if name not in stages]
    while pending:
        progressed = False
        for name in list(pending):
            factory = known[name]
            for dependency in factory.requires + factory.expects:
                if dependency not in names:
                    raise ValueError(
                        f"stage {name!r} requires stage {dependency!r}"
                    )
            wanted = factory.requires + tuple(
                option for option in factory.optional if option in names
            )
            if any(dependency not in stages for dependency in wanted):
                continue
            stages[name] = factory(
                env, **{dependency: stages[dependency] for dependency in wanted}
            )
            pending.remove(name)
            progressed = True
        if not progressed:
            raise ValueError(f"stages depend on each other in a cycle: {sorted(pending)}")
    return stages

