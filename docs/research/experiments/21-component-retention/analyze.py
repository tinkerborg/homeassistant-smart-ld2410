"""Causal motion-anchored still footprint. Labels used ONLY after replay.

Diagnostic prototype, not a wall classifier or production occupancy algorithm.
No future frames, room boundaries, kitchen sensor, or label-selected templates.
"""
import importlib.util, json
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('balance',HERE.parent/'20-channel-balance/analyze.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

def replay(t, move, still, tau=15., bar=40., retain=.4):
 # Seven usable cross-channel gates, no selected room-distance range.
 m=move[:,2:9];s=still[:,2:9]
 background=s[0].copy();h=None
 active=np.zeros(len(t),bool);score=np.zeros(len(t));residual=np.zeros_like(s)
 for i in range(len(t)):
  dt=0. if i==0 else max(0.,float(t[i]-t[i-1]))
  if dt>.55: # Missing evidence: discard the template and restart baseline.
   h=None;background=s[i].copy()
  r=np.maximum(s[i]-background,0.)
  residual[i]=r
  strong=m[i].max()>=bar
  candidate=r*(m[i]/max(float(m[i].max()),1.))
  if strong and np.dot(candidate,candidate)>=1.:
   if h is None or np.dot(candidate,candidate)>np.dot(h,h):h=candidate.copy()
  if h is not None:
   # Scalar least-squares amplitude of the stored footprint in today's excess.
   score[i]=float(np.dot(r,h)/np.dot(h,h))
   active[i]=score[i]>=retain
   if not active[i]:h=None
  if h is None:
   background+=(1-np.exp(-dt/tau))*(s[i]-background)
 return active,score,residual

def assess(f,active):
 rates={c:b.rate(active,b.mask(f,c)) for c in ('IN','TW','EMPTY')}
 visits=[]
 for c,a,z in f.spans:
  if c!='IN':continue
  q=(f.ts>=a)&(f.ts<z);idx=np.flatnonzero(q)
  if not len(idx):continue
  on=idx[active[idx]]
  post=np.flatnonzero((f.ts>=z)&(f.ts<z+10))
  off=post[~active[post]]
  visits.append(dict(start=a,end=z,frames=len(idx),positive_frames=int(active[idx].sum()),
   first_on_after_label_s=float(f.ts[on[0]]-a) if len(on) else None,
   on_at_last_frame=bool(active[idx[-1]]),
   first_off_after_exit_label_s=float(f.ts[off[0]]-z) if len(off) else None,
   positive_frames_in_next_10s=int(active[post].sum()),
   missing_evidence=b.run_stats(~active,f.ts,q)))
 return dict(rates=rates,visits=visits)

def main():
 out={}
 for f in b.fixtures():
  out[f.name]={}
  for tau in (5.,15.,30.):
   for bar in (20.,40.):
    for retain in (.2,.4,.6):
     key=f'tau{tau:g}_motion{bar:g}_retain{retain:g}'
     p,_,_=replay(f.ts,f.move,f.still,tau,bar,retain)
     out[f.name][key]=assess(f,p)
  print(f.name,json.dumps(out[f.name]['tau15_motion40_retain0.4']))
 # Causality check: identical prefix with/without future frames.
 f=b.new_fixture('labeled-walk-0915.db');n=len(f.ts)-700
 full=replay(f.ts,f.move,f.still)
 prefix=replay(f.ts[:n],f.move[:n],f.still[:n])
 for x,y in zip(full,prefix):assert np.array_equal(x[:n],y)
 (HERE/'results.json').write_text(json.dumps(out,indent=2))
 print('Causal prefix check passed.')
if __name__=='__main__':main()
