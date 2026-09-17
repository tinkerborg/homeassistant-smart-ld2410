"""Experiment-only lowest recurring histogram mode in the full balanced stack."""

import importlib.util
import json
import sqlite3
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("experiment35_floor", HERE.parent / "35-continuity-hold/analyze.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
s = e.s

BIN_WIDTH = 2
MODE_BAND = 6
MIN_OBSERVED_S = 60.0


def lowest_recurring_state(counts, sample_rate):
    """Lowest local histogram peak containing a minute of observed samples."""
    bins = np.bincount(np.arange(101) // BIN_WIDTH, weights=counts, minlength=51)
    enough = MIN_OBSERVED_S * sample_rate
    candidates = [k for k, mass in enumerate(bins)
                  if mass >= enough
                  and (k == 0 or mass >= bins[k - 1])
                  and (k == len(bins) - 1 or mass >= bins[k + 1])]
    k = candidates[0] if candidates else int(np.argmax(bins))
    values = np.arange(101)
    inside = values // BIN_WIDTH == k
    mode = s.old.weighted_median(values[inside], counts[inside])
    local = abs(values - mode) <= MODE_BAND
    mad = s.old.weighted_median(abs(values[local] - mode), counts[local])
    return mode, max(1.0, mad)


def estimates(f):
    readings = np.stack((f.move, f.still), axis=1).astype(int)
    counts = np.zeros((2, 9, 101), dtype=int)
    floor = readings[0].astype(float)
    spread = np.ones((2, 9))
    floors = np.zeros_like(readings, dtype=float)
    spreads = np.ones_like(readings, dtype=float)
    last = -float("inf")
    for i, t in enumerate(f.ts):
        for channel in range(2):
            counts[channel, np.arange(9), readings[i, channel]] += 1
        elapsed = float(t - f.ts[0])
        if elapsed >= MIN_OBSERVED_S and t - last >= 5:
            rate = (i + 1) / max(elapsed, 1)
            for channel in range(2):
                for gate in range(9):
                    floor[channel, gate], spread[channel, gate] = lowest_recurring_state(
                        counts[channel, gate], rate
                    )
            last = t
        floors[i] = floor
        spreads[i] = spread
    return floors, spreads


def main():
    living, bathroom, (_, _, _, living_entry) = e.e.new_recording()
    post = s.load("post36", HERE.parent / "28-strength-confirmation/analyze.py").post_fixture()
    fixtures = [s.old.e.b.new_fixture(name) for name in ("labeled-walk-0915.db", "labeled-loop-0915.db")]
    fixtures += [post, living, bathroom]
    cat_db = s.ROOT / "tests/fixtures/recordings/cat-kitchen-0915.db"
    with sqlite3.connect(f"file:{cat_db}?mode=ro", uri=True) as con:
        cat_start, cat_end = con.execute(
            "SELECT MIN(ts),MAX(ts) FROM frames WHERE sensor_id=?", ("B3:26:9E:EE:C5:11",)
        ).fetchone()
    fixtures.append(e.e.fixture("cat-only-kitchen", "B3:26:9E:EE:C5:11", cat_db,
                                [("EMPTY", cat_start, cat_end)]))
    result = {"floor_rule": "lowest 2-unit histogram local peak with >=60 seconds of samples at observed sample rate; otherwise dominant peak", "fixtures": {}}
    for f in fixtures:
        original_fl, original_sp = s.estimates(f)
        low_fl, low_sp = estimates(f)
        variants = {}
        for name, fl, sp in (("dominant", original_fl, original_sp), ("lowest_recurring", low_fl, low_sp)):
            occupied, _, _ = s.replay(f, fl, sp, True, 30.0, same_gate_balance=True)
            variants[name] = e.summarize(f, occupied)
            if f.name == "new-living-room":
                idx = np.searchsorted(f.ts, living_entry)
                later_on = np.flatnonzero(occupied & (np.arange(len(f.ts)) >= idx))
                first_on = int(later_on[0]) if len(later_on) else None
                later_off = np.flatnonzero(~occupied & (np.arange(len(f.ts)) > first_on)) if first_on is not None else []
                variants[name]["first_entry_offset_s"] = None if first_on is None else float(f.ts[first_on] - living_entry)
                variants[name]["first_false_clear_after_entry_s"] = None if not len(later_off) else float(f.ts[later_off[0]] - living_entry)
                variants[name]["preentry_still_floor_gates_2_8"] = fl[idx - 1, 1, 2:9].tolist()
                variants[name]["preentry_still_spread_gates_2_8"] = sp[idx - 1, 1, 2:9].tolist()
        result["fixtures"][f.name] = variants
        # Replaying a prefix must preserve the baseline already seen.
        from dataclasses import replace
        n = len(f.ts) - 300
        prefix = replace(f, ts=f.ts[:n], move=f.move[:n], still=f.still[:n])
        p_fl, p_sp = estimates(prefix)
        assert np.array_equal(p_fl, low_fl[:n]) and np.array_equal(p_sp, low_sp[:n])
    (HERE / "results.json").write_text(json.dumps(result, indent=2))
    for name, variants in result["fixtures"].items():
        print(name)
        for variant, data in variants.items():
            print(variant, "IN", round(data.get("IN_occupied_fraction", 0), 3),
                  "gap", round(data.get("longest_false_vacancy_s", 0), 1),
                  "clear", [round(x, 1) if x is not None else None for x in data.get("clear_offsets_s", [])],
                  "post_false", data.get("false_window_occupied_frames"), "walkby", data.get("walkby_occupied_frames"),
                  "LR_floor", data.get("preentry_still_floor_gates_2_8"))


if __name__ == "__main__":
    main()
