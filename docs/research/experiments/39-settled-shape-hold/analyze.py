"""Causal, experiment-only settled still-shape hold with the full balanced stack."""

import importlib.util
import json
from collections import deque
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("continuity39", HERE.parent / "35-continuity-hold/analyze.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
s = e.s


class SettledShapeHold:
    def __init__(self, cosine_threshold=.9, min_amplitude=.2):
        self.cosine_threshold = cosine_threshold
        self.min_amplitude = min_amplitude
        self.history = deque()
        self.reset()
        self.activations = 0

    def reset(self):
        self.seed = None
        self.pre = None
        self.training = []
        self.template = None
        self.previous = None

    def update(self, ts, move, still, floor, spread, anchor):
        raw = np.asarray(still[2:9], float)
        if self.previous is not None and (ts < self.previous or ts - self.previous > .55):
            self.reset()
        self.previous = ts
        while self.history and self.history[0][0] < ts - 3:
            self.history.popleft()
        candidates = [v for t, v in self.history if .5 <= ts - t <= 2.5]
        self.history.append((ts, raw))
        if self.seed is None:
            if anchor.anchored and candidates:
                self.seed = ts
                self.pre = np.median(candidates, axis=0)
            return anchor.anchored
        age = ts - self.seed
        residual = np.maximum(raw - self.pre, 0)
        if 30 <= age < 60:
            self.training.append(residual)
        if age >= 60 and self.template is None and len(self.training) >= 100:
            self.template = np.median(self.training, axis=0)
            if np.linalg.norm(self.template) < 1:
                self.template = None
            else:
                self.activations += 1
            self.training.clear()
        if age < 60 or self.template is None:
            return anchor.anchored
        norm = np.linalg.norm(residual)
        template_norm = np.linalg.norm(self.template)
        cosine = float(residual @ self.template / max(norm * template_norm, 1e-9))
        return cosine >= self.cosine_threshold and norm >= self.min_amplitude * template_norm


def main():
    living, bathroom, _ = e.e.new_recording()
    post = s.load("post39", HERE.parent / "28-strength-confirmation/analyze.py").post_fixture()
    fixtures = [s.old.e.b.new_fixture(n) for n in ("labeled-walk-0915.db", "labeled-loop-0915.db")]
    fixtures += [post, living, bathroom]
    result = {"method": "At 60 s after anchored entry, use cosine >=0.9 and amplitude >=20% versus median pre-entry-subtracted still-gate shape from 30-60 s; full stack and same-gate balance; 30 s departure hold", "fixtures": {}}
    for f in fixtures:
        fl, sp = s.estimates(f)
        variants = {}
        for name, tracker in (("exact_anchor", None), ("settled_shape", SettledShapeHold())):
            out, _, _ = s.replay(f, fl, sp, True, 30.0, same_gate_balance=True, hold_support=tracker)
            variants[name] = e.summarize(f, out)
            if tracker is not None:
                variants[name]["settled_template_activations"] = tracker.activations
        result["fixtures"][f.name] = variants
    (HERE / "results.json").write_text(json.dumps(result, indent=2))
    for name, variants in result["fixtures"].items():
        print(name, json.dumps(variants))


if __name__ == "__main__":
    main()
