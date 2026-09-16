"""Frozen per-frame IN/TW separability test for the bathroom LD2410."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "15-gate-profile"))
import data  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
BATH = "D0:6E:81:D2:5D:A6"
CONFIRM_N = 3


def vec(move: np.ndarray, still: np.ndarray) -> np.ndarray:
    return np.c_[move, still[:, 2:9]]


def load_db(name: str, sensor: str = BATH) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    p = ROOT / "tests" / "fixtures" / "recordings" / name
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    rows = c.execute("select ts,move,still from frames where sensor_id=? order by ts", (sensor,)).fetchall()
    return (np.array([r[0] for r in rows], float),
            np.array([list(bytes(r[1])) for r in rows], float),
            np.array([list(bytes(r[2])) for r in rows], float))


def robust_fit(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    med = np.median(x, axis=0); scale = 1.4826 * np.median(np.abs(x - med), axis=0)
    scale[~np.isfinite(scale) | (scale < 1e-6)] = 1.0
    z = np.nan_to_num((x - med) / scale)
    X = np.c_[np.ones(len(z)), z]
    reg = np.eye(X.shape[1]) * (2.0 * len(X)); reg[0, 0] = 0.01 * len(X)
    w = np.linalg.solve(X.T @ X + reg, X.T @ y)
    return med, scale, w


def robust_score(x: np.ndarray, fit: tuple[np.ndarray,np.ndarray,np.ndarray]) -> np.ndarray:
    med, scale, w = fit
    return np.c_[np.ones(len(x)), np.nan_to_num((x-med)/scale)] @ w


def best_train_threshold(score: np.ndarray, y: np.ndarray) -> float:
    # Threshold is selected on training data only. Ties choose the higher
    # threshold, which is the conservative choice for false occupancy.
    cand = np.unique(np.percentile(score, np.linspace(0, 100, 401)))
    best = None
    for t in cand:
        tp = (score[y==1] >= t).mean(); fp = (score[y==0] >= t).mean()
        key = (tp-fp, t)
        if best is None or key > best[0]: best = (key, float(t))
    return best[1]


def amp_value(m: np.ndarray, s: np.ndarray) -> np.ndarray:
    # Fixed simple amplitude summary: near/occupied still and move energy.
    return np.c_[s[:,2:5].max(1), s[:,2:9].max(1), m[:,:5].max(1), m.max(1)]


def train_old(exclude: str | None = None) -> dict:
    xs=[]; ys=[]
    for fx in data.all_fixtures().values():
        if fx.sensor != "d06e" or fx.name == exclude: continue
        for cls, y in (("IN",1),("TW",0)):
            mask=fx.class_mask(cls)
            xs.append(vec(fx.move[mask],fx.still[mask])); ys.append(np.full(mask.sum(),y))
    x=np.vstack(xs); y=np.concatenate(ys)
    full=robust_fit(x,y); full_thr=best_train_threshold(robust_score(x,full),y)
    av=[]
    for fx in data.all_fixtures().values():
        if fx.sensor != "d06e" or fx.name == exclude: continue
        for cls,yv in (("IN",1),("TW",0)):
            m=fx.class_mask(cls); av.append((amp_value(fx.move[m],fx.still[m]),np.full(m.sum(),yv)))
    ax=np.vstack([z[0] for z in av]); ay=np.concatenate([z[1] for z in av])
    amp=robust_fit(ax,ay); amp_thr=best_train_threshold(robust_score(ax,amp),ay)
    return {"full":full,"full_thr":full_thr,"amp":amp,"amp_thr":amp_thr,
            "n":len(y),"n_in":int(y.sum()),"n_tw":int((y==0).sum())}


def confirm(raw: np.ndarray, ts: np.ndarray) -> np.ndarray:
    out=np.zeros(len(raw),bool)
    for i in range(CONFIRM_N-1,len(raw)):
        if ts[i]-ts[i-CONFIRM_N+1] <= 0.38 and raw[i-CONFIRM_N+1:i+1].all(): out[i]=True
    return out


def runs(mask: np.ndarray, ts: np.ndarray) -> tuple[int,float,float]:
    ix=np.flatnonzero(mask)
    if not len(ix): return 0,0.0,0.0
    starts=[ix[0]]; ends=[]
    for i,j in zip(ix,ix[1:]):
        # A false frame terminates a run even if the timestamps are close.
        if j != i + 1 or ts[j]-ts[i] > .55: ends.append(i); starts.append(j)
    ends.append(ix[-1]); dur=[float(ts[b]-ts[a]) for a,b in zip(starts,ends)]
    return len(dur),max(dur),sum(dur)


def auc(y,s):
    y=np.asarray(y,bool); s=np.asarray(s,float)
    p=s[y]; n=s[~y]
    if not len(p) or not len(n): return float('nan')
    z=np.sort(np.concatenate([p,n])); ranks=np.arange(1,len(z)+1,dtype=float)
    i=0
    while i<len(z):
        j=i+1
        while j<len(z) and z[j]==z[i]: j+=1
        ranks[i:j]=(i+1+j)/2; i=j
    # Reconstruct rank lookup through a sorted merge; ties are handled by the
    # averaged rank array above.
    ps=np.searchsorted(z,p,side='left'); ns=np.searchsorted(z,n,side='left')
    return float((ranks[ps].sum()-len(p)*(len(p)+1)/2)/(len(p)*len(n)))


def eval_segments(name: str, ts: np.ndarray, move: np.ndarray, still: np.ndarray,
                  segs: list[tuple[str,float,float]], train: dict, split: str) -> None:
    x=vec(move,still); full=robust_score(x,train["full"]); amp=robust_score(amp_value(move,still),train["amp"])
    full_raw=full>=train["full_thr"]; amp_raw=amp>=train["amp_thr"]
    full_conf=confirm(full_raw,ts); amp_conf=confirm(amp_raw,ts)
    rows=[]
    for label,a,b in segs:
        m=(ts>=a)&(ts<b); 
        if not m.any(): continue
        for model,score,thr in (("amp",amp,train["amp_thr"]),("full",full,train["full_thr"])):
            raw=(amp_raw if model=="amp" else full_raw)[m]
            con=(amp_conf if model=="amp" else full_conf)[m]
            nr,mx,tot=runs(raw,ts[m]); nc,cx,ct=runs(con,ts[m])
            first_raw=np.flatnonzero(raw); first_con=np.flatnonzero(con)
            lagr=(float(ts[m][first_raw[0]]-a) if len(first_raw) else float('nan'))
            lagc=(float(ts[m][first_con[0]]-a) if len(first_con) else float('nan'))
            pre=(ts<a)&(ts>=a-1.0)
            pre_active=bool(((amp_raw if model=="amp" else full_raw)[pre]).any())
            rows.append((label,model,int(m.sum()),int(raw.sum()),100.0*float(raw.mean()),nr,mx,tot/60,nc,cx,ct/60,lagr,lagc,pre_active))
    print(f"{name} {split} segments")
    for r in rows: print("  %-12s %-4s n=%5d positive=%5d frame=%5.1f%% runs=%2d max=%5.1fs run_span_min=%5.2f conf_runs=%2d conf_max=%5.1fs conf_span_min=%5.2f lag_raw=%5.2fs lag_conf=%5.2fs pre=%s" % r)
    known=[r for r in segs if r[0] in ('IN','TW')]
    m=np.zeros(len(ts),bool); y=np.zeros(len(ts),int)
    for label,a,b in known:
        q=(ts>=a)&(ts<b); m|=q; y[q]=(label=='IN')
    if m.any():
        for model,score in (("amp",amp),("full",full)):
            print(f"  {name} {model} known AUC={auc(y[m],score[m]):.3f} n={m.sum()}")
        inq=(y==1)&m
        for model,score,thr in (("amp",amp,train["amp_thr"]),("full",full,train["full_thr"])):
            print(f"  {name} {model} IN missed={1-(score[inq]>=thr).mean():.3f}")


def labels_for(name: str, ts: np.ndarray) -> list[tuple[str,float,float]]:
    c=sqlite3.connect(ROOT/"tests"/"fixtures"/"recordings"/name)
    labels=c.execute("select person,room,ts_start,ts_end,note from labels order by ts_start").fetchall()
    if name == 'labeled-walk-0915.db':
        wife=[(a,b) for p,room,a,b,_ in labels if p=='wife' and room=='kitchen']
        rob=[(room,a,b) for p,room,a,b,_ in labels if p=='rob']
        if wife:
            scope_a=min(a for a,_ in wife); scope_b=max(b for _,b in wife)
            cuts={scope_a,scope_b}
            for room,a,b in rob:
                if b>scope_a and a<scope_b: cuts.update((max(a,scope_a),min(b,scope_b)))
            out=[]; cuts=sorted(cuts)
            for a,b in zip(cuts,cuts[1:]):
                rooms=[room for room,x,y in rob if x<=a+.01 and b<=y+.01]
                if not rooms or not any(x<=a+.01 and b<=y+.01 for x,y in wife): continue
                cls='IN' if 'bathroom' in rooms else 'TW'
                if out and out[-1][0]==cls and abs(out[-1][2]-a)<.02: out[-1]=(cls,out[-1][1],b)
                else: out.append((cls,a,b))
            # Explicit Rob labels outside the wife's kitchen scope remain
            # useful segment diagnostics, but are excluded from IN/TW AUC.
            for room,a,b in rob:
                if b<=scope_a or a>=scope_b:
                    out.append((room.upper(),a,b))
            return [(cls,max(a,float(ts[0])),min(b,float(ts[-1]))) for cls,a,b in out if min(b,float(ts[-1]))>max(a,float(ts[0]))]
    out=[]
    for p,room,a,b,note in labels:
        if p!='rob': continue
        cls='IN' if room=='bathroom' else ('TW' if room=='kitchen' else room.upper())
        a=max(a,float(ts[0])); b=min(b,float(ts[-1]))
        if b>a: out.append((cls,a,b))
    return out


def main():
    old=train_old(); print(f"TRAIN old n={old['n']} IN={old['n_in']} TW={old['n_tw']} full_thr={old['full_thr']:.4f} amp_thr={old['amp_thr']:.4f}")
    for name in ('labeled-loop-0915.db','labeled-walk-0915.db'):
        ts,m,s=load_db(name); print(f"\n{name} D0 frames={len(ts)} dt_med={np.median(np.diff(ts)):.3f} gaps>.55={(np.diff(ts)>.55).sum()}")
        eval_segments(name,ts,m,s,labels_for(name,ts),old,'train-all-old')
    for held in ('stove-case-0913-d06e','labeled-sessions-0909-d06e'):
        tr=train_old(held); fx=data.load(held); seg=[]
        for cls in ('IN','TW','EMPTY'):
            for _,a,b in fx.class_spans(cls): seg.append((cls,a,b))
        eval_segments(held,fx.ts,fx.move,fx.still,seg,tr,'old-heldout')


if __name__=='__main__': main()
