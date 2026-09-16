#!/usr/bin/env python3
"""Read-only audit of post-deploy bathroom transitions and raw gate evidence.

The database is opened with SQLite's immutable/read-only URI.  For each
bathroom ``occupied`` event, print the event payload and every raw frame in
the preceding window.  Gate arrays are shown as gates 2..8 because that is
the motion-anchor candidate band; the source arrays remain untouched.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SENSOR = "D0:6E:81:D2:5D:A6"


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="milliseconds")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("db", type=Path)
    ap.add_argument("--sensor", default=SENSOR)
    ap.add_argument("--window", type=float, default=5.0)
    args = ap.parse_args()
    # URI mode=ro prevents writes; immutable avoids journal/WAL side effects.
    db_uri = f"file:{args.db.resolve()}?mode=ro&immutable=1"
    with sqlite3.connect(db_uri, uri=True) as db:
        events = db.execute(
            "SELECT ts_utc, kind, payload FROM events "
            "WHERE sensor_id=? AND kind='occupied' ORDER BY ts_utc",
            (args.sensor,),
        ).fetchall()
        print(f"sensor={args.sensor} occupied_events={len(events)} window_s={args.window}")
        for event_ts, kind, payload_text in events:
            payload = json.loads(payload_text) if payload_text else None
            rows = db.execute(
                "SELECT ts, move, still FROM frames "
                "WHERE sensor_id=? AND ts>=? AND ts<=? ORDER BY ts",
                (args.sensor, event_ts - args.window, event_ts),
            ).fetchall()
            print(f"\nEVENT ts={event_ts:.6f} utc={iso(event_ts)} kind={kind} payload={json.dumps(payload, sort_keys=True)}")
            print("dt_s move_g2_g8 still_g2_g8 peak_move_ge40_gates")
            for ts, move_blob, still_blob in rows:
                move = list(move_blob[2:9])
                still = list(still_blob[2:9])
                gates = [g + 2 for g, value in enumerate(move) if value >= 40]
                print(f"{ts-event_ts:+7.3f} {move!s:25} {still!s:25} {gates}")


if __name__ == "__main__":
    main()
