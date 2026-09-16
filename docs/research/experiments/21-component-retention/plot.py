import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/ld2410-mpl')
os.environ.setdefault('XDG_CACHE_HOME','/tmp/ld2410-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import analyze as a
f=a.b.new_fixture('labeled-walk-0915.db')
p,score,residual=a.replay(f.ts,f.move,f.still)
lo=min(x for c,x,y in f.spans);hi=max(y for c,x,y in f.spans)
q=(f.ts>=lo)&(f.ts<hi)
fig,axs=plt.subplots(3,1,figsize=(12,7),sharex=True,constrained_layout=True)
for g in range(2,7):axs[0].plot(f.ts[q],f.still[q,g],lw=1,label=f'gate {g}')
axs[0].set_ylabel('Raw still energy');axs[0].legend(ncol=5,loc='upper right',fontsize=8)
axs[1].plot(f.ts[q],score[q],color='#8254b8',lw=1)
axs[1].axhline(.4,color='black',ls='--',lw=.8,label='Fixed retention fraction 0.4');axs[1].legend(fontsize=8)
axs[1].set_ylabel('Stored footprint amplitude')
axs[2].step(f.ts[q],p[q].astype(int),where='post',color='#8254b8',lw=1.5,label='Prototype occupied')
axs[2].set_yticks([0,1]);axs[2].set_ylabel('Prototype state');axs[2].legend(fontsize=8)
for ax in axs:
 for c,x,y in f.spans:
  if c=='IN':ax.axvspan(x,y,color='#34a678',alpha=.15)
 ax.grid(alpha=.15)
axs[2].xaxis.set_major_formatter(FuncFormatter(lambda t,_:a.b.time.strftime('%H:%M:%S',a.b.time.localtime(t))))
axs[2].set_xlim(lo,hi)
axs[2].set_xlabel('Sept 15 local time; green = bathroom visit labels. Wife remains in kitchen throughout.')
fig.suptitle('Motion-anchored still footprint: clears after both visits, but fails older controls')
fig.savefig(a.HERE/'overlap-retention.png',dpi=150)
