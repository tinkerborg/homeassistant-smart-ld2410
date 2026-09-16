"""4e (fast): warm-state cached. Signed-retention ownership refresh vs T1-T4."""
import sqlite3, sys, math, copy, itertools
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
from rel import *  # noqa
from custom_components.smart_ld2410.algo.detector import Detector
TAU_F,TAU_S,FLOOR_MIN=2.0,60.0,0.10
class SRet:
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
            s.out[g]=max(s.out[g]*dk,max(d,0.0) if s.signed else abs(d))
        s.prev=[float(v) for v in st]
        return s.out
class C4c(Composite):
    def _advance(self,score,ts_mono,*,entry_suppressed=False):
        ls=self.lead_sup
        if not self._occupied and (ls is None or ls>self.lead_max): entry_suppressed=True
        Detector._advance(self,score,ts_mono,entry_suppressed=entry_suppressed)
W0,W1=T(21,58),T(22,10); WARM0=W0-6*3600.0; K0,K1=T(5,11),T(5,23)
ARRIVE,DEPART=T(22,4,1),T(22,6,43); LEFT,BACK=T(21,20),T(21,39,40)
c=sqlite3.connect('file:%s?mode=ro'%PROD,uri=True)
def fetch(a,b):
    return [(r[0],list(r[1]),list(r[2])) for r in c.execute(
      "select ts,move,still from frames where sensor_id like 'D0:6E%' and ts>=? and ts<? order by ts",(a,b))]
warmD=fetch(WARM0,W0); bath=fetch(W0,W1); kit=fetch(K0,K1); n=min(len(bath),len(kit))
STREAM={'bath':(warmD,bath[:n]),
        'kitchen':(warmD,[(bath[i][0],kit[i][1],kit[i][2]) for i in range(n)]),
        'MAX':(warmD,[(bath[i][0],[max(bath[i][1][g],kit[i][1][g]) for g in range(9)],
                       [max(bath[i][2][g],kit[i][2][g]) for g in range(9)]) for i in range(n)])}
cf=sqlite3.connect('file:%s?mode=ro'%FIX,uri=True)
fdr=[(r[0],list(r[1]),list(r[2])) for r in cf.execute("select ts,move,still from frames order by ts")]
SPLIT=T(21,11); STREAM['fd']=([r for r in fdr if r[0]<SPLIT],[r for r in fdr if r[0]>=SPLIT])
STREAM['fdseed']=(STREAM['fd'][0],[r for r in STREAM['fd'][1] if r[0]<T(21,39)])

# --------- cache warmed detector + retention state per (stream, mode) / (stream,taup,signed)
WARMD={}; WARMR={}
def warmed_det(sname,mode):
    k=(sname,mode)
    if k not in WARMD:
        warm=STREAM[sname][0]; cfg=DetectorConfig(hold_s=30.)
        d=Detector(cfg) if mode=='shipped' else (C4c(cfg) if mode=='4c' else Composite(cfg))
        t0=warm[0][0]
        for ts,mv,st in warm: d.process(Frame(ts,ts-t0,tuple(mv),tuple(st),0,False))
        WARMD[k]=(d,t0)
    d,t0=WARMD[k]; return copy.deepcopy(d),t0
def warmed_ret(sname,taup,signed):
    k=(sname,taup,signed)
    if k not in WARMR:
        warm=STREAM[sname][0]; r=SRet(warm[0][2],taup,signed)
        for ts,mv,st in warm: r.add(ts,st)
        WARMR[k]=r
    return copy.deepcopy(WARMR[k])
def go(sname,*,mode='S',hold_s=30.,taup=60.,signed=True,seed=False,**kw):
    warm,body=STREAM[sname]
    d,t0=warmed_det(sname,mode if mode in ('shipped','4c') else 'S')
    d._config=DetectorConfig(hold_s=hold_s)
    if mode!='shipped':
        for a,v in kw.items(): setattr(d,a,v)
    ret=warmed_ret(sname,taup,signed)
    if seed:
        d._occupied=True; d._hold_until_mono=None
        if mode!='shipped':
            d.occ_gates={2,3}; d._occ_start=body[0][0]-t0
            d._last_near=body[0][0]-t0; d._last_far=None
    rec=[]
    for ts,mv,st in body:
        ret.add(ts,st)
        if mode!='shipped': d.ret=ret.out
        o=d.process(Frame(ts,ts-t0,tuple(mv),tuple(st),0,False))
        rec.append((ts,o.occupied,o.score))
    return rec
