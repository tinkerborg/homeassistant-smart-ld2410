"""Battery of candidate hold statistics across every window that must be ordered."""
import sqlite3, sys, math, statistics
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
from rel import *  # noqa
from lead import Model as LeadModel, GATES

W0,W1=T(21,58),T(22,10); WARM0=W0-6*3600.0; K0,K1=T(5,11),T(5,23)
c=sqlite3.connect('file:%s?mode=ro'%PROD,uri=True)
def fetch(a,b):
    return [(r[0],list(r[1]),list(r[2])) for r in c.execute(
      "select ts,move,still from frames where sensor_id like 'D0:6E%' and ts>=? and ts<? order by ts",(a,b))]
warmD=fetch(WARM0,W0); bath=fetch(W0,W1); kit=fetch(K0,K1); n=min(len(bath),len(kit))
MIX={'bath':bath[:n],'kitchen':[(bath[i][0],kit[i][1],kit[i][2]) for i in range(n)],
     'MAX':[(bath[i][0],[max(bath[i][1][g],kit[i][1][g]) for g in range(9)],
             [max(bath[i][2][g],kit[i][2][g]) for g in range(9)]) for i in range(n)]}
cf=sqlite3.connect('file:%s?mode=ro'%FIX,uri=True)
fd=[(r[0],list(r[1]),list(r[2])) for r in cf.execute("select ts,move,still from frames order by ts")]
SPLIT=T(21,11); warmF=[r for r in fd if r[0]<SPLIT]; bodyF=[r for r in fd if r[0]>=SPLIT]

def stats(warm,rows):
    """per-frame: still residual (baseline model), its slow EMA, |f-s|/floor retention."""
    m=LeadModel(); ret=Retention(warm[0][2])
    slow=[0.0]*9; prev=None; out=[]
    for src,keep in ((warm,False),(rows,True)):
        for ts,mv,st in src:
            r=ret.add(ts,st)
            rs=[0.0]*9
            if m.ready:
                rm,rs=m.res(mv,st)
            dt=2.0 if prev is None else min(max(ts-prev,0.0),2.0); prev=ts
            a=1-math.exp(-dt/30.0)
            for g in range(9): slow[g]+=a*(rs[g]-slow[g])
            if keep: out.append((ts,list(rs),list(slow),list(r),list(st)))
            m.add(ts,mv,st)
    return out

TR={k:stats(warmD,MIX[k]) for k in MIX}; TR['FD68']=stats(warmF,bodyF)
WINS=[('bath','OCCUPIED 22:04:20-22:06:13',T(22,4,20),T(22,6,13),'HOLD'),
      ('bath','post-departure 22:06:43-22:07:15',T(22,6,43),T(22,7,15),'REL'),
      ('bath','post-departure 22:07:15-22:08:30',T(22,7,15),T(22,8,30),'REL'),
      ('MAX','OCCUPIED 22:04:20-22:06:13',T(22,4,20),T(22,6,13),'HOLD'),
      ('MAX','post-dep NEIGHBOUR 22:06:43-22:07:15',T(22,6,43),T(22,7,15),'REL'),
      ('MAX','post-dep NEIGHBOUR 22:07:15-22:08:30',T(22,7,15),T(22,8,30),'REL'),
      ('kitchen','neighbour only 22:06:43-22:08:30',T(22,6,43),T(22,8,30),'REL'),
      ('FD68','occupant seeded 21:12-21:19',T(21,12),T(21,19),'HOLD'),
      ('FD68','EMPTY 21:22-21:29',T(21,22),T(21,29),'REL'),
      ('FD68','EMPTY+cat 21:30-21:36',T(21,30),T(21,36),'REL'),
      ('FD68','SEATED 21:41-21:55',T(21,41),T(21,55),'HOLD'),
      ('FD68','SEATED still 21:49-21:50',T(21,49),T(21,50),'HOLD')]
def med(v): 
    v=sorted(v); return v[len(v)//2] if v else 0.0
G={'bath':range(1,5),'MAX':range(1,5),'kitchen':range(1,5),'FD68':range(2,7)}
print('%-8s %-34s %-5s %8s %8s %8s %8s %8s'%('stream','window','want','ret|f-s|','stillRes','slowRes30','rawStill','p90Res'))
for k,lbl,a,b,want in WINS:
    sel=[r for r in TR[k] if a<=r[0]<b]
    gs=list(G[k])
    print('%-8s %-34s %-5s %8.1f %8.2f %8.2f %8.1f %8.2f'%(k,lbl,want,
      med([max(x[3][g] for g in gs) for x in sel]),
      med([max(x[1][g] for g in gs) for x in sel]),
      med([max(x[2][g] for g in gs) for x in sel]),
      med([max(x[4][g] for g in gs) for x in sel]),
      sorted([max(x[1][g] for g in gs) for x in sel])[int(.9*len(sel))]))
