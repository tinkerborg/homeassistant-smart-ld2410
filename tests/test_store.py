"""Tests for the SQLite frame store (writer thread, iter_frames, retention)."""

from __future__ import annotations

import logging
import queue
import sqlite3
from pathlib import Path

import pytest

from custom_components.smart_ld2410.algo.types import Frame
from custom_components.smart_ld2410.store import FrameStore


def _make_frame(ts_utc: float, ts_mono: float, *, seed: int = 0) -> Frame:
    """Build a Frame with deterministic, distinguishable gate values."""
    return Frame(
        ts_utc=ts_utc,
        ts_mono=ts_mono,
        move_gates=tuple((seed + i) % 101 for i in range(9)),
        still_gates=tuple((seed + 10 + i) % 101 for i in range(9)),
        target_distance_cm=100 + seed,
        device_occupancy=bool(seed % 2),
    )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "smart_ld2410" / "frames.db"


def test_fresh_store_has_incremental_auto_vacuum(db_path: Path) -> None:
    """auto_vacuum must be set before WAL mode, or the pragma silently no-ops.

    WAL mode materializes the database header on first use; once that has
    happened, ``PRAGMA auto_vacuum`` can no longer change the mode. Reading
    it back after store creation is the only reliable way to catch a
    regression in pragma ordering.
    """
    FrameStore(db_path)  # __init__ creates the schema synchronously.

    conn = sqlite3.connect(db_path)
    try:
        (auto_vacuum,) = conn.execute("PRAGMA auto_vacuum").fetchone()
    finally:
        conn.close()

    assert auto_vacuum == 2  # 2 == INCREMENTAL


def test_writer_round_trip(db_path: Path) -> None:
    """Frames written through the writer thread come back byte-identical."""
    store = FrameStore(db_path)
    store.start()
    try:
        frames = [_make_frame(1000.0 + i, 50.0 + i, seed=i) for i in range(25)]
        for frame in frames:
            store.enqueue_frame("AA:BB:CC:DD:EE:FF", frame)
    finally:
        store.stop()

    read_back = list(store.iter_frames("AA:BB:CC:DD:EE:FF", 0.0, 1_000_000.0))
    assert read_back == frames


def test_iter_frames_filters_by_sensor_and_range(db_path: Path) -> None:
    """iter_frames only returns the requested sensor and [start, end) window."""
    store = FrameStore(db_path)
    store.start()
    try:
        for i in range(10):
            store.enqueue_frame("sensor-a", _make_frame(1000.0 + i, i, seed=i))
        for i in range(5):
            store.enqueue_frame("sensor-b", _make_frame(1000.0 + i, i, seed=100 + i))
    finally:
        store.stop()

    all_a = list(store.iter_frames("sensor-a", 0.0, 1_000_000.0))
    assert len(all_a) == 10
    assert all(f.target_distance_cm < 200 for f in all_a)

    windowed = list(store.iter_frames("sensor-a", 1003.0, 1007.0))
    assert [f.ts_utc for f in windowed] == [1003.0, 1004.0, 1005.0, 1006.0]

    only_b = list(store.iter_frames("sensor-b", 0.0, 1_000_000.0))
    assert len(only_b) == 5
    assert all(f.target_distance_cm >= 200 for f in only_b)


def test_iter_frames_orders_by_timestamp(db_path: Path) -> None:
    """Rows come back in ts_utc order regardless of insertion order."""
    store = FrameStore(db_path)
    store.start()
    try:
        for ts in (30.0, 10.0, 20.0):
            store.enqueue_frame("s", _make_frame(ts, ts, seed=int(ts)))
    finally:
        store.stop()

    result = list(store.iter_frames("s", 0.0, 1000.0))
    assert [f.ts_utc for f in result] == [10.0, 20.0, 30.0]


def test_stop_is_idempotent_and_safe_without_start(db_path: Path) -> None:
    """stop() before start(), and double-stop(), don't raise."""
    store = FrameStore(db_path)
    store.stop()  # never started

    store.start()
    store.enqueue_frame("s", _make_frame(1.0, 1.0))
    store.stop()
    store.stop()  # already stopped

    assert len(list(store.iter_frames("s", 0.0, 1000.0))) == 1


