"""Visual comparisons of fixed arithmetic contrasts, no classifier or fit."""
from inspect_signals import *
import sys
sys.path.insert(0,str(OUT.parent/'15-gate-profile'))
import data
fig,axs=plt.subplots(2,3,figsize=(13,8),layout='constrained')
for col,(title,name) in enumerate([('Sept 15: separate rooms','labeled-loop-0915.db'),('Sept 15: simultaneous','labeled-walk-0915.db'),('Sept 9: close-wall','labeled-sessions-0909-d06e.db')]):
 t,m,s,labs=load(name)
 if col==2:
  fx=data.load(name[:-3]);labs=fx.spans
 elif col==1:
  labs=[('TW',stamp('2026-09-15 18:50:40'),stamp('2026-09-15 18:50:52')),('IN',stamp('2026-09-15 18:50:52'),stamp('2026-09-15 18:51:11')),('TW',stamp('2026-09-15 18:51:11'),stamp('2026-09-15 18:51:47')),('IN',stamp('2026-09-15 18:51:48'),stamp('2026-09-15 18:52:11')),('TW',stamp('2026-09-15 18:52:11'),stamp('2026-09-15 18:52:20'))]
 for want,label,color in [(False,'bathroom empty, kitchen active','#d48a17'),(True,'bathroom occupied','#258b51')]:
  idx=np.zeros(len(t),bool)
  for room,a,b in labs:
   is_in=room in ('IN','bathroom','toilet');is_tw=room in ('TW','kitchen','stove','island')
   if is_in==want and (is_in or is_tw):idx|=(t>=a)&(t<b)
  g2=s[idx,2];g3=s[idx,3];den=g2+g3
  axs[0,col].scatter(g2,g3,s=6,alpha=.22,color=color,label=label,rasterized=True)
  axs[1,col].scatter(den,np.divide(g2-g3,den,out=np.zeros_like(den),where=den>0),s=6,alpha=.22,color=color,rasterized=True)
 axs[0,col].plot([0,100],[0,100],color='black',lw=.8,ls='--');axs[0,col].set(xlim=(0,102),ylim=(0,102),xlabel='Still gate 2',ylabel='Still gate 3',title=title)
 axs[1,col].axhline(0,color='black',ls='--',lw=.8);axs[1,col].set(xlim=(0,202),ylim=(-.65,.65),xlabel='Gate 2 + gate 3 energy',ylabel='Normalized spatial slope (g2 − g3)/(g2 + g3)')
 for row in range(2):axs[row,col].grid(alpha=.15)
axs[0,0].legend(fontsize=8,loc='upper left')
fig.suptitle('Bathroom readings: a visible spatial difference, with overlap\nEvery labeled frame plotted; no model, smoothing, learned weights, or selected threshold',fontsize=13)
fig.savefig(OUT/'spatial-contrast.png',dpi=140)
