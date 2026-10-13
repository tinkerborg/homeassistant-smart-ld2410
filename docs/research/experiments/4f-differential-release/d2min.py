"""Literal window-differential D'' (arming gated by pre/post ratio) -- representative scores."""
import sys
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
from d2run import run_all, sc, line, HDR
from d2s import DPRIME
C=[("D' baseline (4e)",dict(diff_off=True,**DPRIME))]
for held,agg,wpre,wpost,fr in ((False,'rate',30.,25.,0.5),(False,'rate',90.,25.,0.5),
                               (False,'rate',300.,25.,0.5),(False,'mean',90.,25.,0.5),
                               (True,'max',30.,25.,0.5),(True,'max',30.,25.,0.7),
                               (True,'mean',90.,45.,0.6)):
    C.append(('D" %s/%s P%.0f Q%.0f f%.1f'%('held' if held else 'unhl',agg,wpre,wpost,fr),
        dict(diff_held=held,agg=agg,w_pre=wpre,w_post=wpost,excl=5.,frac=fr,**DPRIME)))
print(HDR%('variant','bathREL','maxREL','kitch','emp%','seedREL','fd drops','T5 catdrops','T6 rel','T123456'),flush=True)
for nm,kw in C:
    print(line(nm,sc(run_all(kw,30.),30.)),flush=True)
