"""Entry-only anchor; review temporal path of normalized still-gate shape."""
import importlib.util
import json
from collections import deque
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("evolution46", HERE.parent / "43-end-of-hold-shape-review/analyze.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
s = e.s


class WindowShapePath:
    def __init__(self, max_path, window_s=30):
        self.max_path = max_path
        self.window_s = window_s
        self.history = deque()
        self.reviews = []

    def reset(self):
        self.history.clear()

    def observe(self, ts, still):
        x = np.asarray(still[2:9], float)
        std = float(x.std())
        z = (x - x.mean()) / std if std > 1e-9 else np.zeros(7)
        self.history.append((ts, z))
        while self.history and self.history[0][0] < ts - self.window_s - 1:
            self.history.popleft()

    def occupied_looking(self, start, end):
        rows = [(t, z) for t, z in self.history if start <= t <= end]
        if len(rows) < 10:
            return False
        times = np.asarray([t for t, _ in rows])
        profiles = np.asarray([z for _, z in rows])
        adjacent = np.diff(times) <= .55
        paths = np.linalg.norm(np.diff(profiles, axis=0), axis=1)
        path = float(np.mean(paths[adjacent])) if adjacent.any() else float("inf")
        keep = path <= self.max_path
        self.reviews.append({"ts": end, "mean_shape_path": path, "kept": keep})
        return keep


def main():
    living, bathroom, _ = e.e.e.e.new_recording()
    post = s.load("post46", HERE.parent / "28-strength-confirmation/analyze.py").post_fixture()
    fixtures = [s.old.e.b.new_fixture(n) for n in ("labeled-walk-0915.db", "labeled-loop-0915.db")]
    fixtures += [post, living, bathroom, e.e.load_mixed()]
    result = {"method": "Entry-only balanced anchor; at each 30 s hold boundary, review mean frame-to-frame Euclidean path of z-scored still-gate profile. Lower path means more temporally coherent shape, regardless of gate position or magnitude. Labels evaluate only.", "fixtures": {}}
    for f in fixtures:
        fl, sp = s.estimates(f)
        variants = {}
        for name, reviewer in (("exact_anchor", None),
                               ("shape_path_0_08", WindowShapePath(.08)),
                               ("shape_path_0_10", WindowShapePath(.10)),
                               ("shape_path_0_12", WindowShapePath(.12))):
            out, _, _ = s.replay(f, fl, sp, True, 30.0, same_gate_balance=True,
                                 hold_review=reviewer, entry_only_anchor=reviewer is not None)
            metrics = e.e.mixed_summary(f, out) if f.name == "mixed-living-room" else e.e.e.summarize(f, out)
            if reviewer is not None:
                metrics["windows_kept"] = sum(r["kept"] for r in reviewer.reviews)
                metrics["windows_cleared"] = sum(not r["kept"] for r in reviewer.reviews)
            variants[name] = metrics
        result["fixtures"][f.name] = variants
    (HERE / "results.json").write_text(json.dumps(result, indent=2))
    for name, variants in result["fixtures"].items():
        print(name)
        for variant, metrics in variants.items():
            print(variant, json.dumps(metrics))


if __name__ == "__main__":
    main()
