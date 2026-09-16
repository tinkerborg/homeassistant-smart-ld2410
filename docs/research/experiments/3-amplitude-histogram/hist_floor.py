"""Distribution-shape (amplitude-histogram, Gennarelli 2022) floor estimator vs
shipped windowed-quantile floor, on occupied-only data.

Fixture: livingroom-reset-seated-fd68.db (read-only).
Learning starts 21:04 with user seated at gates 2-3 through 21:20.
"""
import sqlite3, datetime, zoneinfo, math, statistics
from collections import Counter

TZ = zoneinfo.ZoneInfo('America/New_York')
DB = '/Users/rmk/Repo/homeassistant-smart-ld2410/tests/fixtures/recordings/livingroom-reset-seated-fd68.db'
G = 9
def T(h, m, s=0): return datetime.datetime(2026, 9, 11, h, m, s, tzinfo=TZ).timestamp()
def hm(t): return datetime.datetime.fromtimestamp(t, TZ).strftime('%H:%M')

c = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
rows = c.execute("select ts,move,still from frames order by ts").fetchall()
TS = [r[0] for r in rows]
ST = [[r[2][g] for r in rows] for g in range(G)]

def sub(g, t0, t1):
    return [ST[g][i] for i, t in enumerate(TS) if t0 <= t < t1]

def q(o, p):
    n = len(o) - 1
    if n <= 0: return float(o[0])
    x = p * n; lo = int(x); hi = min(lo + 1, n)
    return float(o[lo] + (o[hi] - o[lo]) * (x - lo))

