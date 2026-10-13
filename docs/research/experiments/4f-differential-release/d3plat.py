"""Fine plateau + what breaks at each edge, tau90."""
import sys
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
from d3run import sc3,K
from d3 import hm
for hold_s in (30.,60.):
    print('\n-- hold %.0f tau90'%hold_s,flush=True)
    for clamp in (56.,58.,60.,62.,64.,66.,68.,70.,72.,74.):
        o=sc3(dict(clamp_s=clamp,**K),hold_s,90.)
        print('clamp%-4.0f %s  bathREL=%s maxREL=%s catdrop=%s'%(clamp,
          ''.join('.' if o[k] else 'X' for k in ('t1','t2','t3','t4','t5','t6')),
          hm(o['b_rel']) if o['b_rel'] else '--', hm(o['m_rel']) if o['m_rel'] else '--',
          ', '.join(hm(t) for t in o['cdrops']) or 'HELD'),flush=True)
