"""4d release rule on livingroom-reset-seated-fd68.db (no neighbour in this room).

Ground truth (README): seated ~21:04-21:20, OUT 21:20-21:39 (cat g4-6 near 21:30),
walked back in 21:39:40, seated through 21:55. 21:49 is a fully-still minute the
shipped detector wrongly released (vacant 21:49:56).
"""
import sqlite3, sys, collections
S = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0, S)
from rel import *  # noqa
from custom_components.smart_ld2410.algo.detector import Detector

c = sqlite3.connect('file:%s?mode=ro' % FIX, uri=True)
rows = [(r[0], list(r[1]), list(r[2])) for r in c.execute(
    "select ts,move,still from frames order by ts")]
print('fixture frames %d  %s -> %s' % (len(rows), hm(rows[0][0]), hm(rows[-1][0])))

# baseline needs 5x60s buckets; treat the first 6 min as warm-up, evaluate from 21:11
SPLIT = T(21, 11)
warm = [r for r in rows if r[0] < SPLIT]
body = [r for r in rows if r[0] >= SPLIT]
print('warm %d (%s-%s)  body %d (%s-%s)' % (
    len(warm), hm(warm[0][0]), hm(warm[-1][0]), len(body), hm(body[0][0]), hm(body[-1][0])))

LEFT, BACK, STILLMIN = T(21, 20), T(21, 39, 40), T(21, 49)

class C4c(Composite):
    def _advance(self, score, ts_mono, *, entry_suppressed=False):
        ls = self.lead_sup
        if not self._occupied and (ls is None or ls > self.lead_max):
            entry_suppressed = True
        Detector._advance(self, score, ts_mono, entry_suppressed=entry_suppressed)

def run2(mode='composite', hold_s=30.0, **kw):
    if mode == '4c':
        cfg = DetectorConfig(hold_s=hold_s)
        d = C4c(cfg, **kw); ret = Retention(warm[0][2]); t0 = warm[0][0]
        rec = []
        for src, keep in ((warm, False), (body, True)):
            for ts, mv, st in src:
                ret.add(ts, st); d.ret = ret.score
                o = d.process(Frame(ts, ts - t0, tuple(mv), tuple(st), 0, False))
                if keep: rec.append((ts, o.occupied, o.score, o.active_gates, d.lead_sup, d.dbg,
                                     max(ret.score[g] for g in range(2, 9))))
        return d, rec
    return run(warm, body, mode=mode, hold_s=hold_s, **kw)

VARIANTS = [
    ('shipped',           dict(mode='shipped')),
    ('4c (entry only)',   dict(mode='4c')),
    ('A grace=0',         dict(grace_s=0.0)),
    ('A grace=60',        dict(grace_s=60.0)),
    ('A grace=90',        dict(grace_s=90.0)),
    ('B g60 ret20 fh10',  dict(grace_s=60.0, use_ret=True, ret_on=20.0, far_hold_s=10.0)),
    ('B g60 ret50 fh10',  dict(grace_s=60.0, use_ret=True, ret_on=50.0, far_hold_s=10.0)),
    ('B g60 ret100 fh10', dict(grace_s=60.0, use_ret=True, ret_on=100.0, far_hold_s=10.0)),
    ('B g60 ret20 fh30',  dict(grace_s=60.0, use_ret=True, ret_on=20.0, far_hold_s=30.0)),
]

def score_run(rec):
    """Metrics against the README ground truth."""
    tl = edges(rec)
    left_rel = next((t for t, o in tl if not o and t >= LEFT), None)
    # false occupancy while out of the room 21:22-21:39
    out = [r for r in rec if T(21, 22) <= r[0] < T(21, 39)]
    fo = 100.0 * sum(1 for r in out if r[1]) / max(len(out), 1)
    seat = [r for r in rec if BACK + 20 <= r[0] < T(21, 55)]
    fv = 100.0 * sum(1 for r in seat if not r[1]) / max(len(seat), 1)
    drops = [t for t, o in tl if not o and BACK <= t < T(21, 55)]
    entry_back = next((t for t, o in tl if o and t >= BACK - 10), None)
    return left_rel, fo, entry_back, fv, drops

