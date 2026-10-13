"""Post-activation still-gate shape envelope, independent hold diagnostic."""

import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("experiment33_envelope", HERE.parent / "33-entry-change-hold/analyze.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
s = e.stack


def longest_gap(mask, accepted, ts):
    return s.old.e.b.run_stats(mask & ~accepted, ts, mask)["longest_span_s"]


def fit_envelope(samples, ridge_min):
    center = np.median(samples, axis=0)
    cov = np.cov(samples.T)
    ridge = max(float(np.trace(cov) / len(center)) * .1, ridge_min)
    precision = np.linalg.pinv(cov + ridge * np.eye(len(center)))
    distances = np.sqrt(np.einsum("ni,ij,nj->n", samples - center, precision, samples - center))
    threshold = max(float(np.percentile(distances, 95)) * 1.5, 1.)
    return center, precision, threshold


def distance(values, center, precision):
    delta = values - center
    return np.sqrt(np.einsum("ni,ij,nj->n", delta, precision, delta))


def one_visit(f, onset, start, end):
    t = float(f.ts[onset])
    before = (f.ts >= t - 2.5) & (f.ts < t - .5)
    training = (f.ts >= t + 3) & (f.ts < t + 12)
    if before.sum() < 5 or training.sum() < 30:
        return {"onset": t, "error": "insufficient pre-entry or training frames"}
    pre = np.median(f.still[before, 2:9], axis=0)
    raw = f.still[:, 2:9]
    residual = np.maximum(raw - pre, 0)
    report = {"onset": t, "pre_entry_still_gates_2_8": pre.tolist(),
              "training_still_median_gates_2_8": np.median(raw[training], axis=0).tolist(),
              "training_still_p10_gates_2_8": np.percentile(raw[training], 10, axis=0).tolist(),
              "training_still_p90_gates_2_8": np.percentile(raw[training], 90, axis=0).tolist(),
              "features": {}}
    unit_raw = raw / np.maximum(np.linalg.norm(raw, axis=1, keepdims=True), 1)
    unit_residual = residual / np.maximum(np.linalg.norm(residual, axis=1, keepdims=True), 1)
    for name, values in (("raw_still", raw), ("preentry_subtracted_still", residual),
                         ("relative_raw_shape", unit_raw),
                         ("relative_preentry_subtracted_shape", unit_residual)):
        center, precision, threshold = fit_envelope(
            values[training], 1e-4 if name.startswith("relative") else 1.
        )
        d = distance(values, center, precision)
        accepted = d <= threshold
        after_training = (f.ts >= t + 12) & (f.ts < end)
        first30_after_exit = (f.ts >= end) & (f.ts < end + 30)
        report["features"][name] = {
            "threshold": threshold,
            "center_gates_2_8": center.tolist(),
            "inside_after_training_fraction": float(accepted[after_training].mean()) if after_training.any() else None,
            "longest_rejected_run_while_inside_s": longest_gap(after_training, accepted, f.ts),
            "accepted_first_30s_after_exit_fraction": float(accepted[first30_after_exit].mean()) if first30_after_exit.any() else None,
            "distance_median_inside": float(np.median(d[after_training])) if after_training.any() else None,
            "distance_median_after_exit": float(np.median(d[first30_after_exit])) if first30_after_exit.any() else None,
        }
    report["cosine_shape"] = {}
    for name, values in (("raw_still", raw), ("preentry_subtracted_still", residual)):
        template = np.median(values[training], axis=0)
        cosine = (values @ template) / np.maximum(
            np.linalg.norm(values, axis=1) * np.linalg.norm(template), 1e-9
        )
        after_training = (f.ts >= t + 12) & (f.ts < end)
        first30_after_exit = (f.ts >= end) & (f.ts < end + 30)
        amplitude = np.linalg.norm(values, axis=1) / max(np.linalg.norm(template), 1e-9)
        report["cosine_shape"][name] = {
            "training_fifth_percentile": float(np.percentile(cosine[training], 5)),
            "inside_median": float(np.median(cosine[after_training])),
            "after_exit_median": float(np.median(cosine[first30_after_exit])) if first30_after_exit.any() else None,
            "amplitude_ratio_inside_tenth_percentile": float(np.percentile(amplitude[after_training], 10)),
            "amplitude_ratio_inside_median": float(np.median(amplitude[after_training])),
            "amplitude_ratio_after_exit_ninetieth_percentile": float(np.percentile(amplitude[first30_after_exit], 90)) if first30_after_exit.any() else None,
            "pass_rates": {str(threshold): {
                "inside": float((cosine[after_training] >= threshold).mean()),
                "first30_after_exit": float((cosine[first30_after_exit] >= threshold).mean()) if first30_after_exit.any() else None,
            } for threshold in (.8, .9, .95)},
        }
    settled_training = (f.ts >= t + 30) & (f.ts < t + 60)
    if settled_training.sum() >= 100 and end > t + 60:
        template = np.median(residual[settled_training], axis=0)
        cosine = (residual @ template) / np.maximum(
            np.linalg.norm(residual, axis=1) * np.linalg.norm(template), 1e-9
        )
        later = (f.ts >= t + 60) & (f.ts < end)
        after_exit = (f.ts >= end) & (f.ts < end + 30)
        report["settled_30_to_60s_shape"] = {
            "later_inside_cosine_median": float(np.median(cosine[later])),
            "later_inside_cosine_tenth_percentile": float(np.percentile(cosine[later], 10)),
            "first30_after_exit_cosine_median": float(np.median(cosine[after_exit])) if after_exit.any() else None,
            "later_inside_fraction_cosine_ge_0_9": float((cosine[later] >= .9).mean()),
            "first30_after_exit_fraction_cosine_ge_0_9": float((cosine[after_exit] >= .9).mean()) if after_exit.any() else None,
        }
    return report


def main():
    living, _, _ = e.new_recording()
    fixtures = [s.old.e.b.new_fixture(name) for name in ("labeled-walk-0915.db", "labeled-loop-0915.db")]
    fixtures.append(living)
    result = {"method": "post-entry 3-12 s robust Gaussian gate envelope; thresholds from training distances only; full-stack balanced entry determines onset", "fixtures": {}}
    for f in fixtures:
        fl, sp = s.estimates(f)
        occupied, _, _ = s.replay(f, fl, sp, True, 30.0, same_gate_balance=True)
        onsets = np.flatnonzero(occupied & ~np.r_[False, occupied[:-1]])
        visits = []
        for cls, start, end in f.spans:
            if cls != "IN":
                continue
            valid = [i for i in onsets if start - 1 <= f.ts[i] < end]
            if valid:
                visits.append(one_visit(f, valid[0], start, end))
            else:
                visits.append({"label_start": start, "error": "no stack activation in visit"})
        result["fixtures"][f.name] = visits
    (HERE / "results.json").write_text(json.dumps(result, indent=2))
    for name, visits in result["fixtures"].items():
        print(name)
        for visit in visits:
            if "features" not in visit:
                print(visit)
                continue
            print("onset", visit["onset"])
            for feat, data in visit["features"].items():
                print(feat, "inside", round(data["inside_after_training_fraction"], 3),
                      "gap", round(data["longest_rejected_run_while_inside_s"], 1),
                      "postexit", round(data["accepted_first_30s_after_exit_fraction"], 3) if data["accepted_first_30s_after_exit_fraction"] is not None else None)


if __name__ == "__main__":
    main()
