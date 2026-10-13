import sqlite3, datetime, zoneinfo, math, statistics
TZ = zoneinfo.ZoneInfo('America/New_York')
DB = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad/prod-frames.db'
c = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
def T(hh, mm, ss=0):
    return datetime.datetime(2026, 9, 11, hh, mm, ss, tzinfo=TZ).timestamp()
def hm(t): return datetime.datetime.fromtimestamp(t, TZ).strftime('%H:%M:%S')

rows = c.execute("select ts,move,still from frames where sensor_id like 'FD:68%' and ts>=? and ts<? order by ts", (T(20,50), T(22,0))).fetchall()
ts = [r[0] for r in rows]
MOVE = [[r[1][g] for r in rows] for g in range(9)]
STILL = [[r[2][g] for r in rows] for g in range(9)]
N = len(ts)

# how quantized is the stream?
print('=== frame-to-frame change rate (STILL) ===')
for g in (2,3,4,5,6):
    d = [abs(STILL[g][i]-STILL[g][i-1]) for i in range(1,N)]
    nz = sum(1 for x in d if x)
    print(' g%d: %.1f%% of frames change; mean|d|=%.3f  max|d|=%d' % (g, 100*nz/len(d), sum(d)/len(d), max(d)))

# ---- statistic + floors, streamed together ----
TAU_F, TAU_S = 2.0, 60.0
def run():
    f = [STILL[g][0] for g in range(9)]; s = list(f)
    fl_fast = [0.3]*9      # 10s robust EMA of |diff|   (technique 2 as specified)
    fl_min  = [0.3]*9      # asymmetric min-tracking floor (fast down, very slow up)
    stat = [[0.0]*9 for _ in range(N)]
    FF = [[0.0]*9 for _ in range(N)]
    FM = [[0.0]*9 for _ in range(N)]
    for i in range(1, N):
        dt = min(ts[i]-ts[i-1], 2.0)
        af = 1-math.exp(-dt/TAU_F); a_s = 1-math.exp(-dt/TAU_S)
        a10 = 1-math.exp(-dt/10.0)
        aup = 1-math.exp(-dt/600.0); adn = 1-math.exp(-dt/30.0)
        for g in range(9):
            x = STILL[g][i]
            f[g] += af*(x-f[g]); s[g] += a_s*(x-s[g])
            stat[i][g] = abs(f[g]-s[g])
            d = abs(x-STILL[g][i-1])
            dc = min(d, 4*fl_fast[g]+0.5)
            fl_fast[g] += a10*(dc-fl_fast[g])
            a = adn if dc < fl_min[g] else aup
            fl_min[g] += a*(dc-fl_min[g])
            FF[i][g] = fl_fast[g]; FM[i][g] = fl_min[g]
    return stat, FF, FM
stat, FF, FM = run()

WIN = {'learn 21:04-21:20': (T(21,4,40), T(21,20)), 'EMPTY 21:32-21:39': (T(21,32), T(21,39)),
       'present 21:40-21:55': (T(21,40), T(21,55)), 'still-min 21:49': (T(21,49), T(21,50))}
def med(arr, w, g):
    v = [arr[i][g] for i in range(N) if w[0] <= ts[i] < w[1]]
    return statistics.median(v) if v else float('nan')

print('\n=== (2b) floor comparison: 10s-robust-EMA vs asymmetric min-tracking ===')
for nm, A in (('EMA10', FF), ('MINTRK', FM)):
    print('-- %s' % nm)
    print('   %-20s %s' % ('window', ' '.join('g%-5d' % g for g in range(9))))
    for wn, w in WIN.items():
        print('   %-20s %s' % (wn, ' '.join('%-6.3f' % med(A, w, g) for g in range(9))))

# ---- (3) toy detector ----
HUM = range(1, 9)
def score(i, F):
    vals = sorted((stat[i][g]/max(F[i][g], 0.08) for g in HUM), reverse=True)
    return vals[0], max(HUM, key=lambda g: stat[i][g]/max(F[i][g], 0.08))

def replay(F, ON=12.0, OFF=6.0, ON_HOLD=1.5, OFF_HOLD=20.0):
    occ = False; above = None; below = None; out = []
    for i in range(N):
        if ts[i] < T(21,4,40)+30: continue   # 30s warm-up after power-cycle
        sc, gmax = score(i, F)
        if sc >= ON:
            below = None
            if above is None: above = ts[i]
            if not occ and ts[i]-above >= ON_HOLD:
                occ = True; out.append((ts[i], 'occupied', gmax, sc))
        elif sc < OFF:
            above = None
            if below is None: below = ts[i]
            if occ and ts[i]-below >= OFF_HOLD:
                occ = False; out.append((ts[i], 'vacant', gmax, sc))
        else:
            above = below = None
    return out

for nm, F in (('EMA10 floor', FF), ('MINTRK floor', FM)):
    tl = replay(F)
    print('\n=== (3) toy detector timeline [%s] ===' % nm)
    for t, k, g, sc in tl:
        print('   %s %-8s (peak gate %d, score %.1f)' % (hm(t), k, g, sc))

# per-minute score table
print('\n=== per-minute score = max_g stat/floor  (MINTRK floor); gate = argmax ===')
print('min    p50   p10   argmax-gate(mode)   | g2sc  g3sc  g4sc  g5sc  g6sc')
m0, m1 = int(T(21,4)//60), int(T(21,52)//60)
for m in range(m0, m1):
    w = (m*60, m*60+60)
    idx = [i for i in range(N) if w[0] <= ts[i] < w[1]]
    if not idx: continue
    ss = sorted(score(i, FM)[0] for i in idx)
    gg = [score(i, FM)[1] for i in idx]
    mode = max(set(gg), key=gg.count)
    per = []
    for g in (2,3,4,5,6):
        v = sorted(stat[i][g]/max(FM[i][g], 0.08) for i in idx)
        per.append(v[len(v)//2])
    print('%s %-5.1f %-5.1f g%-17d| %s' % (datetime.datetime.fromtimestamp(m*60, TZ).strftime('%H:%M'),
          ss[len(ss)//2], ss[len(ss)//10], mode, ' '.join('%-5.1f' % x for x in per)))

# actual detector events in window
print('\n=== real detector events 21:04-22:00 ===')
for r in c.execute("select ts_utc,kind from events where sensor_id like 'FD:68%' and ts_utc>=? and kind in ('occupied','vacant') order by ts_utc", (T(21,4),)):
    print('   %s %s' % (hm(r[0]), r[1]))
