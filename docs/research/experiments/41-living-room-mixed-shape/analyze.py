"""Shape survey of the unlabeled seven-hour mixed living-room fixture."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

HERE = Path(__file__).resolve().parent
DB = HERE.parents[3] / "tests/fixtures/recordings/living-room-mixed-2026-09-16.db"
SENSOR = "68:43:B2:C2:7C:4A"
ENTITY = "binary_sensor.living_room_living_room_back_occupancy"
OTHER_ENTITIES = {
    "bathroom": "binary_sensor.downstairs_bathroom_downstairs_bathroom_occupancy",
    "kitchen": "binary_sensor.kitchen_kitchen_occupancy",
}


def local_ts(hour, minute=0):
    return datetime(2026, 9, 16, hour, minute, tzinfo=ZoneInfo("America/New_York")).timestamp()


def describe(t, centroid, kurtosis, state, start, end):
    mask = (t >= start) & (t < end)
    result = {"frames": int(mask.sum()), "integration_on_fraction": float(state[mask].mean())}
    for name, values in (("centroid", centroid), ("kurtosis", kurtosis)):
        result[name + "_p10_median_p90"] = np.percentile(values[mask], [10, 50, 90]).tolist()
        result[name + "_median_when_integration_off"] = float(np.median(values[mask & ~state])) if (mask & ~state).any() else None
        result[name + "_median_when_integration_on"] = float(np.median(values[mask & state])) if (mask & state).any() else None
    return result


def align_states(rows, t):
    state_t = np.array([r[0] for r in rows])
    state_v = np.array([r[1] == "on" for r in rows])
    return state_v[np.maximum(np.searchsorted(state_t, t, side="right") - 1, 0)]


def main():
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as con:
        rows = con.execute("SELECT ts,still FROM frames WHERE sensor_id=? ORDER BY ts", (SENSOR,)).fetchall()
        states = con.execute("SELECT ts,state FROM states WHERE entity_id=? ORDER BY ts", (ENTITY,)).fetchall()
        other_rows = {name: con.execute("SELECT ts,state FROM states WHERE entity_id=? ORDER BY ts", (entity,)).fetchall()
                      for name, entity in OTHER_ENTITIES.items()}
        labels = con.execute("SELECT person,room,ts_start,ts_end,note FROM labels").fetchall()
    t = np.array([r[0] for r in rows])
    still = np.array([list(r[1]) for r in rows], float)[:, 2:9]
    centroid = (still @ np.arange(2, 9)) / np.maximum(still.sum(axis=1), 1)
    z = (still - still.mean(axis=1, keepdims=True)) / np.maximum(still.std(axis=1, keepdims=True), 1e-9)
    kurtosis = np.mean(z**4, axis=1)
    state = align_states(states, t)
    other_state = {name: align_states(rows, t) for name, rows in other_rows.items()}
    periods = {
        "known_empty_1139_1140": (local_ts(11, 39), local_ts(11, 40)),
        "known_occupied_1141_1158": (local_ts(11, 41), local_ts(11, 58)),
        "mostly_living_room_1200_1300": (local_ts(12), local_ts(13)),
        "exploratory_1300_1400": (local_ts(13), local_ts(14)),
        "exploratory_1400_1600": (local_ts(14), local_ts(16)),
        "exploratory_1600_1700": (local_ts(16), local_ts(17)),
    }
    result = {"labels": labels, "sensor_id": SENSOR,
              "method": "still gates 2-8 shape, no occupancy labels outside known prior narrative; states are integration output, not ground truth",
              "periods": {name: describe(t, centroid, kurtosis, state, *bounds)
                          for name, bounds in periods.items()}}
    result["isolated_flapping"] = {}
    for name, bounds in {
        "1200_1220": (local_ts(12), local_ts(12, 20)),
        "1230_1250": (local_ts(12, 30), local_ts(12, 50)),
    }.items():
        mask = (t >= bounds[0]) & (t < bounds[1])
        state_slice = state[mask]
        result["isolated_flapping"][name] = {
            "living_room_transitions": int(np.count_nonzero(state_slice[1:] != state_slice[:-1])),
            "living_room_on_fraction": float(state_slice.mean()),
            "other_room_on_fraction": {k: float(v[mask].mean()) for k, v in other_state.items()},
            "centroid_median_lr_on": float(np.median(centroid[mask & state])),
            "centroid_median_lr_off": float(np.median(centroid[mask & ~state])),
            "kurtosis_median_lr_on": float(np.median(kurtosis[mask & state])),
            "kurtosis_median_lr_off": float(np.median(kurtosis[mask & ~state])),
        }
    (HERE / "results.json").write_text(json.dumps(result, indent=2))
    for name, period in result["periods"].items():
        print(name, "on", round(period["integration_on_fraction"], 3),
              "centroid", round(period["centroid_p10_median_p90"][1], 3),
              "kurtosis", round(period["kurtosis_p10_median_p90"][1], 3))


if __name__ == "__main__":
    main()
