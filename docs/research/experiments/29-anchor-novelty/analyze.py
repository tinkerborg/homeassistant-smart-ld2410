"""Causal still-pattern novelty at fixed motion-anchor trigger frames."""
import sqlite3
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[4]
BATH='D0:6E:81:D2:5D:A6'
CASES=[('walk visit 1','labeled-walk-0915.db',1789512653.6932104),('walk visit 2','labeled-walk-0915.db',1789512708.0158184),('solo loop','labeled-loop-0915.db',1789514660.3849833),('kitchen false re-entry','post-deploy-0915.db',1789526209.163709)]
for name,db,target in CASES:
 with sqlite3.connect(f'file:{ROOT / "tests/fixtures/recordings" / db}?mode=ro',uri=True) as c:
  rows=c.execute('select ts,move,still from frames where sensor_id=? and ts>? and ts<? order by ts',(BATH,target-3,target+.2)).fetchall()
 ts=np.array([r[0] for r in rows]);move=np.array([list(r[1]) for r in rows]);still=np.array([list(r[2]) for r in rows]);i=int(np.argmin(abs(ts-target)))
 prior=still[(ts>=ts[i]-1)&(ts<ts[i]-.1),2:9]
 assert len(prior)>=5
 reference=np.median(prior,axis=0);now=still[i,2:9];delta=now-reference
 print(name,'actual_ts',ts[i],'dt_to_target',round(ts[i]-target,4),'motion_peak',int(move[i,2:9].max()),'still_delta_l2',round(float(np.linalg.norm(delta)),2),'delta',delta.tolist())
