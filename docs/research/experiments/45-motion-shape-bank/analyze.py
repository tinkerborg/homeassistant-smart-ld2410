"""Compare completed hold windows to shapes following credible motion anchors."""
import importlib.util
import json
from collections import deque
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("shape45", HERE.parent / "43-end-of-hold-shape-review/analyze.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
s = e.s


def profile(still):
    x = np.asarray(still[2:9], float)
    std = float(x.std())
    return (x - x.mean()) / std if std > 1e-9 else np.zeros(7)


class MotionShapeBank:
    def __init__(self, min_similarity, bank_size=64, window_s=30):
        self.min_similarity = min_similarity
        self.window_s = window_s
        self.history = deque()
        self.pending = deque()
        self.bank = deque(maxlen=bank_size)
        self.previous_template = None
        self.total_prototypes = 0
        self.review_count = 0
        self.reviews = []

    def reset(self):
        self.history.clear()
        self.pending.clear()
        self.bank.clear()
        self.previous_template = None

    def observe(self, ts, still):
        p = profile(still)
        self.history.append((ts, p))
        while self.history and self.history[0][0] < ts - self.window_s - 1:
            self.history.popleft()

    def observe_anchor(self, ts, move, still, anchor):
        template = anchor.template
        balanced = any(
            move[g] >= 40 and move[g] / max(move[g] + still[g], 1) >= 1 / 3
            for g in range(2, 9)
        )
        if template is not None and template != self.previous_template and balanced:
            self.pending.append(ts + 2)
        self.previous_template = template
        while self.pending and self.pending[0] <= ts:
            self.pending.popleft()
            self.bank.append(self.history[-1][1].copy())
            self.total_prototypes += 1

    def occupied_looking(self, start, end):
        self.review_count += 1
        samples = [p for t, p in self.history if start <= t <= end]
        if not samples or not self.bank:
            self.reviews.append({"start": start, "end": end, "similarity": None, "kept": False})
            return False
        # Each profile has zero mean and unit variance; dot/7 is Pearson shape correlation.
        similarities = np.asarray(samples) @ np.asarray(self.bank).T / 7
        score = float(np.median(np.max(similarities, axis=1)))
        keep = score >= self.min_similarity
        self.reviews.append({"start": start, "end": end, "similarity": score, "kept": keep})
        return keep


def main():
    living, bathroom, _ = e.e.e.e.new_recording()
    post = s.load("post45", HERE.parent / "28-strength-confirmation/analyze.py").post_fixture()
    fixtures = [s.old.e.b.new_fixture(n) for n in ("labeled-walk-0915.db", "labeled-loop-0915.db")]
    fixtures += [post, living, bathroom, e.e.load_mixed()]
    result = {"method": "Entry-only balanced anchor; each credible template update records the still-gate z-profile 2 s later, permitting a bank of positions. Every 30 s, review median of per-frame maximum shape correlation to the bank; no labels or absolute energy in rule.", "fixtures": {}}
    for f in fixtures:
        fl, sp = s.estimates(f)
        variants = {}
        for name, tracker, hold_s in (("exact_anchor", None, 30),
                                      ("bank_corr_0_4", MotionShapeBank(.4), 30),
                                      ("bank_corr_0_6", MotionShapeBank(.6), 30),
                                      ("bank_corr_0_8", MotionShapeBank(.8), 30),
                                      ("latest_corr_0_6", MotionShapeBank(.6, 1), 30),
                                      ("latest_corr_0_8", MotionShapeBank(.8, 1), 30),
                                      ("latest_corr_0_8_20s", MotionShapeBank(.8, 1, 20), 20),
                                      ("latest_corr_0_8_10s", MotionShapeBank(.8, 1, 10), 10),
                                      ("recent2_corr_0_8_20s", MotionShapeBank(.8, 2, 20), 20),
                                      ("recent4_corr_0_8_20s", MotionShapeBank(.8, 4, 20), 20),
                                      ("recent8_corr_0_8_20s", MotionShapeBank(.8, 8, 20), 20)):
            out, _, _ = s.replay(f, fl, sp, True, float(hold_s), same_gate_balance=True,
                                 hold_review=tracker, entry_only_anchor=tracker is not None)
            metrics = e.e.mixed_summary(f, out) if f.name == "mixed-living-room" else e.e.e.summarize(f, out)
            if tracker is not None:
                metrics["prototypes_recorded"] = tracker.total_prototypes
                metrics["windows_reviewed"] = tracker.review_count
            variants[name] = metrics
        result["fixtures"][f.name] = variants
    (HERE / "results.json").write_text(json.dumps(result, indent=2))
    for name, variants in result["fixtures"].items():
        print(name)
        for variant, metrics in variants.items():
            print(variant, json.dumps(metrics))


if __name__ == "__main__":
    main()
