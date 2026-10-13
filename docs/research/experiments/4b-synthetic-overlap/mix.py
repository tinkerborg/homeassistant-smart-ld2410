"""Synthesise 'bathroom occupant + kitchen person through the wall' on D0:6E.

Streams (all on the bathroom 21:58:00-22:10:00 timestamps, 7200 frames @10Hz):
  bath    = real genuine visit (control; occupancy 22:04:01 -> 22:06:43)
  kitchen = real kitchen-only block 05:11-05:23 re-timestamped (control, bathroom empty)
  MAX     = per gate/channel max(bath, kitchen)      -- dominant-scatterer approx
  SUM     = per gate/channel min(100, bath+kitchen)  -- additive-clipped

NOT RF physics: two scatterers do not superpose in the LD2410 energy domain.
This is a logic-path stress test of the detection rules, nothing more.

Warm-up: 6h of REAL D0:6E data 15:58:00-21:58:00 fed to every stream, so the
baseline/ceiling/EMA state at the window start is identical and genuine.
"""
import sqlite3, datetime, zoneinfo, math, sys, collections

S = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0, S)
sys.path.insert(0, '/Users/rmk/Repo/homeassistant-smart-ld2410')
from lead import Model as LeadModel, leading_suppressed, leading_raw, K, GATES, SUPPORT_TAU
from custom_components.smart_ld2410.algo.detector import Detector
from custom_components.smart_ld2410.algo.types import DetectorConfig, Frame

TZ = zoneinfo.ZoneInfo('America/New_York')
DB = S + '/prod-frames.db'
def T(h, m, s=0): return datetime.datetime(2026, 9, 11, h, m, s, tzinfo=TZ).timestamp()
def hm(t): return datetime.datetime.fromtimestamp(t, TZ).strftime('%H:%M:%S')
def hhmm(t): return datetime.datetime.fromtimestamp(t, TZ).strftime('%H:%M')

W0, W1 = T(21, 58), T(22, 10)          # bathroom test window
WARM0 = W0 - 6 * 3600.0                # 15:58
K0, K1 = T(5, 11), T(5, 23)            # kitchen-only block
ARRIVE, DEPART = T(22, 4, 1), T(22, 6, 43)

c = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
def fetch(a, b):
    return c.execute("select ts,move,still from frames where sensor_id like 'D0:6E%' "
                     "and ts>=? and ts<? order by ts", (a, b)).fetchall()

warm = [(r[0], list(r[1]), list(r[2])) for r in fetch(WARM0, W0)]
bath = [(r[0], list(r[1]), list(r[2])) for r in fetch(W0, W1)]
kit  = [(r[0], list(r[1]), list(r[2])) for r in fetch(K0, K1)]
n = min(len(bath), len(kit))
print('warm-up frames %d (%s -> %s)' % (len(warm), hm(warm[0][0]), hm(warm[-1][0])))
print('bath %d  kitchen %d  -> aligning %d frames by index' % (len(bath), len(kit), n))

def mix(op):
    out = []
    for i in range(n):
        ts = bath[i][0]
        mv = [op(bath[i][1][g], kit[i][1][g]) for g in range(9)]
        st = [op(bath[i][2][g], kit[i][2][g]) for g in range(9)]
        out.append((ts, mv, st))
    return out

STREAMS = {
    'bath (control)':    bath[:n],
    'kitchen (control)': [(bath[i][0], kit[i][1], kit[i][2]) for i in range(n)],
    'MAX (synth)':       mix(lambda a, b: max(a, b)),
    'SUM (synth)':       mix(lambda a, b: min(100, a + b)),
}

# ---------------------------------------------------------------- real detector
def run_detector(rows):
    d = Detector(DetectorConfig())
    t0 = warm[0][0]
    for ts, mv, st in warm:
        d.process(Frame(ts, ts - t0, tuple(mv), tuple(st), 0, False))
    ceil = d.baseline.move_ceiling
    rec = []
    for ts, mv, st in rows:
        o = d.process(Frame(ts, ts - t0, tuple(mv), tuple(st), 0, False))
        arr_bar = DetectorConfig().arrival_frac * d.baseline.move_ceiling
        rec.append((ts, o.occupied, o.score, o.active_gates, o.leading_gate,
                    max((mv[g] for g in o.active_gates), default=0), arr_bar))
    return ceil, rec

