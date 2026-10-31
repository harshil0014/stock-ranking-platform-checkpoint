"""Compact evidence and figures for the frozen majority-factor family."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'work/round2-plot-deps'))
import hashlib,json,zipfile,re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import professor_majority_20261031 as r


def table(frame):
    return '| '+' | '.join(str(c) for c in frame.columns)+' |\n| '+' | '.join(['---']*len(frame.columns))+' |\n'+''.join('| '+' | '.join(str(v) for v in row)+' |\n' for row in frame.itertuples(index=False,name=None))


def clean_prose(text):
    text=text.replace('3Y','3-year').replace('5Y','5-year').replace('1Y','1-year')
    text=re.sub(r'(?<=\d)(?=[A-Za-z])',' ',text)
    text=re.sub(r'\b(first|separate|roughly|approximately|only|after|before|of|than|about|on|in|with|least)(?=\d)',r'\1 ',text,flags=re.I)
    text=re.sub(r',(?=\S)',', ',text)
    return (text.replace('%of','% of').replace('%to','% to').replace('Top3','Top-3').replace('Top20','Top-20')
            .replace('ppworse','pp worse').replace('pploss','pp loss').replace('ppmean','pp mean').replace('ppcame','pp came')
            .replace('5086 bad3','5086bad3').replace('IC,','IC, '))


def uncertainty():
    rows=[];rng=np.random.default_rng(2026103109)
    for period in ['development','exposed']:
        q=pd.read_csv(r.OUT/f'queries_{period}.csv.gz')
        for metric in ['rank_ic','attainment3','drawdown3']:
            z=q.groupby(['decision_date','model'])[metric].mean().unstack('model').dropna()
            delta=z[r.NAMES[1:]].subtract(z.active_champion,axis=0)
            days=pd.to_datetime(delta.index).to_numpy(dtype='datetime64[D]').astype(int);n=len(days)
            for block in [365,730]:
                if n<3 or days[-1]-days[0]<block:
                    for name in r.NAMES[1:]:rows.append(dict(period=period,metric=metric,block_days=block,model=name,status='INSUFFICIENT_TEMPORAL_SPAN',dates=n,delta=np.nan,lower95=np.nan,upper95=np.nan))
                    continue
                values=delta.to_numpy();center=values.mean(0);span=days[-1]-days[0]+1
                blocks=[]
                for start in range(n):
                    order=np.r_[np.arange(start,n),np.arange(start)]
                    blocks.append(order[np.mod(days[order]-days[start],span)<block])
                draws=[]
                for _ in range(4000):
                    ids=[]
                    while len(ids)<n:ids.extend(blocks[int(rng.integers(n))].tolist())
                    draws.append(values[ids[:n]].mean(0))
                floor=float(np.quantile(np.max(np.abs(np.asarray(draws)-center),axis=1),.95))
                for j,name in enumerate(r.NAMES[1:]):rows.append(dict(period=period,metric=metric,block_days=block,model=name,status=f'PER_METRIC_SIMULTANEOUS_{len(r.NAMES)-1}_CANDIDATES',dates=n,delta=center[j],lower95=center[j]-floor,upper95=center[j]+floor))
    pd.DataFrame(rows).to_csv(r.OUT/'uncertainty.csv',index=False)


def main():
    summary=pd.read_csv(r.OUT/'summary.csv').rename(columns={'model':'model'})
    if 'model' not in summary:summary=summary.rename(columns={summary.columns[0]:'model'})
    decision=json.loads((r.OUT/'decision.json').read_text());audits=json.loads((r.OUT/'fit_audits.json').read_text())
    decision['portfolio_noninferiority']='NOT_ESTABLISHED_FROM_MATCHED_PROXY_COHORTS'
    (r.OUT/'decision.json').write_text(json.dumps(decision,indent=2)+'\n')
    current=pd.read_csv(r.OUT/'current_rankings.csv.gz');eligible=current.loc[current.factor_eligible].copy()
    overlap=[]
    for name in r.NAMES[1:]:
        sets={}
        for col in ['active_champion',name]:
            sets[col]=eligible.sort_values(['sector',col,'isin'],ascending=[True,False,True]).groupby('sector').head(3).groupby('sector')['isin'].agg(set).to_dict()
        rows=[(sector,len(before&sets[name][sector]),before!=sets[name][sector]) for sector,before in sets['active_champion'].items()]
        overlap.append(dict(model=name,sectors=len(rows),changed_sectors=sum(a[2] for a in rows),shared_slots=sum(a[1] for a in rows),slots=3*len(rows)))
    pd.DataFrame(overlap).to_csv(r.OUT/'current_overlap.csv',index=False)
    uncertainty()
    weights=audits[-1]['final_factor_weights']
    package=dict(model_id='professor_majority_factor90_learned_v1',as_of='2026-10-03',label='Retrospective majority-factor research lens',
                 factors=weights,champion_share=.1,transform='Full eligible within-sector percentiles; annual block is mean of five completed annual-return percentiles, then percentile-normalized',
                 eligibility='All factors complete,>=5peers,classified,active trading,SIP investment fraction>=.5,no known unresolved historical action; no imputation',
                 registered_candidates=r.NAMES[1:],selected_by_development=decision['selected_by_development'],production_promoted=False,fresh_forecast=False,
                 inputs_and_sources=json.loads((r.OUT/'source_receipt.json').read_text()),current_eligible=int(current.factor_eligible.sum()),current_total=len(current))
    r.save('model_package.json',package)
    figures=r.OUT/'figures';figures.mkdir(exist_ok=True)
    fig,axes=plt.subplots(1,3,figsize=(13,4),layout='constrained')
    labels=['Champion','Fixed80','Fixed90','Learned90'];colors=['#374151','#0f766e','#2563eb','#b45309']
    for period,marker in [('development','o'),('exposed','s')]:
        z=summary.loc[summary.period.eq(period)].set_index('model').loc[r.NAMES]
        for i,name in enumerate(r.NAMES):
            axes[0].scatter(z.loc[name,'rank_ic'],z.loc[name,'alignment']*100,color=colors[i],marker=marker,s=60,label=labels[i]+(' Dev' if period=='development' else ' Exposed'))
    axes[0].legend(ncol=2,loc='center',fontsize=7,framealpha=.9)
    axes[0].set(xlabel='Within-sector rank IC',ylabel='Mean selected factor percentile',title='Preference versus prediction')
    axes[1].barh(list(weights),np.asarray(list(weights.values()))*100,color='#0f766e');axes[1].set(xlabel='Percent of final score',title='Learned90: frozen current weights',xlim=(0,65))
    axes[1].text(.97,.03,'Champion component:10%',transform=axes[1].transAxes,ha='right',fontsize=8)
    axes[2].bar(['Eligible','Unavailable'],[current.factor_eligible.sum(),(~current.factor_eligible).sum()],color=['#2563eb','#9ca3af'])
    axes[2].set(ylabel='Issuers',title='Complete-factor current coverage')
    for ax in axes:ax.grid(alpha=.2,axis='y');ax.set_axisbelow(True)
    fig.suptitle('NSE/BSE majority-factor experiment — frozen October3 inputs; retrospective evidence',fontsize=12)
    fig.savefig(figures/'majority_factor_comparison.png',dpi=160);plt.close(fig)
    show=summary[['model','period','alignment','changed','rank_ic','attainment3','drawdown3']].copy()
    for col in ['alignment','changed','attainment3','drawdown3']:show[col]=show[col].map(lambda v:f'{v*100:.2f}%')
    show.rank_ic=show.rank_ic.map(lambda v:f'{v:.4f}')
    portfolio=pd.read_csv(r.OUT/'portfolio_paired.csv')
    for col in ['xirr_delta','drawdown_delta']:portfolio[col]=portfolio[col].map(lambda v:'unavailable' if pd.isna(v) else f'{v*100:+.2f}pp')
    text='# Majority-factor ranking experiment\n\nFrozen family before new scoring: commit5086bad3; source-support repair retains earlier mature rows without relaxing cutoffs. All history was previously exposed. No production replacement or fresh-input claim.\n\n'
    text+='## What was built\n\nA transparent weighted-percentile ranker and a positive Ridge adaptation. Fixed90 gives18%each to annual consistency,3Y CAGR,5Y CAGR,recorded-high recency and historical whole-share SIP profit,plus10%to champion. Fixed80 gives16%each and20%to champion. Learned90 assigns90%to the five factors,each at least9%of final score,and10%to champion. These are genuine score coefficients,not accuracy percentages or paper-prescribed optimal weights. The five-year annual block needs six year-end price boundaries. No current fundamentals were backcast.\n\n'
    text+='Positive Ridge constrains fitted coefficient signs; explicit normalization/floors enforce our weight budget. Monotonic trees alone do not guarantee this budget. Primary references: [scikit-learn Ridge](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html), [LightGBM constraints](https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html).\n\n'
    text+=f'## Decision\n\nDevelopment-selected candidate: **{decision["selected_by_development"] or "NONE"}**. Selection maximises development alignment gain subject to >=2percentile-point alignment gain,<=0.01IC loss,<=2ppselected-stock drawdown worsening,and>=10%changed sectors. This is an operational preference gate,not statistical proof. Exposed diagnostics do not change selection. Production promotion remains **false**.\n\n'
    text+='## Matched-cohort results\n\nAlignment is mean selected factor percentile,higher preferred; its improvement is partly mechanical and not predictive accuracy. Changed is mean fraction of sectorTop3sets differing from champion. DD is selected-stock drawdown,less negative preferred. All model comparisons use the same complete-factor cohort; these numbers must not be compared directly with the earlier75-policy full-universe averages.\n\n'+table(show)+'\n'
    text+='## Current coverage and actual stock replacements\n\n'+f'{int(current.factor_eligible.sum())}/{len(current)}issuers have the complete required factor evidence. Others have an unavailable lens,not fabricated factor values or rescaled weights. Production champion coverage is unchanged. Inputs remain dated3October2026.\n\n'+table(pd.DataFrame(overlap))+'\n'
    text+='## Final learned-factor coefficients\n\n'+table(pd.DataFrame([{'factor':k,'final_score_share':f'{v*100:.2f}%'} for k,v in weights.items()]+[{'factor':'champion','final_score_share':'10.00%'}]))+'\n'
    text+='## Portfolio cashflow diagnostic\n\nChampion-relative mean SIP XIRR and cashflow-adjusted drawdown differences at25bps per buy/final sale. Fractional-unit provider AdjClose proxy,7500per30days,12months. Matched/planned date counts matter. Missing selected paths/actions block the entire observation; no reweighting. These overlapping cohort means are not a chainable strategy CAGR or certified executable whole-share returns. No sparse positive result overrides selection.\n\n'+table(portfolio)+'\n'
    text+='## Integrity and uncertainty\n\nSeven learned fits record strict mature endpoints before each fold cutoff. Factor scores use full feature cohorts before outcome filtering. Missing selected future outcomes block Top3metrics for every compared model; no reselection after removing unknown outcomes. The first attempted fit correctly stopped when an initial left join lost earlier training rows; the fix retains those source rows and keeps missing champion scores missing. Failed logs/checkpoint are preserved locally.\n\nuncertainty.csv reports4000paired365/730day circular-block resamples with per-metric95%simultaneous bounds across the three candidates. These bounds do not jointly cover all metrics or turn already-exposed history into a holdout. Unsupported block spans are unavailable. Coverage/support tables and all fitted weights are included.\n\n'
    text+='## Limits and delivery\n\nOne base7500profile only. Current-survivor identities,retrospective sectors,provider-adjusted historical prices and incomplete corporate-action/fundamental certification remain. Fewer complete-history stocks may be a selective universe; champion is restricted identically for comparison. Five annual returns and3Y/5Y CAGR overlap. Recorded closing high is available-history high,not certified lifetime ATH. Absolute goal probabilities and commercial-platform superiority are untested here. Fresh daily champion inputs remain unresolved.\n\n'
    text+='![Majority-factor comparison](../../experiments/professor-majority-20261031/figures/majority_factor_comparison.png)\n'
    text=clean_prose(text)
    target=r.ROOT/'research/reports/professor_majority_20261031.md';target.write_text(text,encoding='utf-8')
    outputs=Path(r'C:\Users\Harshil\Documents\Codex\2026-10-31\you\outputs')
    (outputs/'Professor-majority-model-results-20261031.md').write_text(text.replace('../../experiments/professor-majority-20261031/figures/majority_factor_comparison.png','Professor-majority-model-comparison-20261031.png'),encoding='utf-8')
    (outputs/'Professor-majority-model-comparison-20261031.png').write_bytes((figures/'majority_factor_comparison.png').read_bytes())
    (outputs/'Professor-majority-model-current-rankings-20261031.csv.gz').write_bytes((r.OUT/'current_rankings.csv.gz').read_bytes())
    artifacts=[p for p in r.OUT.rglob('*') if p.is_file() and not p.name.endswith('.pkl.gz') and p.name!='evidence_manifest.json']
    r.save('evidence_manifest.json',{str(p.relative_to(r.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts})
    bundle=outputs/'Professor-majority-model-evidence-20261031.zip'
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
        for p in artifacts+[r.OUT/'evidence_manifest.json',target,r.PROTOCOL,r.ROOT/'src/stock_research/professor_factor_model.py',Path(r.__file__),Path(__file__),r.ROOT/'tests/test_professor_factor_model_20261031.py']:
            z.write(p,str(p.relative_to(r.ROOT)))
    with zipfile.ZipFile(bundle) as z:assert z.testzip() is None
    (outputs/'Professor-majority-model-evidence-20261031.sha256').write_text(hashlib.sha256(bundle.read_bytes()).hexdigest()+'  '+bundle.name+'\n')
    print(text[:4200],flush=True)


if __name__=='__main__':main()
