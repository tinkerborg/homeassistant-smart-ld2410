"""Exp 14 steps 2-5, done right: condition on ENTRY events.

A marginal origin/terminus histogram is symmetric by construction (you leave a
room as often as you enter it), which is what the long-history run showed. The
informative statistic is the origin of the FIRST march after a long silence -
an arrival - versus the terminus of the LAST march before a long silence - a
departure.

Also A/Bs the shipped fixed rule (suppressed leading gate <= lead_gate_max)
against the label-free march rule on every mined entry-shaped event.
"""
import sys, math, sqlite3, json, datetime, zoneinfo
from collections import Counter
sys.path.insert(0, '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad')
from traj2 import cells, smooth, CELL_S
from traj3 import dense_runs, split_march
from lead import Model, GATES, K, SUPPORT_TAU, leading_suppressed
TZ = zoneinfo.ZoneInfo('America/New_York')

SILENCE_S = 60.0     # quiet gap that makes the next march an "arrival"
MIN_DUR, MIN_MONO, MIN_NET = 4.0, 0.80, 2.0
LEAD_GATE_MAX = 1


def lt(t):
    return datetime.datetime.fromtimestamp(t, TZ).strftime('%m-%d %H:%M:%S')


def pipeline(db, sensor):
    """Single pass: cells + per-cell min suppressed leading gate."""
    c = sqlite3.connect('file:%s?mode=ro' % db, uri=True)
    m = Model(); sup = [0.0] * GATES; prev = None
    lead = {}   # cell index -> min leading gate in that cell
    from traj2 import frame_pos, _med, CELL_MIN_FRAC
    cur_i = None; buf = []; nf = 0; seq = []
    for ts, mvb, stb in c.execute(
            "select ts,move,still from frames where sensor_id=? order by ts", (sensor,)):
        mv = list(mvb); st = list(stb)
        if m.ready:
            rm, rs = m.res(mv, st)
            peaks = [max(0.0, rm[g], rs[g]) for g in range(GATES)]
            a = 1.0 if prev is None else (
                1.0 - math.exp(-min(ts - prev, 2.0) / SUPPORT_TAU) if ts > prev else 0.0)
            for g in range(GATES):
                sup[g] += a * (peaks[g] - sup[g])
            ls, _ = leading_suppressed(rm, sup)
            p, _am = frame_pos(rm, sup)
            ci = int(ts // CELL_S)
            if ls is not None:
                lead[ci] = min(lead.get(ci, 99), ls)
            if cur_i is None:
                cur_i = ci
            elif ci != cur_i:
                seq.append((cur_i, _med(buf, nf)))
                for k in range(cur_i + 1, ci):
                    seq.append((k, None))
                cur_i = ci; buf = []; nf = 0
            nf += 1
            if p is not None:
                buf.append(p)
        prev = ts
        m.add(ts, mv, st)
    if cur_i is not None:
        seq.append((cur_i, _med(buf, nf)))
    return seq, lead


def analyse(db, sensor, tag):
    seq, lead = pipeline(db, sensor)
    sm = smooth(seq)
    runs = dense_runs(seq, sm)
    marches = []
    for r in runs:
        if len(r) < 2:
            continue
        for cm, f in split_march(r)[0]:
            marches.append((cm[0][0], cm[-1][0], f))
    marches.sort()
    # activity cells (any detection) for silence detection
    act = sorted(ci for (ci, x), s in zip(seq, sm) if s is not None)
    actset = set(act)

    def quiet_before(ci, secs=SILENCE_S):
        n = int(secs / CELL_S)
        return not any((ci - k) in actset for k in range(1, n + 1))

    def quiet_after(ci, secs=SILENCE_S):
        n = int(secs / CELL_S)
        return not any((ci + k) in actset for k in range(1, n + 1))

    arr_origin = Counter(); arr_term = Counter()
    dep_origin = Counter(); dep_term = Counter()
    arrivals = []
    for s, e, f in marches:
        strong = (f['dur'] >= MIN_DUR and f['mono'] >= MIN_MONO
                  and abs(f['net']) >= MIN_NET)
        if quiet_before(s):
            g0 = int(round(f['x0'])); g1 = int(round(f['x1']))
            arr_origin[g0] += 1; arr_term[g1] += 1
            # min leading gate over the march window + 10 s lead-in
            w = [lead[c] for c in range(s - 20, e + 1) if c in lead]
            arrivals.append(dict(t=s * CELL_S, x0=f['x0'], x1=f['x1'],
                                 dur=f['dur'], mono=f['mono'], net=f['net'],
                                 strong=strong, minlead=min(w) if w else None))
        if quiet_after(e):
            dep_origin[int(round(f['x0']))] += 1
            dep_term[int(round(f['x1']))] += 1
    return dict(tag=tag, arr_origin=arr_origin, arr_term=arr_term,
                dep_origin=dep_origin, dep_term=dep_term,
                arrivals=arrivals, nmarch=len(marches))


def show(r):
    print('\n== %s   marches=%d  arrivals=%d  departures=%d'
          % (r['tag'], r['nmarch'], sum(r['arr_origin'].values()),
             sum(r['dep_term'].values())))
    print('gate  ARRIVAL_origin  ARRIVAL_term   DEPART_origin  DEPART_term')
    for g in range(GATES):
        print('  %d   %13d  %12d   %13d  %11d' %
              (g, r['arr_origin'][g], r['arr_term'][g],
               r['dep_origin'][g], r['dep_term'][g]))
    strong = [a for a in r['arrivals'] if a['strong']]
    print(' strong arrivals: %d' % len(strong))
    rej = [a for a in strong if a['minlead'] is None or a['minlead'] > LEAD_GATE_MAX]
    print(' strong arrivals the FIXED rule (lead<=%d) rejects: %d / %d'
          % (LEAD_GATE_MAX, len(rej), len(strong)))
    lc = Counter(a['minlead'] for a in strong)
    print(' minLeadGate histogram over strong arrivals:',
          dict(sorted(lc.items(), key=lambda kv: (kv[0] is None, kv[0]))))
    for a in rej[:12]:
        print('    REJECTED-by-fixed %s  %.1f->%.1f dur%.1fs mono%.2f minLG=%s'
              % (lt(a['t']), a['x0'], a['x1'], a['dur'], a['mono'], a['minlead']))


if __name__ == '__main__':
    S = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
    DEV = '/Users/rmk/Repo/home-assistant/config/smart_ld2410/frames.db'
    for db, sen, tag in [(S + '/prod-frames.db', 'FD:68:3B:41:6E:FF', 'prod-living 26h'),
                         (S + '/prod-frames.db', 'D0:6E:81:D2:5D:A6', 'prod-bath 28h'),
                         (DEV, 'FD:68:3B:41:6E:FF', 'dev-living 181h'),
                         (DEV, 'D0:6E:81:D2:5D:A6', 'dev-bath 290h')]:
        show(analyse(db, sen, tag))
