"""Descriptive, fixed contrasts following raw visual inspection; no fitted model."""
import sys
from pathlib import Path
import numpy as np
from inspect_signals import load, stamp, OUT
sys.path.insert(0,str(OUT.parent/'15-gate-profile'))
import data

def contrasts(m,s):
 den=s[:,2]+s[:,3]
 return {'s2-s3':s[:,2]-s[:,3], 'near_slope':np.divide(s[:,2]-s[:,3],den,out=np.zeros(len(s)),where=den>0), 'm2-m3':m[:,2]-m[:,3], 's2-min(s3,s4)':s[:,2]-np.minimum(s[:,3],s[:,4]),'s2':s[:,2],'s3':s[:,3]}
def stats(name,t,m,s,spans):
 vals=contrasts(m,s)
 print('\n'+name)
 for lab,a,b in spans:
  idx=(t>=a)&(t<b)
  if not idx.any():continue
  print(lab,'n',idx.sum(),'seconds',round(b-a,1))
  for k,v in vals.items():
   x=v[idx];print(' ',k, 'p10/50/90',np.round(np.percentile(x,[10,50,90]),3).tolist(), '>0',round(100*np.mean(x>0),1), '>=0',round(100*np.mean(x>=0),1))
  # Per-frame sign is a diagnostic only: no acceptance thresholds fitted.
  fail=(s[:,2] < s[:,3]) if lab in ('IN','bathroom','toilet') else (s[:,2]>=s[:,3])
  ids=np.flatnonzero(idx); lengths=[]; start=None; prev=None
  for i in ids:
   if fail[i]:
    if start is None or prev is None or i!=prev+1 or t[i]-t[prev]>.55:
     if start is not None:lengths.append(t[prev]-t[start])
     start=i
    prev=i
   elif start is not None:lengths.append(t[prev]-t[start]);start=prev=None
  if start is not None:lengths.append(t[prev]-t[start])
  print('  longest wrong-order run seconds',round(max(lengths,default=0),2))
if __name__=='__main__':
 for name in ('labeled-loop-0915.db','labeled-walk-0915.db'):
  t,m,s,labs=load(name)
  if 'walk' in name:
   # Explicit user/wife location overlap only; new label data, no fitting.
   spans=[('TW',stamp('2026-09-15 18:50:40'),stamp('2026-09-15 18:50:52')),('IN',stamp('2026-09-15 18:50:52'),stamp('2026-09-15 18:51:11')),('TW',stamp('2026-09-15 18:51:11'),stamp('2026-09-15 18:51:47')),('IN',stamp('2026-09-15 18:51:48'),stamp('2026-09-15 18:52:11')),('TW',stamp('2026-09-15 18:52:11'),stamp('2026-09-15 18:52:20'))]
  else:spans=labs
  stats(name,t,m,s,spans)
 for name in ('labeled-sessions-0909-d06e','stove-case-0913-d06e','bathroom-visit-2204-d06e','throughwall-morning-d06e'):
  fx=data.load(name);stats(name,fx.ts,fx.move,fx.still,fx.spans)
