"""Standalone scientific scorecard figures; no fitting or selection happens here."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'work/round2-plot-deps'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np,pandas as pd
OUT=ROOT/'experiments/champion-vs-market-20261031';FIG=OUT/'figures';FIG.mkdir(exist_ok=True);ANCHOR='active_champion'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.grid':True,'grid.alpha':.18,'figure.facecolor':'#f8fafc','axes.facecolor':'white','savefig.facecolor':'#f8fafc'})
def short(name):return name.replace('ml__','').replace('factor__','').replace('sequence__','').replace('__',' / ').replace('_',' ')
def save(fig,name):
 fig.savefig(FIG/(name+'.png'),dpi=160,bbox_inches='tight');fig.savefig(FIG/(name+'.svg'),bbox_inches='tight');plt.close(fig)
def main():
 x=pd.read_csv(OUT/'full/sector_summary.csv');dev=pd.read_csv(OUT/'full/development_deltas.csv');names=list(dict.fromkeys([ANCHOR]+dev.sort_values('attainment3',ascending=False).model.head(4).tolist()+dev.sort_values('rank_ic',ascending=False).model.head(4).tolist()));colors={ANCHOR:'#dc2626'}
 fig,axes=plt.subplots(1,2,figsize=(13,5))
 for ax,period in zip(axes,['development','exposed']):
  z=x[x.period.eq(period)];ax.scatter(z.rank_ic,z.attainment3*100,s=35,c='#94a3b8',alpha=.7)
  for name in names:
   r=z[z.model.eq(name)].iloc[0];ax.scatter(r.rank_ic,r.attainment3*100,s=90 if name==ANCHOR else 40,c=colors.get(name,'#2563eb'));ax.annotate(short(name),(r.rank_ic,r.attainment3*100),xytext=(5,5),textcoords='offset points',fontsize=7)
  ax.set(title=period.capitalize()+' (historical)',xlabel='Mean within-sector rank IC',ylabel='Top-3 goal attainment (%)')
 fig.suptitle('Champion versus all score policies: ordering and attainment are different objectives',fontsize=13,y=1.03);save(fig,'ranking_attainment_frontier')
 fig,axes=plt.subplots(1,3,figsize=(14,5));metrics=[('rank_ic','Rank IC difference'),('attainment3','Attainment difference (pp)'),('drawdown3','Drawdown difference (pp)')]
 show=names[1:];y=np.arange(len(show));d=x[x.period.eq('development')].set_index('model');e=x[x.period.eq('exposed')].set_index('model')
 for ax,(metric,label) in zip(axes,metrics):
  scale=1 if metric=='rank_ic' else 100
  ax.barh(y-.17,[(d.loc[n,metric]-d.loc[ANCHOR,metric])*scale for n in show],height=.32,color='#2563eb',label='Development')
  ax.barh(y+.17,[(e.loc[n,metric]-e.loc[ANCHOR,metric])*scale for n in show],height=.32,color='#f59e0b',label='Already exposed');ax.axvline(0,color='#334155',lw=1);ax.set_yticks(y,labels=[short(n) for n in show] if ax is axes[0] else []);ax.set_xlabel(label)
 axes[-1].legend(loc='best');fig.suptitle('Development-selected challengers versus frozen champion; higher is better',y=1.02);fig.tight_layout();save(fig,'champion_paired_tradeoffs')
 s=pd.read_csv(OUT/'full/stability_summary.csv');fig,axes=plt.subplots(1,2,figsize=(12,5))
 for ax,period in zip(axes,['development','exposed']):
  z=s[s.period.eq(period)].merge(x[x.period.eq(period)][['model','rank_ic']],on='model');ax.scatter(z.rank_ic,z.top3_churn*100,c='#64748b',s=30,alpha=.7)
  r=z[z.model.eq(ANCHOR)].iloc[0];ax.scatter(r.rank_ic,r.top3_churn*100,c='#dc2626',s=100,label='Frozen champion');ax.set(title=period.capitalize(),xlabel='Mean within-sector rank IC',ylabel='Top-3 membership churn (%)');ax.legend()
 fig.suptitle('Product stability: consecutive historical snapshots, full feature cohort',y=1.02);save(fig,'stability_accuracy_frontier')
 z=pd.read_csv(OUT/'sequence/sector_summary.csv');z=z[z.model.str.startswith('sequence__')|z.model.eq(ANCHOR)];fig,axes=plt.subplots(1,2,figsize=(13,5));order=[ANCHOR]+[n for n in z.model.unique() if n!=ANCHOR];y=np.arange(len(order))
 for ax,period in zip(axes,['development','exposed']):
  a=z[z.period.eq(period)].set_index('model').reindex(order);ax.barh(y,a.rank_ic,color=['#dc2626']+['#2563eb']*(len(order)-1));ax.set_yticks(y,labels=[short(n) for n in order]);ax.axvline(0,color='#334155',lw=1);ax.set(title=period.capitalize(),xlabel='Mean within-sector rank IC')
 fig.suptitle('Foreign architectures and same-input controls on the matched sequence cohort',y=1.02);fig.tight_layout();save(fig,'foreign_models_matched_cohort')
 print('FIGURES',len(list(FIG.glob('*.png'))),flush=True)
if __name__=='__main__':main()
