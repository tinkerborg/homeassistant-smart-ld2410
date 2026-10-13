"""The adversarial multi-occupant case: a stayer OUTSIDE the near band in a
room where arming CAN fire.

A = the real D0:6E bathroom visit (enters 22:04:01, leaves 22:06:43) -- lights
    the near band, so it arms departure.
B = the real FD:68 seated occupant (gates 2-3, still, never near-band), MAXed
    onto A's stream for the whole window and beyond.

Truth: the room is occupied throughout (B never leaves), so NO release is
correct until B's own departure is appended.
"""
import sys, sqlite3
S = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0, S)
sys.path.insert(0, S + '/pinned')
import custom_components.smart_ld2410.algo.detector as _det
assert _det.__file__.startswith(S), _det.__file__
import pol
from pol import STREAM, apply, T, hm, PROD, FIX

c = sqlite3.connect('file:%s?mode=ro' % PROD, uri=True)
cf = sqlite3.connect('file:%s?mode=ro' % FIX, uri=True)
def A(a, b):
    return [(r[0], list(r[1]), list(r[2])) for r in c.execute(
        "select ts,move,still from frames where sensor_id like 'D0:6E%' and ts>=? and ts<? order by ts", (a, b))]
def B(a, b):
    return [(r[0], list(r[1]), list(r[2])) for r in cf.execute(
        "select ts,move,still from frames where ts>=? and ts<? order by ts", (a, b))]

WARM = A(T(21, 58) - 6 * 3600, T(21, 58))
base = A(T(21, 58), T(22, 12))             # A's visit + tail
seat = B(T(21, 44), T(21, 55))             # B seated, still, far gates
gone = B(T(21, 22), T(21, 29))             # B's room genuinely empty

def tile(src, n):
    out = []
    for _ in range(n):
        out += src
    return out

def overlay(base, over):
    """per-gate MAX, over tiled/truncated to base's length."""
    ov = tile(over, len(base) // max(len(over), 1) + 2)[:len(base)]
    out = []
    for i, (ts, mv, st) in enumerate(base):
        m2, s2 = ov[i][1], ov[i][2]
        out.append((ts, [max(mv[g], m2[g]) for g in range(9)],
                    [max(st[g], s2[g]) for g in range(9)]))
    return out

def cont(rows, extra):
    t_end = rows[-1][0]; t0 = extra[0][0]
    return list(rows) + [(t_end + (ts - t0) + 0.1, list(mv), list(st)) for ts, mv, st in extra]

s = overlay(base, seat)
STREAM['adv'] = (WARM, s)                       # B stays for ever
STREAM['adv2'] = (WARM, cont(s, gone))          # then B's room goes empty
BOTH_GONE = s[-1][0]
print('adv window %s..%s ; A leaves 22:06:43 ; B still present throughout' % (hm(s[0][0]), hm(s[-1][0])))
print('adv2 appends an empty tail from %s' % hm(BOTH_GONE))

def tl(rec):
    out = []; p = None
    for ts, o, _ in rec:
        if p is None: p = o; continue
        if o != p: out.append((ts, o)); p = o
    return out

DEP_A = T(22, 6, 43)
print('\n%-7s %-10s %-9s %-10s %-12s %s' % ('stream', 'policy', 'armed', 'entry', 'release', 'verdict'))
for hold_s in (30., 60.):
    print('--- hold_s=%.0f' % hold_s)
    for sname in ('adv', 'adv2'):
        for p in ('arming', 'retention'):
            rec = apply(p, sname, hold_s)
            a = next((ts for ts, o, ar in rec if ar), None)
            t = tl(rec)
            ent = next((x for x, o in t if o), None)
            rel = next((x for x, o in t if not o and ent and x > ent), None)
            if sname == 'adv':
                v = 'DROPS B %+ds after A leaves' % int(rel - DEP_A) if rel else 'holds B (correct)'
            else:
                v = ('releases %+ds vs B gone' % int(rel - BOTH_GONE)) if rel and rel >= BOTH_GONE - 5 else (
                    'DROPS B early @%s' % hm(rel) if rel else 'NEVER releases')
            print('%-7s %-10s %-9s %-10s %-12s %s' % (
                sname, p, hm(a) if a else '--', hm(ent) if ent else '--',
                hm(rel) if rel else 'never', v))
