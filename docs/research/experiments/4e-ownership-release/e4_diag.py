"""4e diagnostic: what does a DEPARTURE look like, vs a neighbour holding on?"""
import sqlite3, sys, collections
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
from rel import *  # noqa
from lead import Model as LeadModel, leading_suppressed, leading_raw, K, GATES, SUPPORT_TAU
import math

W0,W1=T(21,58),T(22,10); WARM0=W0-6*3600.0
K0,K1=T(5,11),T(5,23); ARRIVE,DEPART=T(22,4,1),T(22,6,43)
c=sqlite3.connect('file:%s?mode=ro'%PROD,uri=True)
def fetch(a,b):
    return [(r[0],list(r[1]),list(r[2])) for r in c.execute(
      "select ts,move,still from frames where sensor_id like 'D0:6E%' and ts>=? and ts<? order by ts",(a,b))]
warmD=fetch(WARM0,W0); bath=fetch(W0,W1); kit=fetch(K0,K1); n=min(len(bath),len(kit))
MIX={'bath':bath[:n],
     'kitchen':[(bath[i][0],kit[i][1],kit[i][2]) for i in range(n)],
     'MAX':[(bath[i][0],[max(bath[i][1][g],kit[i][1][g]) for g in range(9)],
             [max(bath[i][2][g],kit[i][2][g]) for g in range(9)]) for i in range(n)]}

def leadtrace(warm,rows):
    m=LeadModel(); sup=[0.0]*GATES; prev=None; out=[]
    for ts,mv,st in warm:
        if m.ready:
            rm,rs=m.res(mv,st); pk=[max(0.0,rm[g],rs[g]) for g in range(GATES)]
            a=1.0 if prev is None else (1.0-math.exp(-min(ts-prev,2.0)/SUPPORT_TAU) if ts>prev else 0.0)
            for g in range(GATES): sup[g]+=a*(pk[g]-sup[g])
        prev=ts; m.add(ts,mv,st)
    for ts,mv,st in rows:
        rm,rs=m.res(mv,st); pk=[max(0.0,rm[g],rs[g]) for g in range(GATES)]
        a=1.0-math.exp(-min(ts-prev,2.0)/SUPPORT_TAU)
        for g in range(GATES): sup[g]+=a*(pk[g]-sup[g])
        ls,runs=leading_suppressed(rm,sup)
        out.append((ts,ls,leading_raw(rm),tuple(rm),tuple(sup),runs))
        prev=ts; m.add(ts,mv,st)
    return out

def rettrace(warm,rows):
    r=Retention(warm[0][2]); out=[]
    for ts,mv,st in warm: r.add(ts,st)
    for ts,mv,st in rows: out.append((ts,list(r.add(ts,st))))
    return out

print('='*110); print('D0:6E  per-10s lead profile 22:03:00-22:09:00 (suppressed lead histogram + max residual per gate band)')
print('='*110)
for nm in ('bath','kitchen','MAX'):
    lt=leadtrace(warmD,MIX[nm]); rt=dict((ts,s) for ts,s in rettrace(warmD,MIX[nm]))
    print('\n-- %s'%nm)
    print('%-9s %-42s %6s %6s %6s | %s'%('t','sup-lead hist','near%','maxR01','maxR2+','retention g2 g3 g4 g5 g6'))
    b=collections.OrderedDict()
    for ts,ls,lr,rm,sup,runs in lt:
        if not (T(22,3)<=ts<T(22,9)): continue
        k=int(ts//10)*10
        e=b.setdefault(k,dict(h=collections.Counter(),n=0,near=0,r01=[],r2=[],ret=[]))
        e['h'][ls if ls is not None else -1]+=1; e['n']+=1
        if ls is not None and ls<=1: e['near']+=1
        e['r01'].append(max(rm[0],rm[1])); e['r2'].append(max(rm[2:]))
        e['ret'].append(rt.get(ts,[0]*9))
    for k,e in b.items():
        med=lambda v:sorted(v)[len(v)//2]
        R=[med([x[g] for x in e['ret']]) for g in range(9)]
        print('%-9s %-42s %5.0f%% %6.1f %6.1f | %s'%(hm(k),
          ' '.join('g%d:%d'%(g,v) for g,v in sorted(e['h'].items())),
          100.0*e['near']/e['n'], max(e['r01']), max(e['r2']),
          ' '.join('%5.0f'%R[g] for g in (2,3,4,5,6))))
