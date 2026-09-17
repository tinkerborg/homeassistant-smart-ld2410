"""Hold windows against normalized shape changes introduced by motion."""
import importlib.util
import json
from collections import deque
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("contrast47", HERE.parent / "45-motion-shape-bank/analyze.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
s = e.s


class ContrastiveShapeBank:
    def __init__(self, min_support, bank_size=4, window_s=20):
        self.min_support = min_support
        self.window_s = window_s
        self.history = deque()
        self.pending = deque()
        self.bank = deque(maxlen=bank_size)
        self.previous_template = None
        self.total_prototypes = 0

    def reset(self):
        self.history.clear()
        self.pending.clear()
        self.bank.clear()
        self.previous_template = None

    def observe(self, ts, still):
        self.history.append((ts, e.profile(still)))
        while self.history and self.history[0][0] < ts - self.window_s - 3:
            self.history.popleft()

    def observe_anchor(self, ts, move, still, anchor):
        template = anchor.template
        balanced = any(
            move[g] >= 40 and move[g] / max(move[g] + still[g], 1) >= 1 / 3
            for g in range(2, 9)
        )
        if template is not None and template != self.previous_template and balanced:
            before = [p for t, p in self.history if .3 <= ts - t <= 2.5]
            if len(before) >= 3:
                self.pending.append((ts + 2, np.median(before, axis=0)))
        self.previous_template = template
        while self.pending and self.pending[0][0] <= ts:
            _, pre = self.pending.popleft()
            post = self.history[-1][1]
            delta = post - pre
            norm2 = float(delta @ delta)
            if norm2 >= .05:
                self.bank.append((pre, delta, norm2))
                self.total_prototypes += 1

    def occupied_looking(self, start, end):
        samples = [p for t, p in self.history if start <= t <= end]
        if not samples or not self.bank:
            return False
        profiles = np.asarray(samples)
        support = np.stack([(profiles - pre) @ delta / norm2
                            for pre, delta, norm2 in self.bank], axis=1)
        return float(np.median(np.max(support, axis=1))) >= self.min_support


def main():
    living, bathroom, _ = e.e.e.e.e.new_recording()
    post = s.load("post47", HERE.parent / "28-strength-confirmation/analyze.py").post_fixture()
    fixtures = [s.old.e.b.new_fixture(n) for n in ("labeled-walk-0915.db", "labeled-loop-0915.db")]
    fixtures += [post, living, bathroom, e.e.e.load_mixed()]
    result = {"method": "Entry-only anchor; each credible motion update saves z-scored still profile change from 0.3-2.5 s before to 2 s after. Every 20 s, review median shape-change projection against the most recent four references. No labels or raw energy in rule.", "fixtures": {}}
    for f in fixtures:
        fl, sp = s.estimates(f)
        variants = {}
        for name, reviewer in (("exact_anchor", None),
                               ("contrast_0_3", ContrastiveShapeBank(.3)),
                               ("contrast_0_5", ContrastiveShapeBank(.5)),
                               ("contrast_0_7", ContrastiveShapeBank(.7))):
            out, _, _ = s.replay(f, fl, sp, True, 30.0 if reviewer is None else 20.0,
                                 same_gate_balance=True, hold_review=reviewer,
                                 entry_only_anchor=reviewer is not None)
            metrics = e.e.e.mixed_summary(f, out) if f.name == "mixed-living-room" else e.e.e.e.summarize(f, out)
            if reviewer is not None:
                metrics["prototypes_recorded"] = reviewer.total_prototypes
            variants[name] = metrics
        result["fixtures"][f.name] = variants
    (HERE / "results.json").write_text(json.dumps(result, indent=2))
    for name, variants in result["fixtures"].items():
        print(name)
        for variant, metrics in variants.items():
            print(variant, json.dumps(metrics))


if __name__ == "__main__":
    main()
