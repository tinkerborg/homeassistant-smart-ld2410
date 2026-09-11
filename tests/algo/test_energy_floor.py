"""Tests for the entry energy floor (spec 23).

The synthetic sensor idles at :data:`NOISE_FLOOR` on both channels, so a gate
elevation of ``e`` reads as raw ``NOISE_FLOOR + e`` and the combined peak the
floor is compared against is the sum of the two channels' raw energies.
"""

from __future__ import annotations

from custom_components.smart_ld2410.algo.detector import Detector
from custom_components.smart_ld2410.algo.types import (
    RESULT_ENTERED,
    RESULT_REJECTED_ENERGY_FLOOR,
    SCOPE_DETECTION,
    DetectorConfig,
    DetectorOutput,
    Episode,
)

from . import NOISE_FLOOR, FrameStream, feed, make_config, make_detector

THROUGH_WALL_MOVE = 10
"""Move elevation of attenuated activity: raw ~15, faint in both channels."""

STILL_DWELL_MOVE = 13
"""Move elevation of a motionless occupant: raw ~18, in the through-wall band."""

STILL_DWELL_STILL = 55
"""Still elevation of that same occupant: raw ~60, what proves they are here."""

WALK_IN_MOVE = 60
"""Move elevation of somebody walking in, strong from the first frame."""

BAND = (3, 4, 5)
"""A three-gate run, wide enough to pass the spatial-coherence test."""


def _elevate(elevation: int) -> dict[int, int]:
    """Raise every gate of the band by ``elevation``."""
    return dict.fromkeys(BAND, elevation)


def _detections(episodes: list[Episode]) -> list[Episode]:
    """Keep only the detection-scope rows."""
    return [episode for episode in episodes if episode.scope == SCOPE_DETECTION]


def _closed_episodes(outputs: list[DetectorOutput]) -> list[Episode]:
    """Every episode closed across a run of outputs."""
    return [episode for output in outputs for episode in output.episodes]


def _ready_detector(stream: FrameStream, config: DetectorConfig) -> Detector:
    """A detector with a warm baseline, ready to be judged on the next burst."""
    detector = make_detector(config)
    feed(detector, stream.burst(10.0))
    return detector


def test_through_wall_energy_is_uniformly_faint() -> None:
    """The exemplar really is under the floor, so the tests below mean something."""
    assert 2 * NOISE_FLOOR + THROUGH_WALL_MOVE < DetectorConfig().energy_floor
    assert (
        2 * NOISE_FLOOR + STILL_DWELL_MOVE + STILL_DWELL_STILL
        > DetectorConfig().energy_floor
    )


def test_weak_entry_is_suppressed_and_recorded() -> None:
    """A candidate faint in both channels never enters, and says why."""
    stream = FrameStream()
    detector = _ready_detector(stream, make_config())

    outputs = feed(detector, stream.burst(60.0, move=_elevate(THROUGH_WALL_MOVE)))

    assert max(output.score for output in outputs) >= detector.config.enter_score
    assert not any(output.occupied for output in outputs)

    quiet = feed(detector, stream.burst(60.0))
    detections = _detections(_closed_episodes(outputs + quiet))
    assert detections
    assert all(
        episode.result == RESULT_REJECTED_ENERGY_FLOOR for episode in detections
    )


def test_still_dwell_with_a_weak_move_channel_enters() -> None:
    """A motionless occupant is carried over the floor by the still channel."""
    stream = FrameStream()
    detector = _ready_detector(stream, make_config())

    outputs = feed(
        detector,
        stream.burst(
            30.0,
            move=_elevate(STILL_DWELL_MOVE),
            still=_elevate(STILL_DWELL_STILL),
        ),
    )

    assert outputs[-1].occupied
    quiet = feed(detector, stream.burst(60.0))
    detections = _detections(_closed_episodes(outputs + quiet))
    assert detections
    assert detections[0].result == RESULT_ENTERED


def test_walk_in_entry_latency_is_unchanged() -> None:
    """A real walk-in clears the floor on the frame it clears ``enter_score``."""
    latencies = []
    for energy_floor in (0.0, DetectorConfig().energy_floor):
        stream = FrameStream()
        detector = _ready_detector(
            stream, make_config(energy_floor=energy_floor, arrival_frac=0.0)
        )
        outputs = feed(detector, stream.burst(5.0, move=_elevate(WALK_IN_MOVE)))
        latencies.append(next(
            index for index, output in enumerate(outputs) if output.occupied
        ))

    assert latencies[0] == latencies[1]
    assert latencies[1] == 0


def test_zero_floor_disables_the_rule() -> None:
    """The same weak candidate enters once the floor is turned off."""
    stream = FrameStream()
    detector = _ready_detector(stream, make_config(energy_floor=0.0))

    outputs = feed(detector, stream.burst(30.0, move=_elevate(THROUGH_WALL_MOVE)))

    assert outputs[-1].occupied


def test_occupancy_survives_energy_decaying_under_the_floor() -> None:
    """Exit stays score-driven: a person going faint and still is not dropped."""
    stream = FrameStream()
    detector = _ready_detector(stream, make_config())

    entry = feed(detector, stream.burst(5.0, move=_elevate(WALK_IN_MOVE)))
    assert entry[-1].occupied

    decayed = feed(detector, stream.burst(40.0, move=_elevate(THROUGH_WALL_MOVE)))

    assert all(output.occupied for output in decayed)
