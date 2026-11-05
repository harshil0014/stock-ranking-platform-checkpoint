"""Concentration plus raw-champion and randomized-tie portfolio controls."""
import os
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
    os.environ[key]='1'
from pathlib import Path
import hashlib,json,sys,shutil
import numpy as np
import pandas as pd
from open_search_review_20261105 import portfolio_rate
import open_search_review_20261105 as audit
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/champion-rank-correction-20261105'
WORK=ROOT/'work/champion-rank-correction-20261105'


def main():
    registration=dict(reason='Post-result diagnostic: within-sector rank normalization ties many sector leaders at1.0, so compare raw champion scores and randomized boundary ties',random_seeds=100,selection_updates=False)
    (OUT/'benchmark_audit_registration.json').write_text(json.dumps(registration,indent=2),encoding='utf-8')
    registry=ROOT/'research/research_variant_ledger.csv';ledger=pd.read_csv(registry)
    key='champion_rank_correction_20261105::benchmark_and_concentration_audit'
    if key not in set(ledger.id):
        ledger=pd.concat([ledger,pd.DataFrame([dict(id=key,family='champion_rank_correction_20261105',name='benchmark_and_concentration_audit',source='experiments/champion-rank-correction-20261105/benchmark_audit_registration.json',category='diagnostic_or_policy_attempt')])],ignore_index=True)
        ledger.to_csv(registry,index=False)
    x=pd.read_pickle(WORK/'development_scored.pkl.gz',compression='gzip')
    audit.OUT=OUT
    concentration=[audit.concentration(x,'development',n) for n in ['error_corrected_raw','error_corrected_professor']]
    for r,n in zip(concentration,['error_corrected_raw','error_corrected_professor']):r['model']=n
    (OUT/'concentration.json').write_text(json.dumps(concentration,indent=2),encoding='utf-8')
    rows=[];ties=[]
    for date,g in x.groupby('decision_date'):
        end=str((pd.Timestamp(date)+pd.DateOffset(months=12)).date())
        deposits=np.arange(np.datetime64(date),np.datetime64(end),np.timedelta64(30,'D'))
        years=(np.datetime64(end)-deposits).astype(float)/365.25
        terminal=pd.Series({i:float(7500*np.sum((1+r)**years)) for i,r in zip(g['isin'],g.new_xirr) if np.isfinite(r)})
        sorted_base=g.sort_values(['champion','isin'],ascending=[False,True])
        boundary=sorted_base.iloc[19].champion
        tied=sorted_base[np.isclose(sorted_base.champion,boundary,rtol=0,atol=1e-12)]
        fixed=sorted_base[sorted_base.champion.gt(boundary+1e-12)]
        ties.append(dict(decision_date=date,boundary_score=boundary,tied_stocks=len(tied),slots=20-len(fixed)))
        selections={name:g.sort_values([col,'isin'],ascending=[False,True]).head(20)['isin'].tolist()
            for name,col in [('champion','champion'),('champion_raw_global','champion_score'),('error_corrected_raw','error_corrected_raw'),('error_corrected_professor','error_corrected_professor')]}
        for seed in range(100):
            rng=np.random.default_rng(20261105+seed)
            ids=fixed['isin'].tolist()+rng.choice(tied['isin'].to_numpy(),20-len(fixed),replace=False).tolist()
            selections['tie_control_'+str(seed)]=ids
        for name,selected in selections.items():
            valid=all(i in terminal.index for i in selected)
            rate=portfolio_rate(terminal.loc[selected].mean(),date,end) if valid else np.nan
            rows.append(dict(decision_date=date,model=name,xirr=rate,valid=valid))
    frame=pd.DataFrame(rows)
    frame.to_csv(OUT/'benchmark_control_portfolios.csv',index=False)
    pd.DataFrame(ties).to_csv(OUT/'boundary_ties.csv',index=False)
    comparisons=[]
    for candidate in ['error_corrected_raw','error_corrected_professor']:
        for control in ['champion','champion_raw_global']+['tie_control_'+str(i) for i in range(100)]:
            p=frame[frame.model.eq(candidate)&frame.valid].merge(frame[frame.model.eq(control)&frame.valid],on='decision_date',suffixes=('_new','_old'))
            comparisons.append(dict(candidate=candidate,control=control,matched_dates=len(p),xirr_delta=float((p.xirr_new-p.xirr_old).mean())))
    comparison=pd.DataFrame(comparisons);comparison.to_csv(OUT/'benchmark_control_comparisons.csv',index=False)
    print(comparison[comparison.control.isin(['champion','champion_raw_global'])].to_string(index=False),flush=True)
    summary=pd.read_csv(OUT/'development_summary.csv').set_index('model')
    pairs=pd.read_csv(OUT/'development_portfolio_pairs.csv')
    base=summary.loc['champion']
    text=['# Champion rank-error correction and benchmark audit','', 'Four annual models learned future within-sector SIP return percentile minus the champion percentile, using only labels mature before each test year. Two fixed policies use the same predicted correction, either directly or with professor-factor constraints on sectorTop3. This is adaptive development research following earlier results. No2024–2025scores were computed for these new policies.','','## Development results, 2020–2023','','| Policy | RankIC | Goal hit delta pp | Professor alignment delta pp | SectorTop3 sets changed | Top20XIRR gain pp | Top20DD gain pp | Matched dates |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for name in ['champion','error_corrected_raw','error_corrected_professor']:
        r=summary.loc[name];p=pairs[pairs.model.eq(name)&pairs.policy.eq('global_top20')].iloc[0]
        text.append(f"| {name} | {r.rank_ic:.6f} | {100*(r.top3_goal_hit-base.top3_goal_hit):+.3f} | {100*(r.alignment-base.alignment):+.3f} | {100*r.changed:.2f}% | {100*p.xirr_delta:+.2f} | {100*p.drawdown_delta:+.2f} | {int(p.matched_dates)} |")
    text+=['','The constrained policy leaves every sectorTop3 set unchanged. Its globalTop20gain therefore comes from changing which sector leaders enter a cross-sector portfolio. It is not evidence of better within-sector Top3 picks. Ranking IC is essentially unchanged. Positive DDdelta means lower drawdown. The reference above is the existing within-sector-percentile-normalized champion used by these research pilots.','','## Stronger benchmark controls','','Many sector leaders share a normalized score of1.0. Earlier globalTop20replays break exact ties byISIN, so the global portfolio can be sensitive to that convention. After seeing the correction gain, we added a raw-champion-score portfolio and100random boundary-tie controls. Selections were made before checking outcomes. Unknown selected outcomes block that observation with no replacement. Each pair reports its own matched support. This is a diagnostic, not an additional selection step.']
    for _,r in comparison[comparison.control.isin(['champion','champion_raw_global'])].iterrows():
        text.append(f"- {r.candidate} versus {r.control}: {100*r.xirr_delta:+.2f}pp on{int(r.matched_dates)}matched dates.")
    for name in ['error_corrected_raw','error_corrected_professor']:
        controls=comparison[comparison.candidate.eq(name)&comparison.control.str.startswith('tie_control_')]
        text.append(f"- {name} versus100tie-control draws: median mean matched XIRR delta {100*controls.xirr_delta.median():+.2f}pp, range[{100*controls.xirr_delta.min():+.2f},{100*controls.xirr_delta.max():+.2f}]pp. Matched support ranges{int(controls.matched_dates.min())}–{int(controls.matched_dates.max())}dates. These random controls measure tie sensitivity on adaptively reused dates and do not supply independent validation.")
    text+=['','## Concentration checks','']
    for a in concentration:
        text.append(f"- {a['model']}: median date gain {100*a['median']:+.2f}pp,winsorized {100*a['winsor']:+.2f}pp,worst leave-one-date-out {100*a['worst_leave_one_date_out']:+.2f}pp,worst leave-one-security-out {100*a['worst_leave_one_security_out']:+.2f}pp. Descriptive block95%interval[{100*a['low95']:+.2f},{100*a['high95']:+.2f}]pp.")
    text+=['','Removed stock allocations stay as0%cash in both portfolios, with no refill. Single-stock terminal labels reproduce the existing actual-next-open portfolioXIRRs to1e-8before attribution. Raw-control and tie-control returns use that same verified terminal-wealth aggregation,100bp per side and identical monthly30daycashflows. These are overlapping12monthcohorts and a survivor-only,five-year-factor-complete sample. No fresh validation or proprietary-software comparison is claimed.','','## Relation to the earlier locked candidate','','The earlier risk_constrained_high policy was locked before its2024–2025transfer test. It gained2.34pp in development but lost0.78pp in later matchedTop20XIRR, with3.61ppworse drawdown. That lock and all failed results are retained. The error-correction policies were designed afterward and are evaluated only on development here. This distinction is required when reading the apparently larger correction gain.','','## Verification','','Nine residual/optimizer tests passed before this round. Fold receipts prove all training label endpoints preceded the corresponding test year. Four LightGBMmodels use one compute thread and fixed settings. Model files stay in ignoredwork with SHA256fold receipts. The actual professor-constrained output memberships are evaluated by the existing shared replay. The production website and prospective ledger retain their existing model configuration.']
    stress=OUT/'cost200_pairs.csv'
    if stress.exists():
        text+=['','## Double-cost diagnostic','','The same frozen selections were replayed using actual adjusted opens at200bp per side, after primary results. No scores or stock sets were changed.']
        for _,r in pd.read_csv(stress).iterrows():text.append(f"- {r['model']}: Top20SIPXIRR gain {100*r.xirr_delta:+.2f}pp,drawdown gain {100*r.drawdown_delta:+.2f}pp,{int(r.matched_dates)}matched dates.")
    p=pd.read_csv(OUT/'development_portfolios.csv')
    a=p[p.model.eq('error_corrected_professor')&p.policy.eq('global_top20')].merge(p[p.model.eq('champion')&p.policy.eq('global_top20')],on='decision_date',suffixes=('_new','_old')).sort_values('decision_date')
    a['delta']=a.xirr_new-a.xirr_old
    yearly=a.groupby(a.decision_date.str[:4]).delta.mean()
    text+=['','## Distribution across dates','',f"The professor-preserving policy improves{int(a.delta.gt(1e-8).sum())}of{len(a)}dates, ties{int(a.delta.abs().le(1e-8).sum())}, and loses{int(a.delta.lt(-1e-8).sum())}. Its median date improvement is zero. Annual average differences are "+', '.join(f'{year}: {100*value:+.2f}pp' for year,value in yearly.items())+'.']
    sys.path.insert(0,str(ROOT/'work/round2-plot-deps'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,4.6),gridspec_kw={'width_ratios':[2,1]})
    axes[0].bar(a.decision_date,100*a.delta,color=['#1b7837' if d>=0 else '#b2182b' for d in a.delta]);axes[0].tick_params(axis='x',rotation=70,labelsize=8);axes[0].axhline(0,color='grey',lw=.8);axes[0].set_title('Paired Top20 SIP XIRR gain by snapshot (pp)')
    axes[1].bar(yearly.index,100*yearly,color='#2166ac');axes[1].axhline(0,color='grey',lw=.8);axes[1].set_title('Mean gain by year (pp)')
    fig.suptitle('Professor-preserving rank-error correction | Adaptive development 2020–2023')
    fig.tight_layout(rect=[0,0,1,.94]);plot=ROOT/'research/reports/champion_rank_correction_20261105.png';fig.savefig(plot,dpi=150);plt.close(fig)
    report=ROOT/'research/reports/champion_rank_correction_20261105.md'
    report.write_text('\n'.join(text)+'\n',encoding='utf-8',newline='\n')
    destination=Path('C:/Users/Harshil/Documents/Codex/2026-10-31/you/outputs')
    for file in [report,plot]:shutil.copy2(file,destination/file.name)
    paths=[p for p in OUT.iterdir() if p.is_file() and p.name!='manifest.json']+[report,plot,ROOT/'research/protocols/champion_rank_correction_20261105.md',ROOT/'research/research_variant_ledger.csv',Path(__file__),ROOT/'research/runners/champion_rank_correction_20261105.py',ROOT/'research/runners/correction_cost_check_20261105.py']
    (OUT/'manifest.json').write_text(json.dumps([dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths],indent=2),encoding='utf-8')


if __name__=='__main__':main()
