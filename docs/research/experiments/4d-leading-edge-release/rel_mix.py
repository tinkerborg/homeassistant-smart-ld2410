"""Drive the 4d release rule over the 4b/4c overlap streams (D0:6E)."""
import sqlite3, sys, collections
S = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0, S)
from rel import *   # noqa

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
    'SUM (synth)':       mix(lambda a, b: min(100, a + b)),
}
print('warm %d frames, window %s-%s, %d frames/stream' % (len(warm), hm(W0), hm(W1), n))

def release_after(rec, t):
    was = None
    for ts, o, *_ in rec:
        if ts < t: was = o; continue
        if was and not o: return ts
        was = o
    return None

VARIANTS = [
    ('shipped',          dict(mode='shipped')),
    ('4c (entry only)',  dict(mode='4c')),
    ('A grace=0',        dict(use_ret=False, grace_s=0.0)),
    ('A grace=30',       dict(use_ret=False, grace_s=30.0)),
    ('A grace=60',       dict(use_ret=False, grace_s=60.0)),
    ('A grace=90',       dict(use_ret=False, grace_s=90.0)),
    ('B g60 ret20 fh10', dict(use_ret=True, grace_s=60.0, ret_on=20.0, far_hold_s=10.0)),
    ('B g60 ret20 fh2',  dict(use_ret=True, grace_s=60.0, ret_on=20.0, far_hold_s=2.0)),
    ('B g60 ret100 fh10', dict(use_ret=True, grace_s=60.0, ret_on=100.0, far_hold_s=10.0)),
    ('B g60 ret20 nofar', dict(use_ret=True, grace_s=60.0, ret_on=20.0, far_hold_s=0.0)),
]

class C4c(Composite):
    """4c: composite entry, shipped release."""
    def _advance(self, score, ts_mono, *, entry_suppressed=False):
        ls = self.lead_sup
        if not self._occupied and (ls is None or ls > self.lead_max):
            entry_suppressed = True
        Detector._advance(self, score, ts_mono, entry_suppressed=entry_suppressed)

def run2(warm, rows, *, mode='composite', hold_s=30.0, **kw):
    if mode == '4c':
        cfg = DetectorConfig(hold_s=hold_s)
        d = C4c(cfg, **kw); ret = Retention(warm[0][2]); t0 = warm[0][0]
        for ts, mv, st in warm:
            ret.add(ts, st); d.ret = ret.score
            d.process(Frame(ts, ts - t0, tuple(mv), tuple(st), 0, False))
        rec = []
        for ts, mv, st in rows:
            ret.add(ts, st); d.ret = ret.score
            o = d.process(Frame(ts, ts - t0, tuple(mv), tuple(st), 0, False))
            rec.append((ts, o.occupied, o.score, o.active_gates, d.lead_sup, d.dbg, 0.0))
        return d, rec
    return run(warm, rows, mode=mode, hold_s=hold_s, **kw)

for hold_s in (30.0, 60.0):
    print('\n' + '=' * 108)
    print('hold_s = %.0f   (target: MAX release ~%s ; bath control %s ; kitchen never enters)'
          % (hold_s, hm(DEPART + hold_s), hm(DEPART)))
    print('=' * 108)
    print('%-21s %-19s %-11s %-11s %s' % ('variant', 'stream', 'entry', 'release', 'timeline'))
    for vname, kw in VARIANTS:
        for sname, rows in STREAMS.items():
            d, rec = run2(warm, rows, hold_s=hold_s, **kw)
            tl = edges(rec)
            entry = next((t for t, o in tl if o), None)
            if entry is None and rec[0][1]: entry = rec[0][0]
            rel = release_after(rec, DEPART)
            print('%-21s %-19s %-11s %-11s %s' % (
                vname, sname, hm(entry) if entry else 'NEVER',
                hm(rel) if rel else ('n/a' if entry is None else 'none by 22:10'), fmt_tl(tl)))
            if vname == 'A near-only' and sname == 'MAX (synth)' and hold_s == 30.0:
                print('     occ_gates=%s' % sorted(d.occ_gates))
        print('')

# ---------------------------------------------------------------- forensics
# hold_s huge => never releases, so the block flags stay observable all the way through
for sname in ('bath (control)', 'MAX (synth)'):
    print('\n' + '=' * 108)
    print('BLOCK forensics, %s  (grace=60 ret_on=20 far_hold=10, hold_s=inf so it never releases)' % sname)
    print('  need BLOCK true up to %s (departure); then a 30s continuous BLOCK-free run to release' % hm(DEPART))
    print('=' * 108)
    d, rec = run2(warm, STREAMS[sname], hold_s=1e9, use_ret=True, grace_s=60.0,
                  ret_on=20.0, far_hold_s=10.0)
    buck = collections.OrderedDict()
    for ts, occ, score, ag, ls, dbg, r in rec:
        if ts < T(22, 4): continue
        b = int(ts // 20) * 20
        e = buck.setdefault(b, collections.Counter())
        e['n'] += 1
        if score >= 1.5: e['hot'] += 1
        if dbg and dbg[2]: e['near_rec'] += 1
        if dbg and dbg[3]: e['far_rec'] += 1
        if dbg and dbg[4]: e['ret_elev'] += 1
        if dbg and dbg[5]: e['BLOCK'] += 1
    print('%-10s %5s %5s %9s %8s %9s %7s' % ('t', 'n', 'hot', 'near_rec', 'far_rec', 'ret_elev', 'BLOCK'))
    for b, e in buck.items():
        print('%-10s %5d %5d %9d %8d %9d %7d%s' % (
            hm(b), e['n'], e['hot'], e['near_rec'], e['far_rec'], e['ret_elev'], e['BLOCK'],
            '   <- departure' if b == 22 * 3600 else ''))
