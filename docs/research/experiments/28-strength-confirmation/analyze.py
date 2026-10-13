"""Fixed strength-scaled confirmation; no production changes or label fitting."""
import importlib.util,json,sqlite3
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('stack26',HERE.parent/'26-motion-anchor-stack/replay.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
Original=s.MotionAnchor
class Confirmed(Original):
 def __init__(self):
  super().__init__();self.count=0;self.last=None
 def update(self,t,move,still,floor,spread):
  if self.last is not None and (t<self.last or t-self.last>self.max_gap_s):self.count=0
  self.last=t
  existing=self.template is not None and (self._previous_ts is None or 0<=t-self._previous_ts<=self.max_gap_s)
  peak=max(move[2:9]);self.count=self.count+1 if peak>=40 and not existing else 0
  permit=existing or peak>=80 or (peak>=60 and self.count>=2) or self.count>=3
  threshold=self.motion_threshold
  if not permit:self.motion_threshold=float('inf')
  try:r=super().update(t,move,still,floor,spread)
  finally:self.motion_threshold=threshold
  if r.anchored:self.count=0
  return r

def post_fixture():
 p=s.ROOT/'tests/fixtures/recordings/post-deploy-0915.db'
 with sqlite3.connect(f'file:{p}?mode=ro',uri=True) as c:
  rows=c.execute('select ts,move,still from frames where sensor_id=? order by ts',(s.old.e.b.BATH,)).fetchall()
  labs=c.execute('select room,ts_start,ts_end from labels where person=?',('rob',)).fetchall()
 return s.old.e.b.data.Fixture('post-deploy-0915','d06e',np.array([x[0] for x in rows]),np.array([list(x[1]) for x in rows],float),np.array([list(x[2]) for x in rows],float),[('IN' if r=='bathroom' else 'TW',a,b) for r,a,b in labs])

def main():
 results={}
 for f in [s.old.e.b.new_fixture(n) for n in ('labeled-walk-0915.db','labeled-loop-0915.db')]+[post_fixture()]:
  fl,sp=s.estimates(f);d={}
  for name,cls in [('original',Original),('scaled',Confirmed)]:
   s.MotionAnchor=cls
   out,_,_=s.replay(f,fl,sp,True,0.)
   d[name]=s.assessment(f,out)
   transitions=np.flatnonzero(out&~np.r_[False,out[:-1]])
   d[name]['onsets']=[float(f.ts[i]) for i in transitions]
   if f.name=='post-deploy-0915':
    a=s.old.e.b.time.mktime(s.old.e.b.time.strptime('2026-09-15 22:36:44','%Y-%m-%d %H:%M:%S'));q=(f.ts>=a)&(f.ts<a+116)
    d[name]['false_event_window_positive_frames']=int(out[q].sum())
   if cls is Confirmed:
    from dataclasses import replace
    n=len(f.ts)-100;prefix=replace(f,ts=f.ts[:n],move=f.move[:n],still=f.still[:n]);pf,ps=s.estimates(prefix)
    assert np.array_equal(out[:n],s.replay(prefix,pf,ps,True,0.)[0])
  results[f.name]=d
 (HERE/'results.json').write_text(json.dumps(results,indent=2))
 for f,d in results.items():
  print(f)
  for k,v in d.items():
   print(k,'entry',[x['entry_offset_s'] for x in v['visits']],'clear',[x['first_clear_offset_s'] for x in v['visits']],'dropouts',[x['dropouts_after_detection']['runs'] for x in v['visits']],'TW',v['rates']['TW'],'falsewindow',v.get('false_event_window_positive_frames'))
if __name__=='__main__':main()
