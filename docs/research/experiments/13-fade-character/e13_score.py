import pickle, numpy as np, collections, math
from e13_lib import FEATNAMES, auc, cohend

rows = pickle.load(open("e13_rows.pkl", "rb"))
for r in rows:
    for k in FEATNAMES:
        if r[k] != r[k]: r[k] = 0.0

def sel(**kw):
    out = rows
    for k, v in kw.items():
        if k == "eband":
            out = [r for r in out if v[0] <= r["mean"] <= v[1]]
        elif k == "gates":
            out = [r for r in out if r["gate"] in v]
        elif k == "fxin":
            out = [r for r in out if r["fx"] in v]
        else:
            out = [r for r in out if r[k] == v]
    return out

def report(title, pos, neg, top=8):
    print(f"\n### {title}   IN n={len(pos)}  TW n={len(neg)}")
    if not pos or not neg:
        print("  (empty)"); return []
    res = []
    for f in FEATNAMES:
        a = np.array([r[f] for r in pos]); b = np.array([r[f] for r in neg])
        A = auc(a, b)
        res.append((abs(A - .5), A, f, a.mean(), b.mean(), cohend(a, b)))
    res.sort(reverse=True)
    print(f"  {'feat':10s} {'AUC':>6s} {'IN mean':>9s} {'TW mean':>9s} {'d':>6s}")
    for _, A, f, am, bm, d in res[:top]:
        print(f"  {f:10s} {A:6.3f} {am:9.3f} {bm:9.3f} {d:6.2f}")
    return res

print("=" * 70)
print("SMOOTHING DIAGNOSTIC (is there frame-to-frame structure at all?)")
for ch in ("move", "still"):
    for cls in ("IN", "TW", "EMPTY"):
        s = sel(ch=ch, cls=cls)
        if not s: continue
        print(f"  {ch:5s} {cls:6s} n={len(s):6d}  ac1={np.mean([r['ac1'] for r in s]):6.3f}"
              f"  mad1={np.mean([r['mad1'] for r in s]):6.3f}"
              f"  cv={np.mean([r['cv'] for r in s]):6.3f}"
              f"  mean={np.mean([r['mean'] for r in s]):6.1f}")

print("\n" + "=" * 70)
for ch in ("move", "still"):
    report(f"ALL WINDOWS · {ch}", sel(ch=ch, cls="IN"), sel(ch=ch, cls="TW"))

print("\n" + "=" * 70)
print("HARD CASE (a): overlap energy band 40-58")
for ch in ("move", "still"):
    report(f"band 40-58 · {ch}", sel(ch=ch, cls="IN", eband=(40, 58)), sel(ch=ch, cls="TW", eband=(40, 58)))

print("\n" + "=" * 70)
print("HARD CASE (b): D0:6E gates 2-3, toilet(IN) vs stove/island(TW), labeled fixture only")
for ch in ("move", "still"):
    report(f"lab g2-3 · {ch}", sel(ch=ch, cls="IN", fxin={"lab"}, gates={2, 3}),
           sel(ch=ch, cls="TW", fxin={"lab"}, gates={2, 3}))
print("\n  same gates, D0:6E all fixtures (bath IN vs tw-morning TW):")
for ch in ("move", "still"):
    report(f"d06e g2-3 all · {ch}", sel(ch=ch, cls="IN", fxin={"lab", "bath"}, gates={2, 3}),
           sel(ch=ch, cls="TW", fxin={"lab", "tw"}, gates={2, 3}))

print("\n" + "=" * 70)
print("HARD CASE (c): still-dominant windows (still channel only, move ceiling low)")
for ch in ("still",):
    report("still ch, energy 40-58, gates 2-3", sel(ch=ch, cls="IN", gates={2,3}, eband=(40,58)),
           sel(ch=ch, cls="TW", gates={2,3}, eband=(40,58)))

print("\n" + "=" * 70)
print("PER-GATE energy distributions by class (D0:6E)")
for ch in ("move", "still"):
    print(f"  -- {ch}")
    for cls in ("IN", "TW"):
        s = [r for r in rows if r["ch"] == ch and r["cls"] == cls and r["fx"] in ("lab", "bath", "tw")]
        by = collections.defaultdict(list)
        for r in s: by[r["gate"]].append(r["mean"])
        print(f"   {cls}: " + " ".join(f"g{g}:{len(by[g])}@{np.mean(by[g]):.0f}" for g in sorted(by)))
