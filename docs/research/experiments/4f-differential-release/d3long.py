"""Long-tail cost: bathroom occupancy fraction 21:58-23:30 under D' vs reset-D''."""
import sys, sqlite3, collections
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
from d3 import *
from d3run import K
from d2s import DPRIME
from d2 import go2
c=sqlite3.connect('file:%s?mode=ro'%PROD,uri=True)
def f(a,b):
    return [(r[0],list(r[1]),list(r[2])) for r in c.execute(
      "select ts,move,still from frames where sensor_id like 'D0:6E%' and ts>=? and ts<? order by ts",(a,b))]
STREAM['bathlong']=(f(T(21,58)-6*3600,T(21,58)), f(T(21,58),T(23,30)))
for hold in (30.,60.):
    rec,d=go2('bathlong',hold_s=hold,diff_off=True,**DPRIME)
    occ=100.*sum(1 for _,o,_ in rec if o)/len(rec)
    rel=next((ts for i,(ts,o,_) in enumerate(rec) if i and not o and rec[i-1][1]),None)
    print("hold%-3.0f D'          release %-9s occupied %.1f%% of 21:58-23:30 (truth 2.9%%)"%(
        hold,hm(rel) if rel else 'NEVER',occ),flush=True)
    rec,d=go3('bathlong',hold_s=hold,taup=90.,clamp_s=60.,**K)
    occ=100.*sum(1 for _,o,_ in rec if o)/len(rec)
    rel=next((ts for i,(ts,o,_) in enumerate(rec) if i and not o and rec[i-1][1]),None)
    print('hold%-3.0f D" reset    release %-9s occupied %.1f%%'%(hold,hm(rel) if rel else 'NEVER',occ),flush=True)
