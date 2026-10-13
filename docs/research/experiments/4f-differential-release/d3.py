"""D''-reset: a near-band crossing CLEARS the peak-held retention instead of arming.
Presence must then re-prove itself from zero (the differential, measured against a
reset baseline instead of a motion-contaminated pre-window).  No new knobs: reuses
ret_on / tau_peak.  Release otherwise identical to 4d form-c (retention decay).
"""
import sys, collections, copy
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
from d2s import *     # STREAM (incl. fdcat/two), SRet, CD, CD2, DPRIME, T, hm, ...

class CD3(CD):
    """crossing -> reset retention peak (and keep it clamped while the crossing runs)."""
    clamp_s=5.0        # keep clearing until near activity has been gone this long
    reset_mode=True
    def __init__(s,*a,**k):
        super().__init__(*a,**k); s.retobj=None; s.crossings=[]; s._clamp_until=None
    def _advance(s,score,ts_mono,*,entry_suppressed=False):
        cfg=s._config; ls=s.lead_sup
        near = ls is not None and ls<=s.near_max
        if near: s._last_near=ts_mono
        if not s._occupied:
            if ls is None or ls>s.lead_max: entry_suppressed=True
            if score>=cfg.enter_score and not entry_suppressed:
                s._occupied=True; s._hold_until_mono=None
                s.occ_gates=set(s._cur_active); s._occ_start=ts_mono
                s.armed=False; s.qgap=False; s._nearq=collections.deque(); s._clamp_until=None
            return
        q=s._nearq
        if near: q.append(ts_mono)
        while q and ts_mono-q[0]>s.cross_win: q.popleft()
        if not s.qgap:
            if s._last_near is None or ts_mono-s._last_near>=s.quiet_s:
                s.qgap=True; q.clear()
        elif len(q)>=s.cross_n and (ts_mono-s._occ_start)>=s.guard_s:
            s.crossings.append(ts_mono)
            s.qgap=False; q.clear()
            s._clamp_until=ts_mono            # start clamping; extended while near persists
        # clamp: zero the held retention through the crossing and clamp_s beyond it
        if s._clamp_until is not None:
            if near: s._clamp_until=ts_mono
            if ts_mono-s._clamp_until<=s.clamp_s:
                if s.reset_mode and s.retobj is not None:
                    for g in range(9): s.retobj.out[g]=0.0
            else:
                s._clamp_until=None
                s.qgap=True; q.clear()      # the next burst is a fresh crossing
        near_recent=near or (s._last_near is not None and ts_mono-s._last_near<=s.grace_s)
        gates=set(range(2,9)) if s.ret_all else (s.occ_gates or set(range(9)))
        ret_hi=max(s.ret[g] for g in gates)>=s.ret_on
        block=(score>=cfg.exit_score and near_recent) or ret_hi
        if block: s._hold_until_mono=None
        elif s._hold_until_mono is None: s._hold_until_mono=ts_mono+cfg.hold_s
        elif ts_mono>=s._hold_until_mono:
            s._occupied=False; s._hold_until_mono=None
            s._freeze_until_mono=ts_mono+cfg.freeze_hold_s

W3={}
def wdet3(sn,taup):
    k=(sn,taup)
    if k not in W3:
        warm=STREAM[sn][0]; d=CD3(DetectorConfig(hold_s=30.)); t0=warm[0][0]
        r=SRet(warm[0][2],taup); d.retobj=r
        for ts,mv,st in warm:
            r.add(ts,st); d.ret=r.out
            d.process(Frame(ts,ts-t0,tuple(mv),tuple(st),0,False))
        W3[k]=(d,t0,r)
    d,t0,r=W3[k]; d2=copy.deepcopy(d); r2=copy.deepcopy(r); d2.retobj=r2
    return d2,t0,r2

def go3(sname,*,hold_s=30.,taup=90.,seed=False,**kw):
    warm,body=STREAM[sname]
    d,t0,r=wdet3(sname,taup); d._config=DetectorConfig(hold_s=hold_s)
    for a,v in kw.items(): setattr(d,a,v)
    d.armed=False; d.qgap=False; d._nearq=collections.deque(); d.crossings=[]; d._clamp_until=None
    if seed:
        d._occupied=True; d._hold_until_mono=None; d.occ_gates={2,3}
        d._occ_start=body[0][0]-t0; d._last_near=None; d.qgap=True
    rec=[]
    for ts,mv,st in body:
        r.add(ts,st); d.ret=r.out
        o=d.process(Frame(ts,ts-t0,tuple(mv),tuple(st),0,False))
        rec.append((ts,o.occupied,bool(d.crossings)))
    d.t0=t0
    return rec,d
