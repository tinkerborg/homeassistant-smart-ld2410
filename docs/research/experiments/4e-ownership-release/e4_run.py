"""4e: signed-retention ownership refresh, scored against T1-T4."""
import sqlite3, sys, math, collections
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
from rel import *  # noqa
from custom_components.smart_ld2410.algo.detector import Detector

TAU_F,TAU_S,FLOOR_MIN=2.0,60.0,0.10
class SRet:
    """acc3 statistic split by sign; `pos` = decayed peak-hold of the POSITIVE part."""
    def __init__(s,st0,taup=60.0,signed=True):
        s.f=list(map(float,st0)); s.s=list(s.f); s.fl=[0.3]*9
        s.prev=list(map(float,st0)); s.pt=None; s.out=[0.0]*9
        s.taup=taup; s.signed=signed
    def add(s,ts,st):
        dt=2.0 if s.pt is None else min(max(ts-s.pt,0.0),2.0); s.pt=ts
        af=1-math.exp(-dt/TAU_F); a_s=1-math.exp(-dt/TAU_S); a10=1-math.exp(-dt/10.)
        dk=math.exp(-dt/s.taup) if s.taup>0 else 0.0
        for g in range(9):
            x=float(st[g]); s.f[g]+=af*(x-s.f[g]); s.s[g]+=a_s*(x-s.s[g])
            dc=min(abs(x-s.prev[g]),4*s.fl[g]+0.5); s.fl[g]+=a10*(dc-s.fl[g])
            d=(s.f[g]-s.s[g])/max(s.fl[g],FLOOR_MIN)
            v=max(d,0.0) if s.signed else abs(d)
            s.out[g]=max(s.out[g]*dk,v)
        s.prev=[float(v) for v in st]
        return s.out

class C4c(Composite):
    def _advance(self,score,ts_mono,*,entry_suppressed=False):
        ls=self.lead_sup
        if not self._occupied and (ls is None or ls>self.lead_max): entry_suppressed=True
        Detector._advance(self,score,ts_mono,entry_suppressed=entry_suppressed)

# ------------------------------------------------------------------ data
W0,W1=T(21,58),T(22,10); WARM0=W0-6*3600.0; K0,K1=T(5,11),T(5,23)
ARRIVE,DEPART=T(22,4,1),T(22,6,43)
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
LEFT,BACK=T(21,20),T(21,39,40)

def go(warm,body,*,mode='S',hold_s=30.0,taup=60.0,signed=True,seed=False,**kw):
    cfg=DetectorConfig(hold_s=hold_s)
    if mode=='shipped': d=Detector(cfg)
    elif mode=='4c':    d=C4c(cfg,**kw)
    else:               d=C4c(cfg,**kw)
    ret=SRet(warm[0][2],taup,signed); t0=warm[0][0]; rec=[]
    for ts,mv,st in warm:
        ret.add(ts,st)
        if mode!='shipped': d.ret=ret.out
        d.process(Frame(ts,ts-t0,tuple(mv),tuple(st),0,False))
    if seed:
        d._occupied=True; d._hold_until_mono=None
        if mode!='shipped':
            d.occ_gates={2,3}; d._occ_start=body[0][0]-t0
            d._last_near=body[0][0]-t0; d._last_far=None
    for ts,mv,st in body:
        ret.add(ts,st)
        if mode!='shipped': d.ret=ret.out
        o=d.process(Frame(ts,ts-t0,tuple(mv),tuple(st),0,False))
        rec.append((ts,o.occupied,o.score))
    return d,rec

def rel_after(rec,t):
    was=None
    for ts,o,_ in rec:
        if ts<t: was=o; continue
        if was and not o: return ts
        was=o
    return None

