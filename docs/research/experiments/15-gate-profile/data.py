"""Class-labelled frame loading for the gate-profile experiment."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FIXTURES = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "recordings"

LABEL_CLASS = {"toilet": "IN", "stove": "TW", "island": "TW", "hall-walk-by": "TW", "empty": "EMPTY"}

ARRIVAL_LEAD_S = 27.0
ISLAND_TAIL_TRIM_S = 5.0
CONTAMINATED_STOVE_START = "2026-09-09 23:08:24"

SPANS = {
    "throughwall-morning-d06e": [
        ("EMPTY", "2026-09-11 04:55:00", "2026-09-11 04:59:30"),
        ("TW", "2026-09-11 05:00:00", "2026-09-11 05:46:00"),
        ("EMPTY", "2026-09-11 05:47:00", "2026-09-11 06:04:59"),
    ],
    "bathroom-visit-2204-d06e": [
        ("EMPTY", "2026-09-11 21:55:00", "2026-09-11 22:03:00"),
        ("IN", "2026-09-11 22:04:01", "2026-09-11 22:06:43"),
        ("EMPTY", "2026-09-11 22:07:30", "2026-09-11 22:11:59"),
    ],
    "stove-case-0913-d06e": [
        ("IN", "2026-09-13 09:24:00", "2026-09-13 09:25:15"),
        ("TW", "2026-09-13 09:25:20", "2026-09-13 09:50:00"),
        ("IN", "2026-09-13 09:50:00", "2026-09-13 10:05:30"),
    ],
    "livingroom-reset-seated-fd68": [
        ("IN", "2026-09-11 21:05:30", "2026-09-11 21:20:00"),
        ("EMPTY", "2026-09-11 21:20:30", "2026-09-11 21:27:30"),
        ("PET", "2026-09-11 21:28:00", "2026-09-11 21:33:00"),
        ("EMPTY", "2026-09-11 21:33:30", "2026-09-11 21:39:30"),
        ("IN", "2026-09-11 21:39:40", "2026-09-11 21:55:00"),
    ],
    "stove-case-0913-fd68": [
        ("IN", "2026-09-13 09:10:00", "2026-09-13 09:23:30"),
    ],
}

SENSOR = {
    "throughwall-morning-d06e": "d06e",
    "bathroom-visit-2204-d06e": "d06e",
    "stove-case-0913-d06e": "d06e",
    "labeled-sessions-0909-d06e": "d06e",
    "livingroom-reset-seated-fd68": "fd68",
    "stove-case-0913-fd68": "fd68",
}


def local(s: str) -> float:
    return time.mktime(time.strptime(s, "%Y-%m-%d %H:%M:%S"))


def clock(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts))


@dataclass
class Fixture:
    name: str
    sensor: str
    ts: np.ndarray
    move: np.ndarray
    still: np.ndarray
    spans: list[tuple[str, float, float]]

    def mask(self, a: float, b: float) -> np.ndarray:
        return (self.ts >= a) & (self.ts < b)

    def class_spans(self, cls: str) -> list[tuple[str, float, float]]:
        return [s for s in self.spans if s[0] == cls]

    def class_mask(self, cls: str) -> np.ndarray:
        m = np.zeros(len(self.ts), dtype=bool)
        for _, a, b in self.class_spans(cls):
            m |= self.mask(a, b)
        return m


def _labeled_spans(con: sqlite3.Connection, last_ts: float) -> list[tuple[str, float, float]]:
    rows = [
        (ts, json.loads(p)["label"])
        for ts, k, p in con.execute("SELECT ts_utc, kind, payload FROM events ORDER BY ts_utc")
        if k == "label"
    ]
    out = []
    bad_stove = local(CONTAMINATED_STOVE_START)
    for i, (ts, label) in enumerate(rows):
        cls = LABEL_CLASS.get(label)
        if cls is None:
            continue
        end = rows[i + 1][0] if i + 1 < len(rows) else last_ts
        if label == "stove" and abs(ts - bad_stove) < 60:
            continue
        if label == "island":
            end -= ISLAND_TAIL_TRIM_S
        end -= min(ARRIVAL_LEAD_S, (end - ts) / 2)
        if end - ts > 8:
            out.append((cls, ts, end))
    return out


def load(name: str) -> Fixture:
    db = FIXTURES / f"{name}.db"
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute("SELECT ts, move, still FROM frames ORDER BY ts").fetchall()
    ts = np.array([r[0] for r in rows], dtype=float)
    move = np.array([list(bytes(r[1])) for r in rows], dtype=float)
    still = np.array([list(bytes(r[2])) for r in rows], dtype=float)
    if name in SPANS:
        spans = [(c, local(a), local(b)) for c, a, b in SPANS[name]]
    else:
        spans = _labeled_spans(con, ts[-1])
    return Fixture(name, SENSOR[name], ts, move, still, spans)


def all_fixtures() -> dict[str, Fixture]:
    return {n: load(n) for n in SENSOR}


def ambient_floor(fx: Fixture, fallback: dict[str, np.ndarray] | None = None) -> tuple[np.ndarray, np.ndarray, str]:
    m = fx.class_mask("EMPTY")
    if m.sum() >= 300:
        return np.median(fx.move[m], axis=0), np.median(fx.still[m], axis=0), "own"
    assert fallback is not None
    return fallback["move"], fallback["still"], "sensor"


def sensor_floors(fixtures: dict[str, Fixture]) -> dict[str, dict[str, np.ndarray]]:
    out: dict[str, dict[str, np.ndarray]] = {}
    for sensor in {f.sensor for f in fixtures.values()}:
        mv, st = [], []
        for fx in fixtures.values():
            if fx.sensor != sensor:
                continue
            m = fx.class_mask("EMPTY")
            if m.sum():
                mv.append(fx.move[m])
                st.append(fx.still[m])
        out[sensor] = {
            "move": np.median(np.vstack(mv), axis=0),
            "still": np.median(np.vstack(st), axis=0),
        }
    return out
