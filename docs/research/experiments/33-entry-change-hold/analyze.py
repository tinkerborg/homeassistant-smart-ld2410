"""Experiment-only pre-entry contrast hold with full stack and balance guard."""

import importlib.util
import json
import sqlite3
from collections import deque
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("stack33", HERE.parent / "26-motion-anchor-stack/replay.py")
stack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stack)
Fixture = stack.old.e.b.data.Fixture


class EntryChangeHold:
    """Track the raw still-energy excess over a pre-entry snapshot."""

    def __init__(self, retention=0.4):
        self.retention = retention
        self.history = deque()
        self.pre_entry = None
        self.reference = 0.0
        self.band = None
        self.previous = None

    def update(self, ts, move, still, floor, spread, anchor):
        if self.previous is not None and (ts < self.previous or ts - self.previous > 0.55):
            self.history.clear()
            self.pre_entry = None
            self.band = None
        self.previous = ts
        while self.history and self.history[0][0] < ts - 3:
            self.history.popleft()
        signal = np.asarray(still[2:9], dtype=float)
        candidates = [v for t, v in self.history if 0.5 <= ts - t <= 2.5]
        if self.band is not None:
            excess = np.maximum(signal - self.pre_entry, 0)
            strength = float(excess[self.band].sum()) / self.reference
            if strength >= self.retention:
                self.history.append((ts, signal))
                return True
            self.band = None
        balanced_motion = any(
            move[g] >= 40 and move[g] / max(move[g] + still[g], 1) >= 1 / 3
            for g in range(2, 9)
        )
        if anchor.anchored and balanced_motion and candidates:
            pre = np.median(candidates, axis=0)
            excess = np.maximum(signal - pre, 0)
            peak = float(excess.max())
            if peak > 0:
                band = excess >= 0.2 * peak
                reference = float(excess[band].sum())
                if reference > 0:
                    self.pre_entry = pre
                    self.band = band
                    self.reference = reference
        self.history.append((ts, signal))
        return self.band is not None


def fixture(name, sensor, db, spans):
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
        rows = con.execute("SELECT ts,move,still FROM frames WHERE sensor_id=? ORDER BY ts", (sensor,)).fetchall()
    return Fixture(name, sensor, np.array([r[0] for r in rows]),
                   np.array([list(r[1]) for r in rows], float),
                   np.array([list(r[2]) for r in rows], float), spans)


def new_recording():
    db = stack.ROOT / "tests/fixtures/recordings/living-room-continuous-occupancy-2026-09-16.db"
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
        labels = con.execute("SELECT room,ts_start,ts_end FROM labels ORDER BY ts_start").fetchall()
    living_entry = labels[-1][1]
    kitchen_start = next(a for room, a, _ in labels if room == "kitchen")
    kitchen_end = next(b for room, _, b in labels if room == "kitchen")
    walk_end = living_entry
    living = fixture("new-living-room", "68:43:B2:C2:7C:4A", db,
                     [("EMPTY", kitchen_start, kitchen_end), ("IN", living_entry, labels[-1][2])])
    bathroom = fixture("new-bathroom-walkby", "D0:6E:81:D2:5D:A6", db,
                       [("TW", kitchen_start, walk_end), ("EMPTY", walk_end, labels[-1][2])])
    return living, bathroom, (kitchen_start, kitchen_end, walk_end, living_entry)


def run():
    recent_living, recent_bath, times = new_recording()
    post = stack.load("post33", HERE.parent / "28-strength-confirmation/analyze.py").post_fixture()
    fixtures = [stack.old.e.b.new_fixture(n) for n in ("labeled-walk-0915.db", "labeled-loop-0915.db")]
    fixtures += [post, recent_living, recent_bath]
    result = {"method": "raw still excess at initial anchor over median 0.5-2.5s pre-entry; support gates >=20% of peak; retain >=40% initial sum", "variants": {}}
    for f in fixtures:
        fl, sp = stack.estimates(f)
        variants = {}
        for hold in (0.0, 30.0):
            for name, tracker in (("exact", None), ("entry_change_40", EntryChangeHold(0.4)),
                                  ("entry_change_20", EntryChangeHold(0.2))):
                occupied, _, _ = stack.replay(f, fl, sp, True, hold, same_gate_balance=True, hold_support=tracker)
                onsets = np.flatnonzero(occupied & ~np.r_[False, occupied[:-1]])
                item = {"onsets": [float(f.ts[i]) for i in onsets]}
                for cls in ("IN", "TW", "EMPTY"):
                    mask = stack.old.e.b.mask(f, cls)
                    if mask.any():
                        item[f"{cls}_occupied_fraction"] = float(occupied[mask].mean())
                if f.name == "new-living-room":
                    mask = stack.old.e.b.mask(f, "IN")
                    item["entry_delay_s"] = next((float(f.ts[i] - times[3]) for i in np.flatnonzero(mask & occupied)), None)
                    item["vacancy_runs"] = stack.old.e.b.run_stats(mask & ~occupied, f.ts, mask)
                if f.name == "new-bathroom-walkby":
                    mask = (f.ts >= 1789573210) & (f.ts < 1789573240)
                    item["walkby_occupied_frames"] = int(occupied[mask].sum())
                    item["walkby_onsets"] = [float(f.ts[i]) for i in onsets if mask[i]]
                if f.name == "post-deploy-0915":
                    target = 1789526209.163709
                    mask = (f.ts >= target - 5) & (f.ts < target + 110)
                    item["false_window_occupied_frames"] = int(occupied[mask].sum())
                if f.name in ("labeled-walk-0915", "labeled-loop-0915", "post-deploy-0915"):
                    item["visits"] = stack.assessment(f, occupied)["visits"]
                variants[f"{name}_hold{hold:g}"] = item
        result["variants"][f.name] = variants
    (HERE / "results.json").write_text(json.dumps(result, indent=2))
    for name, variants in result["variants"].items():
        print(name)
        for variant, item in variants.items():
            print(variant, "IN", round(item.get("IN_occupied_fraction", 0), 3),
                  "entry", item.get("entry_delay_s"), "walkby", item.get("walkby_occupied_frames"),
                  "post_false", item.get("false_window_occupied_frames"))


if __name__ == "__main__":
    run()
