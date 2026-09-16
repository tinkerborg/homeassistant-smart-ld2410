"""Tests for composing a detector out of a list of stage names."""

from __future__ import annotations

import pytest

from custom_components.smart_ld2410.algo.baseline import Baseline
from custom_components.smart_ld2410.algo.pipeline import REGISTRY, build_pipeline
from custom_components.smart_ld2410.algo.roles import StageEnv
from custom_components.smart_ld2410.algo.types import ALL_STAGES, DEFAULT_STAGES, DetectorOutput

from . import FrameStream, feed, make_config, make_detector

BAND = (3, 4, 5)
"""A three-gate run, wide enough to pass the spatial-coherence test."""

THROUGH_WALL_MOVE = 10
"""Move elevation faint enough in both channels for the energy floor to refuse."""


def _entry_run(stages: tuple[str, ...]) -> list[DetectorOutput]:
    """Feed a faint candidate to a detector built from ``stages``."""
    stream = FrameStream()
    detector = make_detector(make_config(stages=stages))
    feed(detector, stream.burst(10.0))
    return feed(
        detector,
        stream.burst(60.0, move=dict.fromkeys(BAND, THROUGH_WALL_MOVE)),
    )


def test_every_default_stage_is_registered() -> None:
    """The shipped pipeline can always be built."""
    assert set(DEFAULT_STAGES) <= set(REGISTRY)


def test_an_unknown_stage_name_is_refused() -> None:
    """A typo in a stage list fails loudly instead of quietly dropping a rule."""
    config = make_config(stages=("energy_floor", "nonesuch"))
    with pytest.raises(ValueError, match="unknown detector stage"):
        build_pipeline(StageEnv(config))


def test_a_stage_that_needs_another_says_so_by_name() -> None:
    """Leaving a dependency out of the list is refused, not silently ignored."""
    config = make_config(
        stages=("quantile_floor", "tail_spread", "arrival", "score_hold")
    )
    with pytest.raises(ValueError, match="'arrival' requires stage 'move_ceiling'"):
        build_pipeline(StageEnv(config))


def test_residuals_need_a_floor_and_a_spread() -> None:
    """Residuals have to come from somewhere, and both halves are somewhere."""
    config = make_config(stages=("quantile_floor", "score_hold"))
    with pytest.raises(ValueError, match="floor stage and a spread stage"):
        Baseline.build(StageEnv(config), config.stages)


def test_a_stage_nothing_depends_on_can_be_dropped() -> None:
    """Composing is subtractive as well as additive."""
    stages = tuple(name for name in ALL_STAGES if name != "energy_ceiling")

    pipeline = build_pipeline(StageEnv(make_config(stages=stages)))

    assert pipeline.gates.boundary_gate is None
    assert pipeline.gates.ceil_profile == (None,) * 9


def test_dropping_the_energy_floor_admits_the_candidate_it_refused() -> None:
    """A stage list is what decides the rules, with no other knob touched."""
    without_floor = tuple(name for name in ALL_STAGES if name != "energy_floor")

    assert not any(output.occupied for output in _entry_run(ALL_STAGES))
    assert any(output.occupied for output in _entry_run(without_floor))
