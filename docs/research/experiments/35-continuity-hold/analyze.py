"""Experiment-only per-gate continuity hold under the full balanced stack."""

import importlib.util
import json
from collections import deque
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("experiment33_continuity", HERE.parent / "33-entry-change-hold/analyze.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
s = e.stack


class ContinuityHold:
    """Low quantile of added still energy in each gate, relative to entry."""

    def __init__(self, retention=0.4, window_s=3.0):
        self.retention = retention
        self.window_s = window_s
        self.history = deque()
        self.pre_entry = None
        self.reference = None
        self.support = None
        self.previous = None
        self.score = 0.0
        self.seed_ts = None

    def update(self, ts, move, still, floor, spread, anchor):
        if self.previous is not None and (ts < self.previous or ts - self.previous > 0.55):
            self.history.clear()
            self.support = None
        self.previous = ts
        while self.history and self.history[0][0] < ts - max(self.window_s, 3.0):
            self.history.popleft()
        raw = np.asarray(still[2:9], dtype=float)
        candidates = [v for t, v in self.history if 0.5 <= ts - t <= 2.5]
        self.history.append((ts, raw))
        if self.support is not None:
            if ts - self.seed_ts < self.window_s:
                return True
            window = [v for t, v in self.history if ts - t <= self.window_s]
            added = np.maximum(np.asarray(window) - self.pre_entry, 0)
            stable = np.percentile(added, 20, axis=0)
            self.score = float(np.minimum(stable[self.support], self.reference[self.support]).sum()
                               / self.reference[self.support].sum())
            if self.score >= self.retention:
                return True
            # A weak window starts or continues the departure countdown. Keep
            # the reference so a subsequent steady window can cancel it.
            return False
        self.score = 0.0
        balanced_motion = any(
            move[g] >= 40 and move[g] / max(move[g] + still[g], 1) >= 1 / 3
            for g in range(2, 9)
        )
        if not (anchor.anchored and balanced_motion and candidates):
            return False
        pre = np.median(candidates, axis=0)
        added = np.maximum(raw - pre, 0)
        peak = float(added.max())
        if peak <= 0:
            return False
        support = added >= 0.2 * peak
        if not added[support].sum():
            return False
        self.pre_entry = pre
        self.reference = added
        self.support = support
        self.seed_ts = ts
        return True


def summarize(f, out):
    result = {}
    for cls in ("IN", "TW", "EMPTY"):
        mask = s.old.e.b.mask(f, cls)
        if mask.any():
            result[f"{cls}_occupied_fraction"] = float(out[mask].mean())
    if f.name == "new-living-room":
        mask = s.old.e.b.mask(f, "IN")
        result["longest_false_vacancy_s"] = s.old.e.b.run_stats(mask & ~out, f.ts, mask)["longest_span_s"]
    if f.name == "new-bathroom-walkby":
        mask = (f.ts >= 1789573210) & (f.ts < 1789573240)
        result["walkby_occupied_frames"] = int(out[mask].sum())
    if f.name == "post-deploy-0915":
        target = 1789526209.163709
        mask = (f.ts >= target - 5) & (f.ts < target + 110)
        result["false_window_occupied_frames"] = int(out[mask].sum())
    if f.name in ("labeled-walk-0915", "labeled-loop-0915", "post-deploy-0915"):
        result["clear_offsets_s"] = [v["first_clear_offset_s"] for v in s.assessment(f, out)["visits"]]
    return result


def main():
    living, bathroom, _ = e.new_recording()
    post = s.load("post35", HERE.parent / "28-strength-confirmation/analyze.py").post_fixture()
    fixtures = [s.old.e.b.new_fixture(name) for name in ("labeled-walk-0915.db", "labeled-loop-0915.db")]
    fixtures += [post, living, bathroom]
    result = {"method": "3-second 20th percentile of per-gate raw still energy added since pre-entry; capped by entry delta, summed across entry gates", "fixtures": {}}
    for f in fixtures:
        fl, sp = s.estimates(f)
        variants = {}
        for name, tracker in (("exact_anchor", None), ("continuity_40", ContinuityHold(.4)),
                              ("continuity_30", ContinuityHold(.3)), ("continuity_20", ContinuityHold(.2))):
            out, _, _ = s.replay(f, fl, sp, True, 30.0, same_gate_balance=True, hold_support=tracker)
            variants[name] = summarize(f, out)
        result["fixtures"][f.name] = variants
    (HERE / "results.json").write_text(json.dumps(result, indent=2))
    for name, variants in result["fixtures"].items():
        print(name)
        for variant, d in variants.items():
            print(variant, "IN", round(d.get("IN_occupied_fraction", 0), 3),
                  "gap", round(d.get("longest_false_vacancy_s", 0), 1),
                  "clears", [round(x, 1) if x is not None else None for x in d.get("clear_offsets_s", [])],
                  "false", d.get("false_window_occupied_frames"), "walkby", d.get("walkby_occupied_frames"))


if __name__ == "__main__":
    main()