# ---------------- estimators ----------------
def est_shipped(vals, ts):
    """60s buckets, floor = p25 of bucket medians (min 5 buckets)."""
    b = {}
    for t, v in zip(ts, vals): b.setdefault(int(t // 60), []).append(v)
    meds = sorted(statistics.median(v) for v in b.values() if v)
    if len(meds) < 5: return None
    return q(meds, 0.25)

def est_histmode(vals, ts=None, bw=2):
    """Peak of the amplitude histogram (bin width bw), reported as bin centre."""
    if not vals: return None
    cnt = Counter(int(v) // bw for v in vals)
    b = max(cnt.items(), key=lambda kv: (kv[1], -kv[0]))[0]
    inbin = [v for v in vals if int(v) // bw == b]
    return statistics.median(inbin)

def est_kde(vals, ts=None, h=1.5):
    """Gaussian-KDE mode over the integer support 0..100."""
    if not vals: return None
    cnt = Counter(int(v) for v in vals)
    best, bx = -1.0, 0
    for x in range(0, 101):
        s = 0.0
        for v, n in cnt.items():
            d = (x - v) / h
            if abs(d) < 4: s += n * math.exp(-0.5 * d * d)
        if s > best: best, bx = s, x
    return float(bx)

def est_mix2(vals, ts=None, iters=80):
    """2-component 1-D Gaussian mixture (EM); return lower component mean."""
    if len(vals) < 20: return None
    v = [float(x) for x in vals]
    lo, hi = min(v), max(v)
    if hi - lo < 1e-6: return lo
    m = [lo + 0.15 * (hi - lo), lo + 0.75 * (hi - lo)]
    s = [max(1.0, (hi - lo) / 6)] * 2
    w = [0.5, 0.5]
    for _ in range(iters):
        n0 = n1 = 0.0; s0 = s1 = 0.0; v0 = v1 = 0.0
        for x in v:
            p = []
            for k in range(2):
                d = (x - m[k]) / s[k]
                p.append(w[k] / s[k] * math.exp(-0.5 * d * d) + 1e-300)
            tot = p[0] + p[1]
            r0 = p[0] / tot; r1 = 1 - r0
            n0 += r0; n1 += r1; s0 += r0 * x; s1 += r1 * x
        if n0 < 1e-6 or n1 < 1e-6: break
        m = [s0 / n0, s1 / n1]
        v0 = v1 = 0.0
        for x in v:
            p = []
            for k in range(2):
                d = (x - m[k]) / s[k]
                p.append(w[k] / s[k] * math.exp(-0.5 * d * d) + 1e-300)
            tot = p[0] + p[1]
            r0 = p[0] / tot; r1 = 1 - r0
            v0 += r0 * (x - m[0]) ** 2; v1 += r1 * (x - m[1]) ** 2
        s = [max(0.5, math.sqrt(v0 / n0)), max(0.5, math.sqrt(v1 / n1))]
        w = [n0 / len(v), n1 / len(v)]
    return min(m)

def est_lowmode(vals, ts=None, bw=2):
    """Histogram peak restricted to values <= overall median (the 'quiet' half)."""
    if not vals: return None
    med = statistics.median(vals)
    low = [v for v in vals if v <= med]
    return est_histmode(low, bw=bw)

EST = [('hist-mode', est_histmode), ('kde-mode', est_kde),
       ('mix2-low', est_mix2), ('lowhalf-mode', est_lowmode),
       ('shipped-p25', est_shipped)]

# ---------------- ground truth ambient from empty window ----------------
EMPTY0, EMPTY1 = T(21, 21), T(21, 39)
CAT0, CAT1 = T(21, 28), T(21, 33)
print('== true ambient, empty window 21:21-21:39 (still) ==')
print('gate  n   med   p25   p75   mean   med(no-cat 21:21-28,21:33-39)')
AMB = {}
for g in range(G):
    v = sorted(sub(g, EMPTY0, EMPTY1))
    nc = sorted([ST[g][i] for i, t in enumerate(TS)
                 if EMPTY0 <= t < EMPTY1 and not (CAT0 <= t < CAT1)])
    AMB[g] = statistics.median(nc)
    print('%4d %5d %5.1f %5.1f %5.1f %6.2f  %5.1f' %
          (g, len(v), statistics.median(v), q(v, .25), q(v, .75),
           statistics.mean(v), statistics.median(nc)))

# ---------------- Q3 sanity: estimators on the empty window ----------------
print('\n== SANITY: estimators over empty window 21:21-21:39 (should == ambient) ==')
hdr = 'gate  true  ' + '  '.join('%12s' % n for n, _ in EST)
print(hdr)
for g in range(G):
    v = sub(g, EMPTY0, EMPTY1)
    t = [t for t in TS if EMPTY0 <= t < EMPTY1]
    out = []
    for n, f in EST:
        r = f(v, t) if n == 'shipped-p25' else f(v)
        out.append('%12s' % ('--' if r is None else '%.1f' % r))
    print('%4d %5.1f  %s' % (g, AMB[g], '  '.join(out)))

# cat-window only, gates 4-6
print('\n-- cat sub-window 21:28-21:33, gates 4-6 --')
for g in (4, 5, 6):
    v = sub(g, CAT0, CAT1); t = [t for t in TS if CAT0 <= t < CAT1]
    out = ['%s=%.1f' % (n, (f(v, t) if n == 'shipped-p25' else f(v)) or -1) for n, f in EST]
    print('  gate %d amb=%.1f  %s' % (g, AMB[g], '  '.join(out)))

# ---------------- Q1/Q2: growing occupied-only window from 21:04 ----------------
LEARN0 = T(21, 4, 30)
print('\n== OCCUPIED-ONLY growing window from 21:04:30, gates 2-3 ==')
first_ok = {}
for g in (2, 3):
    print('\n--- gate %d (true ambient %.1f) ---' % (g, AMB[g]))
    print(' until   n    ' + ' '.join('%12s' % n for n, _ in EST) + '   raw p10/p25/med')
    for mm in range(5, 21):
        t1 = T(21, mm)
        vv = [(t, ST[g][i]) for i, t in enumerate(TS) if LEARN0 <= t < t1]
        if len(vv) < 30: continue
        vals = [x for _, x in vv]; tss = [t for t, _ in vv]
        cells = []
        for n, f in EST:
            r = f(vals, tss) if n == 'shipped-p25' else f(vals)
            if r is None: cells.append('%12s' % '--'); continue
            err = r - AMB[g]
            cells.append('%12s' % ('%.1f(%+.1f)' % (r, err)))
            if abs(err) <= 2.0: first_ok.setdefault((g, n), mm)
        o = sorted(vals)
        print('%6s %5d %s   %.0f/%.0f/%.0f' % (hm(t1), len(vals), ' '.join(cells),
              q(o, .10), q(o, .25), q(o, .50)))

print('\n== minutes-to-within-2 (from 21:04, occupied-only) ==')
for g in (2, 3):
    for n, _ in EST:
        k = first_ok.get((g, n))
        print('  gate %d  %-12s  %s' % (g, n, ('%d min (by %s)' % (k - 4, hm(T(21, k)))) if k else 'NEVER in window'))

# ---------------- Q2 diagnostic: is the seated distribution unimodal-above-ambient? ----------------
print('\n== occupied 21:04:30-21:20 still histograms, gates 1-4 ==')
for g in (1, 2, 3, 4):
    vals = sub(g, LEARN0, T(21, 20))
    cnt = Counter(int(v) for v in vals)
    n = len(vals)
    lo = sum(c for v, c in cnt.items() if v <= AMB[g] + 2)
    print(' gate %d (amb %.1f) n=%d  mass<=amb+2: %.1f%%' % (g, AMB[g], n, 100 * lo / n))
    bars = []
    for v in range(0, min(60, max(cnt) + 1)):
        c = cnt.get(v, 0)
        if c: bars.append('%d:%.1f%%' % (v, 100 * c / n))
    print('    ' + ' '.join(bars[:30]))

# longest quiet runs during occupancy (inter-fidget)
print('\n== quiet-frame structure during occupancy (gate 2&3 both <= amb+2) ==')
run = 0; runs = []
for i, t in enumerate(TS):
    if not (LEARN0 <= t < T(21, 20)): continue
    quiet = all(ST[g][i] <= AMB[g] + 2 for g in (2, 3))
    if quiet: run += 1
    else:
        if run: runs.append(run)
        run = 0
if run: runs.append(run)
runs.sort(reverse=True)
print('  quiet frames %d, runs=%d, longest runs(frames): %s' %
      (sum(runs), len(runs), runs[:10]))

# ---------------- Q4: downstream z-scores 21:39-21:55 ----------------
print('\n== DOWNSTREAM: seated signature 21:39:40-21:55, floor learned on 21:04-21:20 only ==')
def spread(vals):
    b = {}
    return None
LV = {}
for g in range(G):
    vv = [(t, ST[g][i]) for i, t in enumerate(TS) if LEARN0 <= t < T(21, 20)]
    vals = [x for _, x in vv]; tss = [t for t, _ in vv]
    LV[g] = dict(
        ship=est_shipped(vals, tss),
        hist=est_histmode(vals),
        kde=est_kde(vals),
        mix=est_mix2(vals),
        true=AMB[g])
    # shipped spread: p25 of bucket (q90-q50), min 1.0
    b = {}
    for t, v in vv: b.setdefault(int(t // 60), []).append(v)
    spr = sorted(max(0.0, q(sorted(v), .90) - q(sorted(v), .50)) for v in b.values() if v)
    LV[g]['spread'] = max(q(spr, .25), 1.0)

SEAT0, SEAT1 = T(21, 39, 40), T(21, 55)
print('gate spread | floors: true/ship/hist/kde/mix | median still-z at 21:39-21:55')
for g in (1, 2, 3, 4):
    v = sub(g, SEAT0, SEAT1)
    L = LV[g]; s = L['spread']
    z = {k: statistics.median([(x - L[k]) / s for x in v]) for k in ('true', 'ship', 'hist', 'kde', 'mix')}
    print(' %d  %5.2f | %5.1f %5.1f %5.1f %5.1f %5.1f | true %5.2f  ship %5.2f  hist %5.2f  kde %5.2f  mix %5.2f' %
          (g, s, L['true'], L['ship'], L['hist'], L['kde'], L['mix'],
           z['true'], z['ship'], z['hist'], z['kde'], z['mix']))

# 21:49 the shipped detector wrongly released
print('\n-- 21:49 fully-still minute (shipped released 21:49:56) --')
for g in (2, 3):
    v = sub(g, T(21, 49), T(21, 50))
    L = LV[g]; s = L['spread']
    print(' gate %d med=%.1f  z_true=%.2f z_ship=%.2f z_hist=%.2f z_kde=%.2f z_mix=%.2f' %
          (g, statistics.median(v),
           *[ (statistics.median(v) - L[k]) / s for k in ('true','ship','hist','kde','mix')]))
