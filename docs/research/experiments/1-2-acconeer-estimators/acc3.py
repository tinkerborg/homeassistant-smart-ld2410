import sqlite3, datetime, zoneinfo, math, statistics
TZ = zoneinfo.ZoneInfo('America/New_York')
DB = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad/prod-frames.db'
c = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
def T(h, m, s=0): return datetime.datetime(2026, 9, 11, h, m, s, tzinfo=TZ).timestamp()
def hm(t): return datetime.datetime.fromtimestamp(t, TZ).strftime('%H:%M:%S')
rows = c.execute("select ts,move,still from frames where sensor_id like 'FD:68%' and ts>=? and ts<? order by ts", (T(20,50), T(22,0))).fetchall()
ts = [r[0] for r in rows]; N = len(ts)
STILL = [[r[2][g] for r in rows] for g in range(9)]

TAU_F, TAU_S = 2.0, 60.0
f = [STILL[g][0] for g in range(9)]; s = list(f)
flE = [0.3]*9; flM = [0.3]*9
stat = [[0.0]*9 for _ in range(N)]; FE = [[0.3]*9 for _ in range(N)]; FM = [[0.3]*9 for _ in range(N)]
for i in range(1, N):
    dt = min(ts[i]-ts[i-1], 2.0)
    af = 1-math.exp(-dt/TAU_F); a_s = 1-math.exp(-dt/TAU_S); a10 = 1-math.exp(-dt/10.)
    aup = 1-math.exp(-dt/600.); adn = 1-math.exp(-dt/30.)
    for g in range(9):
        x = STILL[g][i]
        f[g] += af*(x-f[g]); s[g] += a_s*(x-s[g]); stat[i][g] = abs(f[g]-s[g])
        dc = min(abs(x-STILL[g][i-1]), 4*flE[g]+0.5)
        flE[g] += a10*(dc-flE[g])
        flM[g] += (adn if dc < flM[g] else aup)*(dc-flM[g])
        FE[i][g] = flE[g]; FM[i][g] = flM[g]

FLOOR_MIN = 0.10
def sc(i, F, gates): return max(stat[i][g]/max(F[i][g], FLOOR_MIN) for g in gates)

def replay(F, gates, ON, OFF, ONH=1.5, OFFH=20.0, t_start=None):
    occ = False; ab = bl = None; out = []
    for i in range(N):
        if ts[i] < t_start: continue
        v = sc(i, F, gates)
        if v >= ON:
            bl = None; ab = ab or ts[i]
            if not occ and ts[i]-ab >= ONH: occ = True; out.append((ts[i], 'occupied'))
        elif v < OFF:
            ab = None; bl = bl or ts[i]
            if occ and ts[i]-bl >= OFFH: occ = False; out.append((ts[i], 'vacant'))
        else: ab = bl = None
    return out

def occ_at(tl, t, init=False):
    st = init
    for tt, k in tl:
        if tt <= t: st = (k == 'occupied')
        else: break
    return st

START = T(21,5,10)
CONF = [('EMA10 floor, gates1-8', FE, range(1,9), 6.0, 3.0),
        ('EMA10 floor, gates2-3', FE, range(2,4), 6.0, 3.0),
        ('MINTRK floor, gates2-3', FM, range(2,4), 25.0, 12.0)]
for nm, F, gts, ON, OFF in CONF:
    tl = replay(F, gts, ON, OFF, t_start=START)
    print('=== toy detector: %s  ON=%.0f OFF=%.0f ===' % (nm, ON, OFF))
    for t, k in tl: print('   %s %s' % (hm(t), k))
    # metrics
    empty = [i for i in range(N) if T(21,32) <= ts[i] < T(21,39)]
    seat  = [i for i in range(N) if T(21,40) <= ts[i] < T(21,55)]
    fo = sum(1 for i in empty if occ_at(tl, ts[i], True))/max(len(empty),1)
    fd = sum(1 for i in seat if not occ_at(tl, ts[i], True))/max(len(seat),1)
    drops = sum(1 for t, k in tl if k == 'vacant' and T(21,40) <= t < T(21,55))
    print('   false-occupied frac in EMPTY 21:32-21:39: %.1f%% | false-vacant frac while SEATED 21:40-21:55: %.1f%% (%d drop events)\n' % (100*fo, 100*fd, drops))

print('=== per-minute score  max_g(stat/floor) with EMA10 floor ===')
print('min    all1-8  g2    g3    g4    g5    g6    g7')
for m in range(int(T(21,5)//60), int(T(21,52)//60)):
    idx = [i for i in range(N) if m*60 <= ts[i] < m*60+60]
    if not idx: continue
    def q(gs):
        v = sorted(sc(i, FE, gs) for i in idx); return v[len(v)//2]
    print('%s %-7.1f %s' % (datetime.datetime.fromtimestamp(m*60, TZ).strftime('%H:%M'), q(range(1,9)),
          ' '.join('%-5.1f' % q([g]) for g in (2,3,4,5,6,7))))
