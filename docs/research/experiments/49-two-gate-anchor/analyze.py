"""Reject one-gate false anchors with subsecond two-gate motion corroboration."""
import importlib.util
import json
from collections import deque
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("two_gate49", HERE.parent / "48-bathroom-false-clear/analyze.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
s = e.s


class TwoGateAnchor(s.MotionAnchor):
    def __init__(self, window_s=.3):
        super().__init__()
        self.window_s = window_s
        self.gate_history = deque()

    def update(self, ts_mono, move, still, floor, spread):
        previous = self._previous_ts
        existing = self.template is not None and (
            previous is None or 0 <= ts_mono - previous <= self.max_gap_s
        )
        balanced = tuple(
            move[g] >= 40 and move[g] / max(move[g] + still[g], 1) >= 1 / 3
            for g in range(2, 9)
        )
        self.gate_history.append((ts_mono, balanced))
        while self.gate_history and self.gate_history[0][0] < ts_mono - self.window_s:
            self.gate_history.popleft()
        corroborated = sum(any(mask[g] for _, mask in self.gate_history) for g in range(7)) >= 2
        threshold = self.motion_threshold
        if not existing and not corroborated:
            self.motion_threshold = float("inf")
        try:
            return super().update(ts_mono, move, still, floor, spread)
        finally:
            self.motion_threshold = threshold


def episodes(t, on):
    starts = np.flatnonzero(on & ~np.r_[False, on[:-1]])
    ends = np.flatnonzero(on & ~np.r_[on[1:], False])
    return [float(t[b] - t[a]) for a, b in zip(starts, ends)]


def main():
    root = s.ROOT / "tests/fixtures/recordings"
    living, _, _ = e.bank.e.e.e.e.new_recording()
    fixtures = [s.old.e.b.new_fixture(n) for n in ("labeled-walk-0915.db", "labeled-loop-0915.db")]
    fixtures += [e.fixture(),
                 s.load("post49_fixture", HERE.parent / "28-strength-confirmation/analyze.py").post_fixture(),
                 living]
    fixtures += [e.bank.e.e.e.e.fixture("overnight-bathroom", "D0:6E:81:D2:5D:A6",
                                        root / "overnight-2026-09-16.db", [])]
    result = {"method": "Require balanced motion at two distinct gates within 0.3 s to create an anchor; subsequent template updates unchanged. Compare full balanced stack and recent-four 20s hold. No labels in rule.", "fixtures": {}}
    for f in fixtures:
        fl, sp = s.estimates(f)
        variants = {}
        for name, factory, reviewer in (
            ("current_balanced", None, None),
            ("two_gate_baseline", TwoGateAnchor, None),
            ("motion55_baseline", lambda: s.SameGateBalanceAnchor(motion_threshold=55), None),
            ("recent4_balanced", None, e.bank.MotionShapeBank(.8, 4, 20)),
            ("recent4_two_gate", TwoGateAnchor, e.bank.MotionShapeBank(.8, 4, 20)),
            ("recent4_motion55", lambda: s.SameGateBalanceAnchor(motion_threshold=55), e.bank.MotionShapeBank(.8, 4, 20)),
            ("recent4_balanced_corr_0_78", None, e.bank.MotionShapeBank(.78, 4, 20)),
            ("recent4_motion55_corr_0_78", lambda: s.SameGateBalanceAnchor(motion_threshold=55), e.bank.MotionShapeBank(.78, 4, 20)),
        ):
            hold_s = 30 if reviewer is None else 20
            out, _, _ = s.replay(f, fl, sp, True, float(hold_s), same_gate_balance=True,
                                 hold_review=reviewer, entry_only_anchor=reviewer is not None,
                                 anchor_factory=factory)
            if f.name == "bathroom-false-clear":
                metrics = e.summarize(f, out)
            elif f.name == "new-living-room":
                metrics = e.bank.e.e.e.summarize(f, out)
                metrics["visits"] = s.assessment(f, out)["visits"]
            elif f.name == "overnight-bathroom":
                spans = episodes(f.ts, out)
                metrics = {"episode_count": len(spans), "longest_episode_s": max(spans, default=0),
                           "occupied_fraction": float(out.mean())}
            else:
                metrics = e.bank.e.e.e.summarize(f, out)
                metrics["visits"] = s.assessment(f, out)["visits"]
            variants[name] = metrics
        result["fixtures"][f.name] = variants
    (HERE / "results.json").write_text(json.dumps(result, indent=2))
    for name, variants in result["fixtures"].items():
        print(name)
        for variant, metrics in variants.items():
            print(variant, json.dumps(metrics))


if __name__ == "__main__":
    main()
