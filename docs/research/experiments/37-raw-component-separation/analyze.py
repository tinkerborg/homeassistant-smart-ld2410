"""Independent noncausal raw-gate source-separation feasibility probe."""

import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("experiment33_raw_components", HERE.parent / "33-entry-change-hold/analyze.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
s = e.stack


def nmf(x, rank, seed, iterations=250):
    rng = np.random.default_rng(seed)
    w = rng.random((len(x), rank)) + .1
    h = rng.random((rank, x.shape[1])) + .1
    for _ in range(iterations):
        w *= (x @ h.T) / (w @ (h @ h.T) + 1e-9)
        h *= (w.T @ x) / ((w.T @ w) @ h + 1e-9)
    norms = np.linalg.norm(h, axis=1)
    h /= norms[:, None]
    w *= norms[None, :]
    error = float(np.linalg.norm(x - w @ h) / max(np.linalg.norm(x), 1e-9))
    return w, h, error


def auc(positive, negative):
    if not len(positive) or not len(negative):
        return None
    negative = np.sort(negative)
    lower = np.searchsorted(negative, positive, side="left")
    upper = np.searchsorted(negative, positive, side="right")
    return float(np.mean((lower + upper) / (2 * len(negative))))


def masked(f, cls):
    return s.old.e.b.mask(f, cls)


def analyze_fixture(f):
    # Each channel/gate gets its own low percentile, using this sensor only.
    # This batch preprocessing is explicitly noncausal: exploratory feasibility only.
    raw = np.concatenate((f.still[:, 2:9], f.move[:, 2:9]), axis=1)
    quiet = np.percentile(raw, 5, axis=0)
    x = np.maximum(raw - quiet, 0)
    labels = ("IN", "TW") if f.name != "new-living-room" else ("IN", "EMPTY")
    positive = masked(f, labels[0])
    negative = masked(f, labels[1])
    result = {"n_frames": len(f.ts), "sensor": f.sensor,
              "quiet_gate_levels": quiet.tolist(), "positive_class": labels[0],
              "negative_class": labels[1], "ranks": {}}
    for rank in (1, 2, 3):
        runs = [nmf(x, rank, seed) for seed in (1, 2, 3)]
        w, h, error = min(runs, key=lambda run: run[2])
        comps = []
        for k in range(rank):
            z = w[:, k]
            comps.append({
                "still_weights": h[k, :7].tolist(),
                "motion_weights": h[k, 7:].tolist(),
                "positive_median": float(np.median(z[positive])) if positive.any() else None,
                "negative_median": float(np.median(z[negative])) if negative.any() else None,
                "positive_tenth_percentile": float(np.percentile(z[positive], 10)) if positive.any() else None,
                "negative_ninetieth_percentile": float(np.percentile(z[negative], 90)) if negative.any() else None,
                "auc_positive_vs_negative": auc(z[positive], z[negative]),
            })
        result["ranks"][str(rank)] = {"relative_reconstruction_error": error,
                                      "components": comps}
    # Equalize each frame's overall strength to ask whether its *shape* has
    # independently recoverable sources. This remains a noncausal batch fit.
    shape = x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1)
    runs = [nmf(shape, 2, seed, 300) for seed in (1, 2, 3)]
    w, h, error = min(runs, key=lambda run: run[2])
    m, st = f.move[:, 2:9], f.still[:, 2:9]
    balanced = np.any((m >= 40) & (m / np.maximum(m + st, 1) >= 1 / 3), axis=1)
    starts = np.flatnonzero(balanced & ~np.r_[False, balanced[:-1]])
    episodes = []
    for cls, a, b in f.spans:
        if cls != "IN":
            continue
        candidates = [i for i in starts if a - 1 <= f.ts[i] < a + 3]
        if not candidates:
            episodes.append({"entry_label_ts": a, "seed_event_ts": None})
            continue
        i = candidates[0]
        event = float(f.ts[i])
        before = (f.ts >= event - 1) & (f.ts < event - .1)
        after = (f.ts >= event) & (f.ts < event + 3)
        delta = np.median(w[after], axis=0) - np.median(w[before], axis=0)
        chosen = int(np.argmax(delta))
        dominant = w[:, chosen] > w[:, 1 - chosen]
        inside = (f.ts >= a) & (f.ts < b)
        next_in = min((x for c, x, _ in f.spans if c == "IN" and x >= b), default=float("inf"))
        after_exit = (f.ts >= b) & (f.ts < min(b + 30, next_in))
        off = np.flatnonzero(after_exit & ~dominant)
        episodes.append({
            "entry_label_ts": a, "seed_event_ts": event,
            "selected_component": chosen, "activation_change_after_3s": delta.tolist(),
            "dominant_fraction_during_IN": float(dominant[inside].mean()),
            "dominant_fraction_first_30s_after_exit": float(dominant[after_exit].mean()) if after_exit.any() else None,
            "first_shape_clear_offset_s": float(f.ts[off[0]] - b) if len(off) else None,
            "longest_false_gap_during_IN_s": s.old.e.b.run_stats(inside & ~dominant, f.ts, inside)["longest_span_s"],
        })
    result["shape_normalized_rank2"] = {
        "relative_reconstruction_error": error,
        "components": [{"still_weights": h[k, :7].tolist(),
                        "motion_weights": h[k, 7:].tolist(),
                        "auc_positive_vs_negative": auc(w[positive, k], w[negative, k]),
                        "positive_median": float(np.median(w[positive, k])),
                        "negative_median": float(np.median(w[negative, k]))}
                       for k in range(2)],
        "motion_seeded_episodes": episodes,
    }
    return result


def main():
    living, _, _ = e.new_recording()
    fixtures = [s.old.e.b.new_fixture(name) for name in ("labeled-walk-0915.db", "labeled-loop-0915.db")]
    fixtures.append(living)
    result = {"method": "unsupervised batch nonnegative matrix factorization of background-subtracted still and motion gates 2-8; labels evaluate factors only", "fixtures": {}}
    for f in fixtures:
        result["fixtures"][f.name] = analyze_fixture(f)
    (HERE / "results.json").write_text(json.dumps(result, indent=2))
    for name, info in result["fixtures"].items():
        print(name)
        for rank, fit in info["ranks"].items():
            print("rank", rank, "error", round(fit["relative_reconstruction_error"], 3),
                  "AUCs", [round(c["auc_positive_vs_negative"], 3) if c["auc_positive_vs_negative"] is not None else None for c in fit["components"]],
                  "medians", [(round(c["positive_median"], 1), round(c["negative_median"], 1)) for c in fit["components"]])
        shape = info["shape_normalized_rank2"]
        print("shape rank2", "AUCs", [round(c["auc_positive_vs_negative"], 3) for c in shape["components"]],
              "seeded episodes", [(round(v.get("dominant_fraction_during_IN", 0), 3),
                                   round(v.get("dominant_fraction_first_30s_after_exit") or 0, 3),
                                   v.get("first_shape_clear_offset_s")) for v in shape["motion_seeded_episodes"]])


if __name__ == "__main__":
    main()
