"""Unsupervised, per-frame shape descriptors; labels only score separation."""
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("exp37_shape", HERE.parent / "37-raw-component-separation/analyze.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


def features(f):
    result = {}
    for channel, x in (("still", f.still[:, 2:9]), ("motion", f.move[:, 2:9])):
        x = x.astype(float)
        # z-score is invariant to positive scale and additive offset per frame.
        z = (x - x.mean(axis=1, keepdims=True)) / np.maximum(x.std(axis=1, keepdims=True), 1e-9)
        p = x / np.maximum(x.sum(axis=1, keepdims=True), 1e-9)
        entropy = -np.sum(np.where(p > 0, p * np.log(np.maximum(p, 1e-9)), 0), axis=1)
        result[channel + "_entropy"] = entropy
        result[channel + "_centroid"] = p @ np.arange(2, 9)
        result[channel + "_kurtosis"] = np.mean(z**4, axis=1)
        result[channel + "_peak_count"] = np.sum((z[:, 1:-1] > z[:, :-2]) & (z[:, 1:-1] > z[:, 2:]), axis=1).astype(float)
        for lag_s in (.1, .5, 1.):
            prior = np.searchsorted(f.ts, f.ts - lag_s, side="right") - 1
            valid = prior >= 0
            corr = np.full(len(x), np.nan)
            corr[valid] = np.mean(z[valid] * z[prior[valid]], axis=1)
            result[f"{channel}_shape_corr_{lag_s:g}s"] = corr
    return result


def main():
    living, _, _ = e.e.new_recording()
    fixtures = [e.s.old.e.b.new_fixture(n) for n in ("labeled-walk-0915.db", "labeled-loop-0915.db")]
    fixtures.append(living)
    out = {"method": "Scale-free per-frame profile descriptors; labels used for evaluation only; no classifier training", "fixtures": {}}
    for f in fixtures:
        positive = e.masked(f, "IN")
        negative = e.masked(f, "EMPTY" if f.name == "new-living-room" else "TW")
        values = features(f)
        summary = {}
        for name, v in values.items():
            pos = v[positive & np.isfinite(v)]
            neg = v[negative & np.isfinite(v)]
            if not len(pos) or not len(neg):
                continue
            summary[name] = {"auc": e.auc(pos, neg), "IN_median": float(np.median(pos)),
                             "other_median": float(np.median(neg)),
                             "IN_p10_p90": np.percentile(pos, [10, 90]).tolist(),
                             "other_p10_p90": np.percentile(neg, [10, 90]).tolist()}
        out["fixtures"][f.name] = summary
        if f.name == "new-living-room":
            fl, sp = e.s.estimates(f)
            occupied, _, _ = e.s.replay(f, fl, sp, True, 30.0, same_gate_balance=True)
            missed = positive & ~occupied
            out["living_room_missed_occupancy"] = {
                "missed_frames": int(missed.sum()),
                "detected_frames": int((positive & occupied).sum()),
                "features": {
                    name: {
                        "missed_median": float(np.nanmedian(values[name][missed])),
                        "detected_median": float(np.nanmedian(values[name][positive & occupied])),
                        "empty_median": float(np.nanmedian(values[name][negative])),
                        "auc_missed_vs_empty": e.auc(values[name][missed & np.isfinite(values[name])],
                                                     values[name][negative & np.isfinite(values[name])]),
                    } for name in ("still_centroid", "still_kurtosis", "still_entropy")
                },
            }
    (HERE / "results.json").write_text(json.dumps(out, indent=2))
    for name, d in out["fixtures"].items():
        print(name)
        for feat, v in d.items():
            print(feat, round(v["auc"], 3), round(v["IN_median"], 3), round(v["other_median"], 3))


if __name__ == "__main__":
    main()
