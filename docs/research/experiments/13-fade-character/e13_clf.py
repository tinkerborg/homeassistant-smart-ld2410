import pickle, numpy as np, collections, itertools
from e13_lib import FEATNAMES, auc

rows = pickle.load(open("e13_rows.pkl", "rb"))
for r in rows:
    for k in FEATNAMES:
        if r[k] != r[k]: r[k] = 0.0

print("=" * 74)
print("DECISIVE TEST: same sensor (D0:6E), same gates 2-3, same fixture (lab),")
print("amplitude-matched bins. toilet(IN) vs stove/island(TW).")
for ch in ("move", "still"):
    print(f"\n -- {ch}")
    print("  bin        " + "".join(f"{f:>8s}" for f in ["cv","dr_db","df70","kurt","ent","K"]) + "   nIN  nTW")
    for lo, hi in [(8,12),(12,16),(16,22),(22,30),(30,40),(40,58),(58,80),(80,100)]:
        P=[r for r in rows if r["ch"]==ch and r["fx"]=="lab" and r["cls"]=="IN" and r["gate"] in (2,3) and lo<=r["mean"]<hi]
        N=[r for r in rows if r["ch"]==ch and r["fx"]=="lab" and r["cls"]=="TW" and r["gate"] in (2,3) and lo<=r["mean"]<hi]
        if len(P)<25 or len(N)<25: continue
        print(f"  {lo}-{hi}".ljust(13) + "".join(f"{auc([r[f] for r in P],[r[f] for r in N]):8.3f}" for f in ["cv","dr_db","df70","kurt","ent","K"]) + f"  {len(P):5d}{len(N):5d}")

print("\n" + "=" * 74)
print("BEST 2-FEATURE PAIRS (logistic-free: linear discriminant on z-scores), move ch, all windows")
def pairauc(P,N,f1,f2):
    a=np.array([[r[f1],r[f2]] for r in P]); b=np.array([[r[f1],r[f2]] for r in N])
    X=np.vstack([a,b]); mu=X.mean(0); sd=X.std(0)+1e-9
    a=(a-mu)/sd; b=(b-mu)/sd
    S=(np.cov(a.T)*len(a)+np.cov(b.T)*len(b))/(len(a)+len(b))
    try: w=np.linalg.solve(S+np.eye(2)*1e-6, a.mean(0)-b.mean(0))
    except Exception: return .5
    return auc(a@w, b@w)
for scope,P,N in [("ALL move",[r for r in rows if r["ch"]=="move" and r["cls"]=="IN"],[r for r in rows if r["ch"]=="move" and r["cls"]=="TW"]),
                  ("lab g2-3 move",[r for r in rows if r["ch"]=="move" and r["fx"]=="lab" and r["cls"]=="IN" and r["gate"] in (2,3)],
                                   [r for r in rows if r["ch"]=="move" and r["fx"]=="lab" and r["cls"]=="TW" and r["gate"] in (2,3)]),
                  ("lab g2-3 still",[r for r in rows if r["ch"]=="still" and r["fx"]=="lab" and r["cls"]=="IN" and r["gate"] in (2,3)],
                                    [r for r in rows if r["ch"]=="still" and r["fx"]=="lab" and r["cls"]=="TW" and r["gate"] in (2,3)])]:
    best=sorted(((pairauc(P,N,f1,f2),f1,f2) for f1,f2 in itertools.combinations(FEATNAMES,2)),reverse=True)[:4]
    print(f"  {scope:16s} " + "  ".join(f"{f1}+{f2}={A:.3f}" for A,f1,f2 in best))

print("\n" + "=" * 74)
print("PER-EVENT CLASSIFIER: one decision per labeled span.")
print("Score = median over that span's windows on the peak move gate.")
ev = collections.defaultdict(list)
for r in rows:
    ev[(r["fx"], r["note"], r["cls"])].append(r)

def event_score(ws, ch, feat):
    w = [r for r in ws if r["ch"] == ch]
    if not w: return None
    by = collections.defaultdict(list)
    for r in w: by[r["gate"]].append(r)
    g = max(by, key=lambda g: np.mean([r["mean"] for r in by[g]]))
    return float(np.median([r[feat] for r in by[g]])), g, len(by[g]), float(np.mean([r["mean"] for r in by[g]]))

print(f"  {'event':28s} {'cls':5s} {'g':>2s} {'E':>5s} {'cv':>6s} {'dr_db':>6s} {'K':>6s} {'ent':>6s}")
tbl = []
for k in sorted(ev, key=lambda k: (k[2], k[0], k[1])):
    fx, note, cls = k
    s = event_score(ev[k], "move", "cv")
    if s is None: continue
    cvv, g, n, E = s
    row = {}
    for f in ("cv", "dr_db", "K", "ent"):
        w = [r for r in ev[k] if r["ch"] == "move" and r["gate"] == g]
        row[f] = float(np.median([r[f] for r in w]))
    print(f"  {fx+'/'+note:28s} {cls:5s} {g:2d} {E:5.1f} {row['cv']:6.3f} {row['dr_db']:6.2f} {row['K']:6.2f} {row['ent']:6.2f}")
    tbl.append((cls, row, fx, note))

print("\n  threshold sweep on median cv (move, peak gate); IN = cv above thr")
for thr in np.arange(0.25, 0.62, 0.05):
    tp=sum(1 for c,r,_,_ in tbl if c=="IN" and r["cv"]>thr); fn=sum(1 for c,r,_,_ in tbl if c=="IN" and r["cv"]<=thr)
    fp=sum(1 for c,r,_,_ in tbl if c=="TW" and r["cv"]>thr); tn=sum(1 for c,r,_,_ in tbl if c=="TW" and r["cv"]<=thr)
    print(f"   thr={thr:.2f}  TP={tp} FN={fn} FP={fp} TN={tn}  acc={(tp+tn)/(tp+fn+fp+tn):.2f}")
