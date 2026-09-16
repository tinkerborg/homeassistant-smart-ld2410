"""4e variant D: departure-armed ownership.
 - qualifying entry -> ownership, occ_gates.
 - while NOT armed: signed retention (POS) refreshes hold  => stillness never releases.
 - a post-entry NEAR-BAND CROSSING (>=cross_n near-lead frames within cross_win, after
   near activity had been quiet >= quiet_s) ARMS departure: the occupant may have left
   through the gates they entered by.
 - once armed: only attributed evidence (score>=exit AND near-lead within grace) refreshes;
   the neighbour, which can never light the near band, cannot hold the door.
"""
import sqlite3, sys, math, copy, itertools, collections
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
from rel import *  # noqa
from custom_components.smart_ld2410.algo.detector import Detector
TAU_F,TAU_S,FLOOR_MIN=2.0,60.0,0.10
class SRet:
    def __init__(s,st0,taup=90.0,signed=True):
        s.f=list(map(float,st0)); s.s=list(s.f); s.fl=[0.3]*9
        s.prev=list(map(float,st0)); s.pt=None; s.out=[0.0]*9; s.taup=taup; s.signed=signed
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
class CD(Composite):
    cross_n=20; cross_win=20.0; quiet_s=20.0; guard_s=0.0; armed=False; qgap=False
    def __init__(self,*a,**k):
        super().__init__(*a,**k); self._nearq=collections.deque()
    def _advance(self,score,ts_mono,*,entry_suppressed=False):
        cfg=self._config; ls=self.lead_sup
        near=ls is not None and ls<=self.near_max
        if near: self._last_near=ts_mono
        if not self._occupied:
            if ls is None or ls>self.lead_max: entry_suppressed=True
            if score>=cfg.enter_score and not entry_suppressed:
                self._occupied=True; self._hold_until_mono=None
                self.occ_gates=set(self._cur_active); self._occ_start=ts_mono
                self.armed=False; self.qgap=False; self._nearq=collections.deque()
            return
        # --- near-crossing detector
        q=self._nearq
        if near: q.append(ts_mono)
        while q and ts_mono-q[0]>self.cross_win: q.popleft()
        if not self.qgap:
            if self._last_near is None or ts_mono-self._last_near>=self.quiet_s:
                self.qgap=True; q.clear()
        elif len(q)>=self.cross_n and (ts_mono-self._occ_start)>=self.guard_s:
            self.armed=True
        near_recent=near or (self._last_near is not None and ts_mono-self._last_near<=self.grace_s)
        gates=set(range(2,9)) if self.ret_all else (self.occ_gates or set(range(9)))
        ret_hi=max(self.ret[g] for g in gates)>=self.ret_on
        block=(score>=cfg.exit_score and near_recent) or (ret_hi and not self.armed)
        if block: self._hold_until_mono=None
        elif self._hold_until_mono is None: self._hold_until_mono=ts_mono+cfg.hold_s
        elif ts_mono>=self._hold_until_mono:
            self._occupied=False; self._hold_until_mono=None
            self._freeze_until_mono=ts_mono+cfg.freeze_hold_s
# ---------------- data
W0,W1=T(21,58),T(22,10); WARM0=W0-6*3600.0; K0,K1=T(5,11),T(5,23)
ARRIVE,DEPART=T(22,4,1),T(22,6,43); BACK=T(21,39,40)
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
WD={}; WR={}
def wdet(s):
    if s not in WD:
        warm=STREAM[s][0]; d=CD(DetectorConfig(hold_s=30.)); t0=warm[0][0]
        for ts,mv,st in warm: d.process(Frame(ts,ts-t0,tuple(mv),tuple(st),0,False))
        WD[s]=(d,t0)
    d,t0=WD[s]; return copy.deepcopy(d),t0
def wret(s,taup):
    k=(s,taup)
    if k not in WR:
        warm=STREAM[s][0]; r=SRet(warm[0][2],taup)
        for ts,mv,st in warm: r.add(ts,st)
        WR[k]=r
    return copy.deepcopy(WR[k])
