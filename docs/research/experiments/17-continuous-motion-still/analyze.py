"""Experiment 17: rolling move/still relationships without event selection.

All features at anchor t use frames in [t-W, t]. Positive lag L means move at
q is compared with still at q+L; negative lag reverses which stream is later.
Both remain in the past of t. Windows must be wholly inside one label span and
contain no timestamp gap. One-second anchors deliberately overlap; evaluation
is grouped by spans/fixtures and is descriptive rather than a claim of N
independent observations.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "15-gate-profile"))
sys.path.insert(0, str(HERE.parent / "16-motion-still-coupling"))
import data  # noqa: E402
import analyze as e16  # noqa: E402

GAP_S = 0.55
GRID_S = 0.1
STEP_S = float(os.environ.get("EXP17_STEP", "1.0"))
WINDOWS = (10.0, 30.0)
LAGS = (-5.0, -2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 5.0)
STILL_GATES = np.arange(2, 9)


def complete_window(ts: np.ndarray, a: float, b: float) -> bool:
    ix = np.flatnonzero((ts >= a) & (ts <= b))
    if len(ix) < 3:
        return False
    if abs(float(ts[ix[0]]) - a) > 0.35 or abs(float(ts[ix[-1]]) - b) > 0.35:
        return False
    return float(np.max(np.diff(ts[ix]))) <= GAP_S


def corr(x: np.ndarray, y: np.ndarray) -> float:
    """Pearson correlation; constant pairs have defined value 0."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    x = x - np.mean(x); y = y - np.mean(y)
    den = float(np.sqrt(np.dot(x, x) * np.dot(y, y)))
    return 0.0 if den <= 1e-9 else float(np.dot(x, y) / den)


def grid(ts: np.ndarray, v: np.ndarray, a: float, b: float) -> np.ndarray:
    m = (ts >= a) & (ts <= b)
    ts = ts[m]; v = v[m]
    q = np.arange(a, b + GRID_S * 0.25, GRID_S)
    return np.column_stack([np.interp(q, ts, v[:, g]) for g in range(v.shape[1])])


def summaries(v: np.ndarray, gates: np.ndarray, prefix: str) -> dict[str, float]:
    x = v[:, gates]
    mag = x.mean(axis=1)
    weights = np.arange(len(gates), dtype=float)
    mass = np.maximum(x.sum(axis=1), 1e-6)
    out = {
        f"{prefix}_mean": float(np.mean(x)),
        f"{prefix}_p95": float(np.percentile(x, 95)),
        f"{prefix}_sd": float(np.mean(np.std(x, axis=0))),
        f"{prefix}_var": float(np.std(mag)),
        f"{prefix}_sat": float(np.mean(x >= 95)),
        f"{prefix}_centroid": float(np.mean((x * weights).sum(axis=1) / mass)),
    }
    for j, g in enumerate(gates):
        out[f"{prefix}_g{int(g)}_mean"] = float(np.mean(v[:, g]))
        out[f"{prefix}_g{int(g)}_sd"] = float(np.std(v[:, g]))
    if len(mag) > 2:
        out[f"{prefix}_ac1"] = corr(mag[:-1], mag[1:])
    else:
        out[f"{prefix}_ac1"] = 0.0
    return out


def features(fx: data.Fixture, cls: str, span_no: int, a: float, b: float, W: float) -> list[dict]:
    ts = fx.ts; out=[]
    # Anchors every second, with the full causal history wholly inside span.
    anchors = np.arange(a + W, b + 1e-6, STEP_S)
    for t in anchors:
        if not complete_window(ts, t - W, t):
            continue
        q = grid(ts, fx.move, t - W, t)
        s = grid(ts, fx.still, t - W, t)
        r = {"fixture": fx.name, "sensor": fx.sensor, "cls": cls,
             "span": span_no, "t": float(t), "W": W}
        r.update(summaries(q, np.arange(9), "m"))
        r.update(summaries(s, STILL_GATES, "s"))
        # Same-gate and adjacent-gate summaries. Each lag gets the same fixed
        # aggregates so feature count does not depend on the recordings.
        for lag in LAGS:
            lo = max(0.0, -lag); hi = min(W, W - max(0.0, lag))
            if hi - lo < 2.0:
                continue
            qa = np.arange(t - W + lo, t - W + hi + GRID_S * .25, GRID_S)
            src = (ts >= t - W) & (ts <= t)
            its = ts[src]; im = fx.move[src]; ist = fx.still[src]
            mv = np.column_stack([np.interp(qa, its, im[:, g]) for g in range(9)])
            st = np.column_stack([np.interp(qa + lag, its, ist[:, g]) for g in range(9)])
            same = np.array([corr(mv[:, g], st[:, g]) for g in STILL_GATES])
            adj = np.array([corr(mv[:, g - d], st[:, g])
                            for d in (-1, 1) for g in STILL_GATES
                            if 0 <= g - d < 9])
            # Detrended/differenced correlation removes common slow level
            # drift. It is a separate predefined feature family.
            md = np.diff(mv, axis=0); sd = np.diff(st, axis=0)
            same_d = np.array([corr(md[:, g], sd[:, g]) for g in STILL_GATES])
            adj_d = np.array([corr(md[:, g - d], sd[:, g])
                              for d in (-1, 1) for g in STILL_GATES
                              if 0 <= g - d < 9])
            sign = f"{lag:g}"
            r[f"c_same_{sign}"] = float(np.median(same))
            r[f"c_sameabs_{sign}"] = float(np.median(np.abs(same)))
            r[f"c_samemax_{sign}"] = float(np.max(np.abs(same)))
            r[f"c_adj_{sign}"] = float(np.median(adj))
            r[f"c_adjmax_{sign}"] = float(np.max(np.abs(adj)))
            r[f"d_same_{sign}"] = float(np.median(same_d))
            r[f"d_samemax_{sign}"] = float(np.max(np.abs(same_d)))
            r[f"d_adj_{sign}"] = float(np.median(adj_d))
            r[f"d_adjmax_{sign}"] = float(np.max(np.abs(adj_d)))
        out.append(r)
    return out


