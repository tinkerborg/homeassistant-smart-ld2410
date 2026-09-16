"""Every fixture's occupancy timeline, against the checked-in baseline.

A stage list is only measurable against a known one, so the timeline each
recording produces at default tuning is recorded under
``tests/fixtures/golden``. Regenerate it with
``uv run python tools/write_golden_timelines.py`` when a behaviour change is
the point of the change, and read the diff as the change's evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.smart_ld2410.algo.types import ALL_STAGES
from custom_components.smart_ld2410.algo.harness import (
    replay,
    sensor_ids,
    timeline_rows,
)

RECORDINGS = Path(__file__).parent.parent / "fixtures" / "recordings"
GOLDEN = Path(__file__).parent.parent / "fixtures" / "golden"


def _cases() -> list[tuple[Path, str]]:
    """Every (recording, sensor) pair in the corpus."""
    return [
        (recording, sensor_id)
        for recording in sorted(RECORDINGS.glob("*.db"))
        for sensor_id in sensor_ids(recording)
    ]


def _case_id(case: tuple[Path, str]) -> str:
    """Name a case after its recording and sensor."""
    recording, sensor_id = case
    return f"{recording.stem}-{sensor_id}"


@pytest.mark.parametrize("case", _cases(), ids=_case_id)
def test_the_timeline_matches_the_recorded_baseline(case: tuple[Path, str]) -> None:
    """The shipped pipeline reproduces the corpus timeline exactly."""
    recording, sensor_id = case
    golden = json.loads((GOLDEN / f"{recording.stem}.json").read_text())

    assert timeline_rows(replay(recording, sensor_id, stages=ALL_STAGES)) == golden[sensor_id]
