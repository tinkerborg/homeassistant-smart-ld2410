"""Additional no-human controls for the recent-four 20-second shape rule."""
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("shape45_controls", HERE / "analyze.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
s = e.s


def episodes(t, on):
    starts = np.flatnonzero(on & ~np.r_[False, on[:-1]])
    ends = np.flatnonzero(on & ~np.r_[on[1:], False])
    return [float(t[b] - t[a]) for a, b in zip(starts, ends)]


def main():
    root = s.ROOT / "tests/fixtures/recordings"
    fixture_fn = e.e.e.e.e.fixture
    sources = [
        ("cat_bathroom", "cat-kitchen-0915.db", "D0:6E:81:D2:5D:A6"),
        ("cat_kitchen", "cat-kitchen-0915.db", "B3:26:9E:EE:C5:11"),
        ("overnight_bathroom", "overnight-2026-09-16.db", "D0:6E:81:D2:5D:A6"),
        ("overnight_old_living", "overnight-2026-09-16.db", "FD:68:3B:41:6E:FF"),
    ]
    result = {"note": "No humans reported in these periods; cat behavior and upstairs bleed are possible. Old living sensor differs from replacement used in main experiment.", "fixtures": {}}
    for name, filename, sensor in sources:
        f = fixture_fn(name, sensor, root / filename, [])
        fl, sp = s.estimates(f)
        variants = {}
        for label, tracker in (("exact_anchor", None),
                               ("recent4_20s", e.MotionShapeBank(.8, 4, 20))):
            out, _, _ = s.replay(f, fl, sp, True, 30.0 if tracker is None else 20.0,
                                 same_gate_balance=True, hold_review=tracker,
                                 entry_only_anchor=tracker is not None)
            spans = episodes(f.ts, out)
            variants[label] = {"occupied_fraction": float(out.mean()),
                               "episode_count": len(spans),
                               "longest_episode_s": max(spans, default=0),
                               "episode_durations_s": spans}
        result["fixtures"][name] = variants
        print(name, variants)
    (HERE / "controls.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
