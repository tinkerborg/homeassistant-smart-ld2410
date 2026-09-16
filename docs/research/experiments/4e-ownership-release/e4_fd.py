"""FD:68 timeline: near-lead events, score, retention, per 20s 21:11-21:56."""
import sqlite3, sys, collections, math
S='/private/tmp/claude-500/-Users-rmk-Repo-home-assistant/5b47b34c-4417-452d-8f77-ce48ba08e904/scratchpad'
sys.path.insert(0,S)
from rel import *  # noqa
from custom_components.smart_ld2410.algo.detector import Detector

cf=sqlite3.connect('file:%s?mode=ro'%FIX,uri=True)
fd=[(r[0],list(r[1]),list(r[2])) for r in cf.execute("select ts,move,still from frames order by ts")]
SPLIT=T(21,11); warm=[r for r in fd if r[0]<SPLIT]; body=[r for r in fd if r[0]>=SPLIT]
class C(Composite):
    def _advance(self,score,ts,*,entry_suppressed=False):
        Detector._advance(self,score,ts,entry_suppressed=True)   # never enter; just observe
d,rec=None,None
cfg=DetectorConfig(hold_s=1e9); dd=C(cfg); ret=Retention(warm[0][2]); t0=warm[0][0]; rec=[]
for src,keep in ((warm,False),(body,True)):
    for ts,mv,st in src:
        ret.add(ts,st); dd.ret=ret.score
        o=dd.process(Frame(ts,ts-t0,tuple(mv),tuple(st),0,False))
        if keep: rec.append((ts,o.score,dd.lead_sup,tuple(o.active_gates),list(ret.score)))
b=collections.OrderedDict()
for ts,sc,ls,ag,r in rec:
    k=int(ts//20)*20
    e=b.setdefault(k,dict(n=0,hot=0,h=collections.Counter(),near=0,sc=[],r=[]))
    e['n']+=1; e['h'][ls if ls is not None else -1]+=1; e['sc'].append(sc); e['r'].append(max(r[2:9]))
    if sc>=1.5: e['hot']+=1
    if ls is not None and ls<=1: e['near']+=1
print('%-9s %4s %4s %5s %7s %7s  %s'%('t','n','hot','near','scMed','retMed','lead hist'))
for k,e in b.items():
    m=lambda v:sorted(v)[len(v)//2]
    tag=''
    for tt,lbl in ((T(21,20),'<- LEFT'),(T(21,39,40),'<- BACK'),(T(21,49),'<- still min'),(T(21,30),'<- cat')):
        if k<=tt<k+20: tag='   '+lbl
    print('%-9s %4d %4d %5d %7.2f %7.1f  %s%s'%(hm(k),e['n'],e['hot'],e['near'],m(e['sc']),m(e['r']),
      ' '.join('g%d:%d'%(g,v) for g,v in sorted(e['h'].items())),tag))
