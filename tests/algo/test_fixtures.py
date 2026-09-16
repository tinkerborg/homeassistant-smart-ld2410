"""Replay of the recorded fixtures, against their README ground truth.

These are the corpus checks spec 24 §5 is written against, run over the full
stage list: the leading edge must refuse a room full of through-wall activity
without costing the genuine visit next door its entry, and retention must
carry a motionless occupant the device has absorbed.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from custom_components.smart_ld2410.algo.detector import Detector
from custom_components.smart_ld2410.algo.types import (
    ALL_STAGES,
    DetectorConfig,
    Frame,
)

RECORDINGS = Path(__file__).parent.parent / "fixtures" / "recordings"
LOCAL = ZoneInfo("America/New_York")
RECORDED_DAY = (2026, 9, 11)

FULL = DetectorConfig(stages=ALL_STAGES)
"""Every stage the detector offers, which is what the corpus is judged against."""

BATHROOM = ("bathroom-visit-2204-d06e.db", "D0:6E:81:D2:5D:A6")
THROUGH_WALL = ("throughwall-morning-d06e.db", "D0:6E:81:D2:5D:A6")
LIVING_ROOM = ("livingroom-reset-seated-fd68.db", "FD:68:3B:41:6E:FF")


def _at(hour: int, minute: int, second: int = 0) -> float:
    """Local recording time as a unix timestamp."""
    return datetime(*RECORDED_DAY, hour, minute, second, tzinfo=LOCAL).timestamp()


def _local(ts: float) -> str:
    """A timestamp as the README writes it, for assertion messages."""
    return datetime.fromtimestamp(ts, UTC).astimezone(LOCAL).strftime("%H:%M:%S")


def _frames(recording: tuple[str, str]) -> list[Frame]:
    """Every recorded frame of one fixture, in timestamp order."""
    name, sensor_id = recording
    # Immutable, not merely read-only: the fixtures are evidence, and even a
    # reader leaves WAL sidecars beside them otherwise.
    connection = sqlite3.connect(
        f"file:{RECORDINGS / name}?mode=ro&immutable=1", uri=True
    )
    try:
        rows = connection.execute(
            "SELECT ts, ts_mono, move, still, distance_cm, device_occ "
            "FROM frames WHERE sensor_id = ? ORDER BY ts",
            (sensor_id,),
        ).fetchall()
    finally:
        connection.close()
    return [
        Frame(
            ts_utc=ts,
            ts_mono=ts_mono,
            move_gates=tuple(move),
            still_gates=tuple(still),
            target_distance_cm=distance_cm,
            device_occupancy=bool(device_occ),
        )
        for ts, ts_mono, move, still, distance_cm, device_occ in rows
    ]


def _timeline(
    recording: tuple[str, str], config: DetectorConfig | None = None
) -> list[tuple[float, bool]]:
    """Occupancy transitions once the baseline is learned: ``(ts, occupied)``."""
    detector = Detector(config or FULL)
    transitions: list[tuple[float, bool]] = []
    previous: bool | None = None
    for frame in _frames(recording):
        output = detector.process(frame)
        if not output.baseline_ready:
            continue
        # The cold-start passthrough hands over whatever bit the device itself
        # was reporting; the detector's own timeline starts where that clears.
        if previous is None and output.occupied:
            continue
        if previous is not None and output.occupied != previous:
            transitions.append((frame.ts_utc, output.occupied))
        previous = output.occupied
    return transitions


def test_through_wall_morning_never_enters() -> None:
    """An hour of kitchen activity beyond the shared wall is not a bathroom visit."""
    entries = [ts for ts, occupied in _timeline(THROUGH_WALL) if occupied]

    assert entries == [], [_local(ts) for ts in entries]


def test_through_wall_morning_entered_before_the_leading_edge() -> None:
    """The same recording is what the rule exists for: without it, false entries."""
    without = DetectorConfig(
        stages=ALL_STAGES, lead_gate_max=-1, retention_off=0.0
    )
    entries = [ts for ts, occupied in _timeline(THROUGH_WALL, without) if occupied]

    assert entries


def test_the_bathroom_visit_is_admitted_at_its_walk_in() -> None:
    """The genuine visit enters when the user arrived, not on its precursor."""
    timeline = _timeline(BATHROOM)
    entries = [ts for ts, occupied in timeline if occupied]

    assert len(entries) == 1
    assert _at(22, 4, 0) <= entries[0] <= _at(22, 4, 15), _local(entries[0])


def test_the_bathroom_visit_releases_at_its_departure() -> None:
    """Ownership is armed by the walk back to the door, so release is prompt."""
    timeline = _timeline(BATHROOM)
    releases = [ts for ts, occupied in timeline if not occupied]

    assert len(releases) == 1
    departure = _at(22, 6, 43)
    assert departure <= releases[0] <= departure + FULL.hold_s, _local(
        releases[0]
    )


def test_the_seated_occupant_is_never_released() -> None:
    """A fully still minute of a real visit must not read as an empty room."""
    timeline = _timeline(LIVING_ROOM)
    entries = [ts for ts, occupied in timeline if occupied]

    assert len(entries) == 1
    assert _at(21, 39, 40) <= entries[0] <= _at(21, 40, 40), _local(entries[0])
    assert [ts for ts, occupied in timeline if not occupied] == []


def test_the_empty_living_room_stays_empty() -> None:
    """The vacant window of the same recording, cat and all, never enters."""
    timeline = _timeline(LIVING_ROOM)

    assert not [
        ts for ts, occupied in timeline if occupied and ts < _at(21, 39, 40)
    ]
