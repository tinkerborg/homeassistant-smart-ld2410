"""Synthetic multi-occupant case on FD:68.

Stayer  = the real seated span 21:44-21:55 (README: seated, typing, gates 2-3).
Leaver  = the real walk-out 21:19:00-21:21:30 (user leaves the room ~21:20),
          overlaid per-gate MAX onto the stayer's frames at a chosen offset.
Caveat inherited from 4b/4e: energies do not superpose; MAX is a rule-behaviour
probe, not a physical mixture.

  S1  stayer + leaver walks out, stayer remains        -> must NOT release
  S2  S1, then the stayer walks out too, then the real
      empty room (21:22-21:29)                         -> must release

Both exit policies are run on both streams.
"""
import sys, sqlite3, copy, collections
S = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0, S)
sys.path.insert(0, S + '/pinned')
import custom_components.smart_ld2410.algo.detector as _det
assert _det.__file__.startswith(S), _det.__file__
import pol
from pol import STREAM, apply, edg, V, T, hm, Retention, Composite, DetectorConfig, Frame, FIX

cf = sqlite3.connect('file:%s?mode=ro' % FIX, uri=True)
ALL = [(r[0], list(r[1]), list(r[2])) for r in cf.execute("select ts,move,still from frames order by ts")]

def span(a, b):
    return [r for r in ALL if a <= r[0] < b]

SEAT = span(T(21, 44), T(21, 55))
EXIT = span(T(21, 19), T(21, 21, 30))
EMPTY = span(T(21, 22), T(21, 29))
print('spans: seat=%d exit=%d empty=%d frames' % (len(SEAT), len(EXIT), len(EMPTY)))

def mix(base, over, off_i):
    """per-gate MAX of `over` onto `base` starting at base index off_i."""
    out = [(ts, list(mv), list(st)) for ts, mv, st in base]
    for k, (_, mv, st) in enumerate(over):
        i = off_i + k
        if i >= len(out):
            break
        for g in range(9):
            out[i][1][g] = max(out[i][1][g], mv[g])
            out[i][2][g] = max(out[i][2][g], st[g])
    return out

def append(rows, extra):
    """re-timestamp `extra` to continue immediately after `rows`."""
    if not rows:
        return [(ts, mv, st) for ts, mv, st in extra]
    t_end = rows[-1][0]
    t0 = extra[0][0]
    return list(rows) + [(t_end + (ts - t0) + 0.1, list(mv), list(st)) for ts, mv, st in extra]

OFF_S = 90.0          # leaver departs 90 s into the observed span
step = (SEAT[-1][0] - SEAT[0][0]) / max(len(SEAT) - 1, 1)
OFF_I = int(OFF_S / step)
LEAVE_T = SEAT[0][0] + OFF_S
print('frame step %.2fs -> leaver overlay at index %d (%s)' % (step, OFF_I, hm(LEAVE_T)))

s1 = mix(SEAT, EXIT, OFF_I)
s2 = append(append(s1, EXIT), EMPTY)
STAYER_OUT = s1[-1][0] + (EXIT[-1][0] - EXIT[0][0]) * 0.4   # ~ when the 2nd exit walk ends

WARM = [r for r in ALL if r[0] < T(21, 44)]
STREAM['mo1'] = (WARM, s1)
STREAM['mo2'] = (WARM, s2)
# control: the stayer alone, no leaver at all
STREAM['mo0'] = (WARM, [(ts, list(mv), list(st)) for ts, mv, st in SEAT])

print('\nstream ends: s1 %s   s2 %s (2nd exit ends ~%s)' % (
    hm(s1[-1][0]), hm(s2[-1][0]), hm(STAYER_OUT)))

def rel_of(rec, after=None):
    was = None
    for ts, o, _ in rec:
        if after is not None and ts < after:
            was = o; continue
        if was and not o:
            return ts
        was = o
    return None

print('\n%-12s %-10s %-12s %-22s %s' % ('stream', 'policy', 'release', 'vs event', 'verdict'))
for hold_s in (30., 60.):
    print('--- hold_s=%.0f' % hold_s)
    for sname, label, ev, evname, want in (
            ('mo0', 'stayer alone (control)', None, '', 'HOLD'),
            ('mo1', 'stayer + leaver exits', LEAVE_T, 'leaver out', 'HOLD'),
            ('mo2', 'both leave', STAYER_OUT, 'stayer out', 'RELEASE')):
        for pol_name in ('arming', 'retention'):
            rec = apply(pol_name, sname, hold_s, seed=True)
            r = rel_of(rec)
            ok = (r is None) if want == 'HOLD' else (r is not None and r >= (ev or 0) - 5)
            note = ''
            if r and ev:
                note = '%+ds vs %s' % (int(r - ev), evname)
            print('%-12s %-10s %-12s %-22s %s  [%s]' % (
                label if pol_name == 'arming' else '', pol_name,
                hm(r) if r else 'never', note, 'ok' if ok else 'FAIL', want))
