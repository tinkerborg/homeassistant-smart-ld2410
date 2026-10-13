"""What statistic separates 'room still occupied at far gates' from 'empty + residue'
in the 30-60 s AFTER a near-band crossing?  Dump candidate stats per stream."""
import sys, math
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
from d2s import *

TRUTH={'bath':'EMPTY after','MAX':'EMPTY after','fdcat':'OCCUPIED after','two':'OCCUPIED after'}
class Probe(CD2):
    def __init__(s,*a,**k):
        super().__init__(*a,**k); s.tr=[]
    def _advance(s,score,ts,*,entry_suppressed=False):
        gates=range(2,9)
        s.tr.append((ts,max(s.ret[g] for g in gates),max(s.ret_u[g] for g in gates),
                     s.lead_sup, score))
        super()._advance(score,ts,entry_suppressed=entry_suppressed)

import d2
d2.CD2_orig=CD2
def run(sname,hold_s=30.):
    warm,body=STREAM[sname]
    d=Probe(DetectorConfig(hold_s=hold_s))
    t0=warm[0][0]; r=SRet(warm[0][2],90.); ru=SRet(warm[0][2],0.0)
    for k,v in DPRIME.items(): setattr(d,k,v)
    for ts,mv,st in warm:
        r.add(ts,st); ru.add(ts,st); d.ret=r.out; d.ret_u=ru.out
        d.process(Frame(ts,ts-t0,tuple(mv),tuple(st),0,False))
    d.tr=[]
    for ts,mv,st in body:
        r.add(ts,st); ru.add(ts,st); d.ret=r.out; d.ret_u=ru.out
        d.process(Frame(ts,ts-t0,tuple(mv),tuple(st),0,False))
    return d,t0

CROSS={'bath':T(22,6,20),'MAX':T(22,6,20),'fdcat':T(21,46,10),'two':T(22,6,20)}
print('%-6s %-14s | %-28s | %-28s'%('stream','truth','PRE  (held / unheld frac>thr)','POST'))
for s in ('bath','MAX','fdcat','two'):
    d,t0=run(s)
    tr=[(t0+t,h,u,ls,sc) for t,h,u,ls,sc in d.tr]
    tc=CROSS[s]
    # burst extent: near frames within +-40s of tc
    nb=[t for t,h,u,ls,sc in tr if ls is not None and ls<=1 and tc-40<=t<=tc+60]
    b0,b1=(min(nb),max(nb)) if nb else (tc,tc)
    def stat(a,b):
        w=[(t,h,u) for t,h,u,ls,sc in tr if a<=t<=b]
        if not w: return None
        hs=[h for _,h,_ in w]; us=[u for _,_,u in w]
        return dict(n=len(w),h_end=hs[-1],h_max=max(hs),u_max=max(us),u_mean=sum(us)/len(us),
                    f12=sum(1 for u in us if u>=12)/len(us),
                    f50=sum(1 for u in us if u>=50)/len(us),
                    f200=sum(1 for u in us if u>=200)/len(us))
    for lbl,(a,b) in (('pre ',(b0-35,b0-5)),('post',(b1+5,b1+35)),('post2',(b1+5,b1+65))):
        st=stat(a,b)
        print('%-6s %-14s %-5s %s -> h_end=%.0f h_max=%.0f u_max=%.0f u_mean=%.0f f12=%.2f f50=%.2f f200=%.2f'%(
            s,TRUTH[s],lbl,'%s..%s'%(hm(a),hm(b)),st['h_end'],st['h_max'],st['u_max'],st['u_mean'],st['f12'],st['f50'],st['f200']))
    print()
