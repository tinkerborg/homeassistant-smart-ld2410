"""Whole-window shape persistence without a fixed entry position."""
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("shape44", HERE.parent / "43-end-of-hold-shape-review/analyze.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
s = e.s


def main():
    living, bathroom, _ = e.e.e.e.new_recording()
    post = s.load("post44", HERE.parent / "28-strength-confirmation/analyze.py").post_fixture()
    fixtures = [s.old.e.b.new_fixture(n) for n in ("labeled-walk-0915.db", "labeled-loop-0915.db")]
    fixtures += [post, living, bathroom, e.e.load_mixed()]
    result = {"method": "Entry-only anchor; every 30 s judge the distribution of per-frame z-scored still-gate kurtosis in the completed window. No fixed gate position or entry template. Percentile 25/50/75 tests how much of a window must retain an occupied-like shape.", "fixtures": {}}
    for f in fixtures:
        fl, sp = s.estimates(f)
        variants = {}
        for percentile in (25, 50, 75):
            review = e.ShapeWindowReview(2.15, 30, percentile=percentile)
            out, _, _ = s.replay(f, fl, sp, True, 30.0, same_gate_balance=True,
                                 hold_review=review, entry_only_anchor=True)
            metrics = e.e.mixed_summary(f, out) if f.name == "mixed-living-room" else e.e.e.summarize(f, out)
            variants[f"p{percentile}"] = metrics
        result["fixtures"][f.name] = variants
    (HERE / "results.json").write_text(json.dumps(result, indent=2))
    for name, variants in result["fixtures"].items():
        print(name, json.dumps(variants))


if __name__ == "__main__":
    main()
