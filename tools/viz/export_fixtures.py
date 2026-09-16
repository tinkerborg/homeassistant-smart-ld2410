"""Build the local Gate Scope viewer from the recording fixtures."""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "recordings"


def local(s: str) -> float:
    return time.mktime(time.strptime(s, "%Y-%m-%d %H:%M:%S"))


TRUTH = {
    "throughwall-morning-d06e": {
        "title": "Bathroom, through-wall morning",
        "spans": [
            ("kitchen activity beyond wall (bathroom EMPTY)", "tw", "2026-09-11 05:00:00", "2026-09-11 05:46:00"),
        ],
    },
    "bathroom-visit-2204-d06e": {
        "title": "Bathroom, confirmed visit",
        "spans": [("toilet visit", "in", "2026-09-11 22:04:01", "2026-09-11 22:06:43")],
    },
    "livingroom-reset-seated-fd68": {
        "title": "Living room, reset while seated",
        "spans": [
            ("seated (learning reset under user)", "in", "2026-09-11 21:04:30", "2026-09-11 21:20:00"),
            ("empty of humans", "empty", "2026-09-11 21:20:30", "2026-09-11 21:39:30"),
            ("cat around gates 4-6", "pet", "2026-09-11 21:28:00", "2026-09-11 21:33:00"),
            ("seated again", "in", "2026-09-11 21:39:40", "2026-09-11 21:55:00"),
        ],
    },
    "stove-case-0913-d06e": {
        "title": "Bathroom, leave-then-far-kitchen",
        "spans": [
            ("toilet visit", "in", "2026-09-13 09:24:00", "2026-09-13 09:25:15"),
            ("user at FAR end of kitchen (bathroom EMPTY)", "tw", "2026-09-13 09:25:20", "2026-09-13 09:50:00"),
            ("clipping hair", "in", "2026-09-13 09:50:00", "2026-09-13 10:05:30"),
        ],
    },
    "stove-case-0913-fd68": {
        "title": "Living room, same window",
        "spans": [("user in living room", "in", "2026-09-13 09:10:00", "2026-09-13 09:23:30")],
    },
    "labeled-sessions-0909-d06e": {"title": "Bathroom, labeled sessions", "spans": []},
}

LABEL_KIND = {"toilet": "in", "stove": "tw", "island": "tw", "hall-walk-by": "tw", "empty": "empty"}


def export(db: Path, out: Path) -> None:
    name = db.stem
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute("SELECT ts, move, still FROM frames ORDER BY ts").fetchall()
    t0 = rows[0][0]
    frames = [[round(ts - t0, 2), bytes(m).hex(), bytes(s).hex()] for ts, m, s in rows]
    events = [
        {"t": round(ts - t0, 2), "kind": k, "payload": p}
        for ts, k, p in con.execute("SELECT ts_utc, kind, payload FROM events ORDER BY ts_utc")
    ]
    truth = TRUTH.get(name, {"title": name, "spans": []})
    spans = [
        {"label": lbl, "kind": kind, "a": round(local(a) - t0, 2), "b": round(local(b) - t0, 2)}
        for lbl, kind, a, b in truth["spans"]
    ]
    labels = [(e["t"], json.loads(e["payload"])["label"]) for e in events if e["kind"] == "label"]
    for i, (t, lbl) in enumerate(labels):
        if lbl == "none":
            continue
        t1 = labels[i + 1][0] if i + 1 < len(labels) else frames[-1][0]
        spans.append({"label": lbl, "kind": LABEL_KIND.get(lbl, "in"), "a": t, "b": t1})
    payload = json.dumps(
            {
                "name": name,
                "title": truth["title"],
                "t0": t0,
                "tz_offset": -time.timezone if not time.daylight else -time.altzone,
                "frames": frames,
                "events": [e for e in events if e["kind"] in ("occupied", "vacant")],
                "spans": spans,
            },
            separators=(",", ":"),
    )
    out.write_text(f'window.__viz=window.__viz||{{}};window.__viz["{name}"]={payload};')
    print(name, len(frames), "frames ->", out)


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("viz-out")
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    for db in sorted(FIXTURES.glob("*.db")):
        export(db, out_dir / "data" / f"{db.stem}.js")
    page = Path(__file__).with_name("gate-scope.html").read_text()
    (out_dir / "gate-scope.html").write_text("<!doctype html><html><head><meta charset=\"utf-8\">" + page + "</html>")
    print("open", out_dir / "gate-scope.html")


if __name__ == "__main__":
    main()
