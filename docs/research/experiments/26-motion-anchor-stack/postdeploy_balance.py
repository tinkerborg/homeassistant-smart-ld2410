"""Replay experiment26 stack with/without experiment20 balance on post-deploy data."""
import importlib.util
import json
import sqlite3
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('stack',HERE/'replay.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
BATH='D0:6E:81:D2:5D:A6'
DB=s.ROOT/'tests/fixtures/recordings/post-deploy-0915.db'
with sqlite3.connect(f'file:{DB}?mode=ro',uri=True) as c:
 rows=c.execute('select ts,move,still from frames where sensor_id=? order by ts',(BATH,)).fetchall()
 labels=c.execute('select room,ts_start,ts_end from labels where person=?',('rob',)).fetchall()
f=s.old.e.b.data.Fixture('post-deploy-0915','d06e',np.array([x[0] for x in rows]),np.array([list(x[1]) for x in rows],float),np.array([list(x[2]) for x in rows],float),[('IN' if room=='bathroom' else 'TW',a,b) for room,a,b in labels])
fl,sp=s.estimates(f)
target=1789526209.163709
result={'source_db':str(DB),'labels_are_reconstructed':True,'source_event_ts':target,'variants':{}}
for hold in (0.,20.,30.):
 for balanced in (False,True):
  key=f'hold{hold:g}_{"balanced" if balanced else "original"}'
  occupied,score,anchor_score=s.replay(f,fl,sp,True,hold,balanced)
  around=(f.ts>=target-5)&(f.ts<target+110)
  onset=np.flatnonzero(occupied&~np.r_[False,occupied[:-1]])
  result['variants'][key]={'assessment':s.assessment(f,occupied),'onsets_after_22_36_40':[float(f.ts[i]) for i in onset if f.ts[i]>=target-9], 'occupied_at_reported_false_event':bool(occupied[np.argmin(abs(f.ts-target))]),'positive_frames_in_false_window':int(occupied[around].sum())}
(HERE/'postdeploy-balance-results.json').write_text(json.dumps(result,indent=2))
for key,value in result['variants'].items():
 print(key,'false_event',value['occupied_at_reported_false_event'],'false_window_frames',value['positive_frames_in_false_window'],'onsets',value['onsets_after_22_36_40'])
