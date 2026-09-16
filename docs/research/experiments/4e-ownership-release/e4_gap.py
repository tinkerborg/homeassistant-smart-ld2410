import sqlite3, sys, math
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
from rel import *  # noqa
TAU_F,TAU_S,FLOOR_MIN=2.0,60.0,0.10
class SRet:
    def __init__(s,st0,taup):
        s.f=list(map(float,st0)); s.s=list(s.f); s.fl=[0.3]*9
        s.prev=list(map(float,st0)); s.pt=None; s.pos=[0.0]*9; s.taup=taup
    def add(s,ts,st):
        dt=2.0 if s.pt is None else min(max(ts-s.pt,0.0),2.0); s.pt=ts
        af=1-math.exp(-dt/TAU_F); a_s=1-math.exp(-dt/TAU_S); a10=1-math.exp(-dt/10.)
        dk=math.exp(-dt/s.taup)
        for g in range(9):
            x=float(st[g]); s.f[g]+=af*(x-s.f[g]); s.s[g]+=a_s*(x-s.s[g])
            dc=min(abs(x-s.prev[g]),4*s.fl[g]+0.5); s.fl[g]+=a10*(dc-s.fl[g])
            v=(s.f[g]-s.s[g])/max(s.fl[g],FLOOR_MIN)
            s.pos[g]=max(s.pos[g]*dk,max(v,0.0))
        s.prev=[float(v) for v in st]
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
G={'bath':range(1,5),'MAX':range(1,5),'kitchen':range(1,5),'FD68':range(2,7)}
WINS=[('bath','post-dep 22:06:13-22:09:00',T(22,6,13),T(22,9),'REL'),
      ('MAX','post-dep 22:06:13-22:09:00',T(22,6,13),T(22,9),'REL'),
      ('kitchen','neighbour 22:00-22:09',T(22,0),T(22,9),'REL'),
      ('FD68','seeded occ 21:12-21:19 HOLD',T(21,12),T(21,19),'HOLD'),
      ('FD68','true exit 21:20-21:29 REL',T(21,20),T(21,29),'REL'),
      ('FD68','SEATED 21:41-21:55 HOLD',T(21,41),T(21,55),'HOLD')]
for taup in (0.001,2.0,5.0,10.0):
    print('\n== peak-hold tau=%.0fs  -- longest gap (s) with POS < thr =='%taup)
    TR={}
    for k,(warm,rows) in {'bath':(warmD,MIX['bath']),'kitchen':(warmD,MIX['kitchen']),
                          'MAX':(warmD,MIX['MAX']),'FD68':(warmF,bodyF)}.items():
        r=SRet(warm[0][2],taup); out=[]
        for ts,mv,st in warm: r.add(ts,st)
        for ts,mv,st in rows: r.add(ts,st); out.append((ts,list(r.pos)))
        TR[k]=out
    print('%-8s %-30s %-5s %s'%('stream','window','want',' '.join('thr%-4d'%t for t in (3,5,8,12,20,30))))
    for k,lbl,a,b,want in WINS:
        sel=[x for x in TR[k] if a<=x[0]<b]; gs=list(G[k]); cells=[]
        for thr in (3,5,8,12,20,30):
            best=0.0; st=None
            for ts,p in sel:
                if max(p[g] for g in gs)<thr:
                    st=ts if st is None else st; best=max(best,ts-st)
                else: st=None
            cells.append('%-7.0f'%best)
        print('%-8s %-30s %-5s %s'%(k,lbl,want,' '.join(cells)))
