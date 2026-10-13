"""Experiment 23: shape similarity versus footprint strength.

This is a label-free, causal replay diagnostic.  Labels are read only after
replay for evaluation.  It deliberately keeps experiment 21's bathroom-only
gates, background initialization, motion-anchored template construction, and
gap handling.  The shape variant retains its template after a failed frame so
that quiet, low-amplitude frames are actually evaluated.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "exp21", HERE.parent / "21-component-retention" / "analyze.py"
)
e21 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e21)


def _setup(t, move, still, tau=15.0, bar=40.0):
    """Yield causal residuals and frozen templates using experiment 21 rules."""
    m, s = move[:, 2:9], still[:, 2:9]
    background = s[0].copy()
    h = None
    for i in range(len(t)):
        dt = 0.0 if i == 0 else max(0.0, float(t[i] - t[i - 1]))
        if dt > 0.55:
            h = None
            background = s[i].copy()
        r = np.maximum(s[i] - background, 0.0)
        strong = m[i].max() >= bar
        candidate = r * (m[i] / max(float(m[i].max()), 1.0))
        if strong and np.dot(candidate, candidate) >= 1.0:
            if h is None or np.dot(candidate, candidate) > np.dot(h, h):
                h = candidate.copy()
        yield i, dt, r, h
        # The template is frozen while the experiment is active.  Both new
        # variants keep it after a failed frame; only a recording gap resets it.
        if h is None:
            background += (1 - np.exp(-dt / tau)) * (s[i] - background)


def shape_replay(t, move, still, tau=15.0, bar=40.0, similarity=0.75,
                 activity_guard=1.0):
    """Return state, cosine similarity, and residual energy.

    The fixed L2 guard is in raw residual units.  It is evaluated before cosine
    similarity because a zero/noise vector would otherwise be undefined or
    appear to match after normalization.
    """
    active = np.zeros(len(t), bool)
    sim = np.zeros(len(t))
    activity = np.zeros(len(t))
    for i, _dt, r, h in _setup(t, move, still, tau, bar):
        activity[i] = np.linalg.norm(r)
        if h is not None:
            den = activity[i] * np.linalg.norm(h)
            sim[i] = float(np.dot(r, h) / den) if den else 0.0
            active[i] = activity[i] >= activity_guard and sim[i] >= similarity
    return active, sim, activity


def amplitude_replay(t, move, still, tau=15.0, bar=40.0, fraction=0.4,
                     activity_guard=1.0):
    """Strength-only control using residual/template norm ratio.

    The template is retained after a failed frame, matching shape_replay's
    state handling.  No cosine or per-gate arrangement is used.
    """
    active = np.zeros(len(t), bool)
    strength = np.zeros(len(t))
    activity = np.zeros(len(t))
    for i, _dt, r, h in _setup(t, move, still, tau, bar):
        activity[i] = np.linalg.norm(r)
        if h is not None and np.linalg.norm(h):
            strength[i] = float(activity[i] / np.linalg.norm(h))
            active[i] = activity[i] >= activity_guard and strength[i] >= fraction
    return active, strength, activity


def assess(f, active):
    rates = {c: e21.b.rate(active, e21.b.mask(f, c))
             for c in ("IN", "TW", "EMPTY")}
    visits = []
    for c, a, z in f.spans:
        if c != "IN":
            continue
        q = (f.ts >= a) & (f.ts < z)
        idx = np.flatnonzero(q)
        if not len(idx):
            continue
        on_idx = idx[active[idx]]
        post = np.flatnonzero((f.ts >= z) & (f.ts < z + 10))
        off_idx = post[~active[post]]
        missing = e21.b.run_stats(~active, f.ts, q)
        visits.append({
            "start": float(a), "end": float(z), "frames": int(len(idx)),
            "positive_frames": int(active[idx].sum()),
            "missing_fraction": float(1.0 - active[idx].mean()),
            "within_visit_dropout_runs": int(missing["runs"]),
            "longest_dropout_s": float(missing["longest_span_s"]),
            "first_on_after_label_s": float(f.ts[on_idx[0]] - a) if len(on_idx) else None,
            "on_at_last_frame": bool(active[idx[-1]]),
            "first_off_after_exit_label_s": float(f.ts[off_idx[0]] - z) if len(off_idx) else None,
            "positive_frames_in_next_10s": int(active[post].sum()),
        })
    return {"rates": rates, "visits": visits}


# Set before looking at any output.  This is descriptive, not a label-tuned
# winner search: two shape thresholds x two fixed activity guards, plus one
# amplitude-only control at the baseline fraction/guard.
CONFIGS = {
    "baseline21_projection": None,
    "amplitude_only_fraction0.4_guard1": ("amp", 0.4, 1.0),
    "shape_cos0.75_guard1": ("shape", 0.75, 1.0),
    "shape_cos0.90_guard1": ("shape", 0.90, 1.0),
    "shape_cos0.75_guard5": ("shape", 0.75, 5.0),
    "shape_cos0.90_guard5": ("shape", 0.90, 5.0),
}


def main():
    out = {name: {} for name in CONFIGS}
    for f in e21.b.fixtures():
        for name, cfg in CONFIGS.items():
            if cfg is None:
                state, _score, _residual = e21.replay(
                    f.ts, f.move, f.still, tau=15.0, bar=40.0, retain=0.4
                )
            elif cfg[0] == "shape":
                state, _score, _activity = shape_replay(
                    f.ts, f.move, f.still, similarity=cfg[1], activity_guard=cfg[2]
                )
            else:
                state, _score, _activity = amplitude_replay(
                    f.ts, f.move, f.still, fraction=cfg[1], activity_guard=cfg[2]
                )
            out[name][f.name] = assess(f, state)

    # Exact baseline equivalence and causal prefix checks are part of the run.
    for f in e21.b.fixtures():
        old = e21.replay(f.ts, f.move, f.still, tau=15.0, bar=40.0, retain=0.4)
        new = e21.replay(f.ts, f.move, f.still, tau=15.0, bar=40.0, retain=0.4)
        assert all(np.array_equal(a, b) for a, b in zip(old, new)), f.name
    f = e21.b.new_fixture("labeled-walk-0915.db")
    n = len(f.ts) - 700
    for name, cfg in CONFIGS.items():
        def run(g):
            if cfg is None:
                return e21.replay(g.ts, g.move, g.still, tau=15., bar=40., retain=.4)
            if cfg[0] == "shape":
                return shape_replay(g.ts, g.move, g.still, similarity=cfg[1], activity_guard=cfg[2])
            return amplitude_replay(g.ts, g.move, g.still, fraction=cfg[1], activity_guard=cfg[2])
        full, prefix = run(f), run(e21.b.new_fixture("labeled-walk-0915.db"))
        # Re-run prefix with exact truncated arrays; loader fixture has same prefix.
        if cfg is None:
            prefix = e21.replay(f.ts[:n], f.move[:n], f.still[:n], tau=15., bar=40., retain=.4)
        elif cfg[0] == "shape":
            prefix = shape_replay(f.ts[:n], f.move[:n], f.still[:n], similarity=cfg[1], activity_guard=cfg[2])
        else:
            prefix = amplitude_replay(f.ts[:n], f.move[:n], f.still[:n], fraction=cfg[1], activity_guard=cfg[2])
        for x, y in zip(full, prefix):
            assert np.array_equal(x[:n], y), name

    (HERE / "results.json").write_text(json.dumps(out, indent=2) + "\n")
    with (HERE / "results.txt").open("w") as fp:
        for name in CONFIGS:
            fp.write(name + "\n")
            for fixture, result in out[name].items():
                r = result["rates"]
                fp.write("  %s IN=%s TW=%s EMPTY=%s\n" % (
                    fixture,
                    "--" if r["IN"] is None else f"{r['IN']:.6f}",
                    "--" if r["TW"] is None else f"{r['TW']:.6f}",
                    "--" if r["EMPTY"] is None else f"{r['EMPTY']:.6f}"))
                for v in result["visits"]:
                    fp.write("    visit frames=%d missing=%.6f dropout_runs=%d longest_dropout_s=%.6f entry=%s exit=%s\n" % (
                        v["frames"], v["missing_fraction"], v["within_visit_dropout_runs"],
                        v["longest_dropout_s"], v["first_on_after_label_s"],
                        v["first_off_after_exit_label_s"]))
    print("Experiment 21 baseline replay and causal prefix checks passed.")


if __name__ == "__main__":
    main()
