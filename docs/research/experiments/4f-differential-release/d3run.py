"""Score the reset form of D'' (crossing clears the held retention) on T1-T6."""
import sys, itertools
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
from d3 import *
from d2run import ed, relafter, V, near_, HDR, BACKT
K=dict(grace_s=90.,ret_on=12.,ret_all=True,near_max=1,lead_max=1,
       cross_n=20,cross_win=20.,quiet_s=10.,guard_s=0.,use_ret=True)

def sc3(kw,hold_s,taup):
    r={s:go3(s,hold_s=hold_s,taup=taup,**kw)[0] for s in ('bath','MAX','kitchen','fd','fdcat','two')}
    r['fdseed']=go3('fdseed',hold_s=hold_s,taup=taup,seed=True,**kw)[0]
    o={}
    tlb=ed(r['bath']); tlm=ed(r['MAX'])
    o['b_ent']=next((t for t,x in tlb if x),None)
    o['b_e']=next((t for t,x in tlb if not x and ARRIVE<t<DEPART),None)
    o['b_rel']=relafter(r['bath'],DEPART)
    o['m_ent']=next((t for t,x in tlm if x),None)
    o['m_e']=next((t for t,x in tlm if not x and ARRIVE<t<DEPART),None)
    o['m_rel']=relafter(r['MAX'],ARRIVE)
    o['k_ent']=next((t for t,x in ed(r['kitchen']) if x),None)
    tlf=ed(r['fd'])
    o['f_ent']=next((t for t,x in tlf if x and t>=BACKT-20),None)
    o['drops']=[t for t,x in tlf if not x and T(21,40,30)<=t<T(21,55)]
    den=[1 for ts,_,_ in r['fd'] if T(21,22)<=ts<T(21,39)]
    o['emp']=100.*sum(1 for ts,oc,_ in r['fd'] if T(21,22)<=ts<T(21,39) and oc)/max(len(den),1)
    o['srel']=next((ts for ts,oc,_ in r['fdseed'] if not oc),None)
    o['cdrops']=[t for t,x in ed(r['fdcat']) if not x and T(21,40,30)<=t<T(21,55)]
    o['twrel']=next((t for t,x in ed(r['two']) if not x and t>T(22,0)),None)
    o['t1']=near_(o['m_ent'],ARRIVE) and o['m_e'] is None and o['m_rel'] and DEPART-2<=o['m_rel']<=DEPART+hold_s+5
    o['t2']=near_(o['b_ent'],ARRIVE) and o['b_e'] is None and near_(o['b_rel'],DEPART+(0 if hold_s==30 else hold_s-30),3)
    o['t3']=o['k_ent'] is None
    o['t4']=(near_(o['f_ent'],BACKT,60) and not o['drops'] and o['emp']<1.0
             and o['srel'] and T(21,19)<=o['srel']<=T(21,21,30))
    o['t5']=not o['cdrops']
    o['t6']=o['twrel'] is None
    return o
if __name__=='__main__':
    for hold_s in (30.,60.):
        print('\n===== hold_s=%.0f ====='%hold_s,flush=True)
        print(HDR%('variant','bathREL','maxREL','kitch','emp%','seedREL','fd drops','T5 catdrops','T6 rel','T123456'),flush=True)
        good=[]
        for taup,clamp in itertools.product((60.,90.,120.),(5.,10.,15.,20.,30.,45.,60.,90.)):
            kw=dict(clamp_s=clamp,**K)
            o=sc3(kw,hold_s,taup)
            tag=''.join('.' if o[k] else 'X' for k in ('t1','t2','t3','t4','t5','t6'))
            if tag=='......': good.append('tau%.0f clamp%.0f'%(taup,clamp))
            print(HDR%('reset tau%-3.0f clamp%-3.0f'%(taup,clamp),
              (V(o['b_e'])+'!') if o['b_e'] else V(o['b_rel']),
              (V(o['m_e'])+'!') if o['m_e'] else V(o['m_rel']),
              V(o['k_ent']) if o['k_ent'] else 'NEVER','%.1f'%o['emp'],V(o['srel']),
              ', '.join(hm(t) for t in o['drops']) or 'none',
              ', '.join(hm(t) for t in o['cdrops']) or 'HELD',
              V(o['twrel']) if o['twrel'] else 'HELD',tag),flush=True)
        print('PASS ALL SIX (hold %.0f): %s'%(hold_s,good or 'NONE'),flush=True)
