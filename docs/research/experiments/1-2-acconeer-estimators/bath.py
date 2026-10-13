import sqlite3, datetime, zoneinfo, math, statistics
TZ = zoneinfo.ZoneInfo('America/New_York')
DB = '/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad/prod-frames.db'
c = sqlite3.connect('file:%s?mode=ro' % DB, uri=True)
def T(h, m, s=0): return datetime.datetime(2026, 9, 11, h, m, s, tzinfo=TZ).timestamp()
def hm(t): return datetime.datetime.fromtimestamp(t, TZ).strftime('%H:%M:%S')

# preroll 5 min so EMAs/floor are warm at 05:00
rows = c.execute("select ts,move,still from frames where sensor_id like 'D0:6E%' and ts>=? and ts<? order by ts", (T(4,55), T(6,0))).fetchall()
ts = [r[0] for r in rows]; N = len(ts)
STILL = [[r[2][g] for r in rows] for g in range(9)]
MOVE = [[r[1][g] for r in rows] for g in range(9)]
print('frames %d  %s -> %s' % (N, hm(ts[0]), hm(ts[-1])))
gaps = [(ts[i-1], ts[i]-ts[i-1]) for i in range(1, N) if ts[i]-ts[i-1] > 2.0]
print('gaps>2s:', [(hm(a), round(d,1)) for a, d in gaps][:15])

TAU_F, TAU_S, FLOOR_MIN = 2.0, 60.0, 0.10
f = [STILL[g][0] for g in range(9)]; s = list(f); flE = [0.3]*9
stat = [[0.0]*9 for _ in range(N)]; FE = [[0.3]*9 for _ in range(N)]
for i in range(1, N):
    dt = min(ts[i]-ts[i-1], 2.0)
    af = 1-math.exp(-dt/TAU_F); a_s = 1-math.exp(-dt/TAU_S); a10 = 1-math.exp(-dt/10.)
    for g in range(9):
        x = STILL[g][i]
        f[g] += af*(x-f[g]); s[g] += a_s*(x-s[g]); stat[i][g] = abs(f[g]-s[g])
        dc = min(abs(x-STILL[g][i-1]), 4*flE[g]+0.5)
        flE[g] += a10*(dc-flE[g]); FE[i][g] = flE[g]
GATES = range(0, 4)
def sc(i, gs=GATES): return max(stat[i][g]/max(FE[i][g], FLOOR_MIN) for g in gs)

def replay(ON=20., OFF=10., ONH=1.5, OFFH=20.0, t0=T(5,0)):
    occ=False; ab=bl=None; out=[]
    for i in range(N):
        if ts[i] < t0: continue
        v = sc(i)
        if v >= ON: bl=None; ab = ab or ts[i]
        elif v < OFF: ab=None; bl = bl or ts[i]
        else: ab=bl=None; continue
        if not occ and ab and ts[i]-ab >= ONH: occ=True; out.append((ts[i],'occupied'))
        if occ and bl and ts[i]-bl >= OFFH: occ=False; out.append((ts[i],'vacant'))
    return out
tl = replay()
print('\n=== TOY detector (still, tau 2/60, EMA10 floor, gates0-3, ON20/OFF10, off-hold 20s) ===')
if not tl: print('   (no transitions; stayed vacant all hour)')
prev=None
for t,k in tl:
    print('   %s %s' % (hm(t), k) + (('   [occupied %.0fs]' % (t-prev)) if k=='vacant' and prev else ''))
    prev = t if k=='occupied' else prev
print('\n=== REAL detector events 05:00-06:00 ===')
ev = c.execute("select ts_utc,kind,payload from events where sensor_id like 'D0:6E%' and ts_utc>=? and ts_utc<? order by ts_utc",(T(5,0),T(6,0))).fetchall()
if not ev: print('   (none)')
for t,k,p in ev: print('   %s %-9s %s' % (hm(t), k, (p or '')[:90]))

print('\n=== per-minute MEDIAN of stat/floor, gates 0-8 (05:00-06:00) ===')
print('min    g0    g1    g2    g3   | g4    g5    g6    g7    g8    max0-3')
for m in range(int(T(5,0)//60), int(T(6,0)//60)):
    idx = [i for i in range(N) if m*60 <= ts[i] < m*60+60]
    if not idx: continue
    def q(g):
        v = sorted(stat[i][g]/max(FE[i][g],FLOOR_MIN) for i in idx); return v[len(v)//2]
    row=[q(g) for g in range(9)]
    mx = sorted(sc(i) for i in idx)[len(idx)//2]
    flag = '  <<' if mx >= 10 else ''
    print('%s %s| %s %-6.1f%s' % (datetime.datetime.fromtimestamp(m*60,TZ).strftime('%H:%M'),
        ' '.join('%-5.1f'%x for x in row[:4]), ' '.join('%-5.1f'%x for x in row[4:]), mx, flag))

print('\n=== raw energies (median) per minute for active minutes, still | move ===')
print('min    s0  s1  s2  s3  s4  s5 | m0  m1  m2  m3  m4  m5')
for m in range(int(T(5,0)//60), int(T(6,0)//60)):
    idx = [i for i in range(N) if m*60 <= ts[i] < m*60+60]
    if not idx: continue
    if sorted(sc(i) for i in idx)[len(idx)//2] < 10: continue
    st = [statistics.median([STILL[g][i] for i in idx]) for g in range(6)]
    mv = [statistics.median([MOVE[g][i] for i in idx]) for g in range(6)]
    print('%s %s| %s' % (datetime.datetime.fromtimestamp(m*60,TZ).strftime('%H:%M'),
        ' '.join('%-3.0f'%x for x in st), ' '.join('%-3.0f'%x for x in mv)))
print('\nbaseline still medians 05:00-06:00 per gate:',
      [round(statistics.median([STILL[g][i] for i in range(N) if ts[i]>=T(5,0)]),1) for g in range(9)])
