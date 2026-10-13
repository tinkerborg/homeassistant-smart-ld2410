"""Reconstruct conservative room spans from user account and raw cross-sensor traces."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
DB=ROOT/'tests/fixtures/recordings/post-deploy-0915.db'
TAG='reconstructed-0916-user-account-v1'
PREFIX=(TAG+'; INFERRED, approximate/conservative interval; user reported bathroom visit then stove/kitchen, bathroom cleared, falsely re-entered, eventually cleared. Timing inferred from bathroom and kitchen raw energy, not independently timed ground truth. Do not use for subsecond latency or circular validation. ')
SPANS=[('kitchen','22:35:05','22:36:18','Kitchen activity before the brief bathroom visit; transition edges excluded.'),('bathroom','22:36:21','22:36:28','Brief strong bathroom-motion interval after kitchen motion subsides; inferred visit, not exact physical entry/exit.'),('kitchen','22:36:34','22:38:45','Kitchen activity after bathroom visit; includes bathroom clear22:36:44.963, falseentry22:36:49.163, clear22:38:37.654. Interval ends conservatively, not an asserted room departure.')]
def stamp(clock):return datetime.fromisoformat('2026-09-15 '+clock).replace(tzinfo=ZoneInfo('America/New_York')).timestamp()
def main():
 rows=[('rob',room,stamp(a),stamp(b),PREFIX+note) for room,a,b,note in SPANS]
 with sqlite3.connect(DB) as c:
  before=c.execute('select * from labels').fetchall()
  if before:
   if sorted(before)!=sorted(rows):raise RuntimeError('Existing labels differ; refusing to overwrite')
  else:
   backup=Path('/tmp/post-deploy-0915-before-reconstructed-labels.db')
   if not backup.exists():
    with sqlite3.connect(backup) as dest:c.backup(dest)
   c.executemany('insert into labels(person,room,ts_start,ts_end,note) values(?,?,?,?,?)',rows)
  assert c.execute('select count(*) from labels').fetchone()[0]==3
  assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
 (HERE/'labels-reconstruction.json').write_text(json.dumps({'provenance':TAG,'independent_ground_truth':False,'unlabeled':'Transitions, earlier startup and later activity remain unknown; no wife labels inferred.','labels':[dict(zip(('person','room','ts_start','ts_end','note'),r)) for r in rows]},indent=2))
 print('Saved 3 reconstructed labels; raw frames and events untouched.')
if __name__=='__main__':main()
