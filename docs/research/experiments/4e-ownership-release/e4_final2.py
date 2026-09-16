"""D' : arming queue reset at the quiet gap (entry burst cannot arm), guard_s=0."""
import sys, itertools
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
exec(open(S+'/e4_final.py').read().split('CANDS=[]')[0].split("exec(open")[0])
exec("exec(open(S+'/e4_dep.py').read().split(\"print('%-26s\")[0])")
exec(open(S+'/e4_final.py').read().split('CANDS=[]')[0].split('exec(open(S+\'/e4_dep.py\').read().split("print(\'%-26s")[0])')[1])
CANDS=[]
for ron,qs,cn in itertools.product((8.,12.,20.),(5.,10.,15.,20.,30.),(10,20,40)):
    CANDS.append(("D' r%-2.0f q%-2.0f n%-2d"%(ron,qs,cn),90.,
        dict(grace_s=90.,use_ret=True,ret_on=ron,ret_all=True,near_max=1,lead_max=1,
             cross_n=cn,cross_win=20.,quiet_s=qs,guard_s=0.)))
for hold_s in (30.,60.):
    print('\n===== hold_s=%.0f (taup=90, grace=90, guard=0) ====='%hold_s,flush=True)
    print('%-20s %-9s %-9s %-9s %-7s | %-9s %-5s %-9s %-16s %-18s %s'%(
      'variant','bathREL','maxENT','maxREL','kitch','fdENT','emp%','seedREL','armed b/M/fd','fd drops','T1234'),flush=True)
    passed=[]
    for nm,taup,kw in CANDS:
        o=sc(run(kw,taup,hold_s),hold_s)
        tag=''.join('.' if o[k] else 'X' for k in ('t1','t2','t3','t4'))
        if tag=='....': passed.append(nm)
        print('%-20s %-9s %-9s %-9s %-7s | %-9s %-5.1f %-9s %-16s %-18s %s'%(
          nm,(V(o['b_e'])+'!') if o['b_e'] else V(o['b_rel']),V(o['m_ent']),
          (V(o['m_e'])+'!') if o['m_e'] else V(o['m_rel']),V(o['k_ent']) if o['k_ent'] else 'NEVER',
          V(o['f_ent']),o['emp'],V(o['srel']),
          '%s/%s/%s'%(V(o['armB'])[3:],V(o['armM'])[3:],V(o['armF'])[3:]),
          ', '.join(hm(t) for t in o['drops']) or 'none',tag),flush=True)
    print('PASS(hold %.0f): %s'%(hold_s,passed or 'NONE'),flush=True)
