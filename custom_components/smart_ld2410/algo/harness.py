"""Replay a recorded fixture through a detector and score what came out.

The same entry point serves the regression suite and the experiments under
``docs/research/experiments``: hand it a recording, a sensor, and either a
:class:`~.types.DetectorConfig` or a list of stage names, and it returns the
occupancy timeline that configuration produces. Scoring a timeline against
ground-truth spans is the second half, so an experiment measures a candidate
pipeline against the shipped one without reimplementing either.

Recordings are opened immutable: they are evidence, and even a reader would
otherwise leave WAL sidecars beside them. Nothing here reads a clock, so a
given recording and configuration always produce the same timeline.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from contextlib import closing
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .detector import Detector
from .types import DetectorConfig, DetectorOutput, Frame


@dataclass(frozen=True, slots=True)
class OccupancyEvent:
    """One occupancy transition, carrying what the integration would record."""

    ts: float
    occupied: bool
    confidence: float
    score: float
    active_gates: tuple[int, ...]

    @property
    def kind(self) -> str:
        """``occupied`` or ``vacant``, as the events table spells it."""
        return "occupied" if self.occupied else "vacant"


@dataclass(frozen=True, slots=True)
class Span:
    """A ground-truth interval the room was occupied."""

    start: float
    end: float
    name: str = ""


@dataclass(frozen=True, slots=True)
class TimelineScore:
    """How a timeline compares against the spans it should have reproduced."""

    entries: int
    false_entries: int
    spans_detected: int
    spans_missed: int
    entry_latency_s: tuple[float, ...]
    overlap_s: float
    false_s: float
    missed_s: float


def sensor_ids(db_path: Path | str) -> tuple[str, ...]:
    """Every sensor with frames in a recording, ascending."""
    with closing(_connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT DISTINCT sensor_id FROM frames ORDER BY sensor_id"
        ).fetchall()
    return tuple(row[0] for row in rows)


def frames(
    db_path: Path | str,
    sensor_id: str,
    *,
    start_utc: float = 0.0,
    end_utc: float = float("inf"),
) -> Iterator[Frame]:
    """Every recorded frame of one sensor, in timestamp order."""
    with closing(_connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT ts, ts_mono, move, still, distance_cm, device_occ FROM frames "
            "WHERE sensor_id = ? AND ts >= ? AND ts < ? ORDER BY ts",
            (sensor_id, start_utc, end_utc),
        ).fetchall()
    for ts, ts_mono, move, still, distance_cm, device_occ in rows:
        yield Frame(
            ts_utc=ts,
            ts_mono=ts_mono,
            move_gates=tuple(move),
            still_gates=tuple(still),
            target_distance_cm=distance_cm,
            device_occupancy=bool(device_occ),
        )


def run(
    db_path: Path | str,
    sensor_id: str,
    *,
    config: DetectorConfig | None = None,
    stages: Sequence[str] | None = None,
    start_utc: float = 0.0,
    end_utc: float = float("inf"),
) -> Iterator[tuple[Frame, DetectorOutput]]:
    """Replay a recording, yielding every frame with the decision it produced."""
    detector = Detector(build_config(config, stages))
    for frame in frames(db_path, sensor_id, start_utc=start_utc, end_utc=end_utc):
        yield frame, detector.process(frame)


def replay(
    db_path: Path | str,
    sensor_id: str,
    *,
    config: DetectorConfig | None = None,
    stages: Sequence[str] | None = None,
    start_utc: float = 0.0,
    end_utc: float = float("inf"),
) -> tuple[OccupancyEvent, ...]:
    """Return the occupancy timeline a configuration produces on a recording.

    The timeline starts from vacant, exactly as the integration's own state
    does, so the cold-start passthrough phase shows up here the way it shows up
    live.
    """
    timeline: list[OccupancyEvent] = []
    occupied = False
    for frame, output in run(
        db_path,
        sensor_id,
        config=config,
        stages=stages,
        start_utc=start_utc,
        end_utc=end_utc,
    ):
        if output.occupied == occupied:
            continue
        occupied = output.occupied
        timeline.append(
            OccupancyEvent(
                ts=frame.ts_utc,
                occupied=occupied,
                confidence=output.confidence,
                score=output.score,
                active_gates=output.active_gates,
            )
        )
    return tuple(timeline)


def build_config(
    config: DetectorConfig | None, stages: Sequence[str] | None
) -> DetectorConfig:
    """Resolve a config and an optional stage list into one config."""
    resolved = config or DetectorConfig()
    if stages is None:
        return resolved
    return replace(resolved, stages=tuple(stages))


def timeline_rows(timeline: Iterable[OccupancyEvent]) -> list[dict[str, Any]]:
    """Render a timeline as JSON-safe rows."""
    return [
        {
            "ts": event.ts,
            "kind": event.kind,
            "confidence": event.confidence,
            "score": event.score,
            "active_gates": list(event.active_gates),
        }
        for event in timeline
    ]


def label_spans(
    db_path: Path | str, *, room: str | None = None, person: str | None = None
) -> tuple[Span, ...]:
    """Ground-truth spans from a recording's ``labels`` table, if it has one."""
    with closing(_connect(db_path)) as connection:
        if not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'labels'"
        ).fetchone():
            return ()
        rows = connection.execute(
            "SELECT person, room, ts_start, ts_end FROM labels ORDER BY ts_start"
        ).fetchall()
    return tuple(
        Span(start=ts_start, end=ts_end, name=f"{label_person}/{label_room}")
        for label_person, label_room, ts_start, ts_end in rows
        if (room is None or label_room == room)
        and (person is None or label_person == person)
    )


