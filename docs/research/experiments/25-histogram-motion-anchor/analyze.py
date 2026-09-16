"""Exp25: causal histogram floor/spread paired with exp21 motion anchoring.

Labels are read only by the reporting layer.  The replay uses bathroom gates
2..8, and learns histogram state from each recording prefix only.
"""
import importlib.util, json, statistics
from collections import Counter
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("exp21", HERE.parent / "21-component-retention" / "analyze.py")
e = importlib.util.module_from_spec(spec); spec.loader.exec_module(e)

BW = 2
MODE_BAND = 6
MIN_MAD = 1.0
MODE_MIN_S = 60.0

def weighted_median(values, counts):
    order=np.argsort(values); v=values[order]; c=np.cumsum(counts[order]); n=int(c[-1])
    return float((v[np.searchsorted(c,(n-1)//2+1)]+v[np.searchsorted(c,n//2+1)])/2)

def hist_state(counts):
    bins=np.bincount(np.arange(101)//BW,weights=counts)
    k=int(np.argmax(bins)); indices=np.arange(101)
    inside=(indices//BW==k)
    mode=weighted_median(indices[inside],counts[inside])
    local=abs(indices-mode)<=MODE_BAND
    mad=weighted_median(abs(indices[local]-mode),counts[local])
    return mode,max(MIN_MAD,mad)

def replay_hist(t, move, still, use_spread=True, tau=15., bar=40., retain=.4):
    m, s = move[:, 2:9], still[:, 2:9]
    counts = np.zeros((7,101),dtype=int)
    assert t[-1]-t[0]<12*3600, "Prototype requires recording shorter than baseline window"
    active = np.zeros(len(t), bool); score = np.zeros(len(t)); residual = np.zeros_like(s)
    h = None; trusted = False; warmup = None; floor = spread = None; last_est_t = None
    for i in range(len(t)):
        dt = 0. if i == 0 else max(0., float(t[i] - t[i-1]))
        if dt > .55: h = None
        counts[np.arange(7),s[i].astype(int)] += 1
        if not trusted and float(t[i] - t[0]) >= MODE_MIN_S:
            trusted = True; warmup = float(t[i] - t[0])
        if trusted and (last_est_t is None or float(t[i]) - last_est_t >= 5.0):
            floor = np.empty(s.shape[1]); spread = np.empty(s.shape[1])
            for g in range(s.shape[1]): floor[g], spread[g] = hist_state(counts[g])
            last_est_t = float(t[i])
        if trusted:
            r = np.maximum(s[i] - floor, 0.)
            z = r / spread
        else:
            r = np.maximum(s[i] - s[0], 0.)
            z = r
        residual[i] = r
        strong = m[i].max() >= bar
        candidate = (z if use_spread else r) * (m[i] / max(float(m[i].max()), 1.))
        if strong and np.dot(candidate, candidate) >= 1.:
            if h is None or np.dot(candidate, candidate) > np.dot(h, h): h = candidate.copy()
        if h is not None:
            score[i] = float(np.dot(z if use_spread else r, h) / np.dot(h, h))
            active[i] = score[i] >= retain
            if not active[i]: h = None
    return active, score, residual, (warmup if warmup is not None else MODE_MIN_S)

def assess(f, active):
    out = {"rates": {c: e.b.rate(active, e.b.mask(f,c)) for c in ("IN","TW","EMPTY")}, "visits": []}
    for c,a,z in f.spans:
        if c != "IN": continue
        q=(f.ts>=a)&(f.ts<z); ids=np.flatnonzero(q); on=ids[active[ids]]
        pre=np.flatnonzero((f.ts>=a-1)&(f.ts<a))
        post=np.flatnonzero((f.ts>=z)&(f.ts<z+10)); off=post[~active[post]]
        budget=np.flatnonzero((f.ts>=z)&(f.ts<z+30)); budget_off=budget[~active[budget]]
        first=int(on[0]) if len(on) else None
        prem=[]
        if first is not None:
            for x,y in runs(~active, f.ts, first):
                if f.ts[x] < z and f.ts[y] >= f.ts[first]: prem.append(float(f.ts[y]-f.ts[x]))
        out["visits"].append({"start":a,"end":z,"detected_frames":int(active[q].sum()),
          "frames":int(q.sum()),"first_detection_offset_s":None if first is None else float(f.ts[first]-a),
          "pre_entry_positive_frames_1s":int(active[pre].sum()),
          "premature_dropout_durations_s":prem,
          "first_clear_offset_s":None if len(off)==0 else float(f.ts[off[0]]-z),
          "clear_within_30s":bool(len(budget_off)),
          "post_exit_positive_frames_10s":int(active[post].sum()),
          "retrigger_after_first_clear_10s":bool(len(off) and np.any(active & (f.ts>f.ts[off[0]]) & (f.ts<z+10)))})
    return out

def runs(x, t, start=0):
    ids=np.flatnonzero(x & (np.arange(len(x))>=start)); out=[]; a=prev=None
    for i in ids:
        if prev is None or i != prev+1 or t[i]-t[prev]>.55:
            if a is not None: out.append((a,prev))
            a=i
        prev=i
    if a is not None: out.append((a,prev))
    return out

def tail_split(f, active, a, z):
    # Bounded per-visit windows: kitchen spans are clipped at the next IN start.
    next_in=min((x for c,x,_ in f.spans if c=="IN" and x>=z), default=float("inf"))
    tw=[(x,min(y,next_in)) for c,x,y in f.spans if c=="TW" and z<=x<next_in]
    clear_end=min(z+30., next_in)
    off=np.flatnonzero((f.ts>=z)&(f.ts<clear_end)&~active); clear=float(f.ts[off[0]]) if len(off) else clear_end
    tail=(f.ts>=z)&(f.ts<clear); later=np.zeros(len(f.ts),bool)
    for x,y in tw: later|=(f.ts>=max(x,clear))&(f.ts<y)
    labeled=np.zeros(len(f.ts),bool)
    for x,y in tw: labeled|=(f.ts>=x)&(f.ts<min(y,clear))
    pct=lambda q: None if not q.any() else 100.*float(np.mean(active[q]))
    return {"clear_offset_s":float(clear-z),"tail_frames":int(tail.sum()),"tail_positive":int((active&tail).sum()),
            "tail_false_fraction_pct":pct(tail),"labeled_tail_frames":int((tail&labeled).sum()),
            "labeled_tail_positive":int((active&tail&labeled).sum()),"later_frames":int(later.sum()),
            "later_positive":int((active&later).sum()),"later_false_fraction_pct":pct(later)}

def main():
    # Verify the imported baseline remains byte-for-byte behaviorally identical.
    old=json.loads((HERE.parent/"21-component-retention"/"reassessment-0915"/"results.json").read_text())
    result={"parameters":{"bin_width":BW,"mode_band":MODE_BAND,"min_mad":MIN_MAD,"mode_min_s":MODE_MIN_S,
      "tau":15.,"motion_bar":40.,"retain":.4},"fixtures":{}}
    for name in ("labeled-walk-0915.db","labeled-loop-0915.db"):
        f=e.b.new_fixture(name); base=e.replay(f.ts,f.move,f.still,15.,40.,.4)[0]
        assert e.assess(f,base)==old["fixtures"][name[:-3]]["default_assessment"]
        base_score=e.replay(f.ts,f.move,f.still,15.,40.,.4)[1]
        variants={"baseline21":(base,None,base_score),}
        for label,spread in (("hist_floor_only",False),("hist_floor_spread",True)):
            a,sc,rr,w=replay_hist(f.ts,f.move,f.still,spread); variants[label]=(a,w,sc)
        result["fixtures"][name]={}
        for label,(a,w,sc) in variants.items():
            d=assess(f,a); d["warmup_s"]=None if w is None else float(w)
            d["active_frames"]=int(a.sum()); d["score_max"]=float(sc.max())
            d["exit_tail_split"]=[tail_split(f,a,x,z) for c,x,z in f.spans if c=="IN"]
            result["fixtures"][name][label]=d
        # Prefix causality for both histogram variants.
        n=max(1,len(f.ts)-700)
        for spread in (False,True):
            full=replay_hist(f.ts,f.move,f.still,spread)[0]; pre=replay_hist(f.ts[:n],f.move[:n],f.still[:n],spread)[0]
            assert np.array_equal(full[:n],pre)
    (HERE/"results.json").write_text(json.dumps(result,indent=2)); (HERE/"results.txt").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))

if __name__=="__main__": main()
