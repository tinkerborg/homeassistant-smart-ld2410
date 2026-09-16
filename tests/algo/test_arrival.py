"""Tests for arrival-gated entry (spec 22).

The synthetic sensor idles at :data:`NOISE_FLOOR`, so a gate elevation of ``e``
reads as raw ``NOISE_FLOOR + e``. The detectors here are first shown one burst
of arrival-scale motion, which is what teaches the move ceiling the gating is
measured against.
"""

from __future__ import annotations

import json

from custom_components.smart_ld2410.algo.baseline import (
    SCHEMA_VERSION,
    Baseline,
)
from custom_components.smart_ld2410.algo.detector import Detector
from custom_components.smart_ld2410.algo.types import (
    MAX_GATE_ENERGY,
    RESULT_REJECTED_ARRIVAL,
    SCOPE_DETECTION,
    DetectorConfig,
    DetectorOutput,
    Episode,
)

from . import NOISE_FLOOR, FrameStream, feed, make_baseline, make_config, make_detector

ARRIVAL_MOVE = 95
"""Move elevation of somebody walking in: raw 100, the top of the scale."""

THROUGH_WALL_MOVE = 35
"""Move elevation of attenuated activity: raw ~40, well clear of the floor."""

BAND = (3, 4, 5)
"""A three-gate run, wide enough to pass the spatial-coherence test."""

FAR_BAND = (6, 7, 8)
"""The same shaped run, but at the far end of the band."""

QUIET_SIGMA = 0.5
"""Idle noise small enough that a quiet gate stays quiet for a whole hold."""

WARMUP_S = 10.0
TEACH_S = 3.0
SETTLE_S = 40.0
"""Long enough after the teaching burst for occupancy to release again."""


ARRIVAL_STAGES = (
    "quantile_floor",
    "tail_spread",
    "move_ceiling",
    "run_score",
    "lone_gate_suppression",
    "arrival",
    "score_hold",
)
"""The scoring core, the move ceiling, and the arrival gate measured against it."""


def _config(**overrides: object) -> DetectorConfig:
    """A config whose only live entry rule is the arrival gate."""
    return make_config(stages=ARRIVAL_STAGES, **overrides)


def _elevate(elevation: int, band: tuple[int, ...] = BAND) -> dict[int, int]:
    """Raise every gate of ``band`` by ``elevation``."""
    return dict.fromkeys(band, elevation)


def _stream() -> FrameStream:
    """A frame source whose idle gates settle within a close window."""
    return FrameStream(sigma=QUIET_SIGMA)


def _detections(episodes: list[Episode]) -> list[Episode]:
    """Keep only the detection-scope rows."""
    return [episode for episode in episodes if episode.scope == SCOPE_DETECTION]


def _closed_episodes(outputs: list[DetectorOutput]) -> list[Episode]:
    """Every episode closed across a run of outputs."""
    return [episode for output in outputs for episode in output.episodes]


def _warm_detector(stream: FrameStream, config: DetectorConfig) -> Detector:
    """A detector with a ready baseline that has never seen strong motion."""
    detector = make_detector(config)
    feed(detector, stream.burst(WARMUP_S))
    return detector


def _learned_detector(stream: FrameStream, config: DetectorConfig) -> Detector:
    """A warm detector that has been shown one arrival, and is vacant again."""
    detector = _warm_detector(stream, config)
    feed(detector, stream.burst(TEACH_S, move=_elevate(ARRIVAL_MOVE)))
    feed(detector, stream.burst(SETTLE_S))
    assert not detector.occupied
    return detector


def test_the_move_ceiling_reaches_arrival_scale_motion() -> None:
    """Teaching burst included, the exemplars sit either side of the threshold."""
    stream = _stream()
    detector = _learned_detector(stream, _config())

    threshold = detector.config.arrival_frac * detector.baseline.move_ceiling

    assert detector.baseline.move_ceiling == MAX_GATE_ENERGY
    assert NOISE_FLOOR + THROUGH_WALL_MOVE < threshold
    assert NOISE_FLOOR + ARRIVAL_MOVE >= threshold


def test_arrival_scale_motion_enters() -> None:
    """A second walk-in is admitted, within the frames the rule asks for."""
    stream = _stream()
    config = _config()
    detector = _learned_detector(stream, config)

    outputs = feed(detector, stream.burst(5.0, move=_elevate(ARRIVAL_MOVE)))

    entered = next(index for index, output in enumerate(outputs) if output.occupied)
    assert entered < config.arrival_min_frames