def score_timeline(
    timeline: Sequence[OccupancyEvent],
    spans: Sequence[Span],
    *,
    end_utc: float | None = None,
) -> TimelineScore:
    """Compare an occupancy timeline against the spans it should reproduce.

    An occupancy still open at the end of the timeline runs to ``end_utc``,
    which defaults to the later of the last transition and the last span.
    """
    horizon = end_utc
    if horizon is None:
        horizon = max(
            (event.ts for event in timeline),
            default=0.0,
        )
        horizon = max(horizon, max((span.end for span in spans), default=0.0))
    runs = _occupied_runs(timeline, horizon)
    entries = [event.ts for event in timeline if event.occupied]

    latencies: list[float] = []
    detected = 0
    for span in spans:
        inside = [ts for ts in entries if span.start <= ts <= span.end]
        if inside:
            detected += 1
            latencies.append(inside[0] - span.start)

    occupied_s = sum(end - start for start, end in runs)
    span_s = sum(span.end - span.start for span in spans)
    overlap_s = sum(
        _overlap(run, (span.start, span.end)) for run in runs for span in spans
    )
    return TimelineScore(
        entries=len(entries),
        false_entries=sum(
            1
            for ts in entries
            if not any(span.start <= ts <= span.end for span in spans)
        ),
        spans_detected=detected,
        spans_missed=len(spans) - detected,
        entry_latency_s=tuple(latencies),
        overlap_s=overlap_s,
        false_s=occupied_s - overlap_s,
        missed_s=span_s - overlap_s,
    )


def _occupied_runs(
    timeline: Sequence[OccupancyEvent], end_utc: float
) -> list[tuple[float, float]]:
    runs: list[tuple[float, float]] = []
    start: float | None = None
    for event in timeline:
        if event.occupied and start is None:
            start = event.ts
        elif not event.occupied and start is not None:
            runs.append((start, event.ts))
            start = None
    if start is not None:
        runs.append((start, max(start, end_utc)))
    return runs


def _overlap(left: tuple[float, float], right: tuple[float, float]) -> float:
    return max(0.0, min(left[1], right[1]) - max(left[0], right[0]))


def _connect(db_path: Path | str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
