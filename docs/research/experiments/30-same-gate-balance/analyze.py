"""Experiment-only same-gate balance guard for NEW anchors."""
import importlib.util,json
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('e28',HERE.parent/'28-strength-confirmation/analyze.py')
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
s=e.s
Original=s.MotionAnchor
class Balanced(Original):
 def update(self,t,move,still,floor,spread):
  existing=self.template is not None and (self._previous_ts is None or 0<=t-self._previous_ts<=self.max_gap_s)
  qualifying=any(move[g]>=40 and move[g]/max(move[g]+still[g],1)>=1/3 for g in range(2,9))
  threshold=self.motion_threshold
  if not existing and not qualifying:self.motion_threshold=float('inf')
  try:return super().update(t,move,still,floor,spread)
  finally:self.motion_threshold=threshold

def main():
 result={}
 fixtures=[s.old.e.b.new_fixture(n) for n in ('labeled-walk-0915.db','labeled-loop-0915.db')]+[e.post_fixture()]
 for f in fixtures:
  fl,sp=s.estimates(f);result[f.name]={}
  for name,cls in [('original',Original),('same_gate_balance',Balanced)]:
   s.MotionAnchor=cls
   out,_,_=s.replay(f,fl,sp,True,0.)
   a=s.assessment(f,out);a['onsets']=[float(f.ts[i]) for i in np.flatnonzero(out&~np.r_[False,out[:-1]])]
   result[f.name][name]=a
  if f.name=='post-deploy-0915':
   target=1789526209.163709
   for name,cls in [('original',Original),('same_gate_balance',Balanced)]:
    s.MotionAnchor=cls;out,_,_=s.replay(f,fl,sp,True,0.)
    q=(f.ts>=target-5)&(f.ts<target+110)
    result[f.name][name]['false_window_positive_frames']=int(out[q].sum())
 (HERE/'results.json').write_text(json.dumps(result,indent=2))
 for f,d in result.items():
  print(f)
  for k,v in d.items():print(k,'entry',[round(x['entry_offset_s'],3) if x['entry_offset_s'] is not None else None for x in v['visits']],'clear',[round(x['first_clear_offset_s'],3) if x['first_clear_offset_s'] is not None else None for x in v['visits']],'false_window',v.get('false_window_positive_frames'))
if __name__=='__main__':main()
