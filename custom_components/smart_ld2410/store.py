"""SQLite-backed storage for radar frames, sensors, and events.

Deliberately free of Home Assistant imports: it is constructed from a plain
path, not a ``hass`` object, so ``scripts/replay.py`` (and tests) can reuse it
outside of HA. ``__init__.py`` is responsible for wiring a config directory
path into :func:`default_db_path` and driving the writer's lifecycle.

A single dedicated writer thread owns the write connection; frames, events,
and (when the writer is running) prune requests are handed to it through a
bounded ``queue.Queue`` and batched into ~1s commits so the event loop is
never blocked on disk I/O. ``iter_frames`` always opens a short-lived
read-only connection of its own and may be called from any thread. ``prune``
does the same, falling back to a direct connection, only when no writer is
running (e.g. replay tooling pointed at a recorded database).
"""

from __future__ import annotations

import json
import logging
import queue
import sqlite3
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from .algo.types import Frame

_LOGGER = logging.getLogger(__name__)

SCHEMA_VERSION: Final = 1
DEFAULT_RETENTION_DAYS: Final = 30

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

_GATE_MOVE_COLUMNS: Final = tuple(f"gate_move_{i}" for i in range(9))
_GATE_STILL_COLUMNS: Final = tuple(f"gate_still_{i}" for i in range(9))

_FRAME_INSERT_COLUMNS: Final = (
    "sensor_id",
    "ts_utc",
    "ts_mono",
    *_GATE_MOVE_COLUMNS,
    *_GATE_STILL_COLUMNS,
    "target_distance_cm",
    "device_occupancy",
)
_FRAME_SELECT_COLUMNS: Final = (
    "ts_utc",
    "ts_mono",
    *_GATE_MOVE_COLUMNS,
    *_GATE_STILL_COLUMNS,
    "target_distance_cm",
    "device_occupancy",
)

_INSERT_FRAME_SQL: Final = (
    f"INSERT INTO frames ({', '.join(_FRAME_INSERT_COLUMNS)}) "
    f"VALUES ({', '.join('?' * len(_FRAME_INSERT_COLUMNS))})"
)
_INSERT_EVENT_SQL: Final = (
    "INSERT INTO events (sensor_id, ts_utc, kind, payload) VALUES (?, ?, ?, ?)"
)
_SELECT_FRAMES_SQL: Final = (
    f"SELECT {', '.join(_FRAME_SELECT_COLUMNS)} FROM frames "
    "WHERE sensor_id = ? AND ts_utc >= ? AND ts_utc < ? ORDER BY ts_utc"
)

