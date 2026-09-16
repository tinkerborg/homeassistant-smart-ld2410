"""Experiment 24: causal per-gate temporal coupling.

Labels are used only to score fixed arithmetic.  At each grid time, this
computes an exponentially weighted Pearson correlation between first
differences of motion and still on the same gate.  A second, predeclared
variant compares motion 0.5 s earlier with still now.  The window and decay
are fixed before reading labels; no model or selected threshold is used.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
GATE = np.arange(2, 9)                 # usable bathroom gates only
GRID = 0.1
HORIZON = 5.0
TAU = 2.0
LAGS = (0.0, 0.5)                     # move earlier, still contemporaneous/later
VAR_FLOOR = 0.05                      # still SD guard; motion must exceed 0.5 below

sys.path.insert(0, str(HERE.parent / "15-gate-profile"))
import data  # noqa: E402

spec = importlib.util.spec_from_file_location("e20", HERE.parent / "20-channel-balance" / "analyze.py")
e20 = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(e20)


def corr(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
    mx = float(np.sum(w * x)); my = float(np.sum(w * y))
    xx = x - mx; yy = y - my
    den = float(np.sqrt(np.sum(w * xx * xx) * np.sum(w * yy * yy)))
    return 0.0 if den <= 1e-12 else float(np.sum(w * xx * yy) / den)


def score(fx, lag: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return frame-time coupling, amplitude control, and information age.

    Resampling and the differencing history reset across timestamp gaps.  Every
    score at t reads only q <= t (and q-lag <= t), so it cannot use future
    samples.  Before HORIZON seconds the score is NaN (startup horizon).
    """
    t = fx.ts
    q = np.arange(float(t[0]), float(t[-1]) + GRID * .25, GRID)
    ok = np.ones(len(q), bool)
    for i in range(len(q)):
        j = np.searchsorted(t, q[i])
        if j == 0 or j == len(t) or t[j] - t[j - 1] > 0.55:
            ok[i] = False
    m = np.full((len(q), 9), np.nan); s = np.full_like(m, np.nan)
    for g in range(9):
        m[ok, g] = np.interp(q[ok], t, fx.move[:, g])
        s[ok, g] = np.interp(q[ok], t, fx.still[:, g])
    dm = np.diff(m, axis=0, prepend=np.nan); ds = np.diff(s, axis=0, prepend=np.nan)
    out = np.full(len(q), np.nan); amp = np.full(len(q), np.nan); age = np.full(len(q), np.nan)
    decay = np.exp(-GRID / TAU)
    for i in range(len(q)):
        if not ok[i] or i < int(HORIZON / GRID):
            continue
        lo = max(1, i - int(HORIZON / GRID))
        idx = np.arange(lo, i + 1)
        valid = ok[idx]
        idx = idx[valid]
        if len(idx) < 10: continue
        w = decay ** (i - idx); w /= w.sum()
        amp[i] = float(np.sum(w * np.nanmean(s[idx][:, GATE], axis=1)))
        vals = []
        shift = int(round(lag / GRID))
        for g in GATE:
            a = idx[idx - shift >= 1]
            b = a - shift
            good = np.isfinite(dm[b, g]) & np.isfinite(ds[a, g])
            a = a[good]; b = b[good]
            if len(a) < 10: continue
            ww = decay ** (i - a); ww /= ww.sum()
            # Guard against correlations of near-constant quantization noise.
            md = np.sqrt(np.sum(ww * (dm[b, g] - np.sum(ww * dm[b, g])) ** 2))
            sd = np.sqrt(np.sum(ww * (ds[a, g] - np.sum(ww * ds[a, g])) ** 2))
            if md >= 0.5 and sd >= VAR_FLOOR:
                vals.append(corr(dm[b, g], ds[a, g], ww))
        if vals:
            out[i] = float(np.median(vals))
            age[i] = HORIZON
    # Map causal grid values back to recorded frame times; NaN outside valid bins.
    if not np.isfinite(out).any():
        coupling = np.full(len(t), np.nan)
    else:
        coupling = np.interp(t, q[np.isfinite(out)], out[np.isfinite(out)], left=np.nan, right=np.nan)
    finite_amp = np.isfinite(amp)
    amplitude = (np.interp(t, q[finite_amp], amp[finite_amp], left=np.nan, right=np.nan)
                 if finite_amp.any() else np.full(len(t), np.nan))
    return coupling, amplitude, age


