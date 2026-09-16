"""Exp 9 baselines: shipped + 4c entry-only + 4e D' on the THREE fixture spans,
graded with the same grader the HMM will use."""
import sys, sqlite3, copy, collections
S = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0, S)
exec(open(S + '/e4_dep.py').read().split("print('%-26s")[0])

# ---------------------------------------------------------------- extra streams
REC = '/Users/rmk/Repo/homeassistant-smart-ld2410/tests/fixtures/recordings/'
def T2(h, m, s=0):
    import datetime
    return datetime.datetime(2026, 9, 11, h, m, s, tzinfo=TZ).timestamp()

TH0, TH1 = T2(4, 55), T2(6, 5)
th_body = fetch(TH0, TH1)
th_warm = fetch(TH0 - 6 * 3600.0, TH0)
STREAM['through'] = (th_warm, th_body)

BA0, BA1 = T2(21, 55), T2(22, 12)
ba_body = fetch(BA0, BA1)
ba_warm = fetch(BA0 - 6 * 3600.0, BA0)
STREAM['bathfix'] = (ba_warm, ba_body)

# ---------------------------------------------------------------- shipped runner
def go_shipped(sname):
    warm, body = STREAM[sname]
    d = Detector(DetectorConfig(hold_s=30.)); t0 = warm[0][0]
    for ts, mv, st in warm:
        d.process(Frame(ts, ts - t0, tuple(mv), tuple(st), 0, False))
    return [(ts, d.process(Frame(ts, ts - t0, tuple(mv), tuple(st), 0, False)).occupied, False)
            for ts, mv, st in body]

def go_4c(sname, **kw):
    """entry-only composite: 4c (arrival + suppressed lead <=1), shipped release."""
    warm, body = STREAM[sname]
    d = Composite(DetectorConfig(hold_s=30.), lead_max=1, use_ret=False,
                  grace_s=0.0, form='c', near_max=99, ret_on=1e9)
    t0 = warm[0][0]
    for ts, mv, st in warm:
        d.process(Frame(ts, ts - t0, tuple(mv), tuple(st), 0, False))
    return [(ts, d.process(Frame(ts, ts - t0, tuple(mv), tuple(st), 0, False)).occupied, False)
            for ts, mv, st in body]

DPRIME = dict(grace_s=90., use_ret=True, ret_on=12., ret_all=True, near_max=1, lead_max=1,
              cross_n=10, cross_win=20., quiet_s=10., guard_s=0.)

# ---------------------------------------------------------------- grader
def frac_occ(rec, a, b):
    sel = [o for ts, o, *_ in rec if a <= ts < b]
    return 100.0 * sum(1 for o in sel if o) / max(len(sel), 1)

def transitions(rec, a=None, b=None):
    tl = []; p = None
    for ts, o, *_ in rec:
        if a is not None and ts < a: p = o; continue
        if b is not None and ts >= b: break
        if p is None: p = o; continue
        if o != p: tl.append((ts, o)); p = o
    return tl

def first_on(rec, t):
    return next((ts for ts, o in transitions(rec) if o and ts >= t), None)

def first_off(rec, t):
    return next((ts for ts, o in transitions(rec) if not o and ts >= t), None)

def grade(name, rf, rt, rb):
    out = {}
    out['fd_seatB_drop'] = frac_occ(rf, T(21, 41), T(21, 55))
    out['fd_drops'] = [hm(t) for t, o in transitions(rf) if not o and T(21, 40, 30) <= t < T(21, 55)]
    out['fd_empty'] = frac_occ(rf, T(21, 22), T(21, 39))
    out['fd_seatA'] = frac_occ(rf, T(21, 12), T(21, 20))
    out['fd_ent'] = first_on(rf, T(21, 39, 40) - 30)
    out['th_all'] = frac_occ(rt, TH0, TH1)
    out['th_bleed'] = frac_occ(rt, T2(5, 0), T2(5, 46))
    out['th_ents'] = [hm(t) for t, o in transitions(rt) if o]
    out['ba_ent'] = first_on(rb, T(22, 3))
    out['ba_rel'] = first_off(rb, out['ba_ent'] + 1) if out['ba_ent'] else None
    out['ba_pre'] = frac_occ(rb, BA0, T(22, 3, 30))
    out['ba_post'] = frac_occ(rb, T(22, 7, 30), BA1)
    return out

def show(name, o):
    def V(x): return hm(x) if x else '--'
    el = lambda x, ref: ('%+.0fs' % (x - ref)) if x else '  n/a'
    print('%-12s | seatB-occ %5.1f%% drops %-22s empty %5.1f%% seatA %5.1f%% ent %s(%s)'
          % (name, o['fd_seatB_drop'], ','.join(o['fd_drops']) or 'none', o['fd_empty'],
             o['fd_seatA'], V(o['fd_ent']), el(o['fd_ent'], T(21, 39, 40))))
    print('%-12s | THROUGH occ %5.1f%% (bleed %5.1f%%) entries=%d %s'
          % ('', o['th_all'], o['th_bleed'], len(o['th_ents']), ','.join(o['th_ents'][:6])))
    print('%-12s | BATH ent %s(%s) rel %s(%s) pre %4.1f%% post %4.1f%%'
          % ('', V(o['ba_ent']), el(o['ba_ent'], T(22, 4, 1)), V(o['ba_rel']),
             el(o['ba_rel'], T(22, 6, 43)), o['ba_pre'], o['ba_post']))

if __name__ == '__main__':
    import json
    res = {}
    for nm, fn in (('shipped', go_shipped), ('4c-entry', go_4c),
                   ("4e-D'", lambda s: go(s, taup=90., **DPRIME))):
        rf = fn('fd'); rt = fn('through'); rb = fn('bathfix')
        o = grade(nm, rf, rt, rb)
        res[nm] = o
        show(nm, o); print()
    json.dump({k: {kk: (vv if not isinstance(vv, float) else round(vv, 2))
                   for kk, vv in v.items()} for k, v in res.items()},
              open(S + '/h9_base.json', 'w'), indent=1, default=str)
