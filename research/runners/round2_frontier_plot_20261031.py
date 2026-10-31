from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'work/round2-plot-deps'))
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
r=Path('experiments/round2-hysteresis-20261031');q=pd.read_csv(r/'quarterly_frontier.csv');d=pd.read_csv(r/'daily_frontier.csv')
fig,axes=plt.subplots(1,3,figsize=(14,4.5),layout='constrained')
for period,g in q.groupby('period'):
 ax=axes[0];ax.plot(g.top3_churn*100,g.ic_delta,marker='o',label=period)
 for row in g.itertuples():
  if row.margin in [0,.02,.03,.05,.1]:ax.annotate(f'{row.margin:g}',(row.top3_churn*100,row.ic_delta),xytext=(4,-14 if period=='development' and row.margin==.03 else 5),textcoords='offset points',fontsize=7)
axes[0].axhline(-.001,color='gray',linestyle='--',lw=1);axes[0].legend();axes[0].set(title='Full champion: sparse saved dates',xlabel='Top-3 membership churn (%)',ylabel='SIP rank IC change')
axes[1].plot(d.top3_churn*100,d.ic_delta,marker='o',color='#38755b')
for row in d.itertuples():axes[1].annotate(f'{row.margin:g}',(row.top3_churn*100,row.ic_delta),xytext=(4,5),textcoords='offset points',fontsize=8)
axes[1].set(title='Daily price + recency component only',xlabel='Top-3 membership churn (%)',ylabel='Mature lump-return proxy IC change')
axes[2].plot(d.margin,d.fraction_entered_within5*100,marker='o',color='#ba5e39');axes[2].axhline(90,color='gray',linestyle='--',label='90% entry gate');axes[2].axvline(.03,color='gray',linestyle=':');axes[2].set(title='Daily persistent-leader entry',xlabel='Hysteresis margin',ylabel='Entered within 5 sessions (%)',ylim=(45,103));axes[2].legend()
for ax in axes:ax.grid(alpha=.18);ax.spines[['top','right']].set_visible(False)
fig.suptitle('Stability buys lag: 0.03 is the development lock, not a daily promotion',fontsize=13)
fig.savefig(r/'frontier.png',dpi=180);fig.savefig(r/'frontier.svg')
print('PLOTS WRITTEN')