def score(vname,kw,hold_s=30.0):
    R={}
    for s in ('bath','MAX','kitchen'):
        d,rec=go(warmD,MIX[s],hold_s=hold_s,**kw); R[s]=(edges(rec),rec)
    # T2 bath
    tlb=R['bath'][0]; eb=next((t for t,o in tlb if o),None); rb=rel_after(R['bath'][1],DEPART)
    early_b=next((t for t,o in tlb if not o and ARRIVE<t<DEPART),None)
    # T1 MAX
    tlm=R['MAX'][0]; em=next((t for t,o in tlm if o),None); rm=rel_after(R['MAX'][1],ARRIVE)
    early_m=next((t for t,o in tlm if not o and ARRIVE<t<DEPART),None)
    # T3 kitchen
    ek=next((t for t,o in R['kitchen'][0] if o),None)
    # T4 FD:68 natural
    d,rec=go(warmF,bodyF,hold_s=hold_s,**kw); tl=edges(rec)
    ent=next((t for t,o in tl if o and t>=BACK-20),None)
    drops=[t for t,o in tl if not o and T(21,40,30)<=t<T(21,55)]
    emptyocc=100.*sum(1 for ts,o,_ in rec if T(21,22)<=ts<T(21,39) and o)/max(
        sum(1 for ts,o,_ in rec if T(21,22)<=ts<T(21,39)),1)
    # T4b seeded departure
    d2,rec2=go(warmF,[r for r in bodyF if r[0]<T(21,39)],hold_s=hold_s,seed=True,**kw)
    srel=next((ts for ts,o,_ in rec2 if not o),None)
    return dict(b_ent=eb,b_rel=rb,b_early=early_b,m_ent=em,m_rel=rm,m_early=early_m,
                k_ent=ek,f_ent=ent,f_drops=drops,f_empty=emptyocc,f_seedrel=srel)

def V(x): return hm(x) if x else '--'
VARIANTS=[
 ('shipped',                dict(mode='shipped')),
 ('4c entry-only',          dict(mode='4c')),
 ('A g60 (4d best)',        dict(grace_s=60.)),
 ('A g90',                  dict(grace_s=90.)),
 ('c |f-s| g60 r20',        dict(grace_s=60.,use_ret=True,ret_on=20.,form='c',ret_all=True,signed=False,taup=0.)),
]
for taup in (30.,60.,90.):
  for ron in (3.,5.,8.,12.,20.):
    for gr in (30.,60.,90.):
        VARIANTS.append(('S t%.0f r%-2.0f g%-2.0f'%(taup,ron,gr),
            dict(grace_s=gr,use_ret=True,ret_on=ron,form='c',ret_all=True,signed=True,taup=taup)))

print('T1 MAX: ent 22:04:01 rel 22:06:43-22:07:13 | T2 bath: ent 22:04:01 rel 22:06:43 | T3 kitchen never'
      ' | T4 fd ent ~21:40, 0 drops, seedrel 21:19-21:21, empty 0%%')
print('%-18s %-9s %-9s %-9s %-9s %-8s | %-9s %-6s %-9s %s'%(
   'variant','bathENT','bathREL','maxENT','maxREL','kitchEN','fdENT','emp%','seedREL','fd drops 21:40-21:55'))
best=[]
for nm,kw in VARIANTS:
    r=score(nm,kw)
    ok1 = r['m_ent']==ARRIVE and r['m_early'] is None and r['m_rel'] and DEPART<=r['m_rel']<=DEPART+35
    ok2 = r['b_ent']==ARRIVE and r['b_early'] is None and r['b_rel']==DEPART
    ok3 = r['k_ent'] is None
    ok4 = (r['f_ent'] is not None and abs(r['f_ent']-BACK)<=60 and not r['f_drops']
           and r['f_empty']<1.0 and r['f_seedrel'] and T(21,19)<=r['f_seedrel']<=T(21,21,30))
    tag=''.join('.' if x else 'X' for x in (ok1,ok2,ok3,ok4))
    if tag=='....': best.append(nm)
    print('%-18s %-9s %-9s %-9s %-9s %-8s | %-9s %-6.1f %-9s %-22s %s'%(
      nm,V(r['b_ent']),(V(r['b_early'])+'!') if r['b_early'] else V(r['b_rel']),
      V(r['m_ent']),(V(r['m_early'])+'!') if r['m_early'] else V(r['m_rel']),
      V(r['k_ent']) if r['k_ent'] else 'NEVER',
      V(r['f_ent']),r['f_empty'],V(r['f_seedrel']),
      ', '.join(hm(t) for t in r['f_drops']) or 'none',tag))
print('\nPASS ALL FOUR:',best or 'NONE')