def test_prune_deletes_only_old_rows(db_path: Path) -> None:
    """Retention prune removes rows older than the cutoff and nothing else."""
    store = FrameStore(db_path, retention_days=30)
    store.start()
    try:
        now_utc = 100 * 86400.0  # day 100, arbitrary epoch-ish base
        old_frames = [
            _make_frame(now_utc - 40 * 86400.0 + i, i, seed=i) for i in range(3)
        ]
        recent_frames = [
            _make_frame(now_utc - 5 * 86400.0 + i, i, seed=50 + i) for i in range(4)
        ]
        for frame in old_frames + recent_frames:
            store.enqueue_frame("s", frame)
    finally:
        store.stop()

    deleted = store.prune(now_utc=now_utc)
    assert deleted == len(old_frames)

    remaining = list(store.iter_frames("s", 0.0, now_utc + 1.0))
    assert len(remaining) == len(recent_frames)
    assert {f.target_distance_cm for f in remaining} == {
        f.target_distance_cm for f in recent_frames
    }


def test_prune_uses_default_retention_when_unset(db_path: Path) -> None:
    """A prune call can override retention_days per-call without mutating it."""
    store = FrameStore(db_path, retention_days=30)
    store.start()
    try:
        now_utc = 100 * 86400.0
        store.enqueue_frame("s", _make_frame(now_utc - 10 * 86400.0, 0.0, seed=1))
    finally:
        store.stop()

    # Default 30-day retention keeps a 10-day-old row.
    assert store.prune(now_utc=now_utc) == 0
    assert len(list(store.iter_frames("s", 0.0, now_utc + 1.0))) == 1

    # An explicit shorter override deletes it.
    assert store.prune(now_utc=now_utc, retention_days=5) == 1
    assert len(list(store.iter_frames("s", 0.0, now_utc + 1.0))) == 0


def test_prune_routes_through_writer_when_running(db_path: Path) -> None:
    """prune() while the writer is alive is serialized through it, not a racing connection."""
    store = FrameStore(db_path, retention_days=30)
    store.start()
    try:
        now_utc = 100 * 86400.0
        old_frames = [
            _make_frame(now_utc - 40 * 86400.0 + i, i, seed=i) for i in range(3)
        ]
        recent_frames = [
            _make_frame(now_utc - 5 * 86400.0 + i, i, seed=50 + i) for i in range(4)
        ]
        for frame in old_frames + recent_frames:
            store.enqueue_frame("s", frame)

        # The prune request lands on the same queue behind the frame writes
        # above, and the writer flushes any pending batch before running the
        # DELETE, so this is deterministic despite the writer thread running.
        deleted = store.prune(now_utc=now_utc)
        assert deleted == len(old_frames)

        remaining = list(store.iter_frames("s", 0.0, now_utc + 1.0))
        assert len(remaining) == len(recent_frames)
    finally:
        store.stop()


def test_enqueue_frame_drops_without_blocking_when_queue_full(
    db_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """enqueue_frame never blocks; once the queue is full it drops and logs a warning."""
    store = FrameStore(db_path)
    # Shrink the queue and never start a writer, so nothing ever drains it.
    store._queue = queue.Queue(maxsize=2)  # noqa: SLF001

    for i in range(2):
        store.enqueue_frame("s", _make_frame(float(i), float(i)))

    with caplog.at_level(logging.WARNING):
        store.enqueue_frame("s", _make_frame(2.0, 2.0))

    assert store._dropped_count == 1  # noqa: SLF001
    assert "dropped" in caplog.text.lower()


def test_writer_thread_death_logs_critical_once(
    db_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An unexpected writer-thread crash is logged loudly instead of dying silently."""
    store = FrameStore(db_path)

    def _boom(self: FrameStore) -> sqlite3.Connection:
        raise RuntimeError("simulated writer connect failure")

    monkeypatch.setattr(FrameStore, "_connect_writer", _boom)

    with caplog.at_level(logging.CRITICAL):
        store.start()
        thread = store._thread  # noqa: SLF001
        assert thread is not None
        thread.join(timeout=5.0)

    assert not thread.is_alive()
    critical_records = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert len(critical_records) == 1
