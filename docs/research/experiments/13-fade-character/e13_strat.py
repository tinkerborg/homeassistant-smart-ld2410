import pickle, numpy as np, collections
from e13_lib import FEATNAMES, auc

rows = pickle.load(open("e13_rows.pkl", "rb"))
for r in rows:
    for k in FEATNAMES:
        if r[k] != r[k]: r[k] = 0.0

print("=" * 74)
print("Q1: is 'mean energy' itself the discriminator? (AUC of raw mean)")
for ch in ("move", "still"):
    a = [r["mean"] for r in rows if r["ch"] == ch and r["cls"] == "IN"]
    b = [r["mean"] for r in rows if r["ch"] == ch and r["cls"] == "TW"]
    print(f"  {ch:5s} mean-energy AUC = {auc(a,b):.3f}")

print("\n" + "=" * 74)
print("Q2: AMPLITUDE-MATCHED strata -- AUC of each feature inside narrow mean bins")
for ch in ("move", "still"):
    print(f"\n -- {ch}")
    bins = [(8,12),(12,16),(16,22),(22,30),(30,40),(40,50),(50,60),(60,75),(75,100)]
    hdr = "  " + "bin".ljust(9) + "".join(f"{f:>8s}" for f in ["cv","dr_db","df70","kurt","ent","K","ac1","mad1"]) + "   nIN  nTW"
    print(hdr)
    for lo, hi in bins:
        P = [r for r in rows if r["ch"]==ch and r["cls"]=="IN" and lo<=r["mean"]<hi]
        N = [r for r in rows if r["ch"]==ch and r["cls"]=="TW" and lo<=r["mean"]<hi]
        if len(P) < 30 or len(N) < 30: continue
        line = f"  {lo}-{hi}".ljust(11)
        for f in ["cv","dr_db","df70","kurt","ent","K","ac1","mad1"]:
            line += f"{auc([r[f] for r in P],[r[f] for r in N]):8.3f}"
        print(line + f"  {len(P):5d}{len(N):5d}")

print("\n" + "=" * 74)
print("Q3: TW vs EMPTY -- can fade features tell a through-wall person from an empty room?")
for ch in ("move", "still"):
    P = [r for r in rows if r["ch"]==ch and r["cls"]=="TW"]
    N = [r for r in rows if r["ch"]==ch and r["cls"]=="EMPTY"]
    res = sorted(((abs(auc([r[f] for r in P],[r[f] for r in N])-.5),
                   auc([r[f] for r in P],[r[f] for r in N]), f) for f in FEATNAMES), reverse=True)
    print(f"  {ch:5s} best: " + "  ".join(f"{f}={A:.3f}" for _,A,f in res[:5]))

print("\n" + "=" * 74)
print("Q4: sign consistency of cv/dr_db across each IN vs TW fixture pairing")
for ch in ("move","still"):
    print(f" -- {ch}")
    for pin in [("bath","IN"),("lab","IN"),("lr","IN")]:
        for pn in [("tw","TW"),("lab","TW")]:
            P=[r for r in rows if r["ch"]==ch and r["fx"]==pin[0] and r["cls"]==pin[1]]
            N=[r for r in rows if r["ch"]==ch and r["fx"]==pn[0] and r["cls"]==pn[1]]
            if len(P)<30 or len(N)<30: continue
            print(f"   {pin[0]:5s}IN vs {pn[0]:4s}TW  cv={auc([r['cv'] for r in P],[r['cv'] for r in N]):.3f}"
                  f"  dr_db={auc([r['dr_db'] for r in P],[r['dr_db'] for r in N]):.3f}"
                  f"  K={auc([r['K'] for r in P],[r['K'] for r in N]):.3f}"
                  f"  ac1={auc([r['ac1'] for r in P],[r['ac1'] for r in N]):.3f}  n={len(P)}/{len(N)}")

print("\n" + "=" * 74)
print("Q5: window-length sweep effect on move-channel ac1 (is fading just below 10 Hz?)")
# lag-k autocorrelation on raw per-gate series for a couple of long spans
from e13_lib import load, FIX, span
import numpy as np
for fx, day, a, b, lab in [("bath","2026-09-11","22:04:04","22:06:40","IN toilet"),
                           ("tw","2026-09-11","05:11:00","05:19:00","TW kitchen"),
                           ("lr","2026-09-11","21:04:30","21:19:30","IN seated")]:
    d = load(FIX[fx]); t0,t1 = span(day,a,b)
    i0,i1 = np.searchsorted(d["ts"],t0), np.searchsorted(d["ts"],t1)
    for ch in ("move","still"):
        X = d[ch][i0:i1]
        g = int(np.argmax(X.mean(axis=0)))
        x = X[:,g]
        acs = []
        for k in (1,2,3,5,10,20):
            if x.std()>0: acs.append(f"{k}:{np.corrcoef(x[:-k],x[k:])[0,1]:+.2f}")
        print(f"  {lab:12s} {ch:5s} g{g} mean={x.mean():5.1f} sd={x.std():5.2f} ac(lag)=" + " ".join(acs))
