"""Aggregate evidence for constrained Top3 selection and commercial access review."""
from pathlib import Path
import json,hashlib,shutil,sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'work/constrained-ranking-20261105'
OUT=ROOT/'experiments/constrained-ranking-20261105'
sys.path.insert(0,str(ROOT/'work/round2-plot-deps'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    decision=json.loads((OUT/'decision.json').read_text())
    summary=pd.read_csv(OUT/'development_summary.csv').set_index('model')
    pairs=pd.read_csv(OUT/'development_portfolio_pairs.csv')
    receipts=pd.read_csv(OUT/'solver_receipts.csv')
    base=summary.loc['champion']
    rows=[]
    for name,r in summary.iterrows():
        p=pairs[pairs.model.eq(name)&pairs.policy.eq('global_top20')].iloc[0]
        rows.append(dict(model=name,rank_ic=r.rank_ic,ic_delta=r.rank_ic-base.rank_ic,professor_gain_pp=100*(r.alignment-base.alignment),goal_gain_pp=100*(r.top3_goal_hit-base.top3_goal_hit),top3_stock_dd_gain_pp=100*(r.top3_stock_dd-base.top3_stock_dd),top20_xirr_gain_pp=100*p.xirr_delta,top20_dd_gain_pp=100*p.drawdown_delta,changed_top3_percent=100*r.changed,portfolio_dates=p.matched_dates))
    comparison=pd.DataFrame(rows)
    comparison.to_csv(OUT/'comparison.csv',index=False)
    x=pd.read_pickle(WORK/'development_scored.pkl.gz',compression='gzip')
    factors=['q_annual_consistency','q_cagr3','q_cagr5','q_high_recency','q_sip_profit']
    alignment=[]
    for (date,sector),g in x.groupby(['decision_date','sector']):
        for name in summary.index:
            selected=g.sort_values([name,'isin'],ascending=[False,True]).head(3)
            alignment.append(dict(decision_date=date,sector=sector,model=name,days_since_high=-selected.high_recency.mean(),**{f:selected[f].mean() for f in factors}))
    alignment=pd.DataFrame(alignment)
    alignment.to_csv(OUT/'factor_alignment.csv',index=False)
    portfolio=pd.read_csv(OUT/'development_portfolios.csv')
    uncertainty=[]
    sys.path.insert(0,str(ROOT/'research/runners'))
    from champion_market_review_20261031 import block_indices
    for name in ['constrained_residual','constrained_high']:
        a=portfolio[portfolio.model.eq(name)&portfolio.policy.eq('global_top20')].merge(portfolio[portfolio.model.eq('champion')&portfolio.policy.eq('global_top20')],on='decision_date',suffixes=('_new','_old')).sort_values('decision_date')
        values=(a.xirr_new-a.xirr_old).to_numpy();rng=np.random.default_rng(20261105)
        draws=np.array([values[block_indices(a.decision_date.to_numpy(),365,rng)].mean() for _ in range(2000)])
        uncertainty.append(dict(model=name,dates=len(a),mean=values.mean(),low95=np.quantile(draws,.025),high95=np.quantile(draws,.975),interpretation='Descriptive block-bootstrap interval on adaptively reused development, not fresh validation'))
    pd.DataFrame(uncertainty).to_csv(OUT/'portfolio_uncertainty.csv',index=False)
    text=['# Professor-constrained stock selection, 5 November 2026','',f"Development investment/preference nominees: **{', '.join(decision['nominees']) or 'none'}**. Two new constrained selection policies were tested. Exposed outcomes were not evaluated.",'','## Change in approach','','The saved residual objectives rank stocks first. A mixed-integer optimization then chooses exactly three stocks per sector/date, maximizing the objective while requiring each of five professor-factor percentile sums to match or exceed the champion trio. Both the residual-momentum and residual-high objectives are tested once. This is a constrained selection policy, with no blend grid or predictive-model retraining. It explicitly reuses the new residual inputs from the immediately prior pilot rather than claiming they are newly discovered again.','','The constraints separately protect annual consistency,CAGR3,CAGR5,raw-high recency and trailing SIPprofit on each sectorTop3 set. They do not prescribe each stock’s weight, raw-day averages, Top1/Top2 alignment or globalTop20 alignment. Selected trios are ordered by the original objective, then the remaining stocks follow that objective. Original sorted score values are reassigned to this ordering with nextafter tie resolution.','','## Development comparison, 2020–2023','','| Policy | RankIC | IC delta | Professor gain pp | Goal hit gain pp | Top3 stock DD gain pp | Top20 XIRR gain pp | Top20 DD gain pp | Changed Top3 % | Matched Top20 dates |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:text.append(f"| {r['model']} | {r['rank_ic']:.5f} | {r['ic_delta']:+.5f} | {r['professor_gain_pp']:+.2f} | {r['goal_gain_pp']:+.2f} | {r['top3_stock_dd_gain_pp']:+.2f} | {r['top20_xirr_gain_pp']:+.2f} | {r['top20_dd_gain_pp']:+.2f} | {r['changed_top3_percent']:.1f} | {r['portfolio_dates']} |")
    text+=['','Higher DD gain means a less severe drawdown. RankIC is within-sector Spearman correlation with twelve-month SIPXIRR, sector-balanced then date-balanced. GlobalTop20 comparisons are matched by date and cost100bp per buy and final sale, using next adjusted Open and the existing corporate-action exclusions. Snapshot coverage inherits the five-year factor requirement and current-survivor, retrospective-sector limitations. Comparisons are against the same reduced common-cohort champion rather than all4,436current stocks.','','## Fixed decisions','']
    for d in decision['candidates']:
        failed=[k for k,v in d['checks'].items() if not v]
        text.append(f"- **{d['model']}**. Positive portfolio years {d['positive_years']}/4. Winsorized return gain {100*d['winsor_xirr_delta']:+.2f}pp. Worst leave-one-date-out gain {100*d['worst_lodo_xirr_delta']:+.2f}pp. Solver fallback {100*d['fallback_fraction']:.2f}%. Failed requirements: {', '.join(failed) or 'none'}. Clears the prior incremental IC floor: {d['clears_prior_head_floor']}.")
    text+=['','The strict goal-hit requirement is the only failed primary requirement for both policies. The decrease is small in percentage points, but the criterion was not relaxed after results. Their positive IC increments also remain below the prior0.010134924head-family hurdle. These policies can be retained as experimental tradeoff candidates without describing them as validated replacements.']
    for u in uncertainty:
        text.append(f"- Descriptive365day-block95%Top20XIRR interval for {u['model']}: [{100*u['low95']:+.2f},{100*u['high95']:+.2f}]pp, on {u['dates']} matched dates.")
    text+=['','Both intervals include losses. In particular, the constrained-high policy’s annual average Top20XIRR differences are -8.69pp in2020,+2.01pp in2021,+5.18pp in2022and+10.41pp in2023. The three positive years and positive leave-one-date-out results do not establish stability in every market regime.']
    stress=OUT/'cost200_pairs.csv'
    if stress.exists():
        text+=['','## Higher-cost diagnostic','','After seeing primary results, we fixed an additional200bp-per-side replay of the same selections. This diagnostic does not change the primary gate or add candidate weights.']
        for _,r in pd.read_csv(stress).iterrows():text.append(f"- {r['model']}: Top20XIRR delta {100*r['xirr_delta']:+.2f}pp, drawdown delta {100*r['drawdown_delta']:+.2f}pp, {int(r['matched_dates'])} matched dates.")
        decision['documented_attempts']=len(pd.read_csv(ROOT/'research/research_variant_ledger.csv'))
    text+=['','This round asks a new investment-selection question. It accepts IC loss up to0.005 in exchange for at least1ppTop20XIRR gain, robust positive gains, at least3positive years, nonworsening goal hit and professor constraints, drawdown cost<=2pp and support. Those rules were fixed before this policy’s results. They differ from the preceding pilot’s IC-superiority question and must not be conflated. No result can turn reused development dates into independent validation.','','## Solver and audit','',f"{len(receipts)} sector/date/policy optimizations were logged. {int(receipts.optimal.sum())} returned confirmed optimal feasible solutions. Every actual outputTop3 set was independently checked against all five factor bounds. The champion set was a known feasible fallback. Eight tests passed, including exhaustive small-case comparison, preference constraint enforcement, missing-factor rejection, score ties, residual self-exclusion and prefix invariance. Both solver and feature calculations used one compute thread under the Windows12.5%CPUcap and4sactive/2srest governor. NoGPU.",'',f"The cumulative incomplete registry now contains {decision['documented_attempts']} documented attempts, with prior IDs preserved. Scan receipts cover409archived source paths and found no prior MILP/linear-programming/constrained-rerank implementation. This is evidence relative to saved history, not proof that every older informal search was catalogued.",'','## Commercial software comparison','','Official pages from Trendlyne,Tickertape,MarketsMojo and Stockopedia were reviewed. A matching historical Indian-stock score export was not obtained. Therefore numerical superiority to these platforms is unmeasured. [The access matrix and exact comparison contract](commercial_benchmark_access_20261105.md) describe the evidence needed. The academic and internal baselines are not substitutes for those proprietary predictions.','','## References','','- Celis,L.E.,Straszak,D.,&Vishnoi,N.K.(2018). Ranking with fairness constraints. ICALP2018. https://arxiv.org/abs/1704.06840. General constrained-ranking inspiration, adapted here to numerical preference-factor bounds rather than fairness categories.','- SciPy developers. scipy.optimize.milp documentation. https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html. Mixed-integer solver interface, with HiGHS threads fixed to1.','- Blitz,D.C.,Huij,J.,&Martens,M.(2011). Residual momentum. Journal of Empirical Finance,18(3),506–521. https://doi.org/10.1016/j.jempfin.2011.01.003. Residual-feature inspiration from the prior pilot.']
    report=ROOT/'research/reports/constrained_ranking_20261105.md'
    report.write_text('\n'.join(text)+'\n',encoding='utf-8',newline='\n')
    fig,axes=plt.subplots(1,2,figsize=(11,4.5))
    names=comparison.model.tolist();colors=['#444444','#2266aa','#1b7837']
    axes[0].barh(names,comparison.professor_gain_pp,color=colors);axes[0].set_title('Sector Top3 professor alignment gain (pp)')
    axes[1].barh(names,comparison.top20_xirr_gain_pp,color=colors);axes[1].set_yticklabels([]);axes[1].axvline(0,color='grey',lw=.8);axes[1].set_title('Matched Top20 SIP XIRR gain (pp)')
    fig.suptitle('Hard preference constraints | Development only | 100bp per side')
    fig.tight_layout(rect=[0,0,1,.94]);plot=ROOT/'research/reports/constrained_ranking_20261105.png';fig.savefig(plot,dpi=150);plt.close(fig)
    shutil.copy2(WORK/'novelty_code_scan.json',OUT/'novelty_code_scan.json')
    dest=Path('C:/Users/Harshil/Documents/Codex/2026-10-31/you/outputs')
    for p in [report,plot,ROOT/'research/reports/commercial_benchmark_access_20261105.md']:shutil.copy2(p,dest/p.name)
    files=[p for p in OUT.iterdir() if p.is_file() and p.name!='manifest.json']+[report,plot,ROOT/'research/reports/commercial_benchmark_access_20261105.md',ROOT/'research/protocols/constrained_ranking_20261105.md',ROOT/'research/research_variant_ledger.csv',ROOT/'src/stock_research/constrained_selection.py',ROOT/'research/runners/constrained_ranking_20261105.py',Path(__file__)]
    (OUT/'manifest.json').write_text(json.dumps([dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files],indent=2),encoding='utf-8')
    print(comparison.to_string(index=False),flush=True)


if __name__=='__main__':main()
