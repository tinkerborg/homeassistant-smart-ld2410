import sys
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
from d2s import *
print('%-6s %-5s %-4s %-4s | verdicts (pre/post/ratio)'%('stream','agg','wpre','wpost'))
for agg in ('rate','mean','max'):
  for wpre in (30.,60.,90.,120.,180.,300.):
    for wpost in (25.,45.):
      for s in ('bath','fdcat','two'):
        rec,d=go2(s,hold_s=30.,diff_held=False,agg=agg,w_pre=wpre,w_post=wpost,excl=5.,frac=0.5,**DPRIME)
        print('%-6s %-5s %-4.0f %-4.0f | %s'%(s,agg,wpre,wpost,
          ' | '.join('%s pre=%.3f post=%.3f r=%.2f'%(hm(d.t0+a),p,q,(q/p if p else 9.99))
                     for a,b,p,q,c in d.verdicts) or '(none)'),flush=True)
