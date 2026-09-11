"""Tests for the SQLite frame store (writer thread, iter_frames, rollup, retention)."""

from __future__ import annotations

import logging
import queue
import sqlite3
from pathlib import Path

import pytest

from custom_components.smart_ld2410.algo.types import SCOPE_DETECTION, Episode, Frame
from custom_components.smart_ld2410.store import CHAN_MOVE, SCHEMA_VERSION, FrameStore


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


def test_fresh_store_creates_contract_tables(db_path: Path) -> None:
    """frames/minute_summary/buckets/episodes/events all exist per the interface contract."""
    FrameStore(db_path)

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        (version,) = conn.execute("SELECT version FROM schema_info").fetchone()
    finally:
        conn.close()

    assert {"frames", "minute_summary", "buckets", "episodes", "events", "sensors"} <= tables
    assert version == SCHEMA_VERSION


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
    """Rows come back in ts order regardless of insertion order."""
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


def test_prune_deletes_only_old_raw_rows(db_path: Path) -> None:
    """Retention prune removes raw frames older than the cutoff and nothing else."""
    store = FrameStore(db_path, raw_retention_days=30)
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


def test_prune_keeps_summaries_of_pruned_raw_frames(db_path: Path) -> None:
    """Rolling up before pruning means summaries outlive the raw frames they came from."""
    store = FrameStore(db_path, raw_retention_days=7, summary_retention_days=365)
    store.start()
    try:
        now_utc = 100 * 86400.0
        old_ts = now_utc - 40 * 86400.0
        old_minute = int(old_ts // 60)
        # A handful of frames within the same complete minute, well before now.
        for i in range(5):
            store.enqueue_frame("s", _make_frame(old_minute * 60.0 + i, i, seed=i))
    finally:
        store.stop()

    deleted = store.prune(now_utc=now_utc)
    assert deleted == 5

    assert list(store.iter_frames("s", 0.0, now_utc + 1.0)) == []

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT gate, chan, q50, q90, qmax, n FROM minute_summary "
            "WHERE sensor_id = ? AND minute = ?",
            ("s", old_minute),
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 9 * 2  # 9 gates x 2 channels


def test_prune_uses_default_retention_when_unset(db_path: Path) -> None:
    """A prune call can override retention per-call without mutating the store's defaults."""
    store = FrameStore(db_path, raw_retention_days=30)
    store.start()
    try:
        now_utc = 100 * 86400.0
        store.enqueue_frame("s", _make_frame(now_utc - 10 * 86400.0, 0.0, seed=1))
    finally:
        store.stop()

    # Default 30-day raw retention keeps a 10-day-old row.
    assert store.prune(now_utc=now_utc) == 0
    assert len(list(store.iter_frames("s", 0.0, now_utc + 1.0))) == 1

    # An explicit shorter override deletes it.
    assert store.prune(now_utc=now_utc, raw_retention_days=5) == 1
    assert len(list(store.iter_frames("s", 0.0, now_utc + 1.0))) == 0


def test_prune_routes_through_writer_when_running(db_path: Path) -> None:
    """prune() while the writer is alive is serialized through it, not a racing connection."""
    store = FrameStore(db_path, raw_retention_days=30)
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
        # maintenance, so this is deterministic despite the writer thread running.
        deleted = store.prune(now_utc=now_utc)
        assert deleted == len(old_frames)

        remaining = list(store.iter_frames("s", 0.0, now_utc + 1.0))
        assert len(remaining) == len(recent_frames)
    finally:
        store.stop()


def test_summary_retention_deletes_old_summaries(db_path: Path) -> None:
    """minute_summary rows older than summary_retention_days are pruned; recent ones aren't."""
    store = FrameStore(db_path)
    now_utc = 500 * 86400.0
    old_minute = int((now_utc - 400 * 86400.0) // 60)
    recent_minute = int((now_utc - 10 * 86400.0) // 60)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO minute_summary (sensor_id, minute, gate, chan, q50, q90, qmax, n) "
            "VALUES ('s', ?, 0, 0, 1.0, 2.0, 3.0, 1)",
            (old_minute,),
        )
        conn.execute(
            "INSERT INTO minute_summary (sensor_id, minute, gate, chan, q50, q90, qmax, n) "
            "VALUES ('s', ?, 0, 0, 1.0, 2.0, 3.0, 1)",
            (recent_minute,),
        )
        conn.commit()
    finally:
        conn.close()

    store.prune(now_utc=now_utc, summary_retention_days=365)

    conn = sqlite3.connect(db_path)
    try:
        remaining_minutes = {
            row[0] for row in conn.execute("SELECT minute FROM minute_summary WHERE sensor_id='s'")
        }
    finally:
        conn.close()
    assert remaining_minutes == {recent_minute}


def test_rollup_computes_correct_quantiles(db_path: Path) -> None:
    """Hand-checked q50/q90/qmax/n for one gate/channel of one minute."""
    store = FrameStore(db_path)
    store.start()
    try:
        # 5 frames in the same minute; gate 0 move values are 10, 20, 30, 40, 50.
        minute = 1000
        base_ts = minute * 60.0
        for i, val in enumerate((10, 20, 30, 40, 50)):
            frame = Frame(
                ts_utc=base_ts + i,
                ts_mono=float(i),
                move_gates=(val, 0, 0, 0, 0, 0, 0, 0, 0),
                still_gates=(0, 0, 0, 0, 0, 0, 0, 0, 0),
                target_distance_cm=100,
                device_occupancy=False,
            )
            store.enqueue_frame("s", frame)
    finally:
        store.stop()

    # Force rollup of this now-complete minute without pruning any frames.
    now_utc = base_ts + 600.0
    store.prune(now_utc=now_utc, raw_retention_days=3650, summary_retention_days=3650)

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT q50, q90, qmax, n FROM minute_summary "
            "WHERE sensor_id = 's' AND minute = ? AND gate = 0 AND chan = ?",
            (minute, CHAN_MOVE),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    q50, q90, qmax, n = row
    # sorted = [10, 20, 30, 40, 50]; numpy 'linear' interpolation:
    # q50 -> index 2.0 -> 30; q90 -> index 3.6 -> 40 + 0.6*(50-40) = 46.
    assert q50 == pytest.approx(30.0)
    assert q90 == pytest.approx(46.0)
    assert qmax == pytest.approx(50.0)
    assert n == 5


def test_rollup_runs_incrementally_before_frames_are_pruned(db_path: Path) -> None:
    """Rollup covers every complete minute since the last one summarized, not just prune targets."""
    store = FrameStore(db_path)
    store.start()
    try:
        now_utc = 200 * 86400.0
        base_minute = int(now_utc // 60) - 10
        # Three separate complete minutes, all well within raw retention (not pruned).
        for m_offset in range(3):
            minute = base_minute + m_offset
            for i in range(3):
                store.enqueue_frame(
                    "s", _make_frame(minute * 60.0 + i, i, seed=m_offset * 10 + i)
                )
    finally:
        store.stop()

    deleted = store.prune(now_utc=now_utc, raw_retention_days=3650)
    assert deleted == 0  # nothing old enough to prune

    conn = sqlite3.connect(db_path)
    try:
        minutes = {
            row[0] for row in conn.execute("SELECT DISTINCT minute FROM minute_summary WHERE sensor_id='s'")
        }
    finally:
        conn.close()
    assert minutes == {base_minute, base_minute + 1, base_minute + 2}


def test_v1_schema_is_rejected(db_path: Path) -> None:
    """A v1-shaped DB (pre-migration-support) fails fast instead of being silently misread."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE schema_info (version INTEGER NOT NULL)")
        conn.execute("INSERT INTO schema_info (version) VALUES (1)")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(RuntimeError, match="Unsupported smart_ld2410 store schema version"):
        FrameStore(db_path)


def test_v2_database_migrates_and_keeps_its_episodes(db_path: Path) -> None:
    """v2 -> v3 adds gate_peaks in place (spec 21 §1) without touching old rows.

    The alternative - refusing to open a v2 database, which is what the
    version check did before there were any migrations - would have thrown
    away every recording this feature is supposed to be validated against.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = FrameStore(db_path)
    conn = sqlite3.connect(db_path)
    try:
        # Roll the database back to exactly what v2 looked like.
        conn.execute("ALTER TABLE episodes DROP COLUMN gate_peaks")
        conn.execute(
            "INSERT INTO episodes (sensor_id, t0, t1, result) VALUES ('AA', 1.0, 2.0, 'entered')"
        )
        conn.execute("UPDATE schema_info SET version = 2")
        conn.commit()
    finally:
        conn.close()

    del store
    FrameStore(db_path)  # reopening runs the migration

    conn = sqlite3.connect(db_path)
    try:
        (version,) = conn.execute("SELECT version FROM schema_info").fetchone()
        rows = conn.execute("SELECT result, gate_peaks FROM episodes").fetchall()
    finally:
        conn.close()

    assert version == SCHEMA_VERSION
    assert rows == [("entered", None)]


def test_episode_gate_peaks_round_trip(db_path: Path) -> None:
    """The per-gate raw-energy profile is stored as its 9-byte BLOB."""
    episode = Episode(
        scope=SCOPE_DETECTION,
        gate=None,
        t0=1.0,
        t1=9.0,
        peak_residual=12.0,
        gate_lo=2,
        gate_hi=4,
        centroid_mean=3.0,
        centroid_vel=0.1,
        still_frac=0.4,
        result="entered",
        gate_peaks=(0, 0, 61, 88, 40, 0, 0, 0, 0),
    )
    store = FrameStore(db_path)
    store.start()
    try:
        store.enqueue_episode("AA:BB:CC:DD:EE:FF", episode)
    finally:
        store.stop()

    conn = sqlite3.connect(db_path)
    try:
        (blob,) = conn.execute("SELECT gate_peaks FROM episodes").fetchone()
    finally:
        conn.close()

    assert tuple(blob) == episode.gate_peaks


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
