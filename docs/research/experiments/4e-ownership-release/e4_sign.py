"""SIGNED retention: is (fast-slow) one-sidedly NEGATIVE after a departure and
two-sided during a still occupant / neighbour?"""
import sqlite3, sys, math
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
from rel import *  # noqa

TAU_F,TAU_S,FLOOR_MIN=2.0,60.0,0.10
class SRet:
    def __init__(s,st0):
        s.f=list(map(float,st0)); s.s=list(s.f); s.fl=[0.3]*9
        s.prev=list(map(float,st0)); s.pt=None; s.sig=[0.0]*9
        s.pos=[0.0]*9; s.neg=[0.0]*9   # decayed peak-hold of each sign, tau 15s
    def add(s,ts,st):
        dt=2.0 if s.pt is None else min(max(ts-s.pt,0.0),2.0); s.pt=ts
        af=1-math.exp(-dt/TAU_F); a_s=1-math.exp(-dt/TAU_S); a10=1-math.exp(-dt/10.)
        dk=math.exp(-dt/15.0)
        for g in range(9):
            x=float(st[g]); s.f[g]+=af*(x-s.f[g]); s.s[g]+=a_s*(x-s.s[g])
            dc=min(abs(x-s.prev[g]),4*s.fl[g]+0.5); s.fl[g]+=a10*(dc-s.fl[g])
            v=(s.f[g]-s.s[g])/max(s.fl[g],FLOOR_MIN); s.sig[g]=v
            s.pos[g]=max(s.pos[g]*dk,max(v,0.0)); s.neg[g]=max(s.neg[g]*dk,max(-v,0.0))
        s.prev=[float(v) for v in st]
        return s.sig

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
fdr=[(r[0],list(r[1]),list(r[2])) for r in cf.execute("select ts,move,still from frames order by ts")]
SPLIT=T(21,11); warmF=[r for r in fdr if r[0]<SPLIT]; bodyF=[r for r in fdr if r[0]>=SPLIT]
def tr(warm,rows):
    r=SRet(warm[0][2]); out=[]
    for ts,mv,st in warm: r.add(ts,st)
    for ts,mv,st in rows: r.add(ts,st); out.append((ts,list(r.sig),list(r.pos),list(r.neg)))
    return out
TR={k:tr(warmD,MIX[k]) for k in MIX}; TR['FD68']=tr(warmF,bodyF)
G={'bath':range(1,5),'MAX':range(1,5),'kitchen':range(1,5),'FD68':range(2,7)}
WINS=[('bath','post-dep 22:06:13-22:06:43 DECIDE',T(22,6,13),T(22,6,43),'REL'),
      ('bath','post-dep 22:06:43-22:07:30',T(22,6,43),T(22,7,30),'REL'),
      ('bath','post-dep 22:07:30-22:09:00',T(22,7,30),T(22,9),'REL'),
      ('MAX','post-dep 22:06:13-22:06:43 DECIDE',T(22,6,13),T(22,6,43),'REL'),
      ('MAX','post-dep 22:06:43-22:07:30',T(22,6,43),T(22,7,30),'REL'),
      ('MAX','post-dep 22:07:30-22:09:00',T(22,7,30),T(22,9),'REL'),
      ('kitchen','neighbour 22:06:43-22:09',T(22,6,43),T(22,9),'REL'),
      ('FD68','seeded occ 21:12-21:19',T(21,12),T(21,19),'HOLD'),
      ('FD68','true exit 21:20-21:22 DECIDE',T(21,20),T(21,22),'REL'),
      ('FD68','EMPTY 21:22-21:29',T(21,22),T(21,29),'REL'),
      ('FD68','EMPTY+cat 21:30-21:36',T(21,30),T(21,36),'REL'),
      ('FD68','SEATED quiet 21:47:40-21:50 CRIT',T(21,47,40),T(21,50),'HOLD'),
      ('FD68','SEATED 21:41-21:55',T(21,41),T(21,55),'HOLD')]
def med(v): v=sorted(v); return v[len(v)//2] if v else 0.
print('%-8s %-36s %-5s %8s %8s %8s %8s %8s'%('stream','window','want','|f-s|','POSpk','NEGpk','pos/neg','pos>20%'))
for k,lbl,a,b,want in WINS:
    sel=[r for r in TR[k] if a<=r[0]<b]; gs=list(G[k])
    A=med([max(abs(x[1][g]) for g in gs) for x in sel])
    P=med([max(x[2][g] for g in gs) for x in sel])
    Ng=med([max(x[3][g] for g in gs) for x in sel])
    frac=100.*sum(1 for x in sel if max(x[2][g] for g in gs)>=20)/max(len(sel),1)
    print('%-8s %-36s %-5s %8.1f %8.1f %8.1f %8.2f %7.0f%%'%(k,lbl,want,A,P,Ng,P/max(Ng,.01),frac))
