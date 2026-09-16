"""Combined sweep: every release-rule form against BOTH the D0:6E overlap mix
and the FD:68 seated fixture, plus per-gate retention separability."""
import sqlite3, sys, collections
S = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0, S)
from rel import *  # noqa
from custom_components.smart_ld2410.algo.detector import Detector

# ------------------------------------------------------------------ data
W0, W1 = T(21, 58), T(22, 10); WARM0 = W0 - 6 * 3600.0
K0, K1 = T(5, 11), T(5, 23); ARRIVE, DEPART = T(22, 4, 1), T(22, 6, 43)
c = sqlite3.connect('file:%s?mode=ro' % PROD, uri=True)
def fetch(a, b):
    return [(r[0], list(r[1]), list(r[2])) for r in c.execute(
        "select ts,move,still from frames where sensor_id like 'D0:6E%' and ts>=? and ts<? order by ts", (a, b))]
warmD = fetch(WARM0, W0); bath = fetch(W0, W1); kit = fetch(K0, K1)
n = min(len(bath), len(kit))
MIXES = {
    'bath ctrl':    bath[:n],
    'kitchen ctrl': [(bath[i][0], kit[i][1], kit[i][2]) for i in range(n)],
    'MAX':          [(bath[i][0], [max(bath[i][1][g], kit[i][1][g]) for g in range(9)],
                      [max(bath[i][2][g], kit[i][2][g]) for g in range(9)]) for i in range(n)],
}
cf = sqlite3.connect('file:%s?mode=ro' % FIX, uri=True)
fd = [(r[0], list(r[1]), list(r[2])) for r in cf.execute("select ts,move,still from frames order by ts")]
SPLIT = T(21, 11)
warmF = [r for r in fd if r[0] < SPLIT]; bodyF = [r for r in fd if r[0] >= SPLIT]
LEFT, BACK = T(21, 20), T(21, 39, 40)

class C4c(Composite):
    def _advance(self, score, ts_mono, *, entry_suppressed=False):
        ls = self.lead_sup
        if not self._occupied and (ls is None or ls > self.lead_max):
            entry_suppressed = True
        Detector._advance(self, score, ts_mono, entry_suppressed=entry_suppressed)

def go(warm, body, mode='composite', hold_s=30.0, **kw):
    if mode in ('shipped', 'composite'):
        return run(warm, body, mode=mode, hold_s=hold_s, **kw)
    cfg = DetectorConfig(hold_s=hold_s); d = C4c(cfg, **kw)
    ret = Retention(warm[0][2]); t0 = warm[0][0]; rec = []
    for src, keep in ((warm, False), (body, True)):
        for ts, mv, st in src:
            ret.add(ts, st); d.ret = ret.score
            o = d.process(Frame(ts, ts - t0, tuple(mv), tuple(st), 0, False))
            if keep: rec.append((ts, o.occupied, o.score, o.active_gates, d.lead_sup, d.dbg,
                                 max(ret.score[g] for g in range(2, 9))))
    return d, rec

VARIANTS = [
    ('shipped',            dict(mode='shipped')),
    ('4c entry only',      dict(mode='4c')),
    ('A g60 near-only',    dict(grace_s=60.0)),
    ('A g90 near-only',    dict(grace_s=90.0)),
    ('a g60 ret20 fh10',   dict(grace_s=60.0, use_ret=True, ret_on=20.0, far_hold_s=10.0, form='a')),
    ('b g60 ret20 occG',   dict(grace_s=60.0, use_ret=True, ret_on=20.0, form='b')),
    ('b g60 ret20 g2-8',   dict(grace_s=60.0, use_ret=True, ret_on=20.0, form='b', ret_all=True)),
    ('b g60 ret100 g2-8',  dict(grace_s=60.0, use_ret=True, ret_on=100.0, form='b', ret_all=True)),
    ('b g60 ret250 g2-8',  dict(grace_s=60.0, use_ret=True, ret_on=250.0, form='b', ret_all=True)),
    ('c g60 ret20 g2-8',   dict(grace_s=60.0, use_ret=True, ret_on=20.0, form='c', ret_all=True)),
    ('c g60 ret100 g2-8',  dict(grace_s=60.0, use_ret=True, ret_on=100.0, form='c', ret_all=True)),
]

def rel_after(rec, t):
    was = None
    for ts, o, *_ in rec:
        if ts < t: was = o; continue
        if was and not o: return ts
        was = o
    return None

