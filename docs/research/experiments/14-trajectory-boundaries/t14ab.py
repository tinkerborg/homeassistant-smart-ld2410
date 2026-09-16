"""Exp 14 step 4b: A/B the shipped fixed near-band entry rule against the
label-free trajectory rule, on the fixtures' ground-truth episodes.

A) shipped: suppressed leading gate (min over the episode) <= lead_gate_max (=1)
B) learned: episode contains a march with dur >= MIN_DUR, mono >= MIN_MONO,
   |net| >= MIN_NET  (no gate numbers anywhere)
C) learned+direction: B, plus the march must terminate in the sensor's learned
   dwell band (from the long-history terminus histogram)
"""
import sys, datetime, zoneinfo, math, sqlite3
sys.path.insert(0, '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad')
from traj2 import cells, smooth, CELL_S, frame_pos
from traj3 import dense_runs, split_march
from lead import Model, GATES, K, SUPPORT_TAU, leading_suppressed
TZ = zoneinfo.ZoneInfo('America/New_York')

LEAD_GATE_MAX = 1
MIN_DUR, MIN_MONO, MIN_NET = 4.0, 0.80, 2.0


def T(s):
    return datetime.datetime.strptime(s, '%Y-%m-%d %H:%M:%S').replace(tzinfo=TZ).timestamp()


def lt(t):
    return datetime.datetime.fromtimestamp(t, TZ).strftime('%H:%M:%S')


def leading_series(db, sensor):
    """(ts, suppressed leading gate) per frame - faithful to the shipped rule."""
    c = sqlite3.connect('file:%s?mode=ro' % db, uri=True)
    m = Model(); sup = [0.0] * GATES; prev = None; out = []
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
            out.append((ts, ls))
        prev = ts
        m.add(ts, mv, st)
    return out


def march_series(db, sensor):
    seq = [(ci, x) for ci, x in cells(db, sensor)]
    sm = smooth(seq)
    out = []
    for r in dense_runs(seq, sm):
        if len(r) < 2:
            continue
        for cm, f in split_march(r)[0]:
            out.append((cm[0][0] * CELL_S, cm[-1][0] * CELL_S, f))
    return sorted(out)


EPISODES = [
    ('fx/bathroom-visit-2204-d06e.db', 'D0:6E:81:D2:5D:A6', 'bath',
     'bath genuine entry', '2026-09-11 22:03:30', '2026-09-11 22:05:00', 1),
    ('fx/throughwall-morning-d06e.db', 'D0:6E:81:D2:5D:A6', 'bath',
     'TW 05:11-05:19 (shipped FP)', '2026-09-11 05:11:00', '2026-09-11 05:19:30', 0),
    ('fx/throughwall-morning-d06e.db', 'D0:6E:81:D2:5D:A6', 'bath',
     'TW 05:28-29', '2026-09-11 05:28:00', '2026-09-11 05:29:30', 0),
    ('fx/throughwall-morning-d06e.db', 'D0:6E:81:D2:5D:A6', 'bath',
     'TW 05:34-37 (shipped FP)', '2026-09-11 05:34:00', '2026-09-11 05:37:30', 0),
    ('fx/throughwall-morning-d06e.db', 'D0:6E:81:D2:5D:A6', 'bath',
     'TW 05:42', '2026-09-11 05:41:30', '2026-09-11 05:43:00', 0),
    ('fx/throughwall-morning-d06e.db', 'D0:6E:81:D2:5D:A6', 'bath',
     'TW 05:00-05:10 quiet', '2026-09-11 05:00:00', '2026-09-11 05:10:00', 0),
    ('fx/livingroom-reset-seated-fd68.db', 'FD:68:3B:41:6E:FF', 'living',
     'LR genuine walk-in', '2026-09-11 21:39:20', '2026-09-11 21:41:00', 1),
    ('fx/livingroom-reset-seated-fd68.db', 'FD:68:3B:41:6E:FF', 'living',
     'LR cat only ~21:30', '2026-09-11 21:28:00', '2026-09-11 21:33:00', 0),
]

DWELL_BAND = {'bath': None, 'living': (2, 4)}   # from long-history terminus hist


def main():
    lead_cache = {}; march_cache = {}
    rows = []
    for db, sen, room, lab, a, b, truth in EPISODES:
        if (db, sen) not in lead_cache:
            lead_cache[(db, sen)] = leading_series(db, sen)
            march_cache[(db, sen)] = march_series(db, sen)
        ta, tb = T(a), T(b)
        lg = [g for ts, g in lead_cache[(db, sen)] if ta <= ts < tb and g is not None]
        minlead = min(lg) if lg else None
        A = minlead is not None and minlead <= LEAD_GATE_MAX
        ms = [(s, e, f) for s, e, f in march_cache[(db, sen)] if ta <= s < tb]
        strong = [(s, e, f) for s, e, f in ms
                  if f['dur'] >= MIN_DUR and f['mono'] >= MIN_MONO
                  and abs(f['net']) >= MIN_NET]
        B = bool(strong)
        band = DWELL_BAND[room]
        C = any(band[0] - 0.5 <= f['x1'] <= band[1] + 0.5 for _, _, f in strong) \
            if (B and band) else B
        rows.append((lab, truth, minlead, A, B, C, len(ms), len(strong),
                     [(lt(s), '%.1f->%.1f' % (f['x0'], f['x1']), '%.1fs' % f['dur'])
                      for s, e, f in strong]))
    print('%-30s %5s %6s %8s %8s %8s   %s' %
          ('episode', 'truth', 'minLG', 'A fixed', 'B march', 'C +band', 'strong marches'))
    for lab, truth, ml, A, B, C, nm, ns, det in rows:
        print('%-30s %5s %6s %8s %8s %8s   %s' %
              (lab, 'IN' if truth else 'OUT', ml if ml is not None else '-',
               'FIRE' if A else '.', 'FIRE' if B else '.', 'FIRE' if C else '.', det))
    for name, i in (('A fixed lead<=1', 3), ('B march', 4), ('C march+band', 5)):
        tp = sum(1 for r in rows if r[1] == 1 and r[i])
        fn = sum(1 for r in rows if r[1] == 1 and not r[i])
        fp = sum(1 for r in rows if r[1] == 0 and r[i])
        tn = sum(1 for r in rows if r[1] == 0 and not r[i])
        print('%-18s TP=%d FN=%d FP=%d TN=%d' % (name, tp, fn, fp, tn))


main()
