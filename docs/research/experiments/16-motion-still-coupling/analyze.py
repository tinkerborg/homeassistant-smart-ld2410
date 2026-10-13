"""Offline test of motion-to-still temporal coupling.

The data are 10 Hz-ish but have occasional timestamp gaps. All windows use
timestamps and are rejected across gaps > GAP_S. A burst is one local maximum
of the maximum move gate after a short causal smoothing window, with nearby
peaks merged. Features are extracted only within a labelled span and at least
BOUNDARY_S from its ends. The label boundary margin avoids treating entry or
exit transitions as evidence for the class.

This is deliberately a small, transparent experiment: no production code is
changed and no random frame split is used. Event-level metrics are descriptive;
leave-one-span-out predictions are the more honest generalization check.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "15-gate-profile"))
import data  # noqa: E402


GAP_S = 0.55
BOUNDARY_S = 5.5
SMOOTH_S = 0.4
MERGE_S = 1.5
PEAK_SEP_S = 2.5
PEAK_MIN = 18.0
LOOKAHEAD_S = (0.5, 1.0, 2.0, 3.0, 5.0)
RESPONSE_WIN_S = 5.0


def med_dt(ts: np.ndarray) -> float:
    return float(np.median(np.diff(ts)))


def smooth_max(ts: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Causal-ish rolling max over a short time window, gap-aware enough."""
    dt = med_dt(ts)
    n = max(1, int(round(SMOOTH_S / dt)))
    # A centered value is only used for event detection, never as a proposed
    # detector feature. The extracted feature itself is at the peak frame.
    y = np.empty(len(x))
    for i in range(len(x)):
        a = max(0, i - n // 2)
        b = min(len(x), i + n // 2 + 1)
        q = ts[a:b]
        v = x[a:b]
        if len(q) and (q[-1] - q[0]) <= SMOOTH_S * 1.8:
            y[i] = np.max(v)
        else:
            y[i] = x[i]
    return y


def local_peaks(ts: np.ndarray, x: np.ndarray) -> list[int]:
    """Find separated peaks without scipy; return source frame indices."""
    sm = smooth_max(ts, x)
    cand = [i for i in range(1, len(x) - 1)
            if sm[i] >= PEAK_MIN and sm[i] >= sm[i - 1] and sm[i] >= sm[i + 1]
            and (ts[i] - ts[i - 1]) <= GAP_S and (ts[i + 1] - ts[i]) <= GAP_S]
    # Non-maximum suppression in time. Prefer the stronger peak in a local
    # burst, which prevents 10 Hz serial correlation becoming many samples.
    out: list[int] = []
    for i in sorted(cand, key=lambda j: sm[j], reverse=True):
        # The smoothed maximum can land anywhere on a saturated plateau. Use
        # the strongest raw frame in a short neighbourhood, then re-apply the
        # separation rule to the shifted/raw event time.
        ix = np.flatnonzero((ts >= ts[i] - 0.25) & (ts <= ts[i] + 0.25))
        j = int(ix[np.argmax(x[ix])]) if len(ix) else i
        if all(abs(ts[j] - ts[k]) >= PEAK_SEP_S for k in out):
            out.append(j)
    return sorted(out)


def nearest(ts: np.ndarray, t: float) -> int | None:
    i = int(np.searchsorted(ts, t))
    choices = [j for j in (i - 1, i) if 0 <= j < len(ts)]
    if not choices:
        return None
    j = min(choices, key=lambda k: abs(float(ts[k]) - t))
    if abs(float(ts[j]) - t) > 0.35:
        return None
    return j


def mean_window(ts: np.ndarray, v: np.ndarray, a: float, b: float) -> np.ndarray | None:
    m = (ts >= a) & (ts < b)
    if not m.any():
        return None
    ix = np.flatnonzero(m)
    if ts[ix[-1]] - ts[ix[0]] > (b - a) * 2.2:
        return None
    if len(ix) > 1 and np.max(np.diff(ts[ix])) > GAP_S:
        return None
    return np.mean(v[m], axis=0)


def full_window_ok(ts: np.ndarray, a: float, b: float) -> bool:
    """Require coverage and no timestamp gap over the complete response window."""
    ix = np.flatnonzero((ts >= a) & (ts <= b))
    if len(ix) < 2:
        return False
    if abs(float(ts[ix[0]]) - a) > 0.35 or abs(float(ts[ix[-1]]) - b) > 0.35:
        return False
    return float(np.max(np.diff(ts[ix]))) <= GAP_S


def extract(fx: data.Fixture) -> list[dict]:
    # Raw max move is used for event finding. This intentionally tests the
    # information actually exported by the LD2410, not learned empty floors.
    mmax = fx.move.max(axis=1)
    peaks = local_peaks(fx.ts, mmax)
    rows: list[dict] = []
    for cls in ("IN", "TW"):
        for span_no, (_, a, b) in enumerate(fx.class_spans(cls)):
            for i in peaks:
                t = float(fx.ts[i])
                if not (a + BOUNDARY_S <= t < b - BOUNDARY_S):
                    continue
                # Any large data gap around the peak invalidates response
                # features; the burst can still be counted by the caller but
                # is not quietly interpolated.
                if i == 0 or i + 1 >= len(fx.ts) or fx.ts[i] - fx.ts[i - 1] > GAP_S:
                    continue
                if not full_window_ok(fx.ts, t - 0.7, t + RESPONSE_WIN_S + 0.35):
                    continue
                pre = mean_window(fx.ts, fx.still, t - 0.7, t - 0.1)
                if pre is None:
                    continue
                peak_gate = int(np.argmax(fx.move[i]))
                strength = float(fx.move[i, peak_gate])
                fut = {}
                for lag in LOOKAHEAD_S:
                    j = nearest(fx.ts, t + lag)
                    fut[lag] = float(fx.still[j, peak_gate]) if j is not None else float("nan")
                post = mean_window(fx.ts, fx.still, t + 0.5, t + RESPONSE_WIN_S)
                if post is None:
                    continue
                # Channel interaction features: response at the motion gate,
                # local response over adjacent gates, and a simple latency.
                post_gate = float(post[peak_gate])
                lo = max(0, peak_gate - 1); hi = min(9, peak_gate + 2)
                pre_gate = float(np.mean(pre[lo:hi]))
                post_local = float(np.mean(post[lo:hi]))
                response = post_local - pre_gate
                vals = [v for v in fut.values() if np.isfinite(v)]
                rise = max(vals) - float(pre[peak_gate]) if vals else float("nan")
                rows.append({
                    "fixture": fx.name, "sensor": fx.sensor, "cls": cls,
                    "span": span_no, "t": t, "peak_gate": peak_gate,
                    "strength": strength, "move_mass": float(fx.move[i].sum()),
                    "pre_still": float(pre[peak_gate]), "post_still": post_gate,
                    "response": response, "rise": rise,
                    "depth": float(np.mean(post[peak_gate:min(9, peak_gate + 3)])),
                    "pre_mass": float(pre.sum()),
                    "pre_centroid": float((pre * np.arange(9)).sum() / max(pre.sum(), 1e-6)),
                    "move_centroid": float((fx.move[i] * np.arange(9)).sum() / max(fx.move[i].sum(), 1e-6)),
                    "saturated": bool(strength >= 95),
                    **{f"s{lag:g}": v for lag, v in fut.items()},
                })
                for lag, v in fut.items():
                    rows[-1][f"d{lag:g}"] = v - float(pre[peak_gate]) if np.isfinite(v) else float("nan")
    return rows


def auc(y: np.ndarray, s: np.ndarray) -> float:
    m = np.isfinite(s)
    y = y[m]; s = s[m]
    p = s[y == 1]; n = s[y == 0]
    if not len(p) or not len(n):
        return float("nan")
    # Mann-Whitney probability, ties half credit.
    return float(((p[:, None] > n[None, :]).sum() + 0.5 * (p[:, None] == n[None, :]).sum()) / (len(p) * len(n)))


def rank_score(rows: list[dict], keys: list[str], train: list[dict], test: list[dict]) -> np.ndarray:
    """A small regularized linear score fit on train, no sklearn dependency."""
    def mat(rs):
        return np.array([[float(r[k]) for k in keys] for r in rs], float)
    x = mat(train); z = mat(test)
    y = np.array([1.0 if r["cls"] == "IN" else 0.0 for r in train])
    mu = np.nanmedian(x, axis=0); sd = np.nanmedian(np.abs(x - mu), axis=0) * 1.4826
    sd[~np.isfinite(sd) | (sd < 1e-6)] = 1.0
    x = np.nan_to_num((x - mu) / sd); z = np.nan_to_num((z - mu) / sd)
    # Ridge least-squares is stable enough for a separability probe and keeps
    # the model interpretable; it is not proposed production classifier.
    X = np.c_[np.ones(len(x)), x]; Z = np.c_[np.ones(len(z)), z]
    reg = np.eye(X.shape[1]) * 2.0; reg[0, 0] = 0.01
    w = np.linalg.solve(X.T @ X + reg, X.T @ y)
    return Z @ w


def group_rows(rows: list[dict]) -> dict[str, list[dict]]:
    out = {}
    for r in rows:
        out.setdefault(f"{r['fixture']}:{r['cls']}:{r['span']}", []).append(r)
    return out


def print_summary(rows: list[dict]) -> None:
    print(f"events={len(rows)} IN={sum(r['cls']=='IN' for r in rows)} TW={sum(r['cls']=='TW' for r in rows)}")
    print(f"motion-saturated (>=95): {sum(r['saturated'] for r in rows)} ({sum(r['saturated'] for r in rows)/max(len(rows),1):.1%})")
    print("per-span event counts:")
    for k, rs in group_rows(rows).items():
        print(f"  {k:60s} n={len(rs):3d} gates={sorted(set(r['peak_gate'] for r in rs))}")
    y = np.array([r["cls"] == "IN" for r in rows])
    print("pooled AUC (descriptive; serially dependent events):")
    for k in ("strength", "peak_gate", "move_mass", "response", "rise", "depth", "s0.5", "s1", "s2", "s3", "s5"):
        s = np.array([r[k] for r in rows], float)
        if k == "peak_gate":
            # gate number is a location baseline; orientation is arbitrary,
            # so report the better of either direction.
            a = max(auc(y, s), auc(y, -s))
        else:
            a = max(auc(y, s), auc(y, -s))
            print(f"  {k:10s} {a:.3f}")
    active = [r for r in rows if r["peak_gate"] >= 2]
    print(f"still-active gate>=2 events={len(active)} IN={sum(r['cls']=='IN' for r in active)} TW={sum(r['cls']=='TW' for r in active)}")
    ya = np.array([r["cls"] == "IN" for r in active])
    for k in ("response", "rise", "d0.5", "d1", "d2", "d3", "d5"):
        s = np.array([r[k] for r in active], float)
        print(f"  active {k:6s} {max(auc(ya,s),auc(ya,-s)):.3f} (descriptive best direction)")
    ns = [r for r in rows if not r["saturated"]]
    if len(ns) >= 20:
        yy = np.array([r["cls"] == "IN" for r in ns])
        print(f"nonsaturated-only events={len(ns)}")
        for k in ("response", "rise", "d0.5", "d1", "d2", "d3", "d5"):
            s=np.array([r[k] for r in ns], float)
            print(f"  {k:10s} {max(auc(yy,s),auc(yy,-s)):.3f}")


def loo(rows: list[dict]) -> None:
    groups = sorted({(r["fixture"], r["cls"], r["span"]) for r in rows})
    print("leave-one-span-out AUC (held-out span; model fit on other spans):")
    # Baseline gets the current motion amplitude/location and the already
    # present still state. This avoids crediting a temporal feature for an
    # ordinary level/profile difference.
    base = ["strength", "move_mass", "peak_gate", "pre_still", "pre_mass", "pre_centroid", "move_centroid"]
    temporal = base + ["response", "rise", "d0.5", "d1", "d2", "d3", "d5"]
    level = base + ["depth", "s0.5", "s1", "s2", "s3", "s5"]
    for keys in (base, temporal, level):
        pred=[]; yy=[]
        for g in groups:
            tr=[r for r in rows if (r["fixture"],r["cls"],r["span"]) != g]
            te=[r for r in rows if (r["fixture"],r["cls"],r["span"]) == g]
            if not tr or not te or {r["cls"] for r in tr} != {"IN","TW"}:
                continue
            pred.extend(rank_score(tr, keys, tr, te)); yy.extend(1 if r["cls"]=="IN" else 0 for r in te)
        # Keep the orientation learned from training. Do not choose the better
        # sign using the held-out labels.
        a=auc(np.array(yy),np.array(pred))
        tag = 'baseline' if keys==base else ('delta' if keys==temporal else 'level')
        print(f"  {tag:9s} n={len(yy):3d} AUC={a:.3f}")

    # Whole-fixture holdouts are the primary generalization check where both
    # classes exist in the held-out fixture. Other fixtures contain only one
    # class and cannot yield an AUC by themselves.
    print("whole-fixture holdout AUC (only fixtures containing IN and TW):")
    for fixture in sorted({r["fixture"] for r in rows}):
        te=[r for r in rows if r["fixture"] == fixture]
        if {r["cls"] for r in te} != {"IN", "TW"}: continue
        tr=[r for r in rows if r["fixture"] != fixture]
        if {r["cls"] for r in tr} != {"IN", "TW"}: continue
        vals=[]
        for name, keys in (("baseline",base),("delta",temporal),("level",level)):
            p=rank_score(tr,keys,tr,te); y=np.array([r["cls"]=="IN" for r in te])
            vals.append(f"{name}={auc(y,p):.3f}")
        print(f"  {fixture}: n={len(te)} " + " ".join(vals))


def matched(rows: list[dict]) -> None:
    """Greedy deterministic pairs within the same gate and motion strength."""
    print("matched IN/TW bursts (same peak gate, strength within max(5,20%));")
    rows = [r for r in rows if r["peak_gate"] >= 2]
    for fixture in sorted({r["fixture"] for r in rows}):
        ins = [r for r in rows if r["fixture"] == fixture and r["cls"] == "IN"]
        tws = [r for r in rows if r["fixture"] == fixture and r["cls"] == "TW"]
        used=set(); pairs=[]
        for a in sorted(ins, key=lambda r: (r["peak_gate"], r["strength"], r["t"])):
            cand=[(abs(a["strength"]-b["strength"]),j,b) for j,b in enumerate(tws)
                  if j not in used and b["peak_gate"] == a["peak_gate"]
                  and abs(a["strength"]-b["strength"]) <= max(5.0, .2*a["strength"])]
            if cand:
                _,j,b=min(cand,key=lambda x:x[0]); used.add(j); pairs.append((a,b))
        if not pairs: continue
        print(f"  {fixture:38s} pairs={len(pairs):3d}")
        for k in ("response", "rise", "d0.5", "d1", "d2", "d3", "d5", "depth"):
            dif=np.array([a[k]-b[k] for a,b in pairs if np.isfinite(a[k]) and np.isfinite(b[k])])
            if len(dif): print(f"    {k:8s} IN-TW median={np.median(dif):7.2f}  p10/p90={np.percentile(dif,[10,90])}")


def hard_case(rows: list[dict]) -> None:
    print("hard near-wall labeled-sessions case (stove/island TW vs toilet IN):")
    rows = [r for r in rows if r["peak_gate"] >= 2]
    for cls in ("IN", "TW"):
        q = [r for r in rows if r["fixture"] == "labeled-sessions-0909-d06e" and r["cls"] == cls]
        if not q: continue
        print(f"  {cls}: n={len(q)} gates={sorted(set(r['peak_gate'] for r in q))} "
              f"move_p50={np.median([r['strength'] for r in q]):.1f} "
              f"response_p50={np.median([r['response'] for r in q]):.1f} "
              f"d1_p50={np.median([r['d1'] for r in q]):.1f} "
              f"depth_p50={np.median([r['depth'] for r in q]):.1f}")
    # The hard labeled session is the late close stove/island activity versus
    # the earlier toilet visit. Fit only on other fixtures and freeze the sign.
    toilet_a = data.local("2026-09-09 21:24:20")
    toilet_b = data.local("2026-09-09 21:25:00")
    toilet2_a = data.local("2026-09-09 23:15:27")
    toilet2_b = data.local("2026-09-09 23:22:37")
    late_a = data.local("2026-09-09 23:10:54")
    late_b = data.local("2026-09-09 23:13:46")
    te = [r for r in rows if r["fixture"] == "labeled-sessions-0909-d06e"
          and ((r["cls"] == "IN" and ((toilet_a <= r["t"] <= toilet_b)
                                         or (toilet2_a <= r["t"] <= toilet2_b)))
               or (r["cls"] == "TW" and late_a <= r["t"] <= late_b))]
    tr = [r for r in rows if r["fixture"] != "labeled-sessions-0909-d06e"]
    base = ["strength", "move_mass", "peak_gate", "pre_still", "pre_mass", "pre_centroid", "move_centroid"]
    delta = base + ["response", "rise", "d0.5", "d1", "d2", "d3", "d5"]
    level = base + ["depth", "s0.5", "s1", "s2", "s3", "s5"]
    if len(te) and {r["cls"] for r in te} == {"IN", "TW"}:
        y=np.array([r["cls"] == "IN" for r in te])
        print(f"late stove/island vs toilet holdout (gate>=2, train excludes fixture): n={len(te)}")
        for name, keys in (("baseline",base),("delta",delta),("level",level)):
            p=rank_score(tr,keys,tr,te)
            print(f"  {name}: signed AUC={auc(y,p):.3f}")


def main() -> None:
    fixtures = data.all_fixtures()
    rows=[]
    for fx in fixtures.values():
        if fx.sensor == "d06e":
            rows.extend(extract(fx))
    print_summary(rows)
    active = [r for r in rows if r["peak_gate"] >= 2]
    print("\nPRIMARY ANALYSIS: still-active gates only (peak_gate >= 2)")
    loo(active)
    matched(active)
    hard_case(active)


if __name__ == "__main__":
    main()
