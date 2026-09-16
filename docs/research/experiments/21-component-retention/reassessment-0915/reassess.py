"""Narrow reassessment of experiment 21 on the two trusted Sept 15 fixtures.

Labels are evaluation metadata only.  The replay and default parameters are
imported unchanged from experiment 21; no production code is changed.
"""
import importlib.util
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("exp21", HERE / "analyze.py")
exp21 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp21)

OUT = Path(__file__).resolve().parent
DEFAULT = dict(tau=15.0, bar=40.0, retain=0.4)


def runs(x, t, start=0):
    """Return contiguous true runs, allowing the recorder's .55 s gap."""
    ids = np.flatnonzero(x & (np.arange(len(x)) >= start))
    out = []
    a = prev = None
    for i in ids:
        if prev is None or i != prev + 1 or t[i] - t[prev] > .55:
            if a is not None:
                out.append((a, prev))
            a = i
        prev = i
    if a is not None:
        out.append((a, prev))
    return out


def pct(x, q):
    return None if not np.any(q) else 100.0 * float(np.mean(x[q]))


def spans_for(f, cls):
    return [(a, z) for c, a, z in f.spans if c == cls]


def visit_detail(f, active, a, z):
    q = (f.ts >= a) & (f.ts < z)
    ids = np.flatnonzero(q)
    on = ids[active[ids]]
    first = int(on[0]) if len(on) else None
    # A dropout is premature only after the first detection and before the
    # labeled visit end.  Report all such gaps, not just the first one.
    prem = []
    if first is not None:
        rr = runs(~active, f.ts, first)
        for i, j in rr:
            if f.ts[i] < z and f.ts[j] >= f.ts[first]:
                prem.append(dict(start_offset_s=float(f.ts[i] - a),
                                 duration_s=float(f.ts[j] - f.ts[i])))
    post = np.flatnonzero(f.ts >= z)
    off = post[~active[post]]
    first_off = int(off[0]) if len(off) else None
    # Check re-triggering in the ten seconds after the first clear, and in the
    # whole remainder.  This distinguishes a brief off pulse from clear hold.
    retrig10 = bool(np.any(active & (f.ts >= z) & (f.ts < z + 10)))
    retrig_after_off = bool(first_off is not None and np.any(active & (f.ts > f.ts[first_off]) & (f.ts < z + 10)))
    return dict(start=a, end=z, frames=int(q.sum()), detected_frames=int(active[q].sum()),
                first_detection_offset_s=None if first is None else float(f.ts[first] - a),
                premature_dropouts_after_first_detection=prem,
                first_clear_offset_s=None if first_off is None else float(f.ts[first_off] - z),
                retrigger_within_10s= retrig_after_off,
                post_exit_positive_frames_10s=int(np.sum(active & (f.ts >= z) & (f.ts < z + 10))),
                exit_behavior=("brief-off/retrigger" if retrig_after_off else "sustained-clear"))


def tail_split(f, active, a, z):
    """Split through-wall positives at the first sustained post-exit clear."""
    next_in = min((x for c, x, _ in f.spans if c == "IN" and x >= z), default=float("inf"))
    future = [(x, min(y, next_in)) for c, x, y in f.spans
              if c == "TW" and x >= z and x < next_in]
    kitchen_start = min((x for x, _ in future), default=None)
    off = np.flatnonzero((f.ts >= z) & ~active)
    clear = float(f.ts[off[0]]) if len(off) else float(f.ts[-1])
    tail_q = (f.ts >= z) & (f.ts < clear)
    later_q = np.zeros(len(f.ts), bool)
    for x, y in future:
        later_q |= (f.ts >= max(x, clear)) & (f.ts < y)
    labeled_tail_q = np.zeros(len(f.ts), bool)
    for x, y in future:
        labeled_tail_q |= (f.ts >= x) & (f.ts < min(y, clear))
    unlabeled_tail_q = tail_q & ~labeled_tail_q
    return dict(exit_label_to_kitchen_start_s=None if kitchen_start is None else float(kitchen_start-z),
                first_sustained_clear_offset_s=float(clear-z),
                tail_window_s=float(clear-z), tail_frames=int(tail_q.sum()),
                tail_positive_frames=int(np.sum(active & tail_q)),
                tail_false_fraction_pct=pct(active, tail_q),
                unlabeled_tail_frames=int(unlabeled_tail_q.sum()),
                unlabeled_tail_positive_frames=int(np.sum(active & unlabeled_tail_q)),
                labeled_kitchen_tail_frames=int(labeled_tail_q.sum()),
                labeled_kitchen_tail_positive_frames=int(np.sum(active & labeled_tail_q)),
                labeled_kitchen_tail_false_fraction_pct=pct(active, labeled_tail_q),
                later_kitchen_frames=int(later_q.sum()),
                later_kitchen_positive_frames=int(np.sum(active & later_q)),
                later_kitchen_false_fraction_pct=pct(active, later_q))


def descriptive_controls(f):
    m = f.move[:, 2:9]
    s = f.still[:, 2:9]
    out = {"raw_motion_ge40": m.max(axis=1) >= 40}
    for threshold in (40, 60, 80):
        out[f"raw_still_max_ge{threshold}"] = s.max(axis=1) >= threshold
    rates = {}
    for name, p in out.items():
        rates[name] = {}
        for c in ("IN", "TW", "EMPTY"):
            q = np.zeros(len(f.ts), bool)
            for span_c, a, z in f.spans:
                if span_c == c:
                    q |= (f.ts >= a) & (f.ts < z)
            rates[name][c] = pct(p, q)
    return rates


def main():
    old = json.loads((HERE / "results.json").read_text())
    result = {"parameters": DEFAULT, "fixtures": {}, "controls": {}}
    for name in ("labeled-walk-0915.db", "labeled-loop-0915.db"):
        f = exp21.b.new_fixture(name)
        active, score, residual = exp21.replay(f.ts, f.move, f.still, **DEFAULT)
        # Exact equality guard against the historical exp21 default output.
        prior = old[f.name]["tau15_motion40_retain0.4"]
        current = exp21.assess(f, active)
        assert current == prior, f"default output changed for {name}"
        visits = [visit_detail(f, active, a, z) for a, z in spans_for(f, "IN")]
        tails = [tail_split(f, active, a, z) for a, z in spans_for(f, "IN")]
        result["fixtures"][f.name] = {"default_assessment": current,
                                       "visits": visits, "exit_tail_split": tails,
                                       "active_frames": int(active.sum()),
                                       "active_score_max": float(score.max()),
                                       "quiet_retention_within_78s_pct": None}
        # The loop visit starts at the first fixture-relative 0; report the
        # actual visit interval's first 78 seconds explicitly below.
        if name == "labeled-loop-0915.db":
            a, z = spans_for(f, "IN")[0]
            result["fixtures"][f.name]["quiet_retention_within_78s_pct"] = pct(active, (f.ts >= a) & (f.ts < a + 78))
        result["controls"][f.name] = descriptive_controls(f)
    (OUT / "results.json").write_text(json.dumps(result, indent=2))
    (OUT / "results.txt").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
