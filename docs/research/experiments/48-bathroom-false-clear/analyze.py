"""Replay the new confirmed bathroom false-clear against window experiments."""
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bank = load("bank48", HERE.parent / "45-motion-shape-bank/analyze.py")
evolution = load("evolution48", HERE.parent / "46-window-shape-evolution/analyze.py")
contrast = load("contrast48", HERE.parent / "47-contrastive-motion-shape/analyze.py")
shape = load("shape48", HERE.parent / "43-end-of-hold-shape-review/analyze.py")
s = bank.s


def fixture():
    db = s.ROOT / "tests/fixtures/recordings/bathroom-false-clear-2026-09-16.db"
    start, end = 1789603725.0, 1789603990.0
    f = bank.e.e.e.e.fixture("bathroom-false-clear", "D0:6E:81:D2:5D:A6", db, [])
    f.spans = [("EMPTY", float(f.ts[0]), start), ("IN", start, end),
               ("EMPTY", end, float(f.ts[-1]))]
    return f


def summarize(f, out):
    inside = (f.ts >= 1789603725) & (f.ts < 1789603990)
    known_gap = (f.ts >= 1789603838) & (f.ts < 1789603891)
    empty_before = f.ts < 1789603725
    empty_after = f.ts >= 1789603990
    gaps = s.old.e.b.run_stats(inside & ~out, f.ts, inside)
    return {
        "inside_occupied_fraction": float(out[inside].mean()),
        "longest_false_vacancy_s": gaps["longest_span_s"],
        "known_false_clear_window_occupied_fraction": float(out[known_gap].mean()),
        "empty_before_occupied_fraction": float(out[empty_before].mean()),
        "empty_after_occupied_fraction": float(out[empty_after].mean()),
        "visit": s.assessment(f, out)["visits"][0],
    }


def main():
    f = fixture()
    fl, sp = s.estimates(f)
    configs = [
        ("current_anchor", None, 30, False),
        ("balanced_anchor", None, 30, True),
        ("recent4_20s", bank.MotionShapeBank(.8, 4, 20), 20, True),
        ("latest1_20s", bank.MotionShapeBank(.8, 1, 20), 20, True),
        ("shape_path_0_12_30s", evolution.WindowShapePath(.12), 30, True),
        ("contrast_0_5_20s", contrast.ContrastiveShapeBank(.5), 20, True),
        ("kurtosis_2_15_30s", shape.ShapeWindowReview(2.15), 30, True),
    ]
    result = {"fixture": f.name, "label_basis": "user-confirmed bathroom occupancy 20:08:45-20:13:10; integration state history independent of replay", "variants": {}}
    for name, reviewer, hold_s, balanced in configs:
        out, _, _ = s.replay(f, fl, sp, True, float(hold_s),
                             same_gate_balance=balanced, hold_review=reviewer,
                             entry_only_anchor=reviewer is not None)
        result["variants"][name] = summarize(f, out)
    (HERE / "results.json").write_text(json.dumps(result, indent=2))
    for name, metrics in result["variants"].items():
        print(name, "IN", round(metrics["inside_occupied_fraction"], 3),
              "gap", round(metrics["longest_false_vacancy_s"], 1),
              "known-gap-on", round(metrics["known_false_clear_window_occupied_fraction"], 3),
              "clear-after-exit", metrics["visit"]["first_clear_offset_s"])


if __name__ == "__main__":
    main()
