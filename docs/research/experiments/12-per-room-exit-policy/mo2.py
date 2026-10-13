"""Multi-occupant probe on D0:6E (the room where arming CAN fire) and the
cost of the mismatched assignment measured past the fixture window.

stayer  = the real still-occupant span 22:04:30-22:06:00 of the genuine
          bathroom visit, looped to give a long observation tail
leaver  = the real departure walk 22:06:00-22:07:00 overlaid per-gate MAX
          at +60 s
Expect: a stayer-only control must never release; with the leaver overlaid,
arming arms on the leaver's crossing and the stayer is then dropped.
"""
import sys, sqlite3, copy, collections
S = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0, S)
sys.path.insert(0, S + '/pinned')
import custom_components.smart_ld2410.algo.detector as _det
assert _det.__file__.startswith(S), _det.__file__
import pol
from pol import STREAM, apply, V, T, hm, PROD

c = sqlite3.connect('file:%s?mode=ro' % PROD, uri=True)
def fetch(a, b):
    return [(r[0], list(r[1]), list(r[2])) for r in c.execute(
        "select ts,move,still from frames where sensor_id like 'D0:6E%' and ts>=? and ts<? order by ts", (a, b))]

STILL = fetch(T(22, 4, 30), T(22, 6, 0))
WALK = fetch(T(22, 6, 0), T(22, 7, 0))
WARM = fetch(T(22, 4, 30) - 6 * 3600, T(22, 4, 30))
print('still=%d walk=%d warm=%d' % (len(STILL), len(WALK), len(WARM)))

def loop(rows, n):
    out = []; t = rows[0][0]
    step = (rows[-1][0] - rows[0][0]) / max(len(rows) - 1, 1)
    for k in range(n):
        for ts, mv, st in rows:
            out.append((t, list(mv), list(st))); t += step
    return out

BASE = loop(STILL, 5)          # ~7.5 min of a still occupant
step = (BASE[-1][0] - BASE[0][0]) / max(len(BASE) - 1, 1)
OFF_I = int(60.0 / step)
LEAVE_T = BASE[0][0] + 60.0

def mix(base, over, off_i):
    out = [(ts, list(mv), list(st)) for ts, mv, st in base]
    for k, (_, mv, st) in enumerate(over):
        i = off_i + k
        if i >= len(out): break
        for g in range(9):
            out[i][1][g] = max(out[i][1][g], mv[g])
            out[i][2][g] = max(out[i][2][g], st[g])
    return out

STREAM['bm0'] = (WARM, BASE)                       # stayer alone
STREAM['bm1'] = (WARM, mix(BASE, WALK, OFF_I))     # stayer + leaver walks out
print('base %s .. %s ; leaver walks out at %s' % (hm(BASE[0][0]), hm(BASE[-1][0]), hm(LEAVE_T)))

def rel_of(rec):
    was = None
    for ts, o, _ in rec:
        if was and not o: return ts
        was = o
    return None
def arm_of(rec):
    return next((ts for ts, o, a in rec if a), None)

print('\n%-28s %-10s %-10s %-10s %s' % ('stream', 'policy', 'armed', 'release', 'stayer'))
for hold_s in (30., 60.):
    print('--- hold_s=%.0f' % hold_s)
    for sname, label in (('bm0', 'stayer alone (control)'), ('bm1', 'stayer + leaver exits')):
        for p in ('arming', 'retention'):
            rec = apply(p, sname, hold_s, seed=True)
            r = rel_of(rec); a = arm_of(rec)
            print('%-28s %-10s %-10s %-10s %s' % (
                label if p == 'arming' else '', p, hm(a) if a else '--',
                hm(r) if r else 'never',
                'DROPPED %+ds after leaver' % int(r - LEAVE_T) if r else 'held'))

# ---- how long does form-c stay latched in the bathroom after a real visit? ----
print('\n--- mismatch cost: retention-only on D0:6E, extended past the fixture window')
LONG = fetch(T(21, 58), T(23, 30))
STREAM['bathlong'] = (fetch(T(21, 58) - 6 * 3600, T(21, 58)), LONG)
for p in ('arming', 'retention'):
    rec = apply(p, 'bathlong', 30.)
    tl = []; prev = None
    for ts, o, _ in rec:
        if prev is None: prev = o; continue
        if o != prev: tl.append((ts, o)); prev = o
    ent = next((t for t, o in tl if o), None)
    rel = next((t for t, o in tl if not o and ent and t > ent), None)
    occ = sum(1 for _, o, _ in rec if o) / max(len(rec), 1) * 100
    print('%-10s entry %-9s release %-9s  occupied %.1f%% of 21:58-23:30 (truth: 2m42s = 2.9%%)' % (
        p, hm(ent) if ent else '--', hm(rel) if rel else 'NEVER', occ))
