"""SQLite-backed storage for radar frames, sensors, events, and rollups.

Deliberately free of Home Assistant imports: it is constructed from a plain
path, not a ``hass`` object, so ``replay.py`` (and tests) can reuse it outside
of HA. ``__init__.py`` is responsible for wiring a config directory path into
:func:`default_db_path` and driving the writer's lifecycle.

Schema follows docs/spec/10-interfaces.md §2. ``frames`` stores raw per-frame
gate energies as 9-byte BLOBs (gate order 0..8); ``minute_summary`` stores the
long-lived rollup (median/p90/max/n per sensor/minute/gate/channel);
``buckets`` is created per the contract but is not yet written to -- baseline
persistence stays in the HA ``Store`` for this pass; ``episodes`` holds
detection-scope episodes only (per-gate episodes drive the dwell classifier
in-process and are never persisted). ``events`` is kept in addition to the
contract tables (connect/disconnect + occupancy/gate-class transitions).

A single dedicated writer thread owns the write connection; frames, events,
and (when the writer is running) maintenance (rollup + prune) requests are
handed to it through a bounded ``queue.Queue`` and batched into ~1s commits
so the event loop is never blocked on disk I/O. ``iter_frames`` always opens
a short-lived read-only connection of its own and may be called from any
thread. ``prune`` does the same, falling back to a direct connection, only
when no writer is running (e.g. replay tooling pointed at a recorded
database).
"""

from __future__ import annotations

import json
import logging
import queue
import sqlite3
import threading
import time
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from .algo.types import Episode, Frame

_LOGGER = logging.getLogger(__name__)

SCHEMA_VERSION: Final = 4
DEFAULT_RAW_RETENTION_DAYS: Final = 7
DEFAULT_SUMMARY_RETENTION_DAYS: Final = 365

# Channel ids used in minute_summary (per docs/spec/10-interfaces.md §2).
CHAN_MOVE: Final = 0
CHAN_STILL: Final = 1

# How often the writer thread batches queued writes into a commit.
_COMMIT_INTERVAL_S: Final = 1.0

# Bound on the writer queue. If the writer thread stalls or dies, callers must
# never block (frames arrive at ~10Hz from the event loop); once this many
# items are queued, new frames/events are dropped instead of piling up
# unbounded in memory.
_MAX_QUEUE_SIZE: Final = 20000

# Only log a "queue full, dropping" warning this often (in dropped items),
# so a stalled writer doesn't spam the log at 10Hz.
_DROP_LOG_INTERVAL: Final = 600

_GATE_COUNT: Final = 9

_FRAME_INSERT_COLUMNS: Final = (
    "sensor_id",
    "ts",
    "ts_mono",
    "move",
    "still",
    "distance_cm",
    "device_occ",
)
_FRAME_SELECT_COLUMNS: Final = (
    "ts",
    "ts_mono",
    "move",
    "still",
    "distance_cm",
    "device_occ",
)

