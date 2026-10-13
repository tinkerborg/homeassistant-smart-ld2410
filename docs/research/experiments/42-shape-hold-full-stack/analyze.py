"""Experiment-only scale-free gate-shape hold in the full balanced stack."""
import importlib.util
import json
from collections import deque
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("shape42", HERE.parent / "35-continuity-hold/analyze.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
s = e.s


class ShapeHold:
    def __init__(self, max_kurtosis, window_s=0):
        self.max_kurtosis = max_kurtosis
        self.window_s = window_s
        self.history = deque()

    def reset(self):
        self.history.clear()

    def update(self, ts, move, still, floor, spread, anchor):
        x = np.asarray(still[2:9], float)
        std = float(x.std())
        if std <= 1e-9:
            return anchor.anchored
        z = (x - x.mean()) / std
        kurtosis = float(np.mean(z**4))
        self.history.append((ts, kurtosis))
        while self.history and self.history[0][0] < ts - self.window_s:
            self.history.popleft()
        if self.window_s and (ts - self.history[0][0] < self.window_s * .9):
            return anchor.anchored
        stable_kurtosis = float(np.median([v for _, v in self.history]))
        return anchor.anchored or stable_kurtosis <= self.max_kurtosis


def load_mixed():
    db = s.ROOT / "tests/fixtures/recordings/living-room-mixed-2026-09-16.db"
    return e.e.fixture("mixed-living-room", "68:43:B2:C2:7C:4A", db, [])


def mixed_summary(f, out):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    zone = ZoneInfo("America/New_York")
    def when(h, m=0):
        return datetime(2026, 9, 16, h, m, tzinfo=zone).timestamp()
    periods = {"known_empty": (when(11, 39), when(11, 40)),
               "known_occupied": (when(11, 41), when(11, 58)),
               "isolated_flapping_1200_1220": (when(12), when(12, 20)),
               "isolated_flapping_1230_1250": (when(12, 30), when(12, 50)),
               "unverified_quiet_1400_1600": (when(14), when(16))}
    result = {}
    for name, (a, b) in periods.items():
        mask = (f.ts >= a) & (f.ts < b)
        x = out[mask]
        result[name] = {"occupied_fraction": float(x.mean()),
                        "transitions": int(np.count_nonzero(x[1:] != x[:-1]))}
    return result


def main():
    living, bathroom, _ = e.e.new_recording()
    post = s.load("post42", HERE.parent / "28-strength-confirmation/analyze.py").post_fixture()
    fixtures = [s.old.e.b.new_fixture(n) for n in ("labeled-walk-0915.db", "labeled-loop-0915.db")]
    fixtures += [post, living, bathroom, load_mixed()]
    result = {"method": "Original balanced full-stack entry; hold supported by original anchor OR per-frame z-scored still-gate kurtosis below a single dimensionless cutoff; 30 s departure hold. Labels only evaluate.", "fixtures": {}}
    for f in fixtures:
        fl, sp = s.estimates(f)
        variants = {}
        for name, tracker in (("exact_anchor", None),
                              ("shape_kurtosis_1_8", ShapeHold(1.8)),
                              ("shape_kurtosis_2_0", ShapeHold(2.0)),
                              ("shape_kurtosis_2_2", ShapeHold(2.2)),
                              ("shape_kurtosis_1_8_2s", ShapeHold(1.8, 2)),
                              ("shape_kurtosis_2_0_2s", ShapeHold(2.0, 2)),
                              ("shape_kurtosis_1_8_5s", ShapeHold(1.8, 5)),
                              ("shape_kurtosis_2_0_5s", ShapeHold(2.0, 5))):
            out, _, _ = s.replay(f, fl, sp, True, 30.0, same_gate_balance=True, hold_support=tracker)
            variants[name] = mixed_summary(f, out) if f.name == "mixed-living-room" else e.summarize(f, out)
        result["fixtures"][f.name] = variants
    (HERE / "results.json").write_text(json.dumps(result, indent=2))
    for name, variants in result["fixtures"].items():
        print(name)
        for variant, metrics in variants.items():
            print(variant, json.dumps(metrics))


if __name__ == "__main__":
    main()
