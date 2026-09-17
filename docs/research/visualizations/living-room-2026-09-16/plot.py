"""Raw living-room gate data against recorded integration state."""
import os,sqlite3,json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
os.environ.setdefault('MPLCONFIGDIR','/tmp/ld2410-mpl')
os.environ.setdefault('XDG_CACHE_HOME','/tmp/ld2410-cache')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
HERE=Path(__file__).resolve().parent
DB=HERE.parents[3]/'tests/fixtures/recordings/living-room-continuous-occupancy-2026-09-16.db'
SENSOR='FD:68:3B:41:6E:FF';TZ=ZoneInfo('America/New_York')
with sqlite3.connect(f'file:{DB}?mode=ro',uri=True) as c:
 frames=c.execute('select ts,move,still from frames where sensor_id=? order by ts',(SENSOR,)).fetchall()
 states=c.execute("select ts,state,attributes from states where entity_id='binary_sensor.living_room_living_room_rear_occupancy' order by ts").fetchall()
 events=c.execute("select ts_utc,kind from events where sensor_id=? and kind in ('occupied','vacant') order by ts_utc",(SENSOR,)).fetchall()
t=np.array([x[0] for x in frames]);m=np.array([list(x[1]) for x in frames]);st=np.array([list(x[2]) for x in frames]);ut=np.array([x[0] for x in states]);occ=np.array([x[1]=='on' for x in states],int);conf=np.array([json.loads(x[2]).get('confidence',np.nan) if x[2] else np.nan for x in states]);cols=plt.get_cmap('tab10')
def stamp(s):return datetime.fromisoformat('2026-09-16 '+s).replace(tzinfo=TZ).timestamp()
def timefmt(ax):
 import matplotlib.dates as md
 ax.xaxis.set_major_formatter(DateFormatter('%H:%M:%S',tz=TZ))
def render(name,lo,hi):
 q=(t>=lo)&(t<=hi);r=(ut>=lo)&(ut<=hi)
 fig,ax=plt.subplots(4,1,figsize=(15,10),sharex=True,constrained_layout=True,gridspec_kw={'height_ratios':[1,1,1.15,.75]})
 x=np.array([datetime.fromtimestamp(v,TZ) for v in t[q]])
 ux=np.array([datetime.fromtimestamp(v,TZ) for v in ut[r]])
 for j,v in enumerate((m,st)):
  ax[j].pcolormesh(x,np.arange(9),v[q].T,shading='nearest',cmap='magma',vmin=0,vmax=100,rasterized=True)
  ax[j].set_yticks(range(9));ax[j].set_ylabel(('Motion' if j==0 else 'Still')+' gate')
 for g in range(2,8):ax[2].plot(x,st[q,g],color=cols(g),lw=.7,label=f'Gate {g}')
 ax[2].set_ylim(0,105);ax[2].set_ylabel('Still energy');ax[2].legend(ncol=6,fontsize=8,loc='upper right')
 ax[3].step(ux,occ[r],where='post',color='#167a72',lw=2,label='Recorded occupancy')
 ax[3].plot(ux,conf[r],color='#3061ac',lw=.7,alpha=.7,label='Reported confidence')
 ax[3].set_yticks([0,1]);ax[3].set_ylabel('State / confidence');ax[3].set_ylim(-.08,1.08);ax[3].legend(loc='upper right',fontsize=8,ncol=2)
 for tt,kind in events:
  if lo<=tt<=hi:
   dt=datetime.fromtimestamp(tt,TZ)
   for a in ax:a.axvline(dt,color='#b6243b' if kind=='vacant' else '#17a87b',ls='--',lw=.8,alpha=.9)
 for a in ax:a.grid(alpha=.10)
 timefmt(ax[3]);ax[3].set_xlim(datetime.fromtimestamp(lo,TZ),datetime.fromtimestamp(hi,TZ));ax[3].set_xlabel('Sept 16 local time • green dashed = occupied event, red dashed = vacant event')
 fig.colorbar(ScalarMappable(norm=Normalize(0,100),cmap='magma'),ax=ax[:2].tolist(),pad=.01,label='Raw energy 0–100',shrink=.8)
 fig.suptitle('Living room: user seated throughout • raw sensor gates vs integration state\nGate 2 still is saturated at 100 for the entire recording',fontsize=14)
 fig.savefig(HERE/name,dpi=140);plt.close(fig)
render('full-recording.png',float(t[0]),float(t[-1]))
render('first-false-clears.png',stamp('07:50:20'),stamp('07:52:40'))
render('later-false-clears.png',stamp('08:09:45'),stamp('08:11:10'))
