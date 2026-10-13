"""4e final: variant D scored with tolerances, + armed-time forensics, + hold_s=60."""
import sys, itertools, collections
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
exec(open(S+'/e4_dep.py').read().split("print('%-26s")[0])

def armed_at(rec):
    for ts,o,a in rec:
        if a: return ts
    return None
def ed(rec):
    tl=[];p=None
    for ts,o,_ in rec:
        if p is None: p=o; continue
        if o!=p: tl.append((ts,o)); p=o
    return tl
def rel_after(rec,t):
    was=None
    for ts,o,_ in rec:
        if ts<t: was=o; continue
        if was and not o: return ts
        was=o
    return None
def V(x): return hm(x) if x else '--'
def near(a,b,tol=2.0): return a is not None and abs(a-b)<=tol

def run(kw,taup,hold_s):
    r={}
    for s in ('bath','MAX','kitchen'): r[s]=go(s,taup=taup,hold_s=hold_s,**kw)
    r['fd']=go('fd',taup=taup,hold_s=hold_s,**kw)
    r['fdseed']=go('fdseed',taup=taup,hold_s=hold_s,seed=True,**kw)
    return r
def sc(r,hold_s):
    tlb=ed(r['bath']); tlm=ed(r['MAX'])
    o=dict(b_ent=next((t for t,o2 in tlb if o2),None), b_rel=rel_after(r['bath'],DEPART),
      b_e=next((t for t,o2 in tlb if not o2 and ARRIVE<t<DEPART),None),
      m_ent=next((t for t,o2 in tlm if o2),None), m_rel=rel_after(r['MAX'],ARRIVE),
      m_e=next((t for t,o2 in tlm if not o2 and ARRIVE<t<DEPART),None),
      k_ent=next((t for t,o2 in ed(r['kitchen']) if o2),None))
    tlf=ed(r['fd'])
    o['f_ent']=next((t for t,o2 in tlf if o2 and t>=BACK-20),None)
    o['drops']=[t for t,o2 in tlf if not o2 and T(21,40,30)<=t<T(21,55)]
    den=[1 for ts,_,_ in r['fd'] if T(21,22)<=ts<T(21,39)]
    o['emp']=100.*sum(1 for ts,oc,_ in r['fd'] if T(21,22)<=ts<T(21,39) and oc)/max(len(den),1)
    o['srel']=next((ts for ts,oc,_ in r['fdseed'] if not oc),None)
    o['armB']=armed_at(r['bath']); o['armM']=armed_at(r['MAX']); o['armF']=armed_at(r['fd'])
    o['t1']=near(o['m_ent'],ARRIVE) and o['m_e'] is None and o['m_rel'] and DEPART-2<=o['m_rel']<=DEPART+hold_s+5
    o['t2']=near(o['b_ent'],ARRIVE) and o['b_e'] is None and near(o['b_rel'],DEPART+ (0 if hold_s==30 else hold_s-30),3)
    o['t3']=o['k_ent'] is None
    o['t4']=(near(o['f_ent'],BACK,60) and not o['drops'] and o['emp']<1.0
             and o['srel'] and T(21,19)<=o['srel']<=T(21,21,30))
    return o
CANDS=[]
for taup,ron,gr,gd in itertools.product((60.,90.),(8.,12.,20.),(60.,90.),(45.,50.,55.,60.,75.,90.)):
    CANDS.append(('D t%.0f r%-2.0f g%-2.0f gd%-3.0f'%(taup,ron,gr,gd),taup,
        dict(grace_s=gr,use_ret=True,ret_on=ron,ret_all=True,near_max=1,lead_max=1,
             cross_n=10,cross_win=20.,quiet_s=10.,guard_s=gd)))
for hold_s in (30.,60.):
    print('\n===== hold_s=%.0f ====='%hold_s,flush=True)
    print('%-24s %-9s %-9s %-9s %-9s %-7s | %-9s %-5s %-9s %-16s %-22s %s'%(
      'variant','bathENT','bathREL','maxENT','maxREL','kitch','fdENT','emp%','seedREL','armed b/M/fd','fd drops','T1234'),flush=True)
    passed=[]
    for nm,taup,kw in CANDS:
        o=sc(run(kw,taup,hold_s),hold_s)
        tag=''.join('.' if o[k] else 'X' for k in ('t1','t2','t3','t4'))
        if tag=='....': passed.append(nm)
        print('%-24s %-9s %-9s %-9s %-9s %-7s | %-9s %-5.1f %-9s %-16s %-22s %s'%(
          nm,V(o['b_ent']),(V(o['b_e'])+'!') if o['b_e'] else V(o['b_rel']),V(o['m_ent']),
          (V(o['m_e'])+'!') if o['m_e'] else V(o['m_rel']),V(o['k_ent']) if o['k_ent'] else 'NEVER',
          V(o['f_ent']),o['emp'],V(o['srel']),
          '%s/%s/%s'%(V(o['armB'])[3:],V(o['armM'])[3:],V(o['armF'])[3:]),
          ', '.join(hm(t) for t in o['drops']) or 'none',tag),flush=True)
    print('PASS ALL FOUR (hold %.0f): %s'%(hold_s,passed or 'NONE'),flush=True)