def test_sub_arrival_activity_is_suppressed_and_recorded() -> None:
    """Activity that never reaches arrival scale stays out, and says why."""
    stream = _stream()
    detector = _learned_detector(stream, _config())

    outputs = feed(detector, stream.burst(12.0, move=_elevate(THROUGH_WALL_MOVE)))

    assert max(output.score for output in outputs) >= detector.config.enter_score
    assert not any(output.occupied for output in outputs)

    quiet = feed(detector, stream.burst(SETTLE_S))
    detections = _detections(_closed_episodes(outputs + quiet))
    assert detections
    assert all(episode.result == RESULT_REJECTED_ARRIVAL for episode in detections)


def test_an_unlearned_ceiling_admits_the_same_candidate() -> None:
    """A sensor that has never seen strong motion is never tightened by the rule."""
    stream = _stream()
    detector = _warm_detector(stream, _config())

    outputs = feed(detector, stream.burst(12.0, move=_elevate(THROUGH_WALL_MOVE)))

    assert outputs[-1].occupied


def test_a_fresh_baseline_has_no_ceiling() -> None:
    """Nothing has been observed, so there is nothing to measure an arrival against."""
    baseline = make_baseline(_config())

    assert not baseline.move_ceiling_learned
    assert baseline.move_ceiling == 0.0


def test_arrival_scale_motion_must_last_the_required_frames() -> None:
    """Reaching the threshold in too few frames does not admit an entry."""
    stream = _stream()
    detector = _learned_detector(stream, _config(arrival_min_frames=50))

    outputs = feed(detector, stream.burst(2.0, move=_elevate(ARRIVAL_MOVE)))

    assert max(output.score for output in outputs) >= detector.config.enter_score
    assert not any(output.occupied for output in outputs)


def test_zero_arrival_frac_disables_the_rule() -> None:
    """The same sub-arrival candidate enters once the rule is turned off."""
    stream = _stream()
    detector = _learned_detector(stream, _config(arrival_frac=0.0))

    outputs = feed(detector, stream.burst(12.0, move=_elevate(THROUGH_WALL_MOVE)))

    assert outputs[-1].occupied


def test_occupancy_survives_motion_decaying_below_arrival_scale() -> None:
    """Exit stays score-driven: entry gating never releases an occupancy."""
    stream = _stream()
    detector = _learned_detector(stream, _config())

    entry = feed(detector, stream.burst(5.0, move=_elevate(ARRIVAL_MOVE)))
    assert entry[-1].occupied

    decayed = feed(detector, stream.burst(40.0, move=_elevate(THROUGH_WALL_MOVE)))

    assert all(output.occupied for output in decayed)


def test_leading_gate_reports_the_nearest_elevated_gate() -> None:
    """Activity confined to the far gates leads there, and says so on its episodes."""
    stream = _stream()
    detector = _learned_detector(stream, _config())

    outputs = feed(
        detector, stream.burst(12.0, move=_elevate(THROUGH_WALL_MOVE, FAR_BAND))
    )
    assert outputs[-1].leading_gate == FAR_BAND[0]

    quiet = feed(detector, stream.burst(SETTLE_S))
    detections = _detections(_closed_episodes(outputs + quiet))
    assert detections
    assert all(episode.leading_gate == FAR_BAND[0] for episode in detections)

    near = feed(detector, stream.burst(2.0, move=_elevate(ARRIVAL_MOVE)))
    assert near[-1].leading_gate == BAND[0]


def test_state_round_trip_preserves_the_move_ceiling() -> None:
    """A restored sensor keeps gating on what it had already learned."""
    stream = _stream()
    model = make_baseline(_config())
    for frame in [
        *stream.burst(WARMUP_S),
        *stream.burst(TEACH_S, move=_elevate(ARRIVAL_MOVE)),
    ]:
        model.add_frame(frame)

    payload = json.loads(json.dumps(model.to_dict()))
    assert payload["version"] == SCHEMA_VERSION
    restored = Baseline.from_dict(payload, _config())

    assert model.move_ceiling_learned
    assert restored.move_ceiling_learned
    assert restored.move_ceiling == model.move_ceiling


def test_state_without_a_ceiling_loads_with_it_unlearned() -> None:
    """Persisted state from before the ceiling existed relearns it, keeping the rest."""
    stream = _stream()
    model = make_baseline(_config())
    for frame in stream.burst(25.0):
        model.add_frame(frame)

    payload = model.to_dict()
    del payload["move_ceiling"]
    payload["version"] = SCHEMA_VERSION - 1

    restored = Baseline.from_dict(payload, _config())

    assert not restored.move_ceiling_learned
    assert restored.bucket_count == model.bucket_count
    assert restored.floor(0) == model.floor(0)
