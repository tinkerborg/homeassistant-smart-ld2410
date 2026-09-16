"""Is a far-lead frame separable by NEAR-BAND SUPPORT (gates 0-1)?"""
import sqlite3, sys, collections, math
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
from rel import *  # noqa
from lead import Model as LeadModel, leading_suppressed, leading_raw, K, GATES, SUPPORT_TAU

def leadtrace(warm,rows):
    m=LeadModel(); sup=[0.0]*GATES; prev=None; out=[]
    for src,keep in ((warm,False),(rows,True)):
        for ts,mv,st in src:
            if m.ready:
                rm,rs=m.res(mv,st); pk=[max(0.0,rm[g],rs[g]) for g in range(GATES)]
                a=1.0 if prev is None else (1.0-math.exp(-min(ts-prev,2.0)/SUPPORT_TAU) if ts>prev else 0.0)
                for g in range(GATES): sup[g]+=a*(pk[g]-sup[g])
                if keep:
                    ls,_=leading_suppressed(rm,sup)
                    out.append((ts,ls,max(sup[0],sup[1]),max(rm[0],rm[1]),tuple(rm)))
            elif keep: out.append((ts,None,0.0,0.0,tuple([0]*9)))
            prev=ts; m.add(ts,mv,st)
    return out

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

TR={k:leadtrace(warmD,MIX[k]) for k in MIX}
TR['FD68']=leadtrace(warmF,bodyF)

WINS=[('bath','GENUINE hold/still 22:05:20-22:06:43',T(22,5,20),T(22,6,43)),
      ('bath','post-departure 22:06:43-22:08:30',T(22,6,43),T(22,8,30)),
      ('MAX','GENUINE visit 22:04:01-22:06:13',T(22,4,1),T(22,6,13)),
      ('MAX','post-departure NEIGHBOUR 22:06:13-22:08:30',T(22,6,13),T(22,8,30)),
      ('kitchen','neighbour only 22:00-22:09',T(22,0),T(22,9)),
      ('FD68','seeded occ 21:11-21:19 (occupant present)',T(21,11),T(21,19)),
      ('FD68','EMPTY 21:22-21:29',T(21,22),T(21,29)),
      ('FD68','EMPTY+cat 21:30-21:36',T(21,30),T(21,36)),
      ('FD68','SEATED 21:41-21:55',T(21,41),T(21,55)),
      ('FD68','SEATED still minute 21:49-21:50',T(21,49),T(21,50)),
     ]
print('%-8s %-42s %6s %7s %7s | far-lead frames split by near-band support sup01'%('stream','window','n','far%','near%'))
print('%-8s %-42s %6s %7s %7s | %s'%('','','','','',' '.join('sup01>=%.1f'%t for t in (1.0,2.0,3.0,4.5))))
for k,lbl,a,b in WINS:
    sel=[r for r in TR[k] if a<=r[0]<b]
    if not sel: continue
    far=[r for r in sel if r[1] is not None and r[1]>=2]
    near=[r for r in sel if r[1] is not None and r[1]<=1]
    cols=[]
    for thr in (1.0,2.0,3.0,4.5):
        cols.append('%5.1f%%'%(100.0*sum(1 for r in far if r[2]>=thr)/max(len(far),1)))
    print('%-8s %-42s %6d %6.1f%% %6.1f%% | %s  (far n=%d, med sup01 far=%.2f all=%.2f)'%(
       k,lbl,len(sel),100.0*len(far)/len(sel),100.0*len(near)/len(sel),' '.join(cols),len(far),
       sorted(r[2] for r in far)[len(far)//2] if far else -1,
       sorted(r[2] for r in sel)[len(sel)//2]))