# ---------------------------------------------------------------- lead.py suppressed leading gate
def run_lead(rows):
    m = LeadModel(); sup = [0.0] * GATES; prev = None; out = []
    for ts, mv, st in warm:
        if m.ready:
            rm, rs = m.res(mv, st)
            peaks = [max(0.0, rm[g], rs[g]) for g in range(GATES)]
            a = 1.0 if prev is None else (1.0 - math.exp(-min(ts - prev, 2.0) / SUPPORT_TAU) if ts > prev else 0.0)
            for g in range(GATES): sup[g] += a * (peaks[g] - sup[g])
        prev = ts; m.add(ts, mv, st)
    for ts, mv, st in rows:
        rm, rs = m.res(mv, st)
        peaks = [max(0.0, rm[g], rs[g]) for g in range(GATES)]
        a = 1.0 - math.exp(-min(ts - prev, 2.0) / SUPPORT_TAU)
        for g in range(GATES): sup[g] += a * (peaks[g] - sup[g])
        ls, runs = leading_suppressed(rm, sup)
        out.append((ts, leading_raw(rm), ls, tuple(rm)))
        prev = ts; m.add(ts, mv, st)
    return out

# ---------------------------------------------------------------- retention stat (acc1-3)
TAU_F, TAU_S, FLOOR_MIN = 2.0, 60.0, 0.10
def run_ret(rows):
    """slow/fast still-EMA divergence over adaptive floor; acc3.py statistic."""
    pre = warm[-1200:]                      # 2 min preroll is plenty for tau_s=60
    seq = pre + rows
    f = list(seq[0][2]); s = list(f); fl = [0.3] * 9
    prev = seq[0][0]; out = []
    for i in range(1, len(seq)):
        ts, mv, st = seq[i]
        dt = min(ts - prev, 2.0); prev = ts
        af = 1 - math.exp(-dt / TAU_F); a_s = 1 - math.exp(-dt / TAU_S); a10 = 1 - math.exp(-dt / 10.)
        stat = [0.0] * 9; sco = [0.0] * 9
        for g in range(9):
            x = st[g]
            f[g] += af * (x - f[g]); s[g] += a_s * (x - s[g])
            stat[g] = abs(f[g] - s[g])
            dc = min(abs(x - seq[i - 1][2][g]), 4 * fl[g] + 0.5)
            fl[g] += a10 * (dc - fl[g])
            sco[g] = stat[g] / max(fl[g], FLOOR_MIN)
        if ts >= rows[0][0]: out.append((ts, sco))
    return out

RES = {}
for name, rows in STREAMS.items():
    ceil, det = run_detector(rows)
    RES[name] = dict(ceil=ceil, det=det, lead=run_lead(rows), ret=run_ret(rows))
    print('%-18s move_ceiling=%.1f  arrival bar=%.1f' % (name, ceil, 0.55 * ceil))

# ================================================================ Q1 arrival gate
print('\n' + '=' * 92)
print('Q1  ARRIVAL GATING (bar = 0.55 x move_ceiling), entry window 22:03:00-22:04:30')
print('=' * 92)
print('%-18s %8s %8s  %s' % ('stream', 'bar', 'maxMove', 'frames over bar (in candidate gates)'))
for name in STREAMS:
    bar = 0.55 * RES[name]['ceil']
    sel = [r for r in RES[name]['det'] if T(22, 3) <= r[0] <= T(22, 4, 30)]
    over = sum(1 for r in sel if r[5] >= bar)
    print('%-18s %8.1f %8d  %d frames >= bar  -> %s' % (
        name, bar, max((r[5] for r in sel), default=0), over,
        'CLEARS (min_frames=1)' if over >= 1 else 'BLOCKED'))

# ================================================================ occupancy timeline
print('\n' + '=' * 92)
print('OCCUPANCY (real shipped detector, default config) over the 12-min window')
print('=' * 92)
for name in STREAMS:
    det = RES[name]['det']; tl = []; prev = None
    for ts, occ, *_ in det:
        if prev is None or occ != prev: tl.append((ts, occ)); prev = occ
    occ_s = 0.0; on = None
    for ts, o in tl:
        if o: on = ts
        elif on is not None: occ_s += ts - on; on = None
    if on is not None: occ_s += det[-1][0] - on
    print('%-18s occupied %5.0fs  %s' % (name, occ_s,
          ' '.join('%s%s' % ('ON@' if o else 'off@', hm(t)) for t, o in tl[1:] or tl)))

