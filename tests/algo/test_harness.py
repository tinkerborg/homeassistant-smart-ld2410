"""Tests for the replay harness and its scorer."""

from __future__ import annotations

from pathlib import Path

from custom_components.smart_ld2410.algo.harness import (
    OccupancyEvent,
    Span,
    build_config,
    label_spans,
    replay,
    score_timeline,
    sensor_ids,
)
from custom_components.smart_ld2410.algo.types import DEFAULT_STAGES, DetectorConfig

RECORDINGS = Path(__file__).parent.parent / "fixtures" / "recordings"
WALK = RECORDINGS / "labeled-walk-0915.db"
BATHROOM = RECORDINGS / "bathroom-visit-2204-d06e.db"
BATHROOM_SENSOR = "D0:6E:81:D2:5D:A6"


def _event(ts: float, *, occupied: bool) -> OccupancyEvent:
    """A timeline entry with the payload fields at arbitrary values."""
    return OccupancyEvent(
        ts=ts, occupied=occupied, confidence=0.9, score=5.0, active_gates=(2, 3)
    )


def test_a_multi_sensor_recording_lists_all_of_its_sensors() -> None:
    """Five sensors in one file are five replayable streams."""
    assert len(sensor_ids(WALK)) == 5


def test_label_spans_read_the_ground_truth_table() -> None:
    """The labels table is ground truth the scorer can be pointed at."""
    spans = label_spans(WALK, room="bathroom", person="rob")

    assert len(spans) == 2
    assert all(span.name == "rob/bathroom" for span in spans)
    assert all(span.end > span.start for span in spans)


def test_a_recording_without_labels_yields_no_spans() -> None:
    """Most fixtures carry their ground truth in the README, not in a table."""
    assert label_spans(BATHROOM) == ()


def test_a_stage_list_overrides_the_config_it_is_given() -> None:
    """An experiment may vary the stages while keeping every other knob."""
    config = build_config(DetectorConfig(k=6.0), ("quantile_baseline", "score_hold"))

    assert config.k == 6.0
    assert config.stages == ("quantile_baseline", "score_hold")
    assert build_config(None, None).stages == DEFAULT_STAGES


def test_the_replayed_visit_is_one_occupied_span() -> None:
    """The harness reports the transitions, in order, with their payload."""
    timeline = replay(BATHROOM, BATHROOM_SENSOR)

    assert [event.kind for event in timeline] == [
        "occupied",
        "vacant",
        "occupied",
        "vacant",
    ]
    assert all(event.confidence > 0.0 for event in timeline)


def test_the_scorer_counts_detections_misses_and_wasted_time() -> None:
    """One visit found late, one entry nobody asked for, one visit missed."""
    timeline = (
        _event(100.0, occupied=True),
        _event(160.0, occupied=False),
        _event(400.0, occupied=True),
        _event(410.0, occupied=False),
    )
    spans = (Span(90.0, 200.0, "visit"), Span(600.0, 700.0, "missed"))

    score = score_timeline(timeline, spans)

    assert score.entries == 2
    assert score.false_entries == 1
    assert score.spans_detected == 1
    assert score.spans_missed == 1
    assert score.entry_latency_s == (10.0,)
    assert score.overlap_s == 60.0
    assert score.false_s == 10.0
    assert score.missed_s == 150.0


def test_an_occupancy_still_open_at_the_end_is_scored_to_the_horizon() -> None:
    """A timeline that never releases has not been occupied for ever."""
    timeline = (_event(100.0, occupied=True),)
    spans = (Span(100.0, 200.0, "visit"),)

    score = score_timeline(timeline, spans, end_utc=300.0)

    assert score.overlap_s == 100.0
    assert score.false_s == 100.0
    assert score.missed_s == 0.0