for hold_s in (30.0, 60.0):
    print('\n' + '=' * 124)
    print('hold_s=%.0f  | D0:6E mix: bath ctrl rel target %s, MAX rel target %s, kitchen NEVER'
          '  | FD:68: rel after %s, re-enter %s, NO drop 21:40-21:55'
          % (hold_s, hm(DEPART), hm(DEPART + hold_s), hm(LEFT), hm(BACK)))
    print('=' * 124)
    print('%-20s %-10s %-10s %-10s | %-10s %-6s %-10s %-8s %s'
          % ('variant', 'bath rel', 'MAX rel', 'kitch ent', 'fd rel@out', 'out%', 'fd re-entry', 'seatvac%', 'fd drops 21:40-21:55'))
    for vname, kw in VARIANTS:
        cells = []
        for sname in ('bath ctrl', 'MAX', 'kitchen ctrl'):
            d, rec = go(warmD, MIXES[sname], hold_s=hold_s, **kw)
            tl = edges(rec)
            if sname == 'kitchen ctrl':
                e = next((t for t, o in tl if o), None)
                cells.append(hm(e) if e else 'NEVER')
            else:
                r = rel_after(rec, DEPART if sname == 'bath ctrl' else ARRIVE)
                early = next((t for t, o in tl if not o and ARRIVE < t < DEPART), None)
                cells.append((hm(early) + '!') if early else (hm(r) if r else 'none'))
        d, rec = go(warmF, bodyF, hold_s=hold_s, **kw)
        tl = edges(rec)
        lr = next((t for t, o in tl if not o and t >= LEFT), None)
        out = [r for r in rec if T(21, 22) <= r[0] < T(21, 39)]
        fo = 100.0 * sum(1 for r in out if r[1]) / max(len(out), 1)
        eb = next((t for t, o in tl if o and t >= BACK - 10), None)
        seat = [r for r in rec if T(21, 40, 30) <= r[0] < T(21, 55)]
        fv = 100.0 * sum(1 for r in seat if not r[1]) / max(len(seat), 1)
        drops = [t for t, o in tl if not o and T(21, 40) <= t < T(21, 55)]
        print('%-20s %-10s %-10s %-10s | %-10s %-6.1f %-10s %-8.1f %s'
              % (vname, cells[0], cells[1], cells[2], hm(lr) if lr else 'NONE', fo,
                 hm(eb) if eb else 'NEVER', fv, ', '.join(hm(t) for t in drops) or 'none'))
    print('  (! = released before the genuine departure / while the user was present)')

# ------------------------------------------------------------------ per-gate retention
print('\n' + '=' * 124)
print('PER-GATE RETENTION (median stat/floor) in the windows that must be told apart')
print('=' * 124)
def ret_trace(rows, warm):
    r = Retention(warm[0][2]); out = []
    for ts, mv, st in warm: r.add(ts, st)
    for ts, mv, st in rows: out.append((ts, list(r.add(ts, st))))
    return out
WINS = [
    ('bath ctrl',   'HOLD  occupant still 22:05:13-22:06:43', T(22, 5, 13), T(22, 6, 43)),
    ('MAX',         'REL   neighbour only 22:06:43-22:08:00', DEPART, T(22, 8)),
    ('MAX',         'REL   neighbour only 22:08:00-22:10:00', T(22, 8), T(22, 10)),
    ('kitchen ctrl', 'REL  neighbour only 22:06:43-22:08:00', DEPART, T(22, 8)),
]
tr = {k: ret_trace(MIXES[k], warmD) for k in MIXES}
print('%-13s %-40s %s' % ('stream', 'window', ' '.join('g%d' % g for g in range(2, 9))))
for k, lbl, a, b in WINS:
    sel = [s for ts, s in tr[k] if a <= ts < b]
    med = [sorted(x[g] for x in sel)[len(sel) // 2] for g in range(9)]
    print('%-13s %-40s %s' % (k, lbl, ' '.join('%6.1f' % med[g] for g in range(2, 9))))
trF = ret_trace(bodyF, warmF)
for lbl, a, b in [('HOLD  seated 21:43-21:55', T(21, 43), T(21, 55)),
                  ('HOLD  still minute 21:49-21:50', T(21, 49), T(21, 50)),
                  ('REL   empty 21:22-21:29', T(21, 22), T(21, 29)),
                  ('REL   empty+cat 21:30-21:36', T(21, 30), T(21, 36))]:
    sel = [s for ts, s in trF if a <= ts < b]
    med = [sorted(x[g] for x in sel)[len(sel) // 2] for g in range(9)]
    print('%-13s %-40s %s' % ('FD:68', lbl, ' '.join('%6.1f' % med[g] for g in range(2, 9))))
