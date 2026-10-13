"""Compare Sept15 recordings, bathroom sensor only; raw values, labels annotations."""
import os,importlib.util,sqlite3
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/tmp/ld2410-mpl')
os.environ.setdefault('XDG_CACHE_HOME','/tmp/ld2410-cache')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('raw',HERE.parents[1]/'experiments/19-raw-signal-inspection/inspect_signals.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
fig,axes=plt.subplots(4,2,figsize=(16,10),sharey='row',constrained_layout=True)
colors=plt.get_cmap('tab10')
cases=[('labeled-walk-0915.db','You + wife in kitchen','18:50:40','18:52:20'),('labeled-loop-0915.db','You moving between rooms; wife in living room','19:24:10','19:26:55')]
for col,(name,title,start,end) in enumerate(cases):
 t,m,s,labs=r.load(name);a=r.stamp('2026-09-15 '+start);b=r.stamp('2026-09-15 '+end);q=(t>=a)&(t<b);x=t[q]-a
 for j,v in enumerate((m,s)):
  axes[j,col].pcolormesh(x,np.arange(9),v[q].T,shading='nearest',cmap='magma',vmin=0,vmax=100)
  axes[j,col].set_yticks(range(9));axes[j,col].set_ylabel(('Motion' if j==0 else 'Still')+' gate')
 for j,v in enumerate((m,s),2):
  for g in range(2,9):axes[j,col].plot(x,v[q,g],color=colors(g),lw=.8,label=f'Gate {g}')
  axes[j,col].set_ylim(0,105);axes[j,col].set_ylabel(('Motion' if j==2 else 'Still')+' energy');axes[j,col].grid(alpha=.15)
 for room,l,h in labs:
  l=max(a,l);h=min(b,h)
  if h<=l:continue
  if room=='bathroom':color='#00998e'
  elif room=='kitchen':color='#d48718'
  else:continue
  for ax in axes[:,col]:
   ax.axvline(l-a,color=color,ls='--',lw=.8);ax.axvline(h-a,color=color,ls='--',lw=.8)
  for ax in axes[2:,col]:ax.axvspan(l-a,h-a,color=color,alpha=.10)
  axes[0,col].text((l+h)/2-a,9, 'BATH' if room=='bathroom' else 'KITCHEN',ha='center',fontsize=8,color=color)
 for ax in axes[:,col]:ax.set_xlim(0,165)
 # Equal time scale: walk has no displayed data after its chosen 100-second interval.
 if b-a<165:
  for ax in axes[:,col]:ax.axvspan(b-a,165,color='#eeeeee');ax.axvline(b-a,color='#999999',lw=.5)
  axes[1,col].text(132,4,'End of selected\ncomparison interval',ha='center',color='#777777',fontsize=9)
 axes[0,col].set_title(name+'\n'+title+'\n'+start+'–'+end,fontsize=11,pad=25)
 axes[-1,col].set_xlabel('Seconds from '+start+' (same time scale in both columns)')
 axes[2,col].legend(ncol=4,fontsize=8,loc='upper right')
fig.colorbar(ScalarMappable(norm=Normalize(0,100),cmap='magma'),ax=axes[:2,:].ravel().tolist(),label='Reported energy (0–100)',shrink=.8,pad=.01)
fig.suptitle('September 15: simultaneous occupancy versus solo bathroom/kitchen loop\nBathroom sensor only • raw samples • green: you in bathroom; orange: you in kitchen',fontsize=14)
fig.savefig(HERE/'walk-vs-loop.png',dpi=150)
