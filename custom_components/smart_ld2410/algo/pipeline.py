"""The stage registry, and the pipeline one detector runs each frame.

A detector is exactly the stages its config names, in the order it names them,
so any combination of techniques can be composed - and measured - without
touching the detector itself. A stage that another stage needs declares it, and
the build refuses a list that leaves the dependency out.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from . import baseline as baseline_stages
from . import entry as entry_stages
from . import gates as gate_stages
from . import hold as hold_stages
from . import presence as presence_stages
from . import scoring as scoring_stages
from .baseline import Baseline
from .gates import GateModel
from .presence import Presence
from .roles import (
    ADMIT,
    ROLE_ENTRY_FILTER,
    ROLE_HOLD_REFRESHER,
    ROLE_SCORER,
    EntryVerdict,
    Stage,
    StageEnv,
    build_stages,
)
from .scoring.runs import RunScorer, admit_every_gate
from .types import DetectorConfig

if TYPE_CHECKING:
    from .context import DetectorContext

REGISTRY: dict[str, type[Stage]] = {
    **baseline_stages.STAGES,
    **scoring_stages.STAGES,
    **gate_stages.STAGES,
    **entry_stages.STAGES,
    **presence_stages.STAGES,
    **hold_stages.STAGES,
}
"""Every stage a config may name, by that name."""


class Pipeline:
    """The stages of one detector, grouped by role and ordered within it."""

    __slots__ = (
        "_entry_filters",
        "_hold_refreshers",
        "_scorer",
        "_stages",
        "baseline",
        "gates",
        "presence",
    )

    def __init__(
        self,
        stages: dict[str, Stage],
        *,
        baseline: Baseline,
        gates: GateModel,
        presence: Presence,
    ) -> None:
        """Hold the stages, and the composites that persist what they learn."""
        self._stages = stages
        self.baseline = baseline
        self.gates = gates
        self.presence = presence
        self._scorer: RunScorer | None = next(
            (stage for stage in stages.values() if stage.role == ROLE_SCORER), None
        )
        self._entry_filters = tuple(
            stage for stage in stages.values() if stage.role == ROLE_ENTRY_FILTER
        )
        self._hold_refreshers = tuple(
            stage for stage in stages.values() if stage.role == ROLE_HOLD_REFRESHER
        )

    def reconfigure(self, config: DetectorConfig) -> None:
        """Adopt new tuning knobs across every stage."""
        self.gates.reconfigure(config)
        for stage in self._stages.values():
            stage.reconfigure(config)

    def score(
        self,
        peaks: Sequence[float],
        support: Sequence[float],
        *,
        excluded: Callable[[int], bool] = admit_every_gate,
    ) -> tuple[float, tuple[int, ...]]:
        """Score this frame's strongest coherent run of hot gates."""
        if self._scorer is None:
            return 0.0, ()
        return self._scorer.best_run(peaks, support, excluded=excluded)

    def leading_gate(
        self, residuals: Sequence[float], support: Sequence[float]
    ) -> int | None:
        """The nearest gate the activity in progress reaches."""
        if self._scorer is None:
            return None
        return self._scorer.leading_gate(residuals, support)

    def observe_entry(self, context: DetectorContext) -> None:
        """Fold this frame into every entry filter's own candidate evidence."""
        for stage in self._entry_filters:
            stage.accumulate(context)

    def entry_verdict(self, context: DetectorContext) -> EntryVerdict:
        """Ask every entry filter in turn, stopping at the first rejection.

        The first rejection is the one the episode records, and the filters run
        in config order, so each rule only judges frames the ones before it let
        through.
        """
        if context.occupied or not context.active_gates:
            return ADMIT
        for stage in self._entry_filters:
            verdict = stage.verdict(context)
            if not verdict.admitted:
                return verdict
        return ADMIT

    def refreshes_hold(self, context: DetectorContext) -> bool:
        """Whether any refresher keeps the occupancy alive this frame."""
        anchor = self._stages.get("motion_anchor")
        if anchor is not None:
            return anchor.refreshes(context)
        return any(stage.refreshes(context) for stage in self._hold_refreshers)


def build_pipeline(
    env: StageEnv,
    *,
    baseline: Baseline | None = None,
    gates: GateModel | None = None,
    presence: Presence | None = None,
) -> Pipeline:
    """Build the pipeline ``env.config.stages`` names.

    Composites handed in are adopted whole - that is how a restored baseline or
    a month of gate statistics survives a restart - and the stages they already
    hold are what the rest of the pipeline is wired to.
    """
    names = env.config.stages
    for name in names:
        if name not in REGISTRY:
            raise ValueError(f"unknown detector stage {name!r}")
    built: dict[str, Stage] = {}
    for composite in (baseline, gates, presence):
        if composite is not None:
            built.update(composite.stages)
    stages = build_stages(env, names, REGISTRY, built)
    return Pipeline(
        stages,
        baseline=baseline or Baseline(env, _of(stages, baseline_stages.STAGES)),
        gates=gates or GateModel(env, _of(stages, gate_stages.STAGES)),
        presence=presence or Presence(_of(stages, presence_stages.STAGES)),
    )


def _of(stages: dict[str, Stage], registry: dict[str, Any]) -> dict[str, Stage]:
    return {name: stage for name, stage in stages.items() if name in registry}