def rel_after(rec,t):
    was=None
    for ts,o,_ in rec:
        if ts<t: was=o; continue
        if was and not o: return ts
        was=o
    return None
def V(x): return hm(x) if x else '--'
def score(kw):
    out={}
    for s in ('bath','MAX','kitchen'): out[s]=go(s,**kw)
    tlb=edges(out['bath']); tlm=edges(out['MAX'])
    r=dict(b_ent=next((t for t,o in tlb if o),None), b_rel=rel_after(out['bath'],DEPART),
           b_early=next((t for t,o in tlb if not o and ARRIVE<t<DEPART),None),
           m_ent=next((t for t,o in tlm if o),None), m_rel=rel_after(out['MAX'],ARRIVE),
           m_early=next((t for t,o in tlm if not o and ARRIVE<t<DEPART),None),
           k_ent=next((t for t,o in edges(out['kitchen']) if o),None))
    rec=go('fd',**kw); tl=edges(rec)
    r['f_ent']=next((t for t,o in tl if o and t>=BACK-20),None)
    r['f_drops']=[t for t,o in tl if not o and T(21,40,30)<=t<T(21,55)]
    den=[1 for ts,o,_ in rec if T(21,22)<=ts<T(21,39)]
    r['f_empty']=100.*sum(1 for ts,o,_ in rec if T(21,22)<=ts<T(21,39) and o)/max(len(den),1)
    rec2=go('fdseed',seed=True,**kw)
    r['f_seedrel']=next((ts for ts,o,_ in rec2 if not o),None)
    return r
VAR=[('shipped',dict(mode='shipped')),('4c entry-only',dict(mode='4c')),
     ('A g60 (4d)',dict(grace_s=60.)),('A g90',dict(grace_s=90.)),
     ('c |f-s| g60 r20',dict(grace_s=60.,use_ret=True,ret_on=20.,form='c',ret_all=True,signed=False,taup=0.))]
for taup,ron,gr in itertools.product((30.,60.,90.),(3.,5.,8.,12.,20.),(30.,60.,90.)):
    VAR.append(('S t%.0f r%-2.0f g%-2.0f'%(taup,ron,gr),
        dict(grace_s=gr,use_ret=True,ret_on=ron,form='c',ret_all=True,signed=True,taup=taup)))
print('%-18s %-9s %-9s %-9s %-9s %-7s | %-9s %-5s %-9s %-24s %s'%(
  'variant','bathENT','bathREL','maxENT','maxREL','kitch','fdENT','emp%','seedREL','fd drops 21:40-21:55','T1234'),flush=True)
best=[]
for nm,kw in VAR:
    r=score(kw)
    ok1=r['m_ent']==ARRIVE and r['m_early'] is None and r['m_rel'] and DEPART<=r['m_rel']<=DEPART+35
    ok2=r['b_ent']==ARRIVE and r['b_early'] is None and r['b_rel']==DEPART
    ok3=r['k_ent'] is None
    ok4=(r['f_ent'] is not None and abs(r['f_ent']-BACK)<=60 and not r['f_drops'] and r['f_empty']<1.0
         and r['f_seedrel'] and T(21,19)<=r['f_seedrel']<=T(21,21,30))
    tag=''.join('.' if x else 'X' for x in (ok1,ok2,ok3,ok4))
    if tag=='....': best.append(nm)
    print('%-18s %-9s %-9s %-9s %-9s %-7s | %-9s %-5.1f %-9s %-24s %s'%(
      nm,V(r['b_ent']),(V(r['b_early'])+'!') if r['b_early'] else V(r['b_rel']),
      V(r['m_ent']),(V(r['m_early'])+'!') if r['m_early'] else V(r['m_rel']),
      V(r['k_ent']) if r['k_ent'] else 'NEVER',V(r['f_ent']),r['f_empty'],V(r['f_seedrel']),
      ', '.join(hm(t) for t in r['f_drops']) or 'none',tag),flush=True)
print('\nPASS ALL FOUR:',best or 'NONE',flush=True)