# ================================================================ Q2 leading gate
print('\n' + '=' * 92)
print('Q2  LEADING GATE at entry (lead.py, isolated-gate suppression), 22:03:00-22:04:30')
print('=' * 92)
print('%-18s %-10s  %s' % ('stream', 'min lead', 'suppressed-lead histogram'))
for name in STREAMS:
    sel = [r for r in RES[name]['lead'] if T(22, 3) <= r[0] <= T(22, 4, 30)]
    sups = [r[2] for r in sel if r[2] is not None]
    h = collections.Counter(sups)
    print('%-18s %-10s  %s' % (name, min(sups) if sups else 'none',
          ' '.join('g%d:%d' % (g, h[g]) for g in sorted(h)) or '(nothing survives)'))

# ================================================================ per-minute table
print('\n' + '=' * 92)
print('PER-MINUTE: detector score (median) | retention stat max g0-3 (median) | suppressed lead (mode)')
print('=' * 92)
mins = list(range(int(W0 // 60), int(W1 // 60)))
for name in STREAMS:
    det = {}; ret = {}; led = {}
    for r in RES[name]['det']: det.setdefault(int(r[0] // 60), []).append(r[2])
    for ts, sc in RES[name]['ret']: ret.setdefault(int(ts // 60), []).append(max(sc[0:4]))
    for r in RES[name]['lead']: led.setdefault(int(r[0] // 60), []).append(r[2])
    print('\n-- %s' % name)
    print('  %-6s %7s %7s  %s' % ('min', 'score', 'retain', 'lead'))
    for m in mins:
        d = sorted(det.get(m, [0])); rr = sorted(ret.get(m, [0]))
        ls = [x for x in led.get(m, []) if x is not None]
        mode = collections.Counter(ls).most_common(1)
        tag = ''
        if m == int(ARRIVE // 60): tag = '  <- arrival 22:04:01'
        if m == int(DEPART // 60): tag = '  <- departure 22:06:43'
        if int(DEPART // 60) < m <= int(DEPART // 60) + 3: tag = '  <- POST-DEPARTURE'
        print('  %-6s %7.1f %7.1f  %-6s%s' % (
            hhmm(m * 60), d[len(d) // 2], rr[len(rr) // 2],
            ('g%d(%d%%)' % (mode[0][0], 100 * mode[0][1] // len(led.get(m, [1])))) if mode else '-', tag))

# ================================================================ Q4 departure hole
print('\n' + '=' * 92)
print('Q4  POST-DEPARTURE (22:06:43 +3min): does occupancy stay latched?')
print('=' * 92)
print('%-18s %-11s %-11s %-9s %s' % ('stream', 'occ@+30s', 'occ@+3min', 'released', 'release time'))
for name in STREAMS:
    det = RES[name]['det']
    def occ_at(t):
        v = False
        for ts, o, *_ in det:
            if ts <= t: v = o
            else: break
        return v
    rel = None; was = False
    for ts, o, *_ in det:
        if ts < DEPART: was = o; continue
        if was and not o: rel = ts; break
        was = o
    print('%-18s %-11s %-11s %-9s %s' % (
        name, occ_at(DEPART + 30), occ_at(DEPART + 180),
        'yes' if rel else 'NO', hm(rel) if rel else '--- still occupied at 22:10 ---'))

# ================================================================ Q3/Q4 detail at occupancy gates 1-4
print('\n' + '=' * 92)
print('Q3/Q4 DETAIL at the occupancy\'s own gates 1-4 (event active_gates=[1,2,3,4])')
print('  retain = median max_g1..4 stat/floor | occ%% = frames occupied | lead = suppressed-lead mode')
print('=' * 92)
for name in STREAMS:
    ret = {}; det = {}; led = {}
    for ts, sc in RES[name]['ret']: ret.setdefault(int(ts // 60), []).append(max(sc[1:5]))
    for r in RES[name]['det']: det.setdefault(int(r[0] // 60), []).append(r[1])
    for r in RES[name]['lead']: led.setdefault(int(r[0] // 60), []).append(r[2])
    print('\n-- %s' % name)
    print('  %-6s %8s %6s  %s' % ('min', 'retain', 'occ%', 'lead'))
    for m in range(int(T(22, 4) // 60), int(W1 // 60)):
        rr = sorted(ret.get(m, [0])); dd = det.get(m, [False])
        ls = [x for x in led.get(m, []) if x is not None]
        mode = collections.Counter(ls).most_common(1)
        print('  %-6s %8.1f %5.0f%%  %s' % (hhmm(m * 60), rr[len(rr) // 2],
              100.0 * sum(dd) / len(dd),
              ('g%d in %d%% of frames' % (mode[0][0], 100 * mode[0][1] // len(led.get(m, [1])))) if mode else 'no surviving run'))