def go(sname,*,hold_s=30.,taup=90.,seed=False,**kw):
    warm,body=STREAM[sname]; d,t0=wdet(sname); d._config=DetectorConfig(hold_s=hold_s)
    for a,v in kw.items(): setattr(d,a,v)
    d.armed=False; d.qgap=False; d._nearq=collections.deque()
    ret=wret(sname,taup); rec=[]
    if seed:
        d._occupied=True; d._hold_until_mono=None; d.occ_gates={2,3}
        d._occ_start=body[0][0]-t0; d._last_near=None; d.qgap=True
    for ts,mv,st in body:
        ret.add(ts,st); d.ret=ret.out
        o=d.process(Frame(ts,ts-t0,tuple(mv),tuple(st),0,False))
        rec.append((ts,o.occupied,d.armed))
    return rec
def rel_after(rec,t):
    was=None
    for ts,o,_ in rec:
        if ts<t: was=o; continue
        if was and not o: return ts
        was=o
    return None
def V(x): return hm(x) if x else '--'
def ed(rec): 
    tl=[];p=None
    for ts,o,_ in rec:
        if p is None: p=o; continue
        if o!=p: tl.append((ts,o)); p=o
    return tl
print('%-26s %-9s %-9s %-9s %-9s %-7s | %-9s %-5s %-9s %-22s %s'%(
 'variant','bathENT','bathREL','maxENT','maxREL','kitch','fdENT','emp%','seedREL','fd drops','T1234'),flush=True)
best=[]
for taup,ron,gr,gd in itertools.product((60.,90.),(8.,12.,20.),(60.,90.),(0.,30.,40.,45.,50.,60.,75.)):
    cn,qs=10,10.
    kw=dict(grace_s=gr,use_ret=True,ret_on=ron,ret_all=True,near_max=1,lead_max=1,
            cross_n=cn,cross_win=20.,quiet_s=qs,guard_s=gd)
    rb=go('bath',taup=taup,**kw); rm=go('MAX',taup=taup,**kw); rk=go('kitchen',taup=taup,**kw)
    tlb=ed(rb); tlm=ed(rm)
    b_ent=next((t for t,o in tlb if o),None); b_rel=rel_after(rb,DEPART)
    b_e=next((t for t,o in tlb if not o and ARRIVE<t<DEPART),None)
    m_ent=next((t for t,o in tlm if o),None); m_rel=rel_after(rm,ARRIVE)
    m_e=next((t for t,o in tlm if not o and ARRIVE<t<DEPART),None)
    k_ent=next((t for t,o in ed(rk) if o),None)
    rf=go('fd',taup=taup,**kw); tlf=ed(rf)
    f_ent=next((t for t,o in tlf if o and t>=BACK-20),None)
    drops=[t for t,o in tlf if not o and T(21,40,30)<=t<T(21,55)]
    den=[1 for ts,o,_ in rf if T(21,22)<=ts<T(21,39)]
    emp=100.*sum(1 for ts,o,_ in rf if T(21,22)<=ts<T(21,39) and o)/max(len(den),1)
    rs=go('fdseed',taup=taup,seed=True,**kw)
    srel=next((ts for ts,o,_ in rs if not o),None)
    ok1=m_ent==ARRIVE and m_e is None and m_rel and DEPART<=m_rel<=DEPART+35
    ok2=b_ent==ARRIVE and b_e is None and b_rel==DEPART
    ok3=k_ent is None
    ok4=(f_ent is not None and abs(f_ent-BACK)<=60 and not drops and emp<1.0
         and srel and T(21,19)<=srel<=T(21,21,30))
    tag=''.join('.' if x else 'X' for x in (ok1,ok2,ok3,ok4))
    nm='D t%.0f r%-2.0f g%-2.0f guard%-3.0f'%(taup,ron,gr,gd)
    if tag=='....': best.append(nm)
    print('%-26s %-9s %-9s %-9s %-9s %-7s | %-9s %-5.1f %-9s %-22s %s'%(
      nm,V(b_ent),(V(b_e)+'!') if b_e else V(b_rel),V(m_ent),(V(m_e)+'!') if m_e else V(m_rel),
      V(k_ent) if k_ent else 'NEVER',V(f_ent),emp,V(srel),
      ', '.join(hm(t) for t in drops) or 'none',tag),flush=True)
print('\nPASS ALL FOUR:',best or 'NONE',flush=True)
