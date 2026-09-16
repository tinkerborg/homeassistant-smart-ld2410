"""Spec24 §1: unsupervised separation learning.

Build candidate activity episodes across all sensors / all history, score each
with the NON-STICKY suppressed leading gate at onset, class each by outcome
(confirmed sustained dwell / fizzled / ambiguous), dump to JSON.

Reuses lead.py (faithful baseline.residuals + detector._score isolated-gate rule).
"""
import sys, json, math, sqlite3, datetime, zoneinfo
sys.path.insert(0, '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad')
from lead import Model, leading_suppressed, leading_raw, GATES, K, SUPPORT_TAU, TZ

S = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
PROD = S + '/prod-frames.db'
DEV = '/Users/rmk/Repo/home-assistant/config/smart_ld2410/frames.db'

QUIET_S = 15.0     # silence required before a raw-hot frame counts as an ONSET
ONSET_S = 30.0     # entry window kept per episode (re-sliced offline at 3/10/20/30s)
EV_GAP_S = 10.0    # evidence gap tolerated inside one dwell
CONFIRM_S = 60.0   # dwell >= this  -> confirmed sustained occupancy
FIZZLE_S = 20.0    # dwell <  this  -> fizzled


def build(db, sensor, tag):
    c = sqlite3.connect('file:%s?mode=ro' % db, uri=True)
    cur = c.execute("select ts,move,still from frames where sensor_id=? order by ts", (sensor,))
    m = Model()
    sup = [0.0] * GATES
    prev = None
    eps = []
    ep = None            # dict in progress
    last_hot = -1e18     # last raw-move-hot ts
    last_ev = -1e18      # last evidence ts (move or still hot)
    nframes = 0
    t0_all = None
    for ts, mvb, stb in cur:
        mv = list(mvb); st = list(stb)
        if m.ready:
            nframes += 1
            if t0_all is None:
                t0_all = ts
            rm, rs = m.res(mv, st)
            peaks = [max(0.0, rm[g], rs[g]) for g in range(GATES)]
            a = 1.0 if prev is None else (1.0 - math.exp(-min(ts - prev, 2.0) / SUPPORT_TAU) if ts > prev else 0.0)
            for g in range(GATES):
                sup[g] += a * (peaks[g] - sup[g])
            ls, _runs = leading_suppressed(rm, sup)
            hot = ls is not None                      # SUPPRESSED activity
            evid = hot or any(r >= K for r in rs)
            # close a running episode whose evidence has lapsed
            if ep is not None and ts - last_ev > EV_GAP_S:
                ep['dwell'] = last_ev - ep['t0']
                eps.append(ep); ep = None
            if hot:
                if ep is None and ts - last_hot > QUIET_S:
                    ep = {'t0': ts, 'leads': [], 'nosurv': 0, 'n': 0}
                if ep is not None and ts - ep['t0'] <= ONSET_S:
                    ep['leads'].append((round(ts - ep['t0'], 2), ls))
                    ep['n'] += 1
                last_hot = ts
            if evid:
                last_ev = ts
        prev = ts
        m.add(ts, mv, st)
    if ep is not None:
        ep['dwell'] = last_ev - ep['t0']
        eps.append(ep)
    out = []
    for e in eps:
        mins = {}
        for hz in (3, 10, 20, 30):
            v = [g for dt, g in e['leads'] if dt <= hz]
            mins['m%d' % hz] = min(v) if v else None
        lead = mins['m3']
        d = e['dwell']
        cls = 'confirmed' if d >= CONFIRM_S else ('fizzled' if d < FIZZLE_S else 'ambiguous')
        rec = {'t0': e['t0'], 'lead': lead, 'n': e['n'], 'dwell': d, 'cls': cls}
        rec.update(mins)
        out.append(rec)
    return {'tag': tag, 'sensor': sensor, 'db': db, 'nframes': nframes,
            't_start': t0_all, 'episodes': out}


if __name__ == '__main__':
    jobs = [
        (PROD, 'D0:6E:81:D2:5D:A6', 'prod-D06E-bath'),
        (PROD, 'FD:68:3B:41:6E:FF', 'prod-FD68-living'),
        (DEV, 'D0:6E:81:D2:5D:A6', 'dev-D06E-bath'),
        (DEV, 'FD:68:3B:41:6E:FF', 'dev-FD68-living'),
        (DEV, '99:CD:E0:3E:66:15', 'dev-99CD'),
    ]
    which = sys.argv[1] if len(sys.argv) > 1 else None
    res = []
    for db, sen, tag in jobs:
        if which and which != tag:
            continue
        r = build(db, sen, tag)
        print('%-20s frames=%-9d episodes=%d' % (tag, r['nframes'], len(r['episodes'])), flush=True)
        res.append(r)
        json.dump(r, open('%s/ep_%s.json' % (S, tag), 'w'))
