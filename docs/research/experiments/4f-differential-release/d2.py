"""4f: differential release (D"). Crossing arms ONLY if held presence collapsed with it.

Builds on 4e D' (CD in e4_dep.py). New machinery:
  * a second, UN-HELD signed retention stat (taup=0) alongside the peak-held one
  * a crossing becomes a PENDING candidate; pre = agg(signal) over
    [burst_start-excl-w_pre, burst_start-excl], post = agg over
    [last_near+excl, +w_post].  collapsed = pre<ret_on (nothing held) or post<frac*pre
  * collapsed -> armed (D' semantics resume).  not collapsed -> crossing discarded,
    qgap reset (a fresh quiet gap is required before another candidate).
  * while pending the detector arms PROVISIONALLY (so the hold countdown is not
    delayed by w_post) but the release FLIP is deferred until the verdict.
"""
import sys, collections, copy, itertools
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S); sys.path.insert(0,S+'/pinned')
import custom_components.smart_ld2410.algo.detector as _det
assert _det.__file__.startswith(S), _det.__file__
exec(open(S+'/e4_dep.py').read().split("print('%-26s")[0])   # SRet, CD, STREAM, T, hm, ...

DPRIME = dict(grace_s=90., use_ret=True, ret_on=12., ret_all=True, near_max=1, lead_max=1,
              cross_n=20, cross_win=20., quiet_s=10., guard_s=0.)

class CD2(CD):
    """D'' : differential (collapse-gated) arming."""
    w_pre=25.0; w_post=25.0; excl=5.0; frac=0.5
    diff_held=False      # False -> un-held signed retention drives the collapse test
    agg='max'            # 'max' | 'mean'
    prov=True            # provisional arming while a candidate is pending
    diff_off=False       # True -> behave exactly like D' (baseline)

    def __init__(self,*a,**k):
        super().__init__(*a,**k)
        self.ret_u=[0.0]*9          # un-held signed retention
        self.hist=collections.deque()
        self.pending=None
        self.verdicts=[]
        self._burst0=None

    def _sig(self):
        gates=set(range(2,9)) if self.ret_all else (self.occ_gates or set(range(9)))
        src=self.ret if self.diff_held else self.ret_u
        return max(src[g] for g in gates)

    min_pre=0.02          # 'rate': pre-rate below this == nothing was being held
    def _agg(self,vals):
        if not vals: return 0.0
        if self.agg=='max': return max(vals)
        if self.agg=='mean': return sum(vals)/len(vals)
        # 'rate': fraction of the window whose signal is live (>= ret_on)
        return sum(1 for v in vals if v>=self.ret_on)/len(vals)

    def _win(self,a,b):
        return [v for t,v in self.hist if a<=t<=b]

    def _advance(self,score,ts_mono,*,entry_suppressed=False):
        cfg=self._config; ls=self.lead_sup
        near = ls is not None and ls<=self.near_max
        if near: self._last_near=ts_mono
        self.hist.append((ts_mono,self._sig()))
        horizon=self.w_pre+self.w_post+self.excl*2+self.cross_win+10.
        while self.hist and ts_mono-self.hist[0][0]>horizon: self.hist.popleft()
        if not self._occupied:
            if ls is None or ls>self.lead_max: entry_suppressed=True
            if score>=cfg.enter_score and not entry_suppressed:
                self._occupied=True; self._hold_until_mono=None
                self.occ_gates=set(self._cur_active); self._occ_start=ts_mono
                self.armed=False; self.qgap=False; self._nearq=collections.deque()
                self.pending=None; self._burst0=None
            return
        q=self._nearq
        if near:
            q.append(ts_mono)
            if self.qgap and self._burst0 is None: self._burst0=ts_mono
        while q and ts_mono-q[0]>self.cross_win: q.popleft()
        if not self.qgap:
            if self._last_near is None or ts_mono-self._last_near>=self.quiet_s:
                self.qgap=True; q.clear(); self._burst0=None
        elif not self.armed and self.pending is None and len(q)>=self.cross_n \
                and (ts_mono-self._occ_start)>=self.guard_s:
            if self.diff_off:
                self.armed=True
            else:
                b0=self._burst0 if self._burst0 is not None else q[0]
                pre=self._agg(self._win(b0-self.excl-self.w_pre,b0-self.excl))
                self.pending=dict(pre=pre,t_c=ts_mono,ps=None,post=[])
        p=self.pending
        if p is not None:
            if near:
                p['ps']=None; p['post']=[]
            elif p['ps'] is None:
                if self._last_near is not None and ts_mono-self._last_near>=self.excl:
                    p['ps']=ts_mono
            else:
                p['post'].append(self._sig())
                if ts_mono-p['ps']>=self.w_post:
                    post=self._agg(p['post'])
                    floor=self.min_pre if self.agg=='rate' else self.ret_on
                    coll=(p['pre']<floor) or (post<self.frac*p['pre'])
                    self.verdicts.append((p['t_c'],ts_mono,p['pre'],post,coll))
                    if coll: self.armed=True
                    else:
                        self.qgap=False; self._nearq.clear()
                    self.pending=None; p=None
        armed_eff=self.armed or (p is not None and self.prov)
        near_recent=near or (self._last_near is not None and ts_mono-self._last_near<=self.grace_s)
        gates=set(range(2,9)) if self.ret_all else (self.occ_gates or set(range(9)))
        ret_hi=max(self.ret[g] for g in gates)>=self.ret_on
        block=(score>=cfg.exit_score and near_recent) or (ret_hi and not armed_eff)
        if block: self._hold_until_mono=None
        elif self._hold_until_mono is None: self._hold_until_mono=ts_mono+cfg.hold_s
        elif ts_mono>=self._hold_until_mono:
            if p is not None: return          # defer the flip until the verdict
            self._occupied=False; self._hold_until_mono=None
            self._freeze_until_mono=ts_mono+cfg.freeze_hold_s

# ---------------- runner (warm caches keyed per stream) ----------------
WD2={}; WR2={}
def wdet2(s):
    if s not in WD2:
        warm=STREAM[s][0]; d=CD2(DetectorConfig(hold_s=30.)); t0=warm[0][0]
        r=SRet(warm[0][2],90.); ru=SRet(warm[0][2],0.0)
        for ts,mv,st in warm:
            r.add(ts,st); ru.add(ts,st); d.ret=r.out; d.ret_u=ru.out
            d.process(Frame(ts,ts-t0,tuple(mv),tuple(st),0,False))
        WD2[s]=(d,t0,r,ru)
    d,t0,r,ru=WD2[s]
    return copy.deepcopy(d),t0,copy.deepcopy(r),copy.deepcopy(ru)

def go2(sname,*,hold_s=30.,seed=False,**kw):
    warm,body=STREAM[sname]
    d,t0,r,ru=wdet2(sname); d._config=DetectorConfig(hold_s=hold_s)
    for a,v in kw.items(): setattr(d,a,v)
    d.armed=False; d.qgap=False; d._nearq=collections.deque(); d.pending=None; d.verdicts=[]
    if seed:
        d._occupied=True; d._hold_until_mono=None; d.occ_gates={2,3}
        d._occ_start=body[0][0]-t0; d._last_near=None; d.qgap=True
    rec=[]
    for ts,mv,st in body:
        r.add(ts,st); ru.add(ts,st); d.ret=r.out; d.ret_u=ru.out
        o=d.process(Frame(ts,ts-t0,tuple(mv),tuple(st),0,False))
        rec.append((ts,o.occupied,d.armed))
    d.t0=t0
    return rec,d
