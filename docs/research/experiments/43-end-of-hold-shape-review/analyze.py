"""Review the whole shape window only when the normal hold countdown expires."""
import importlib.util
import json
from collections import deque
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("shape43", HERE.parent / "42-shape-hold-full-stack/analyze.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
s = e.s


class ShapeWindowReview:
    def __init__(self, max_kurtosis, max_window_s=30, consecutive_clear_windows=1, percentile=50):
        self.max_kurtosis = max_kurtosis
        self.max_window_s = max_window_s
        self.consecutive_clear_windows = consecutive_clear_windows
        self.percentile = percentile
        self.clear_streak = 0
        self.history = deque()
        self.reviews = []

    def reset(self):
        self.history.clear()
        self.clear_streak = 0

    def observe(self, ts, still):
        x = np.asarray(still[2:9], float)
        std = float(x.std())
        if std <= 1e-9:
            kurtosis = float("inf")
        else:
            z = (x - x.mean()) / std
            kurtosis = float(np.mean(z**4))
        self.history.append((ts, kurtosis))
        while self.history and self.history[0][0] < ts - self.max_window_s - 1:
            self.history.popleft()

    def occupied_looking(self, start, end):
        values = [v for t, v in self.history if start <= t <= end]
        statistic = float(np.percentile(values, self.percentile)) if values else float("inf")
        self.clear_streak = 0 if statistic <= self.max_kurtosis else self.clear_streak + 1
        keep = self.clear_streak < self.consecutive_clear_windows
        self.reviews.append({"ts": end, "window_kurtosis": statistic, "kept": keep})
        return keep


def main():
    living, bathroom, _ = e.e.e.new_recording()
    post = s.load("post43", HERE.parent / "28-strength-confirmation/analyze.py").post_fixture()
    fixtures = [s.old.e.b.new_fixture(n) for n in ("labeled-walk-0915.db", "labeled-loop-0915.db")]
    fixtures += [post, living, bathroom, e.load_mixed()]
    result = {"method": "Balanced-stack anchor qualifies entry only. Thereafter, review median z-scored still-profile kurtosis at each 30 s boundary; if occupied-looking, start another 30 s window, else clear. No anchor or per-frame shape refreshes occupancy. Labels evaluate only.", "fixtures": {}}
    for f in fixtures:
        fl, sp = s.estimates(f)
        variants = {}
        for name, threshold, hold_s in (("exact_anchor", None, 30),
                                        ("window_kurtosis_1_8", 1.8, 30),
                                        ("window_kurtosis_2_0", 2.0, 30),
                                        ("window_kurtosis_2_1", 2.1, 30),
                                        ("window_kurtosis_2_15", 2.15, 30),
                                        ("window_kurtosis_2_2", 2.2, 30),
                                        ("window_kurtosis_2_15_10s", 2.15, 10),
                                        ("window_kurtosis_2_15_20s", 2.15, 20),
                                        ("window_kurtosis_2_15_10s_2bad", 2.15, 10),
                                        ("window_kurtosis_2_15_10s_3bad", 2.15, 10),
                                        ("window_kurtosis_2_0_10s_2bad", 2.0, 10)):
            clear_windows = 3 if name.endswith("3bad") else 2 if name.endswith("2bad") else 1
            review = None if threshold is None else ShapeWindowReview(threshold, hold_s, clear_windows)
            out, _, _ = s.replay(f, fl, sp, True, float(hold_s), same_gate_balance=True,
                                 hold_review=review, entry_only_anchor=review is not None)
            metrics = e.mixed_summary(f, out) if f.name == "mixed-living-room" else e.e.summarize(f, out)
            if review is not None:
                metrics["shape_reviews_kept"] = sum(r["kept"] for r in review.reviews)
                metrics["shape_reviews_cleared"] = sum(not r["kept"] for r in review.reviews)
            variants[name] = metrics
        result["fixtures"][f.name] = variants
    (HERE / "results.json").write_text(json.dumps(result, indent=2))
    for name, variants in result["fixtures"].items():
        print(name)
        for variant, metrics in variants.items():
            print(variant, json.dumps(metrics))


if __name__ == "__main__":
    main()
