"""Tests for the leading-edge entry condition (spec 24 §1).

The synthetic sensor idles at :data:`NOISE_FLOOR`; a band raised by ``e`` reads
as raw ``NOISE_FLOOR + e``. The leading edge is the only entry rule in the
pipeline here, so it alone admits or refuses an entry.
"""

from __future__ import annotations

from custom_components.smart_ld2410.algo.detector import Detector
from custom_components.smart_ld2410.algo.types import (
    OWNERSHIP_DISARMED,
    RESULT_REJECTED_LEADING_EDGE,
    SCOPE_DETECTION,
    DetectorConfig,
    DetectorOutput,
    Episode,
)

from . import FrameStream, feed, make_config, make_detector, warmup_frames

WALK_IN_MOVE = 50
"""Move elevation of activity strong enough to clear every other entry rule."""

NEAR_BAND = (0, 1, 2)
"""A three-gate run starting at the room's entry gates."""

FAR_BAND = (3, 4, 5)
"""The same shaped run, but starting beyond the entry band."""

BURST_S = 5.0
SETTLE_S = 40.0
QUIET_SIGMA = 0.5


LEADING_EDGE_STAGES = (
    "quantile_floor",
    "tail_spread",
    "run_score",
    "lone_gate_suppression",
    "leading_edge",
    "ownership",
    "crossing_arming",
    "score_hold",
)
"""The scoring core, the leading edge, and the ownership it confers."""


def _config(**overrides: object) -> DetectorConfig:
    """A config whose only live entry rule is the leading edge."""
    values: dict[str, object] = {"stages": LEADING_EDGE_STAGES, "lead_gate_max": 1}
    values.update(overrides)
    return make_config(**values)


def _warm_detector(stream: FrameStream, config: DetectorConfig) -> Detector:
    """A detector with a ready baseline over an idle room."""
    detector = make_detector(config)
    feed(detector, warmup_frames(stream))
    return detector


def _elevate(band: tuple[int, ...]) -> dict[int, int]:
    """Raise every gate of ``band`` to walk-in strength."""
    return dict.fromkeys(band, WALK_IN_MOVE)


def _detections(outputs: list[DetectorOutput]) -> list[Episode]:
    """Every detection-scope episode closed across a run of outputs."""
    return [
        episode
        for output in outputs
        for episode in output.episodes
        if episode.scope == SCOPE_DETECTION
    ]


def test_activity_leading_at_the_entry_gates_enters() -> None:
    """A walk-in lights the near gates first, which is what an entry looks like."""
    stream = FrameStream(sigma=QUIET_SIGMA)
    detector = _warm_detector(stream, _config())

    outputs = feed(detector, stream.burst(BURST_S, move=_elevate(NEAR_BAND)))

    assert outputs[-1].occupied
    assert outputs[-1].leading_gate == NEAR_BAND[0]


def test_activity_leading_beyond_the_entry_gates_is_refused() -> None:
    """The same signal further out never crossed the room's entry band."""
    stream = FrameStream(sigma=QUIET_SIGMA)
    detector = _warm_detector(stream, _config())

    outputs = feed(detector, stream.burst(BURST_S, move=_elevate(FAR_BAND)))

    assert max(output.score for output in outputs) >= detector.config.enter_score
    assert not any(output.occupied for output in outputs)
    assert outputs[-1].leading_gate == FAR_BAND[0]


def test_a_refused_candidate_records_why() -> None:
    """Refused entries still produce episodes, tagged with the rule that held them."""
    stream = FrameStream(sigma=QUIET_SIGMA)
    detector = _warm_detector(stream, _config())

    outputs = feed(detector, stream.burst(BURST_S, move=_elevate(FAR_BAND)))
    outputs += feed(detector, stream.burst(SETTLE_S))

    detections = _detections(outputs)
    assert detections
    assert all(
        episode.result == RESULT_REJECTED_LEADING_EDGE for episode in detections
    )


def test_a_lone_near_spike_does_not_claim_the_leading_edge() -> None:
    """An isolated hot gate is noise, and must not pin the leading edge to it."""
    stream = FrameStream(sigma=QUIET_SIGMA)
    detector = _warm_detector(stream, _config())

    outputs = feed(
        detector,
        stream.burst(
            BURST_S, move=_elevate(FAR_BAND), move_spikes={0: (0.3, WALK_IN_MOVE)}
        ),
    )

    assert any(output.residuals_move[0] >= detector.config.k for output in outputs)
    assert not any(output.occupied for output in outputs)
    assert all(output.leading_gate == FAR_BAND[0] for output in outputs)


def test_a_wider_limit_admits_the_same_far_candidate() -> None:
    """The limit is this room's geometry, so a looser one lets the band in."""
    stream = FrameStream(sigma=QUIET_SIGMA)
    detector = _warm_detector(stream, _config(lead_gate_max=FAR_BAND[0]))

    outputs = feed(detector, stream.burst(BURST_S, move=_elevate(FAR_BAND)))

    assert outputs[-1].occupied


def test_a_disabled_rule_admits_the_same_far_candidate() -> None:
    """-1 turns the rule off for a room whose geometry does not separate."""
    stream = FrameStream(sigma=QUIET_SIGMA)
    detector = _warm_detector(stream, _config(lead_gate_max=-1))

    outputs = feed(detector, stream.burst(BURST_S, move=_elevate(FAR_BAND)))

    assert outputs[-1].occupied


def test_a_qualifying_entry_takes_disarmed_ownership() -> None:
    """Ownership starts at the entry that proved it came through the room."""
    stream = FrameStream(sigma=QUIET_SIGMA)
    detector = _warm_detector(stream, _config())

    outputs = feed(detector, stream.burst(BURST_S, move=_elevate(NEAR_BAND)))

    assert outputs[-1].ownership == OWNERSHIP_DISARMED


def test_a_fallback_entry_is_never_owned() -> None:
    """With the rule off there is no proof of entry, so nothing is owned."""
    stream = FrameStream(sigma=QUIET_SIGMA)
    detector = _warm_detector(stream, _config(lead_gate_max=-1))

    outputs = feed(detector, stream.burst(BURST_S, move=_elevate(FAR_BAND)))

    assert outputs[-1].occupied
    assert outputs[-1].ownership is None


def test_an_unowned_occupancy_releases_on_the_score_alone() -> None:
    """Without ownership, hold is exactly what spec 20 §4 says it is."""
    stream = FrameStream(sigma=QUIET_SIGMA)
    config = _config(lead_gate_max=-1)
    detector = _warm_detector(stream, config)

    feed(detector, stream.burst(BURST_S, move=_elevate(FAR_BAND)))
    assert detector.occupied

    outputs = feed(detector, stream.burst(config.hold_s + 10.0))

    assert not outputs[-1].occupied
