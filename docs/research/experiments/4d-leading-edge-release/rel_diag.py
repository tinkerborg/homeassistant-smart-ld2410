"""Diagnostics: near-lead occurrence over time, and retention, per stream."""
import sqlite3, sys, collections
S = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0, S)
from rel import *  # noqa

W0, W1 = T(21, 58), T(22, 10)
WARM0 = W0 - 6 * 3600.0
K0, K1 = T(5, 11), T(5, 23)
ARRIVE, DEPART = T(22, 4, 1), T(22, 6, 43)
c = sqlite3.connect('file:%s?mode=ro' % PROD, uri=True)
def fetch(a, b):
    return [(r[0], list(r[1]), list(r[2])) for r in c.execute(
        "select ts,move,still from frames where sensor_id like 'D0:6E%' and ts>=? and ts<? order by ts", (a, b))]
warm = fetch(WARM0, W0); bath = fetch(W0, W1); kit = fetch(K0, K1)
n = min(len(bath), len(kit))
def mix(op):
    return [(bath[i][0], [op(bath[i][1][g], kit[i][1][g]) for g in range(9)],
             [op(bath[i][2][g], kit[i][2][g]) for g in range(9)]) for i in range(n)]
STREAMS = {
    'bath (control)':    bath[:n],
    'kitchen (control)': [(bath[i][0], kit[i][1], kit[i][2]) for i in range(n)],
    'MAX (synth)':       mix(max),
}

# run composite once per stream purely to record lead/score/retention traces
for name, rows in STREAMS.items():
    d, rec = run(warm, rows, use_ret=True, ret_on=20.0, far_hold_s=1e9)
    print('\n' + '=' * 100)
    print('%s' % name)
    print('=' * 100)
    # per 20s bucket: frames, score>=1.5, near(<=1), lead histogram, retention max g2-4 median
    b = collections.OrderedDict()
    for ts, occ, score, ag, ls, dbg, rmax in rec:
        k = int(ts // 20) * 20
        e = b.setdefault(k, dict(n=0, hot=0, near=0, h=collections.Counter(), r=[]))
        e['n'] += 1
        if score >= 1.5: e['hot'] += 1
        if ls is not None and ls <= 1: e['near'] += 1
        e['h'][ls if ls is not None else -1] += 1
        e['r'].append(rmax)
    print('%-10s %4s %5s %5s %8s  %s' % ('t', 'n', 'hot', 'near', 'ret(med)', 'lead hist (-1 = none)'))
    for k, e in b.items():
        r = sorted(e['r'])
        print('%-10s %4d %5d %5d %8.1f  %s' % (
            hm(k), e['n'], e['hot'], e['near'], r[len(r) // 2],
            ' '.join('g%d:%d' % (g, v) for g, v in sorted(e['h'].items()))))
    near_ts = [r[0] for r in rec if r[4] is not None and r[4] <= 1]
    if near_ts:
        gaps = [near_ts[i + 1] - near_ts[i] for i in range(len(near_ts) - 1)]
        print('near-lead frames: %d, first %s last %s, max gap %.0fs'
              % (len(near_ts), hm(near_ts[0]), hm(near_ts[-1]), max(gaps) if gaps else 0))
        # gaps during the genuine visit only
        v = [t for t in near_ts if ARRIVE <= t <= DEPART]
        if len(v) > 1:
            g2 = [v[i + 1] - v[i] for i in range(len(v) - 1)]
            print('  during visit %s-%s: %d frames, max gap %.0fs' % (hm(ARRIVE), hm(DEPART), len(v), max(g2)))
    else:
        print('near-lead frames: NONE')
