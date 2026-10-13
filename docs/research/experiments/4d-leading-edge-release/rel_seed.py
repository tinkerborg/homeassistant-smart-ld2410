"""FD:68 departure test. The composite never *enters* before 21:20 (the seated
user predates the fixture's first frame), so occupancy is seeded at 21:11 with
the README's seat gates and we measure when each release rule lets go after the
user leaves ~21:20."""
import sqlite3, sys
S = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0, S)
from rel import *  # noqa
from custom_components.smart_ld2410.algo.detector import Detector

cf = sqlite3.connect('file:%s?mode=ro' % FIX, uri=True)
fd = [(r[0], list(r[1]), list(r[2])) for r in cf.execute("select ts,move,still from frames order by ts")]
SPLIT = T(21, 11); LEFT = T(21, 20)
warm = [r for r in fd if r[0] < SPLIT]; body = [r for r in fd if r[0] >= SPLIT]

def seeded(hold_s=30.0, shipped=False, **kw):
    cfg = DetectorConfig(hold_s=hold_s)
    d = Detector(cfg) if shipped else Composite(cfg, **kw)
    ret = Retention(warm[0][2]); t0 = warm[0][0]
    for ts, mv, st in warm:
        ret.add(ts, st)
        if not shipped: d.ret = ret.score
        d.process(Frame(ts, ts - t0, tuple(mv), tuple(st), 0, False))
    d._occupied = True; d._hold_until_mono = None
    if not shipped:
        d.occ_gates = {2, 3}; d._occ_start = body[0][0] - t0
        d._last_near = body[0][0] - t0; d._last_far = None
    rec = []
    for ts, mv, st in body:
        ret.add(ts, st)
        if not shipped: d.ret = ret.score
        o = d.process(Frame(ts, ts - t0, tuple(mv), tuple(st), 0, False))
        rec.append((ts, o.occupied, o.score, o.active_gates, None, None, 0.0))
        if ts > T(21, 39): break
    return d, rec

V = [('shipped/4c release', dict(shipped=True)),
     ('A g60 near-only',    dict(grace_s=60.0)),
     ('A g90 near-only',    dict(grace_s=90.0)),
     ('a g60 ret20 fh10',   dict(grace_s=60.0, use_ret=True, ret_on=20.0, far_hold_s=10.0, form='a')),
     ('b g60 ret20 occG',   dict(grace_s=60.0, use_ret=True, ret_on=20.0, form='b')),
     ('c g60 ret20 occG',   dict(grace_s=60.0, use_ret=True, ret_on=20.0, form='c')),
     ('c g60 ret20 g2-8',   dict(grace_s=60.0, use_ret=True, ret_on=20.0, form='c', ret_all=True)),
     ('c g60 ret10 occG',   dict(grace_s=60.0, use_ret=True, ret_on=10.0, form='c'))]
for hold_s in (30.0, 60.0):
    print('\nFD:68 seeded-occupied at 21:11, user leaves ~21:20 (hold_s=%.0f)' % hold_s)
    print('%-20s %-11s %s' % ('variant', 'release', 'lateness vs 21:20'))
    for nm, kw in V:
        d, rec = seeded(hold_s=hold_s, **kw)
        rel = next((ts for ts, o, *_ in rec if not o), None)
        print('%-20s %-11s %s' % (nm, hm(rel) if rel else 'NONE by 21:39',
                                  ('+%ds' % int(rel - LEFT)) if rel else '---'))