def auc(y: np.ndarray, x: np.ndarray) -> float:
    z = np.isfinite(x)
    y = y[z].astype(bool); x = x[z]
    pos = x[y]; neg = x[~y]
    if not len(pos) or not len(neg): return float("nan")
    return float((np.sum(pos[:, None] > neg[None, :]) + .5 * np.sum(pos[:, None] == neg[None, :])) / (len(pos) * len(neg)))


def mask(fx, cls):
    z = np.zeros(len(fx.ts), bool)
    for c, a, b in fx.spans:
        if c == cls: z |= (fx.ts >= a) & (fx.ts < b)
    return z


def load_fixtures():
    # New labels are interpreted by the existing loader; no labels enter score().
    return [e20.new_fixture(x) for x in ("labeled-loop-0915.db", "labeled-walk-0915.db")] + [
        data.load(x) for x in ("throughwall-morning-d06e", "bathroom-visit-2204-d06e", "labeled-sessions-0909-d06e", "stove-case-0913-d06e")]


def main():
    rows = []
    print(f"fixed horizon={HORIZON:g}s tau={TAU:g}s grid={GRID:g}s var_floor={VAR_FLOOR:g} gates=2..8")
    for fx in load_fixtures():
        cs = {}
        for lag in LAGS:
            cs[lag], amp, _ = score(fx, lag)
        print(f"fixture {fx.name} frames={len(fx.ts)}")
        for cls in ("IN", "TW", "EMPTY"):
            q = mask(fx, cls)
            if not q.any(): continue
            print(f"  {cls:5s} n={q.sum():5d} coupling0 p10/50/90=" + ",".join(f"{x:.3f}" for x in np.nanpercentile(cs[0.0][q],[10,50,90])) +
                  " lag05=" + ",".join(f"{x:.3f}" for x in np.nanpercentile(cs[0.5][q],[10,50,90])) +
                  " amp=" + ",".join(f"{x:.1f}" for x in np.nanpercentile(amp[q],[10,50,90])))
            rows.append((fx, cls, q, cs, amp))
        # Per-span descriptive metrics, including quiet bathroom retention.
        for cls, a, b in fx.spans:
            q = (fx.ts >= a) & (fx.ts < b)
            if q.any():
                print(f"  span {cls:5s} {b-a:6.1f}s finite={np.isfinite(cs[0.0][q]).mean()*100:5.1f}%")
    print("\nPAIRWISE DESCRIPTIVE AUC (no fitted thresholds; pooled labeled spans)")
    seen = set()
    for fx, _, _, cs, amp in rows:
        if fx.name not in ("labeled-loop-0915", "labeled-walk-0915"): continue
        if fx.name in seen: continue
        seen.add(fx.name)
        qi = mask(fx, "IN"); qt = mask(fx, "TW")
        y = np.r_[np.ones(qi.sum()), np.zeros(qt.sum())]
        print(f"  {fx.name} nIN={qi.sum()} nTW={qt.sum()} coupling0={auc(y,np.r_[cs[0.0][qi],cs[0.0][qt]]):.3f} lag05={auc(y,np.r_[cs[0.5][qi],cs[0.5][qt]]):.3f} amp={auc(y,np.r_[amp[qi],amp[qt]]):.3f}")
    # Causality sanity: prefix replay gives identical prefix scores.
    fx = e20.new_fixture("labeled-walk-0915.db"); cut = len(fx.ts) - 500
    for lag in LAGS:
        full = score(fx, lag)[0][:cut]
        pref = score(type(fx)(fx.name, fx.sensor, fx.ts[:cut], fx.move[:cut], fx.still[:cut], fx.spans), lag)[0]
        # Ignore the final second where interpolation at a truncated endpoint
        # can differ; all earlier scores must be identical.
        assert np.allclose(full[:-10], pref[:-10], equal_nan=True)
    print("causality_prefix_check=PASS")


if __name__ == "__main__": main()
