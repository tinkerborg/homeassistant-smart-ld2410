"""Raw signal comparisons; labels provide annotations only."""
import os, importlib.util
os.environ.setdefault('MPLCONFIGDIR','/tmp/ld2410-mpl')
os.environ.setdefault('XDG_CACHE_HOME','/tmp/ld2410-cache')
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('raw',HERE.parents[1]/'experiments/19-raw-signal-inspection/inspect_signals.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
colors=plt.get_cmap('tab10')
# All gates shown in heatmaps; same gate colors and raw 0..100 scales throughout.
def panels(ax,t,m,s):
 for j,v in enumerate((m,s)):
  ax[j].pcolormesh(t,np.arange(9),v.T,shading='nearest',vmin=0,vmax=100,cmap='magma',rasterized=True)
  ax[j].set_yticks(range(9));ax[j].set_ylabel(('Motion' if j==0 else 'Still')+' gate')
 for j,v in enumerate((m,s),2):
  for g in range(2,9):ax[j].plot(t,v[:,g],color=colors(g),lw=1,label=f'Gate {g}')
  ax[j].set_ylim(0,105);ax[j].set_ylabel(('Motion' if j==2 else 'Still')+' energy');ax[j].grid(alpha=.2)

f='labeled-walk-0915.db';t,m,s,labs=r.load(f)
a,b=r.stamp('2026-09-15 18:50:40'),r.stamp('2026-09-15 18:52:20');q=(t>=a)&(t<b)
fig,ax=plt.subplots(4,1,figsize=(13,9),sharex=True,constrained_layout=True)
panels(ax,t[q],m[q],s[q])
for room,x,y in labs:
 if room!='bathroom':continue
 for z in ax:
  z.axvline(x,color='#008c95',ls='--',lw=1.3);z.axvline(y,color='#008c95',ls='--',lw=1.3)
 for z in ax[2:]:z.axvspan(x,y,color='#008c95',alpha=.12)
 ax[0].text((x+y)/2,9,'BATHROOM VISIT',ha='center',fontsize=9,color='#00757d')
ax[2].legend(ncol=7,loc='upper right',fontsize=8)
ax[-1].xaxis.set_major_formatter(FuncFormatter(lambda x,_:r.datetime.fromtimestamp(x,r.TZ).strftime('%H:%M:%S')))
ax[-1].set_xlim(a,b);ax[-1].set_xlabel('Sept 15 local time • shaded spans: Rob in bathroom; wife in kitchen throughout')
fig.suptitle('What disappears when the bathroom occupant leaves?\nBathroom sensor only • raw samples, no smoothing • heatmaps: black=0, white=100',fontsize=14)
fig.savefig(HERE/'simultaneous.png',dpi=150);plt.close(fig)

f='labeled-sessions-0909-d06e.db';t,m,s,labs=r.load(f)
fig,axes=plt.subplots(4,2,figsize=(14,9),sharex='col',sharey='row',constrained_layout=True)
for col,(title,start) in enumerate([('Kitchen only — stove','2026-09-09 23:11:00'),('Bathroom — within longer toilet visit','2026-09-09 23:19:00')]):
 a=r.stamp(start);q=(t>=a)&(t<a+60)
 panels(axes[:,col],t[q]-a,m[q],s[q]);axes[0,col].set_title(title+'\n'+start[11:]+'–'+r.datetime.fromtimestamp(a+60,r.TZ).strftime('%H:%M:%S'),fontsize=11,pad=10)
 axes[-1,col].set_xlim(0,60);axes[-1,col].set_xlabel('Seconds from start of this excerpt')
axes[2,1].legend(ncol=4,fontsize=8,loc='upper right')
fig.suptitle('The harder comparison: kitchen bleed versus quiet bathroom presence\nSept 9 • separate sessions, not simultaneous • same scales and gate colors',fontsize=14)
fig.savefig(HERE/'quiet-vs-kitchen.png',dpi=150);plt.close(fig)