BASE = ["m_mean", "m_p95", "m_sd", "m_var", "m_sat", "m_centroid", "m_ac1",
        "s_mean", "s_p95", "s_sd", "s_var", "s_sat", "s_centroid", "s_ac1"]
BASE += [f"m_g{g}_{k}" for g in range(9) for k in ("mean", "sd")]
BASE += [f"s_g{g}_{k}" for g in range(2, 9) for k in ("mean", "sd")]
LEVEL = ([f"c_same_{l:g}" for l in LAGS] + [f"c_samemax_{l:g}" for l in LAGS]
         + [f"c_adj_{l:g}" for l in LAGS] + [f"c_adjmax_{l:g}" for l in LAGS])
DIFF = ([f"d_same_{l:g}" for l in LAGS] + [f"d_samemax_{l:g}" for l in LAGS]
        + [f"d_adj_{l:g}" for l in LAGS] + [f"d_adjmax_{l:g}" for l in LAGS])


def rank_score(rows: list[dict], keys: list[str], train: list[dict], test: list[dict]) -> np.ndarray:
    """Ridge probe with a fixed per-sample penalty across anchor spacings."""
    def mat(rs): return np.array([[float(r[k]) for k in keys] for r in rs], float)
    x = mat(train); z = mat(test)
    y = np.array([1.0 if r["cls"] == "IN" else 0.0 for r in train])
    mu = np.nanmedian(x, axis=0); sd = np.nanmedian(np.abs(x - mu), axis=0) * 1.4826
    sd[~np.isfinite(sd) | (sd < 1e-6)] = 1.0
    x = np.nan_to_num((x - mu) / sd); z = np.nan_to_num((z - mu) / sd)
    X = np.c_[np.ones(len(x)), x]; Z = np.c_[np.ones(len(z)), z]
    # Equivalent to minimizing mean squared loss + alpha * ||w||^2.
    reg = np.eye(X.shape[1]) * (2.0 * len(X)); reg[0, 0] = 0.01 * len(X)
    return Z @ np.linalg.solve(X.T @ X + reg, X.T @ y)


def evaluate(rows: list[dict], W: float) -> None:
    rows = [r for r in rows if r["W"] == W]
    print(f"\nWINDOW {W:.0f}s: windows={len(rows)} IN={sum(r['cls']=='IN' for r in rows)} TW={sum(r['cls']=='TW' for r in rows)}")
    groups=sorted({r["fixture"] for r in rows})
    for held in groups:
        te=[r for r in rows if r["fixture"] == held]
        tr=[r for r in rows if r["fixture"] != held]
        if {r["cls"] for r in te} != {"IN","TW"} or {r["cls"] for r in tr} != {"IN","TW"}:
            continue
        y=np.array([r["cls"]=="IN" for r in te])
        print(f"  holdout {held} n={len(te)}", end="")
        for name, keys in (("baseline", BASE), ("level", BASE+LEVEL), ("detrended", BASE+DIFF)):
            p=rank_score(tr, keys, tr, te)
            print(f" {name}={e16.auc(y,p):.3f}", end="")
        print()
    # Per-span counts and simple descriptive correlation ranges.
    for k in sorted({(r["fixture"],r["cls"],r["span"]) for r in rows}):
        q=[r for r in rows if (r["fixture"],r["cls"],r["span"])==k]
        print(f"  span {k[0]}:{k[1]}:{k[2]} n={len(q)}")


def hard(rows: list[dict]) -> None:
    print("\nHARD LATE STOVE/ISLAND VS ALL TOILET WINDOWS")
    ta=data.local("2026-09-09 21:24:20"); tb=data.local("2026-09-09 21:25:00")
    tc=data.local("2026-09-09 23:15:27"); td=data.local("2026-09-09 23:22:37")
    a=data.local("2026-09-09 23:10:54"); b=data.local("2026-09-09 23:13:46")
    for W in WINDOWS:
        te=[r for r in rows if r["W"]==W and r["fixture"].startswith("labeled-sessions")
            and ((r["cls"]=="IN" and (ta<=r["t"]<=tb or tc<=r["t"]<=td))
                 or (r["cls"]=="TW" and a<=r["t"]<=b))]
        tr=[r for r in rows if r["W"]==W and not r["fixture"].startswith("labeled-sessions")]
        if {r["cls"] for r in te}!={"IN","TW"}: continue
        y=np.array([r["cls"]=="IN" for r in te])
        print(f"  W={W:.0f}s n={len(te)} IN={y.sum()} TW={(~y).sum()}",end="")
        for name, keys in (("baseline",BASE),("level",BASE+LEVEL),("detrended",BASE+DIFF)):
            p=rank_score(tr,keys,tr,te); print(f" {name}={e16.auc(y,p):.3f}",end="")
        print()


def main() -> None:
    rows=[]
    for fx in data.all_fixtures().values():
        if fx.sensor != "d06e": continue
        for cls in ("IN","TW"):
            for no,(_,a,b) in enumerate(fx.class_spans(cls)):
                for W in WINDOWS:
                    rows.extend(features(fx,cls,no,a,b,W))
    print(f"step={STEP_S:g}s rows={len(rows)} fixtures={sorted(set(r['fixture'] for r in rows))}")
    for W in WINDOWS: evaluate(rows,W)
    hard(rows)


if __name__ == "__main__": main()
