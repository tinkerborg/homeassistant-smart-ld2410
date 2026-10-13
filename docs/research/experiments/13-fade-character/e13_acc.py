"""Task 4: per-gate accumulation of fade-class over days; + within-bin residual check."""
import sqlite3, numpy as np, collections, pickle, sys
from e13_lib import feats, auc, FEATNAMES

# ---- part A: within-bin residual (is the 16-22 bin separation still amplitude?)
rows = pickle.load(open("e13_rows.pkl", "rb"))
print("=" * 74)
print("A. Within-bin residual: does 'mean' itself still separate inside each bin?")
for ch in ("move",):
    for lo, hi in [(8,12),(12,16),(16,22)]:
        P=[r for r in rows if r["ch"]==ch and r["fx"]=="lab" and r["cls"]=="IN" and r["gate"] in (2,3) and lo<=r["mean"]<hi]
        N=[r for r in rows if r["ch"]==ch and r["fx"]=="lab" and r["cls"]=="TW" and r["gate"] in (2,3) and lo<=r["mean"]<hi]
        if len(P)<25 or len(N)<25: continue
        # residualise cv on mean via linear fit on pooled data
        X=np.array([r["mean"] for r in P+N]); Y=np.array([r["cv"] for r in P+N])
        b=np.polyfit(X,Y,1); res=Y-np.polyval(b,X)
        print(f"  {ch} {lo}-{hi}: mean-AUC={auc([r['mean'] for r in P],[r['mean'] for r in N]):.3f}"
              f"  cv-AUC={auc([r['cv'] for r in P],[r['cv'] for r in N]):.3f}"
              f"  cv|mean-resid-AUC={auc(res[:len(P)],res[len(P):]):.3f}   n={len(P)}/{len(N)}")

# ---- part B: per-gate accumulation over days
DBS = {
    "dev": "/Users/rmk/Repo/home-assistant/config/smart_ld2410/frames.db",
    "prod": "/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad/prod-frames.db",
}
SENSORS = {"D0:6E:81:D2:5D:A6": "bathroom", "FD:68:3B:41:6E:FF": "livingroom", "99:CD:E0:3E:66:15": "sensor99cd"}
NW, NS, MIN_MED = 20, 10, 8.0
CHUNK = 200_000

print("\n" + "=" * 74)
print("B. Per-gate accumulation of move-channel fade class over all days")
print("   active window = median move energy >= 8; 'IN-class' = cv > 0.45")
for dbn, path in DBS.items():
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    for sid, name in SENSORS.items():
        n = c.execute("select count(*) from frames where sensor_id=?", (sid,)).fetchone()[0]
        if n < 10000: continue
        acc = {g: {"n": 0, "hi": 0, "cvs": [], "E": []} for g in range(9)}
        off, seen = 0, 0
        prev_tail = None
        cur = c.execute("select ts,move from frames where sensor_id=? order by ts", (sid,))
        buf_ts, buf_mv = [], []
        for ts, mv in cur:
            buf_ts.append(ts); buf_mv.append(list(mv))
            if len(buf_ts) >= CHUNK:
                T = np.array(buf_ts); M = np.array(buf_mv, dtype=float)
                for s in range(0, len(T) - NW + 1, NS):
                    tt = T[s:s+NW]
                    if tt[-1]-tt[0] > 3.2: continue
                    for g in range(9):
                        x = M[s:s+NW, g]
                        m = np.median(x)
                        if m < MIN_MED: continue
                        mu = x.mean(); sd = x.std()
                        cv = sd/mu if mu>0 else 0.0
                        a = acc[g]; a["n"] += 1; a["hi"] += cv > 0.45
                        if len(a["cvs"]) < 40000: a["cvs"].append(cv); a["E"].append(mu)
                seen += len(T)
                buf_ts, buf_mv = [], []
        if buf_ts:
            T = np.array(buf_ts); M = np.array(buf_mv, dtype=float)
            for s in range(0, len(T) - NW + 1, NS):
                tt = T[s:s+NW]
                if tt[-1]-tt[0] > 3.2: continue
                for g in range(9):
                    x = M[s:s+NW, g]; m = np.median(x)
                    if m < MIN_MED: continue
                    mu = x.mean(); sd = x.std(); cv = sd/mu if mu>0 else 0.0
                    a = acc[g]; a["n"] += 1; a["hi"] += cv>0.45
                    if len(a["cvs"]) < 40000: a["cvs"].append(cv); a["E"].append(mu)
            seen += len(T)
        days = n/10.0/86400
        print(f"\n  {dbn}/{name} ({sid[:5]})  frames={n}  ~{days:.1f} days")
        print(f"   {'gate':5s}{'nwin':>9s}{'%active':>8s}{'meanE':>7s}{'cv p25':>7s}{'cv p50':>7s}{'cv p75':>7s}{'%cv>.45':>8s}")
        tot = max(1, sum(acc[g]['n'] for g in range(9)))
        for g in range(9):
            a = acc[g]
            if a["n"] < 50:
                print(f"   g{g:<4d}{a['n']:>9d}{'':>8s}"); continue
            cv = np.array(a["cvs"])
            print(f"   g{g:<4d}{a['n']:>9d}{100*a['n']/ (seen/NS):7.1f}%{np.mean(a['E']):7.1f}"
                  f"{np.percentile(cv,25):7.3f}{np.percentile(cv,50):7.3f}{np.percentile(cv,75):7.3f}{100*a['hi']/a['n']:7.1f}%")
