"""Raw bathroom plots; labels annotate observations, never fit a model."""
import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/ld2410-mpl')
os.environ.setdefault('XDG_CACHE_HOME','/tmp/ld2410-cache')
import sqlite3, json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
TZ=ZoneInfo('America/New_York')
BATH='D0:6E:81:D2:5D:A6'
def stamp(x):return datetime.fromisoformat(x).replace(tzinfo=TZ).timestamp()
def load(name):
 c=sqlite3.connect(f'file:{ROOT / "tests/fixtures/recordings" / name}?mode=ro',uri=True)
 cols=[r[1] for r in c.execute('pragma table_info(frames)')]
 rows=c.execute('select ts,move,still from frames '+('where sensor_id=? ' if 'sensor_id' in cols else '')+'order by ts', (BATH,) if 'sensor_id' in cols else ()).fetchall()
 t=np.array([r[0] for r in rows]); m=np.array([list(r[1]) for r in rows],float); s=np.array([list(r[2]) for r in rows],float)
 labs=[]
 if c.execute("select count(*) from sqlite_master where name='labels'").fetchone()[0]:
  labs=[(room,a,b) for person,room,a,b in c.execute('select person,room,ts_start,ts_end from labels') if person=='rob']
 else:
  ev=[(t,json.loads(p)['label']) for t,p in c.execute("select ts_utc,payload from events where kind='label' order by ts_utc")]
  labs=[(lab,a,ev[i+1][0] if i+1<len(ev) else t[-1]) for i,(a,lab) in enumerate(ev) if lab!='none']
 c.close();return t,m,s,labs
CASES=[('loop','labeled-loop-0915.db','2026-09-15 19:24:00','2026-09-15 19:27:15'),('overlap','labeled-walk-0915.db','2026-09-15 18:50:30','2026-09-15 18:52:30'),('old_close','labeled-sessions-0909-d06e.db','2026-09-09 23:10:45','2026-09-09 23:22:45')]
def plot_case(tag,name,start,end):
 t,m,s,labs=load(name); a,b=stamp(start),stamp(end); ix=(t>=a)&(t<=b); t,m,s=t[ix],m[ix],s[ix]
 fig,axes=plt.subplots(4,1,figsize=(15,10),sharex=True,constrained_layout=True)
 colors={g:plt.get_cmap('tab10')(g) for g in range(9)}
 for ax,v,label in zip(axes[:2],(m,s),('MOVE — all gates','STILL — all gates')):
  mesh=ax.pcolormesh(t,np.arange(9),v.T,shading='auto',vmin=0,vmax=100,cmap='viridis');ax.set_ylabel(label);ax.set_yticks(range(9));fig.colorbar(mesh,ax=ax,pad=.01,label='reported energy')
 for ax,v,label in zip(axes[2:],(m,s),('MOVE traces','STILL traces')):
  for g in range(2,7):ax.plot(t,v[:,g],lw=.8,label=f'g{g}',color=colors[g])
  ax.set_ylim(-3,105);ax.set_ylabel(label);ax.legend(loc='upper right',ncol=5,fontsize=8);ax.grid(alpha=.2)
 for room,x,y in labs:
  x,y=max(a,x),min(b,y)
  if y<=x:continue
  col='#2c9d56' if room in ('bathroom','toilet') else '#d89126' if room in ('kitchen','stove','island') else '#999999'
  for ax in axes:
   ax.axvline(x,color=col,lw=1,alpha=.8);ax.axvline(y,color=col,lw=1,alpha=.8)
  axes[2].axvspan(x,y,color=col,alpha=.09);axes[3].axvspan(x,y,color=col,alpha=.09)
  axes[0].text((x+y)/2,8.6,room,ha='center',va='bottom',fontsize=8,color=col)
 axes[-1].xaxis.set_major_formatter(FuncFormatter(lambda x,pos:datetime.fromtimestamp(x,TZ).strftime('%H:%M:%S')))
 axes[-1].set_xlim(a,b);fig.suptitle(f'{name} | bathroom sensor only | raw, unsmoothed | green=bathroom, orange=kitchen')
 fig.savefig(OUT/f'{tag}-raw.png',dpi=130);plt.close(fig)
if __name__=='__main__':
 for case in CASES:plot_case(*case)
