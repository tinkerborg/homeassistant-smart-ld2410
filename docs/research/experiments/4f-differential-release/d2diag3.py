"""Verdict trace: every crossing candidate, its pre/post statistic and the ruling."""
import sys
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
from d2s import *
TRUTH={'bath':'empty after 22:06:43','MAX':'empty after 22:06:43','fd':'occupied',
       'fdcat':'OCCUPIED throughout (cat crosses 21:46)','two':'OCCUPIED (far-gate stayer)'}
for agg,w,ex,fr in (('rate',25.,5.,0.5),('rate',30.,5.,0.5),('rate',20.,5.,0.5)):
    print('\n===== agg=%s w=%.0f excl=%.0f frac=%.1f  (un-held signed retention, gates 2-8)'%(agg,w,ex,fr),flush=True)
    for s in ('bath','MAX','fd','fdcat','two'):
        rec,d=go2(s,hold_s=30.,diff_held=False,agg=agg,w_pre=w,w_post=w,excl=ex,frac=fr,**DPRIME)
        tl=[];p=None
        for ts,o,a in rec:
            if p is None: p=o;continue
            if o!=p: tl.append((ts,o));p=o
        print('%-6s %-34s verdicts: %s'%(s,TRUTH[s],
          ' | '.join('%s pre=%.2f post=%.2f %s'%(hm(d.t0+a),pr,po,'COLLAPSE->arm' if c else 'discard')
                     for a,b,pr,po,c in d.verdicts) or '(no crossing candidate)'),flush=True)
        print('       armed=%s  edges=%s'%(hm(next((t for t,o,a in rec if a),0)) if any(a for _,_,a in rec) else 'never',
              [(hm(t),o) for t,o in tl]),flush=True)
