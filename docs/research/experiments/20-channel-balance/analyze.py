"""Per-frame channel balance. Labels evaluate fixed arithmetic, never fit it.

All inference inputs are bathroom gate readings. No classifier, smoothing,
confirmation period, entry/departure state, or learned threshold is used.
The fixed sensitivity grid is descriptive, not a search for a selected rule.
"""
from __future__ import annotations
import os, time, sys, sqlite3, json
from pathlib import Path
import numpy as np
os.environ['TZ']='America/New_York'
if hasattr(time,'tzset'): time.tzset()
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(HERE.parent/'15-gate-profile'))
import data
BATH='D0:6E:81:D2:5D:A6'
GATES=np.arange(2,9) # Only these gates have both channels; not a room boundary.
MOTION_BARS=(20.,40.,60.)
SHARES=(.20,1/3,.50)

def new_fixture(name):
 p=ROOT/'tests/fixtures/recordings'/name
 with sqlite3.connect(f'file:{p}?mode=ro',uri=True) as c:
  rows=c.execute('select ts,move,still from frames where sensor_id=? order by ts',(BATH,)).fetchall()
  labs=c.execute('select person,room,ts_start,ts_end,note from labels').fetchall()
 ts=np.array([r[0] for r in rows]);m=np.array([list(r[1]) for r in rows],float);s=np.array([list(r[2]) for r in rows],float)
 rob=[(room,a,b) for p,room,a,b,_ in labs if p=='rob'];wife=[(room,a,b) for p,room,a,b,_ in labs if p=='wife']
 cuts=sorted({v for _,_,a,b,_ in labs for v in (a,b)}|{float(ts[0]),float(ts[-1])})
 spans=[]
 for a,b in zip(cuts,cuts[1:]):
  a=max(a,float(ts[0]));b=min(b,float(ts[-1]))
  if b<=a:continue
  rr=[r for r,x,y in rob if x<=a and b<=y];wr=[r for r,x,y in wife if x<=a and b<=y]
  if len(rr)!=1 or len(wr)!=1:continue
  rooms=rr+wr
  cls='IN' if 'bathroom' in rooms else 'TW' if 'kitchen' in rooms else 'HALL' if 'hall' in rooms else 'EMPTY'
  if spans and spans[-1][0]==cls and spans[-1][2]==a:spans[-1]=(cls,spans[-1][1],b)
  else:spans.append((cls,a,b))
 return data.Fixture(name[:-3],'d06e',ts,m,s,spans)

def fixtures():
 out=[new_fixture(x) for x in ('labeled-loop-0915.db','labeled-walk-0915.db')]
 for name in ('labeled-sessions-0909-d06e','throughwall-morning-d06e','bathroom-visit-2204-d06e','stove-case-0913-d06e','livingroom-reset-seated-fd68'):
  out.append(data.load(name))
 return out

def signals(fx):
 m=fx.move[:,GATES];s=fx.still[:,GATES]
 share=m/np.maximum(m+s,1.)
 peak_index=np.argmax(m,axis=1);row=np.arange(len(m))
 return m,s,share,{'move_peak':m.max(1),'still_at_move_peak':s[row,peak_index],
  'local_share_at_move_peak':share[row,peak_index],
  'whole_share':m.sum(1)/np.maximum(m.sum(1)+s.sum(1),1.),
  'max_unqualified_local_share':share.max(1)}

def predicates(fx):
 m,s,share,sig=signals(fx);out={}
 for bar in MOTION_BARS:
  out[f'motion_{bar:g}']=m.max(1)>=bar
  for sh in SHARES:
   # Same gate must satisfy both conditions. A distant denominator never
   # cancels a qualifying local gate, but same-gate mixtures remain possible.
   out[f'local_{bar:g}_{sh:.3f}']=((m>=bar)&(share>=sh)).any(1)
   out[f'whole_{bar:g}_{sh:.3f}']=(m.max(1)>=bar)&(sig['whole_share']>=sh)
 return out

def mask(fx,cls):
 q=np.zeros(len(fx.ts),bool)
 for c,a,b in fx.spans:
  if c==cls:q|=(fx.ts>=a)&(fx.ts<b)
 return q

def rate(x,q):return float(100*np.mean(x[q])) if q.any() else None

def run_stats(x,t,q):
 ids=np.flatnonzero(x&q);runs=[];start=prev=None
 for i in ids:
  if prev is None or i!=prev+1 or t[i]-t[prev]>.55:
   if start is not None:runs.append((start,prev))
   start=i
  prev=i
 if start is not None:runs.append((start,prev))
 return {'positive_frames':int(len(ids)),'runs':len(runs),'longest_span_s':max((float(t[b]-t[a]) for a,b in runs),default=0.)}

def describe(fx):
 _,_,_,sig=signals(fx)
 print('\nFIXTURE',fx.name,'sensor',fx.sensor,'frames',len(fx.ts))
 for cls,a,b in fx.spans:
  q=(fx.ts>=a)&(fx.ts<b)
  if not q.any():continue
  print('SPAN',cls,time.strftime('%H:%M:%S',time.localtime(a)),time.strftime('%H:%M:%S',time.localtime(b)),'n',int(q.sum()))
  for k in ('move_peak','still_at_move_peak','local_share_at_move_peak','whole_share','max_unqualified_local_share'):
   print(' ',k,'p10/50/90',np.round(np.percentile(sig[k][q],[10,50,90]),3).tolist())
  # Prespecified motion bands distinguish ratio shifts from stronger motion.
  for lo,hi in ((0,10),(10,20),(20,40),(40,60),(60,101)):
   z=q&(sig['move_peak']>=lo)&(sig['move_peak']<hi)
   if z.any():print('  matched_motion_band',lo,hi,'n',int(z.sum()),'local_share_p10/50/90',np.round(np.percentile(sig['local_share_at_move_peak'][z],[10,50,90]),3).tolist())

def evaluate(fx):
 pred=predicates(fx);summary={}
 print('\nRATES',fx.name,'percent positive, NOT accuracy; IN low means absent positive evidence, not inferred vacancy')
 print('rule IN TW EMPTY HALL PET')
 for name,p in pred.items():
  rates={c:rate(p,mask(fx,c)) for c in ('IN','TW','EMPTY','HALL','PET')}
  summary[name]=rates
  print(name,' '.join('--' if rates[c] is None else f'{rates[c]:.2f}' for c in rates))
 # Report fixed example 40 / one-third plus controls in all spans. Not chosen
 # for good performance: these were set before loading experimental results.
 details=[]
 for cls,a,b in fx.spans:
  q=(fx.ts>=a)&(fx.ts<b)
  if not q.any():continue
  for name in ('motion_40','local_40_0.333','whole_40_0.333'):
   p=pred[name];r=run_stats(p,fx.ts,q);r.update(rule=name,cls=cls,start=a,end=b,frames=int(q.sum()))
   ix=np.flatnonzero(p&q)
   r['first_positive_after_label_s']=float(fx.ts[ix[0]]-a) if len(ix) else None
   r['positive_in_previous_second']=bool((p&(fx.ts>=a-1)&(fx.ts<a)).any())
   details.append(r)
   print('DETAIL',json.dumps(r))
 return {'rates':summary,'details':details}

if __name__=='__main__':
 result={}
 for fx in fixtures():describe(fx);result[fx.name]=evaluate(fx)
 (HERE/'results.json').write_text(json.dumps(result,indent=2))