_INSERT_FRAME_SQL: Final = (
    f"INSERT INTO frames ({', '.join(_FRAME_INSERT_COLUMNS)}) "
    f"VALUES ({', '.join('?' * len(_FRAME_INSERT_COLUMNS))})"
)
_INSERT_EVENT_SQL: Final = (
    "INSERT INTO events (sensor_id, ts_utc, kind, payload) VALUES (?, ?, ?, ?)"
)
# Detection-scope episodes only (contract §2); per-gate episodes are consumed
# in-process by the dwell classifier and never reach this table. label/
# label_source/label_conf are Phase 3+ columns, left NULL here.
_EPISODE_INSERT_COLUMNS: Final = (
    "sensor_id",
    "t0",
    "t1",
    "peak_residual",
    "gate_lo",
    "gate_hi",
    "centroid_mean",
    "centroid_vel",
    "still_frac",
    "result",
    "gate_peaks",
    "leading_gate",
)
_INSERT_EPISODE_SQL: Final = (
    f"INSERT INTO episodes ({', '.join(_EPISODE_INSERT_COLUMNS)}) "
    f"VALUES ({', '.join('?' * len(_EPISODE_INSERT_COLUMNS))})"
)
_SELECT_FRAMES_SQL: Final = (
    f"SELECT {', '.join(_FRAME_SELECT_COLUMNS)} FROM frames "
    "WHERE sensor_id = ? AND ts >= ? AND ts < ? ORDER BY ts"
)
_INSERT_MINUTE_SUMMARY_SQL: Final = (
    "INSERT OR REPLACE INTO minute_summary "
    "(sensor_id, minute, gate, chan, q50, q90, qmax, n) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)

_SCHEMA_SQL: Final = """
CREATE TABLE IF NOT EXISTS schema_info (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS frames (
    sensor_id TEXT NOT NULL,
    ts REAL NOT NULL,
    ts_mono REAL NOT NULL,
    move BLOB NOT NULL,
    still BLOB NOT NULL,
    distance_cm INTEGER NOT NULL,
    device_occ INTEGER NOT NULL,
    PRIMARY KEY (sensor_id, ts)
);

CREATE TABLE IF NOT EXISTS minute_summary (
    sensor_id TEXT NOT NULL,
    minute INTEGER NOT NULL,
    gate INTEGER NOT NULL,
    chan INTEGER NOT NULL,
    q50 REAL NOT NULL,
    q90 REAL NOT NULL,
    qmax REAL NOT NULL,
    n INTEGER NOT NULL,
    PRIMARY KEY (sensor_id, minute, gate, chan)
);

-- 60s baseline inputs per docs/spec/10-interfaces.md §2 (schema v3 there).
-- Created for contract conformance but NOT YET WRITTEN TO: baseline
-- persistence stays in the HA `Store` (JSON) this pass. A later pass moves
-- baseline persistence here.
CREATE TABLE IF NOT EXISTS buckets (
    sensor_id TEXT NOT NULL,
    bucket INTEGER NOT NULL,
    gate INTEGER NOT NULL,
    chan INTEGER NOT NULL,
    med REAL NOT NULL,
    spread REAL NOT NULL,
    n INTEGER NOT NULL
);

-- Detection-scope episodes (spec 20 §1); label/label_source/label_conf are
-- written by later phases (Phase 3+ labeling).
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY,
    sensor_id TEXT NOT NULL,
    t0 REAL NOT NULL,
    t1 REAL NOT NULL,
    peak_residual REAL,
    gate_lo INTEGER,
    gate_hi INTEGER,
    centroid_mean REAL,
    centroid_vel REAL,
    still_frac REAL,
    result TEXT,
    -- Peak raw move energy per gate over the episode, 9 bytes in gate order
    -- (spec 21 §1). Raw, so the energy ceiling stays baseline-independent.
    gate_peaks BLOB,
    -- Nearest gate whose moving channel rose above its learned quiet level.
    leading_gate INTEGER,
    label TEXT,
    label_source TEXT,
    label_conf REAL
);

CREATE TABLE IF NOT EXISTS sensors (
    sensor_id TEXT PRIMARY KEY,
    name TEXT,
    room TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS events (
    sensor_id TEXT NOT NULL,
    ts_utc REAL NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_sensor_ts ON events(sensor_id, ts_utc);
"""


def default_db_path(config_dir: str | Path) -> Path:
    """Return the standard frames.db location for a HA config directory."""
    return Path(config_dir) / "smart_ld2410" / "frames.db"


@dataclass(frozen=True, slots=True)
class _FrameWrite:
    """A queued frame insert."""

    sensor_id: str
    frame: Frame


@dataclass(frozen=True, slots=True)
class _EventWrite:
    """A queued event insert. ``payload`` is already JSON-encoded, or None."""

    sensor_id: str
    ts_utc: float
    kind: str
    payload: str | None


@dataclass(frozen=True, slots=True)
class _EpisodeWrite:
    """A queued detection-scope episode insert.

    Callers are responsible for only enqueuing detection-scope episodes
    (:data:`.algo.types.SCOPE_DETECTION`); the store trusts that filter
    rather than importing the scope constant itself.
    """

    sensor_id: str
    episode: Episode


class _StopSignal:
    """Sentinel telling the writer thread to drain and exit."""

    __slots__ = ()


_STOP: Final = _StopSignal()


class _MaintenanceRequest:
    """A rollup+prune command routed through the writer thread.

    Serializing this through the writer avoids it contending with batched
    inserts for the write lock (a long-running rollup/DELETE holding the lock
    past the writer's timeout would make a batch get dropped).
    """

    __slots__ = (
        "raw_cutoff",
        "summary_cutoff_minute",
        "rollup_hi_minute",
        "event",
        "result",
        "error",
    )

    def __init__(self, raw_cutoff: float, summary_cutoff_minute: int, rollup_hi_minute: int) -> None:
        self.raw_cutoff = raw_cutoff
        self.summary_cutoff_minute = summary_cutoff_minute
        self.rollup_hi_minute = rollup_hi_minute
        self.event = threading.Event()
        self.result: int | None = None
        self.error: BaseException | None = None


_QueueItem = _FrameWrite | _EventWrite | _EpisodeWrite | _StopSignal | _MaintenanceRequest


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(
        row[1] == column for row in conn.execute(f"PRAGMA table_info({table})")
    )


# Purely additive migrations, keyed by the version they upgrade *to*, as
# ``(table, column, type)`` triples. Adding a nullable column is the only
# shape allowed here: anything that rewrites or reinterprets existing rows
# belongs in a real migration path with its own tests, not in this table.
_MIGRATIONS: Final[dict[int, tuple[tuple[str, str, str], ...]]] = {
    3: (("episodes", "gate_peaks", "BLOB"),),
    4: (("episodes", "leading_gate", "INTEGER"),),
}

_OLDEST_MIGRATABLE_VERSION: Final = 2
"""Schema version below which a database can no longer be opened at all."""


def _migrate(conn: sqlite3.Connection, from_version: int) -> None:
    """Apply every additive migration between ``from_version`` and current.

    Each step is skipped if already applied, so a database that was
    half-upgraded by an interrupted start still converges.
    """
    for version in range(from_version + 1, SCHEMA_VERSION + 1):
        for table, column, column_type in _MIGRATIONS.get(version, ()):
            if _column_exists(conn, table, column):
                continue
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
    conn.execute("UPDATE schema_info SET version = ?", (SCHEMA_VERSION,))
    conn.commit()
    _LOGGER.info(
        "smart_ld2410 store migrated from schema version %d to %d",
        from_version,
        SCHEMA_VERSION,
    )


def _init_schema(db_path: Path) -> None:
    """Create the schema (idempotent), rejecting an unsupported older schema.

    ``auto_vacuum`` only takes effect when set before any tables exist, so
    this must run before the writer thread's first connection.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
        conn.execute("PRAGMA journal_mode=WAL")

        if not _table_exists(conn, "schema_info"):
            # Fresh database.
            conn.executescript(_SCHEMA_SQL)
            conn.execute("INSERT INTO schema_info (version) VALUES (?)", (SCHEMA_VERSION,))
            conn.commit()
            return

        (version,) = conn.execute("SELECT version FROM schema_info").fetchone()
        if version < _OLDEST_MIGRATABLE_VERSION:
            _LOGGER.error(
                "smart_ld2410 store %s has unsupported schema version %d (need %d); "
                "this database predates schema migration support and can no longer "
                "be opened",
                db_path,
                version,
                SCHEMA_VERSION,
            )
            raise RuntimeError(
                f"Unsupported smart_ld2410 store schema version {version} in {db_path} "
                f"(need {SCHEMA_VERSION})"
            )
        # Make sure any tables added since (buckets, episodes, minute_summary)
        # exist for DBs created at an earlier version already. CREATE TABLE IF
        # NOT EXISTS cannot add a column to a table that is already there,
        # which is what _migrate is for.
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
        if version < SCHEMA_VERSION:
            _migrate(conn, version)
    finally:
        conn.close()


def _frame_row(item: _FrameWrite) -> tuple[Any, ...]:
    frame = item.frame
    return (
        item.sensor_id,
        frame.ts_utc,
        frame.ts_mono,
        bytes(frame.move_gates),
        bytes(frame.still_gates),
        frame.target_distance_cm,
        int(frame.device_occupancy),
    )


def _episode_row(item: _EpisodeWrite) -> tuple[Any, ...]:
    episode = item.episode
    return (
        item.sensor_id,
        episode.t0,
        episode.t1,
        episode.peak_residual,
        episode.gate_lo,
        episode.gate_hi,
        episode.centroid_mean,
        episode.centroid_vel,
        episode.still_frac,
        episode.result,
        bytes(episode.gate_peaks),
        episode.leading_gate,
    )


def _row_to_frame(row: tuple[Any, ...]) -> Frame:
    ts, ts_mono, move_blob, still_blob, distance_cm, device_occ = row
    return Frame(
        ts_utc=ts,
        ts_mono=ts_mono,
        move_gates=tuple(move_blob),
        still_gates=tuple(still_blob),
        target_distance_cm=distance_cm,
        device_occupancy=bool(device_occ),
    )


def _quantile(sorted_values: Sequence[int], q: float) -> float:
    """Linear-interpolation quantile over already-sorted values (numpy 'linear')."""
    n = len(sorted_values)
    if n == 1:
        return float(sorted_values[0])
    pos = q * (n - 1)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


def _rollup_minutes(conn: sqlite3.Connection, sensor_id: str, minute_lo: int, minute_hi: int) -> None:
    """Aggregate raw frames in ``[minute_lo, minute_hi)`` into minute_summary.

    Idempotent (INSERT OR REPLACE) so re-running over an already-summarized
    range is harmless.
    """
    rows = conn.execute(
        "SELECT CAST(ts / 60 AS INTEGER) AS minute, move, still FROM frames "
        "WHERE sensor_id = ? AND ts >= ? AND ts < ? ORDER BY minute",
        (sensor_id, minute_lo * 60.0, minute_hi * 60.0),
    ).fetchall()
    if not rows:
        return

    per_minute: dict[int, list[tuple[bytes, bytes]]] = defaultdict(list)
    for minute, move_blob, still_blob in rows:
        per_minute[minute].append((move_blob, still_blob))

    summary_rows: list[tuple[Any, ...]] = []
    for minute, entries in per_minute.items():
        n = len(entries)
        for gate in range(_GATE_COUNT):
            move_vals = sorted(move_blob[gate] for move_blob, _ in entries)
            still_vals = sorted(still_blob[gate] for _, still_blob in entries)
            summary_rows.append(
                (
                    sensor_id,
                    minute,
                    gate,
                    CHAN_MOVE,
                    _quantile(move_vals, 0.5),
                    _quantile(move_vals, 0.9),
                    float(move_vals[-1]),
                    n,
                )
            )
            summary_rows.append(
                (
                    sensor_id,
                    minute,
                    gate,
                    CHAN_STILL,
                    _quantile(still_vals, 0.5),
                    _quantile(still_vals, 0.9),
                    float(still_vals[-1]),
                    n,
                )
            )
    conn.executemany(_INSERT_MINUTE_SUMMARY_SQL, summary_rows)


def _run_maintenance(conn: sqlite3.Connection, request: _MaintenanceRequest) -> int:
    """Roll up all complete un-summarized minutes, then prune both tiers.

    Rollup runs incrementally: every sensor with any raw frames gets all
    complete minutes since its last summarized minute rolled up, not just
    the minutes about to be pruned -- so summaries accumulate from day one
    even while raw_retention_days keeps far more than one day of frames.
    """
    sensor_ids = [row[0] for row in conn.execute("SELECT DISTINCT sensor_id FROM frames")]
    for sensor_id in sensor_ids:
        row = conn.execute(
            "SELECT MAX(minute) FROM minute_summary WHERE sensor_id = ?", (sensor_id,)
        ).fetchone()
        last_minute = row[0]
        minute_lo = 0 if last_minute is None else last_minute + 1
        if minute_lo < request.rollup_hi_minute:
            _rollup_minutes(conn, sensor_id, minute_lo, request.rollup_hi_minute)

    deleted = conn.execute("DELETE FROM frames WHERE ts < ?", (request.raw_cutoff,)).rowcount
    conn.execute("DELETE FROM events WHERE ts_utc < ?", (request.raw_cutoff,))
    conn.execute("DELETE FROM minute_summary WHERE minute < ?", (request.summary_cutoff_minute,))
    return deleted


class FrameStore:
    """SQLite-backed store for one integration's worth of radar frames."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        raw_retention_days: int = DEFAULT_RAW_RETENTION_DAYS,
        summary_retention_days: int = DEFAULT_SUMMARY_RETENTION_DAYS,
    ) -> None:
        """Create the store and its schema (does not start the writer)."""
        self._db_path = Path(db_path)
        self.raw_retention_days = raw_retention_days
        self.summary_retention_days = summary_retention_days
        self._queue: queue.Queue[_QueueItem] = queue.Queue(maxsize=_MAX_QUEUE_SIZE)
        self._thread: threading.Thread | None = None
        self._drop_lock = threading.Lock()
        self._dropped_count = 0
        _init_schema(self._db_path)

    @property
    def db_path(self) -> Path:
        """Path to the underlying SQLite database file."""
        return self._db_path

    def start(self) -> None:
        """Start the dedicated writer thread. Call once."""
        if self._thread is not None:
            raise RuntimeError("FrameStore writer already started")
        self._thread = threading.Thread(
            target=self._writer_loop, name="smart_ld2410-writer", daemon=True
        )
        self._thread.start()

    def stop(self, *, timeout: float | None = 10.0) -> None:
        """Signal the writer to drain its queue, commit, and exit.

        Safe to call even if :meth:`start` was never called.
        """
        if self._thread is None:
            return
        self._queue.put(_STOP)
        self._thread.join(timeout=timeout)
        self._thread = None

    def enqueue_frame(self, sensor_id: str, frame: Frame) -> None:
        """Queue a frame for the writer thread. Non-blocking; drops on backpressure."""
        try:
            self._queue.put_nowait(_FrameWrite(sensor_id, frame))
        except queue.Full:
            self._on_queue_full()

    def enqueue_event(
        self,
        sensor_id: str,
        ts_utc: float,
        kind: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Queue an event for the writer thread. Non-blocking; drops on backpressure."""
        payload_json = json.dumps(payload) if payload is not None else None
        try:
            self._queue.put_nowait(_EventWrite(sensor_id, ts_utc, kind, payload_json))
        except queue.Full:
            self._on_queue_full()

    def enqueue_episode(self, sensor_id: str, episode: Episode) -> None:
        """Queue a detection-scope episode row for the writer thread.

        Non-blocking; drops on backpressure. Per-gate episodes are not stored
        (spec 20 §1) -- only pass detection-scope episodes here.
        """
        try:
            self._queue.put_nowait(_EpisodeWrite(sensor_id, episode))
        except queue.Full:
            self._on_queue_full()

    def _on_queue_full(self) -> None:
        """Record a dropped frame/event, log only occasionally to avoid spam."""
        with self._drop_lock:
            self._dropped_count += 1
            count = self._dropped_count
        if count == 1 or count % _DROP_LOG_INTERVAL == 0:
            _LOGGER.warning(
                "FrameStore writer queue for %s is full (writer stalled or dead); "
                "dropped %d item(s) so far",
                self._db_path,
                count,
            )

    def _connect_writer(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _writer_loop(self) -> None:
        # The whole body is guarded: if anything here raises, the thread would
        # otherwise die silently while enqueue_frame keeps accepting (and, once
        # the queue fills, dropping) items forever with no indication anything
        # is wrong. Log CRITICAL exactly once so the failure is visible.
        try:
            conn = self._connect_writer()
            try:
                frames: list[_FrameWrite] = []
                events: list[_EventWrite] = []
                episodes: list[_EpisodeWrite] = []
                deadline = time.monotonic() + _COMMIT_INTERVAL_S
                while True:
                    timeout = max(0.0, deadline - time.monotonic())
                    try:
                        item: _QueueItem | None = self._queue.get(timeout=timeout)
                    except queue.Empty:
                        item = None

                    if item is _STOP:
                        if frames or events or episodes:
                            self._flush(conn, frames, events, episodes)
                        return
                    if isinstance(item, _FrameWrite):
                        frames.append(item)
                    elif isinstance(item, _EventWrite):
                        events.append(item)
                    elif isinstance(item, _EpisodeWrite):
                        episodes.append(item)
                    elif isinstance(item, _MaintenanceRequest):
                        if frames or events or episodes:
                            self._flush(conn, frames, events, episodes)
                            frames = []
                            events = []
                            episodes = []
                        self._execute_maintenance(conn, item)

                    if time.monotonic() >= deadline:
                        if frames or events or episodes:
                            self._flush(conn, frames, events, episodes)
                            frames = []
                            events = []
                            episodes = []
                        deadline = time.monotonic() + _COMMIT_INTERVAL_S
            finally:
                conn.close()
        except Exception:
            _LOGGER.critical(
                "smart_ld2410 writer thread for %s died unexpectedly; "
                "frame/event persistence has stopped",
                self._db_path,
                exc_info=True,
            )

    def _flush(
        self,
        conn: sqlite3.Connection,
        frames: list[_FrameWrite],
        events: list[_EventWrite],
        episodes: list[_EpisodeWrite],
    ) -> None:
        try:
            if frames:
                conn.executemany(_INSERT_FRAME_SQL, [_frame_row(item) for item in frames])
            if events:
                conn.executemany(
                    _INSERT_EVENT_SQL,
                    [(e.sensor_id, e.ts_utc, e.kind, e.payload) for e in events],
                )
            if episodes:
                conn.executemany(
                    _INSERT_EPISODE_SQL, [_episode_row(item) for item in episodes]
                )
            conn.commit()
        except sqlite3.Error:
            _LOGGER.exception(
                "Failed to flush %d frame(s) / %d event(s) / %d episode(s) to %s",
                len(frames),
                len(events),
                len(episodes),
                self._db_path,
            )
            conn.rollback()

    def _execute_maintenance(self, conn: sqlite3.Connection, request: _MaintenanceRequest) -> None:
        """Run a queued rollup + prune + incremental vacuum on the writer's connection."""
        try:
            deleted = _run_maintenance(conn, request)
            conn.commit()
            conn.execute("PRAGMA incremental_vacuum")
            conn.commit()
            request.result = deleted
        except sqlite3.Error as err:
            _LOGGER.exception("Failed to run maintenance on %s", self._db_path)
            conn.rollback()
            request.error = err
            request.result = 0
        finally:
            request.event.set()

    def _connect_reader(self) -> sqlite3.Connection:
        return sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)

    def iter_frames(
        self, sensor_id: str, start_utc: float, end_utc: float
    ) -> Iterator[Frame]:
        """Yield frames for ``sensor_id`` in ``[start_utc, end_utc)``, ts-ordered."""
        conn = self._connect_reader()
        try:
            cursor = conn.execute(_SELECT_FRAMES_SQL, (sensor_id, start_utc, end_utc))
            for row in cursor:
                yield _row_to_frame(row)
        finally:
            conn.close()

    def prune(
        self,
        *,
        now_utc: float,
        raw_retention_days: int | None = None,
        summary_retention_days: int | None = None,
        timeout: float = 30.0,
    ) -> int:
        """Roll up complete un-summarized minutes, then prune both retention tiers.

        Returns the number of raw frame rows deleted. Runs an incremental
        vacuum afterwards to release freed pages (the db was created with
        ``auto_vacuum=INCREMENTAL`` for exactly this).

        Frames older than ``raw_retention_days`` (default 7) are deleted;
        minute_summary rows older than ``summary_retention_days`` (default
        365) are deleted; episodes are kept indefinitely (not touched here).
        Before any frames are deleted, every complete minute not yet present
        in ``minute_summary`` is rolled up -- this runs on every call, not
        just for minutes about to be pruned, so summaries accumulate from day
        one regardless of how long raw retention is.

        When the writer thread is running, this whole operation is routed
        through it (serialized with batched inserts) so it can't hold the
        write lock past the writer's own timeout and cause a batch to be
        dropped; ``timeout`` bounds how long to wait for that handoff. When
        no writer is running (replay/maintenance tooling), this runs
        directly on a short-lived connection instead.
        """
        raw_days = self.raw_retention_days if raw_retention_days is None else raw_retention_days
        summary_days = (
            self.summary_retention_days if summary_retention_days is None else summary_retention_days
        )
        raw_cutoff = now_utc - raw_days * 86400.0
        summary_cutoff_minute = int((now_utc - summary_days * 86400.0) // 60)
        rollup_hi_minute = int(now_utc // 60)

        if self._thread is not None and self._thread.is_alive():
            request = _MaintenanceRequest(raw_cutoff, summary_cutoff_minute, rollup_hi_minute)
            self._queue.put(request)
            if not request.event.wait(timeout=timeout):
                _LOGGER.warning(
                    "Timed out waiting for writer thread to run maintenance on %s; "
                    "falling back to a direct connection",
                    self._db_path,
                )
                return self._maintenance_direct(raw_cutoff, summary_cutoff_minute, rollup_hi_minute)
            return request.result if request.result is not None else 0

        return self._maintenance_direct(raw_cutoff, summary_cutoff_minute, rollup_hi_minute)

    def _maintenance_direct(
        self, raw_cutoff: float, summary_cutoff_minute: int, rollup_hi_minute: int
    ) -> int:
        """Synchronous rollup + prune on a dedicated connection (no writer thread running)."""
        conn = sqlite3.connect(self._db_path, timeout=30.0)
        try:
            conn.execute("PRAGMA synchronous=NORMAL")
            request = _MaintenanceRequest(raw_cutoff, summary_cutoff_minute, rollup_hi_minute)
            deleted = _run_maintenance(conn, request)
            conn.commit()
            conn.execute("PRAGMA incremental_vacuum")
            conn.commit()
            return deleted
        finally:
            conn.close()