for hold_s in (30.0, 60.0):
    print('\n' + '=' * 116)
    print('FD:68  hold_s=%.0f   targets: release soon after %s | 0%% occupied while out | re-entry ~%s | NO drop 21:39-21:55'
          % (hold_s, hm(LEFT), hm(BACK)))
    print('=' * 116)
    print('%-19s %-11s %-8s %-11s %-8s %s' % ('variant', 'rel@left', 'out-occ%', 're-entry', 'seat-vac%', 'drops while seated'))
    for vname, kw in VARIANTS:
        d, rec = run2(hold_s=hold_s, **kw)
        lr, fo, eb, fv, drops = score_run(rec)
        print('%-19s %-11s %-8.1f %-11s %-8.1f %s' % (
            vname, hm(lr) if lr else 'NONE', fo, hm(eb) if eb else 'NEVER', fv,
            ', '.join(hm(t) for t in drops) or '-- none --'))

# --------------------------------------------------------------- timelines
print('\n' + '=' * 116)
print('FULL TIMELINES (hold_s=30)')
print('=' * 116)
for vname, kw in VARIANTS:
    d, rec = run2(hold_s=30.0, **kw)
    print('%-19s %s' % (vname, fmt_tl(edges(rec))))

# --------------------------------------------------------------- 21:49 forensics
print('\n' + '=' * 116)
print('BLOCK forensics 21:39-21:56 (B g60 ret20 fh10, hold_s=inf), per 20s')
print('=' * 116)
d, rec = run2(hold_s=1e9, grace_s=60.0, use_ret=True, ret_on=20.0, far_hold_s=10.0)
print('  occ_gates = %s' % sorted(d.occ_gates))
b = collections.OrderedDict()
for ts, occ, score, ag, ls, dbg, r in rec:
    if not (T(21, 39) <= ts < T(21, 56)): continue
    k = int(ts // 20) * 20
    e = b.setdefault(k, dict(n=0, hot=0, near=0, far=0, ret=0, blk=0, r=[], h=collections.Counter()))
    e['n'] += 1; e['r'].append(r); e['h'][ls if ls is not None else -1] += 1
    if score >= 1.5: e['hot'] += 1
    if dbg and dbg[2]: e['near'] += 1
    if dbg and dbg[3]: e['far'] += 1
    if dbg and dbg[4]: e['ret'] += 1
    if dbg and dbg[5]: e['blk'] += 1
print('%-10s %4s %4s %8s %7s %8s %6s %8s  %s' % ('t', 'n', 'hot', 'near_rec', 'far_rec', 'ret_elev', 'BLOCK', 'ret(med)', 'lead hist'))
for k, e in b.items():
    rr = sorted(e['r'])
    print('%-10s %4d %4d %8d %7d %8d %6d %8.1f  %s%s' % (
        hm(k), e['n'], e['hot'], e['near'], e['far'], e['ret'], e['blk'], rr[len(rr) // 2],
        ' '.join('g%d:%d' % (g, v) for g, v in sorted(e['h'].items())),
        '   <- fully-still minute' if T(21, 49) <= k < T(21, 50) else ''))

# --------------------------------------------------------------- cat window
print('\n' + '=' * 116)
print('CAT / EMPTY window 21:20-21:39 (B g60 ret20 fh10, real run hold_s=30), per 60s')
print('=' * 116)
d, rec = run2(hold_s=30.0, grace_s=60.0, use_ret=True, ret_on=20.0, far_hold_s=10.0)
b = collections.OrderedDict()
for ts, occ, score, ag, ls, dbg, r in rec:
    if not (T(21, 20) <= ts < T(21, 40)): continue
    k = int(ts // 60) * 60
    e = b.setdefault(k, dict(n=0, occ=0, hot=0, r=[], h=collections.Counter()))
    e['n'] += 1; e['r'].append(r); e['h'][ls if ls is not None else -1] += 1
    if occ: e['occ'] += 1
    if score >= 1.5: e['hot'] += 1
print('%-8s %5s %5s %5s %9s  %s' % ('t', 'n', 'occ', 'hot', 'ret(med)', 'lead hist'))
for k, e in b.items():
    rr = sorted(e['r'])
    print('%-8s %5d %5d %5d %9.1f  %s' % (hm(k)[:5], e['n'], e['occ'], e['hot'], rr[len(rr) // 2],
          ' '.join('g%d:%d' % (g, v) for g, v in sorted(e['h'].items()))))
