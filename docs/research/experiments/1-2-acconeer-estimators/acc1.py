import sqlite3, datetime, zoneinfo, math, statistics, sys
TZ = zoneinfo.ZoneInfo('America/New_York')
DB = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad/prod-frames.db'
c = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)

def T(hh, mm, ss=0):
    return datetime.datetime(2026, 9, 11, hh, mm, ss, tzinfo=TZ).timestamp()

T0, T1 = T(20, 50), T(22, 0)
rows = c.execute("select ts,move,still,distance_cm,device_occ from frames where sensor_id like 'FD:68%' and ts>=? and ts<? order by ts", (T0, T1)).fetchall()
print('frames', len(rows), 'span', datetime.datetime.fromtimestamp(rows[0][0], TZ).strftime('%H:%M:%S'), datetime.datetime.fromtimestamp(rows[-1][0], TZ).strftime('%H:%M:%S'))
ts = [r[0] for r in rows]
MOVE = [[r[1][g] for r in rows] for g in range(9)]
STILL = [[r[2][g] for r in rows] for g in range(9)]

# gaps
gaps = [(ts[i-1], ts[i]-ts[i-1]) for i in range(1, len(ts)) if ts[i]-ts[i-1] > 1.0]
print('gaps>1s:', [(datetime.datetime.fromtimestamp(a, TZ).strftime('%H:%M:%S'), round(d, 1)) for a, d in gaps][:20])
dts = [ts[i]-ts[i-1] for i in range(1, len(ts))]
print('median dt %.3f' % statistics.median(dts))

WIN = {
 'learn 21:00-21:20': (T(21,0), T(21,20)),
 'EMPTY 21:32-21:39': (T(21,32), T(21,39)),
 'present 21:40-21:55': (T(21,40), T(21,55)),
 'still-min 21:49': (T(21,49), T(21,50)),
}

def emapair(sig, tsv, tau_f, tau_s):
    """returns list of |fast-slow|"""
    f = s = sig[0]
    out = [0.0]
    for i in range(1, len(sig)):
        dt = min(tsv[i]-tsv[i-1], 2.0)
        af = 1-math.exp(-dt/tau_f); a_s = 1-math.exp(-dt/tau_s)
        f += af*(sig[i]-f); s += a_s*(sig[i]-s)
        out.append(abs(f-s))
    return out

def noisefloor(sig, tsv, tau=10.0, order=1, robust=True):
    """running robust mean of |n-th difference|, EMA time constant tau"""
    d = []
    if order == 1:
        d = [(tsv[i], abs(sig[i]-sig[i-1])) for i in range(1, len(sig))]
    elif order == 2:
        d = [(tsv[i], abs(sig[i]-2*sig[i-1]+sig[i-2])/math.sqrt(6)) for i in range(2, len(sig))]
    else:
        d = [(tsv[i], abs(sig[i]-3*sig[i-1]+3*sig[i-2]-sig[i-3])/math.sqrt(20)) for i in range(3, len(sig))]
    fl = d[0][1] if d else 0.0
    out = []
    prev = d[0][0]
    for t, v in d:
        dt = min(t-prev, 2.0); prev = t
        a = 1-math.exp(-dt/tau)
        if robust:
            v = min(v, 4*fl+0.5)     # clip outliers (motion bursts) so floor stays noise-only
        fl += a*(v-fl)
        out.append((t, fl))
    return out

def wslice(pairs, w):
    a, b = w
    return [v for t, v in pairs if a <= t < b]

def wslice_sig(sig, w):
    a, b = w
    return [sig[i] for i in range(len(ts)) if a <= ts[i] < b]

print('\n=== RAW ENERGY levels per gate (median) ===')
print('%-20s %s' % ('window', ' '.join('g%-5d' % g for g in range(9))))
for nm, w in WIN.items():
    for lbl, CH in (('still', STILL), ('move', MOVE)):
        vals = []
        for g in range(9):
            v = wslice_sig(CH[g], w)
            vals.append(statistics.median(v) if v else float('nan'))
        print('%-20s %s   %s' % (nm if lbl == 'still' else '', ' '.join('%-6.1f' % v for v in vals), lbl))

# ---------- 1. slow/fast filter difference ----------
print('\n=== (1) |fastEMA - slowEMA| ; per-window MEDIAN of the statistic ===')
TAUS = [(1.0, 30.0), (2.0, 60.0), (3.0, 90.0)]
for chname, CH in (('STILL', STILL), ('MOVE', MOVE)):
    for tf, tsl in TAUS:
        stats = [list(zip(ts, emapair(CH[g], ts, tf, tsl))) for g in range(9)]
        print('-- %s tau=(%.0f,%.0f)' % (chname, tf, tsl))
        print('   %-20s %s' % ('window', ' '.join('g%-5d' % g for g in range(9))))
        for nm, w in WIN.items():
            vv = []
            for g in range(9):
                s = wslice(stats[g], w)
                vv.append(statistics.median(s) if s else float('nan'))
            print('   %-20s %s' % (nm, ' '.join('%-6.2f' % v for v in vv)))

print('\n=== (1b) per-MINUTE median of |fast-slow| on STILL, tau=(2,60), gates 1..4 ===')
stats = {g: list(zip(ts, emapair(STILL[g], ts, 2.0, 60.0))) for g in range(9)}
mstats = {g: list(zip(ts, emapair(MOVE[g], ts, 2.0, 60.0))) for g in range(9)}
print('min    ' + ' '.join('s_g%d  ' % g for g in (1,2,3,4)) + '| ' + ' '.join('m_g%d  ' % g for g in (1,2,3,4)))
m0 = int(T(20, 55)//60)
m1 = int(T(22, 0)//60)
for m in range(m0, m1):
    w = (m*60, m*60+60)
    row = []
    for g in (1,2,3,4):
        s = wslice(stats[g], w); row.append(statistics.median(s) if s else float('nan'))
    row2 = []
    for g in (1,2,3,4):
        s = wslice(mstats[g], w); row2.append(statistics.median(s) if s else float('nan'))
    if all(math.isnan(x) for x in row):
        continue
    print('%s ' % datetime.datetime.fromtimestamp(m*60, TZ).strftime('%H:%M') + ' '.join('%-6.2f' % v for v in row) + '| ' + ' '.join('%-6.2f' % v for v in row2))

# ---------- 2. noise floor ----------
print('\n=== (2) frame-to-frame noise floor (robust EMA of |diff|, tau=10s) ===')
for order in (1, 2):
    for robust in (True, False):
        fl = {g: noisefloor(STILL[g], ts, 10.0, order, robust) for g in range(9)}
        print('-- STILL order=%d robust=%s' % (order, robust))
        print('   %-20s %s' % ('window', ' '.join('g%-5d' % g for g in range(9))))
        for nm, w in WIN.items():
            vv = []
            for g in range(9):
                s = wslice(fl[g], w)
                vv.append(statistics.median(s) if s else float('nan'))
            print('   %-20s %s' % (nm, ' '.join('%-6.2f' % v for v in vv)))