_GATE_COLUMN_DEFS: Final = ",\n    ".join(
    f"{name} INTEGER NOT NULL" for name in (*_GATE_MOVE_COLUMNS, *_GATE_STILL_COLUMNS)
)
_SCHEMA_SQL: Final = f"""
CREATE TABLE IF NOT EXISTS schema_info (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS frames (
    sensor_id TEXT NOT NULL,
    ts_utc REAL NOT NULL,
    ts_mono REAL NOT NULL,
    {_GATE_COLUMN_DEFS},
    target_distance_cm INTEGER NOT NULL,
    device_occupancy INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_frames_sensor_ts ON frames(sensor_id, ts_utc);

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


class _StopSignal:
    """Sentinel telling the writer thread to drain and exit."""

    __slots__ = ()


_STOP: Final = _StopSignal()


class _PruneRequest:
    """A prune command routed through the writer thread, with a handoff for the result.

    Serializing prune's DELETE through the writer avoids it contending with
    batched inserts for the write lock (a long-running DELETE holding the
    lock past the writer's timeout would make a batch get dropped).
    """

    __slots__ = ("cutoff", "event", "result", "error")

    def __init__(self, cutoff: float) -> None:
        self.cutoff = cutoff
        self.event = threading.Event()
        self.result: int | None = None
        self.error: BaseException | None = None


_QueueItem = _FrameWrite | _EventWrite | _StopSignal | _PruneRequest


def _init_schema(db_path: Path) -> None:
    """Create the schema (idempotent) and set creation-time pragmas.

    ``auto_vacuum`` only takes effect when set before any tables exist, so
    this must run before the writer thread's first connection.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA_SQL)
        if conn.execute("SELECT version FROM schema_info").fetchone() is None:
            conn.execute("INSERT INTO schema_info (version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
    finally:
        conn.close()


def _frame_row(item: _FrameWrite) -> tuple[Any, ...]:
    frame = item.frame
    return (
        item.sensor_id,
        frame.ts_utc,
        frame.ts_mono,
        *frame.move_gates,
        *frame.still_gates,
        frame.target_distance_cm,
        int(frame.device_occupancy),
    )


def _row_to_frame(row: tuple[Any, ...]) -> Frame:
    ts_utc, ts_mono, *gates, target_distance_cm, device_occupancy = row
    return Frame(
        ts_utc=ts_utc,
        ts_mono=ts_mono,
        move_gates=tuple(gates[:9]),
        still_gates=tuple(gates[9:18]),
        target_distance_cm=target_distance_cm,
        device_occupancy=bool(device_occupancy),
    )


class FrameStore:
    """SQLite-backed store for one integration's worth of radar frames."""

    def __init__(
        self, db_path: str | Path, *, retention_days: int = DEFAULT_RETENTION_DAYS
    ) -> None:
        """Create the store and its schema (does not start the writer)."""
        self._db_path = Path(db_path)
        self.retention_days = retention_days
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
                deadline = time.monotonic() + _COMMIT_INTERVAL_S
                while True:
                    timeout = max(0.0, deadline - time.monotonic())
                    try:
                        item: _QueueItem | None = self._queue.get(timeout=timeout)
                    except queue.Empty:
                        item = None

                    if item is _STOP:
                        if frames or events:
                            self._flush(conn, frames, events)
                        return
                    if isinstance(item, _FrameWrite):
                        frames.append(item)
                    elif isinstance(item, _EventWrite):
                        events.append(item)
                    elif isinstance(item, _PruneRequest):
                        if frames or events:
                            self._flush(conn, frames, events)
                            frames = []
                            events = []
                        self._execute_prune(conn, item)

                    if time.monotonic() >= deadline:
                        if frames or events:
                            self._flush(conn, frames, events)
                            frames = []
                            events = []
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
    ) -> None:
        try:
            if frames:
                conn.executemany(_INSERT_FRAME_SQL, [_frame_row(item) for item in frames])
            if events:
                conn.executemany(
                    _INSERT_EVENT_SQL,
                    [(e.sensor_id, e.ts_utc, e.kind, e.payload) for e in events],
                )
            conn.commit()
        except sqlite3.Error:
            _LOGGER.exception(
                "Failed to flush %d frame(s) / %d event(s) to %s",
                len(frames),
                len(events),
                self._db_path,
            )
            conn.rollback()

    def _execute_prune(self, conn: sqlite3.Connection, request: _PruneRequest) -> None:
        """Run a queued prune's DELETE + incremental vacuum on the writer's connection."""
        try:
            deleted = conn.execute(
                "DELETE FROM frames WHERE ts_utc < ?", (request.cutoff,)
            ).rowcount
            conn.execute("DELETE FROM events WHERE ts_utc < ?", (request.cutoff,))
            conn.commit()
            conn.execute("PRAGMA incremental_vacuum")
            conn.commit()
            request.result = deleted
        except sqlite3.Error as err:
            _LOGGER.exception("Failed to prune %s", self._db_path)
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
        retention_days: int | None = None,
        timeout: float = 30.0,
    ) -> int:
        """Delete frames/events older than the retention window.

        Returns the number of frame rows deleted. Runs an incremental vacuum
        afterwards to release freed pages (the db was created with
        ``auto_vacuum=INCREMENTAL`` for exactly this).

        When the writer thread is running, the DELETE is routed through it
        (serialized with batched inserts) so it can't hold the write lock
        past the writer's own timeout and cause a batch to be dropped;
        ``timeout`` bounds how long to wait for that handoff. When no writer
        is running (replay/maintenance tooling), this runs the DELETE
        directly on a short-lived connection instead.
        """
        days = self.retention_days if retention_days is None else retention_days
        cutoff = now_utc - days * 86400.0

        if self._thread is not None and self._thread.is_alive():
            request = _PruneRequest(cutoff)
            self._queue.put(request)
            if not request.event.wait(timeout=timeout):
                _LOGGER.warning(
                    "Timed out waiting for writer thread to prune %s; "
                    "falling back to a direct delete",
                    self._db_path,
                )
                return self._prune_direct(cutoff)
            return request.result if request.result is not None else 0

        return self._prune_direct(cutoff)

    def _prune_direct(self, cutoff: float) -> int:
        """Synchronous prune on a dedicated connection (no writer thread running)."""
        conn = sqlite3.connect(self._db_path, timeout=30.0)
        try:
            conn.execute("PRAGMA synchronous=NORMAL")
            deleted = conn.execute("DELETE FROM frames WHERE ts_utc < ?", (cutoff,)).rowcount
            conn.execute("DELETE FROM events WHERE ts_utc < ?", (cutoff,))
            conn.commit()
            conn.execute("PRAGMA incremental_vacuum")
            conn.commit()
            return deleted
        finally:
            conn.close()
