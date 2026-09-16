"""Plateau map for the reset form: clamp_s x tau_peak x ret_on x cross_n."""
import sys, itertools
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
from d3run import sc3, K
from d3 import hm
for hold_s in (30.,60.):
    print('\n== hold %.0f : clamp x tau (T123456)'%hold_s,flush=True)
    for taup in (60.,90.,120.):
        row=[]
        for clamp in (45.,50.,55.,60.,65.,70.,75.,80.,85.,90.):
            o=sc3(dict(clamp_s=clamp,**K),hold_s,taup)
            row.append('%.0f:%s'%(clamp,''.join('.' if o[k] else 'X' for k in ('t1','t2','t3','t4','t5','t6'))))
        print('tau%-4.0f %s'%(taup,'  '.join(row)),flush=True)
print('\n== secondary knobs at tau90 clamp60',flush=True)
for hold_s in (30.,60.):
    for nm,kw in (('ret_on 8',dict(ret_on=8.)),('ret_on 12',{}),('ret_on 20',dict(ret_on=20.)),
                  ('cross_n 10',dict(cross_n=10)),('cross_n 40',dict(cross_n=40)),
                  ('quiet 5',dict(quiet_s=5.)),('quiet 20',dict(quiet_s=20.)),
                  ('grace 60',dict(grace_s=60.))):
        k=dict(K); k.update(kw)
        o=sc3(dict(clamp_s=60.,**k),hold_s,90.)
        print('hold%-3.0f %-11s %s'%(hold_s,nm,''.join('.' if o[x] else 'X' for x in ('t1','t2','t3','t4','t5','t6'))),flush=True)
