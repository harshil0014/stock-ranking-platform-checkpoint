"""Compare the locked research candidate and audit date/security concentration."""
from pathlib import Path
import json,hashlib,sys,shutil
import numpy as np
import pandas as pd
from scipy.optimize import brentq
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'work/champion-open-search-20261105'
OUT=ROOT/'experiments/champion-open-search-20261105'
sys.path.insert(0,str(ROOT/'research/runners'))
from champion_market_review_20261031 import block_indices


def portfolio_rate(terminal,start,end):
    deposits=np.arange(np.datetime64(start),np.datetime64(end),np.timedelta64(30,'D'))
    years=(np.datetime64(end)-deposits).astype(float)/365.25
    return brentq(lambda r:7500*np.sum((1+r)**years)-terminal,-.999999,1e6)


def concentration(frame,period,winner):
    portfolio=pd.read_csv(OUT/(period+'_portfolios.csv'))
    pair=portfolio[portfolio.model.eq(winner)&portfolio.policy.eq('global_top20')].merge(
        portfolio[portfolio.model.eq('champion')&portfolio.policy.eq('global_top20')],
        on='decision_date',suffixes=('_new','_old')).sort_values('decision_date')
    dates=[]
    attribution={}
    for _,r in pair.iterrows():
        start=r.decision_date
        end=str((pd.Timestamp(start)+pd.DateOffset(months=12)).date())
        g=frame[frame.decision_date.eq(start)].set_index('isin',drop=False).rename_axis('identity')
        chosen={n:g.sort_values([n,'isin'],ascending=[False,True]).head(20)['isin'].tolist() for n in [winner,'champion']}
        deposits=np.arange(np.datetime64(start),np.datetime64(end),np.timedelta64(30,'D'))
        years=(np.datetime64(end)-deposits).astype(float)/365.25
        cash=7500*len(deposits)
        terminal={i:float(7500*np.sum((1+g.loc[i,'new_xirr'])**years)) for i in set(chosen[winner]+chosen['champion'])}
        for name,column in [(winner,'xirr_new'),('champion','xirr_old')]:
            reproduced=portfolio_rate(np.mean([terminal[i] for i in chosen[name]]),start,end)
            assert abs(reproduced-r[column])<1e-8,'Stock terminal labels do not reproduce portfolio'
        for i in terminal:
            contribution=(int(i in chosen[winner])-int(i in chosen['champion']))*(terminal[i]-cash)/20
            attribution[i]=attribution.get(i,0.)+contribution
        dates.append(dict(start=start,end=end,terminal=terminal,chosen=chosen,cash=cash))
    values=(pair.xirr_new-pair.xirr_old).to_numpy()
    results=[]
    for excluded in attribution:
        differences=[]
        for r in dates:
            rates=[]
            for name in [winner,'champion']:
                wealth=np.mean([r['cash'] if i==excluded else r['terminal'][i] for i in r['chosen'][name]])
                rates.append(portfolio_rate(wealth,r['start'],r['end']))
            differences.append(rates[0]-rates[1])
        results.append(float(np.mean(differences)))
    rng=np.random.default_rng(20261105)
    draws=np.array([values[block_indices(pair.decision_date.to_numpy(),365,rng)].mean() for _ in range(2000)])
    ordered=np.sort(values);cut=int(len(ordered)*.1)
    best=int(np.argmax(values))
    total_wealth=sum(attribution.values())
    return dict(period=period,matched_dates=len(pair),mean=float(values.mean()),median=float(np.median(values)),
        winsor=float(np.clip(ordered,ordered[cut],ordered[-cut-1]).mean()),
        worst_leave_one_date_out=float(min(np.delete(values,i).mean() for i in range(len(values)))),
        best_date=pair.iloc[best].decision_date,
        best_date_share_of_net_xirr_delta=float(values[best]/values.sum()) if values.sum() else None,
        worst_leave_one_security_out=float(min(results)),
        largest_security_share_of_net_terminal_wealth=float(max(attribution.values())/total_wealth) if total_wealth else None,
        low95=float(np.quantile(draws,.025)),high95=float(np.quantile(draws,.975)),securities_audited=len(attribution),
        deletion_policy='Replace removed allocation by zero-interest cash in both portfolios, no refill, preserve original blocked-date support',
        interpretation='Adaptive historical results, not fresh validation')


def main():
    lock=json.loads((OUT/'selection_lock.json').read_text())
    winner=lock['selected']
    transfer=json.loads((OUT/'transfer_receipt.json').read_text())
    assert transfer['selection_lock_sha256']==hashlib.sha256((OUT/'selection_lock.json').read_bytes()).hexdigest()
    rows=[];audit=[]
    for period in ['development','transfer']:
        summary=pd.read_csv(OUT/(period+'_summary.csv')).set_index('model')
        pairs=pd.read_csv(OUT/(period+'_portfolio_pairs.csv'))
        base=summary.loc['champion']
        names=list(summary.index) if period=='development' else ['champion',winner]
        for name in names:
            r=summary.loc[name]
            p=pairs[pairs.model.eq(name)&pairs.policy.eq('global_top20')].iloc[0]
            rows.append(dict(period=period,model=name,rank_ic=r.rank_ic,ic_delta=r.rank_ic-base.rank_ic,
                professor_gain_pp=100*(r.alignment-base.alignment),goal_gain_pp=100*(r.top3_goal_hit-base.top3_goal_hit),
                xirr_gain_pp=100*p.xirr_delta,dd_gain_pp=100*p.drawdown_delta,matched_dates=p.matched_dates))
        frame=pd.read_pickle(WORK/(period+'_scored.pkl.gz'),compression='gzip')
        audit.append(concentration(frame,period,winner))
        print('CONCENTRATION',period,audit[-1],flush=True)
    pd.DataFrame(rows).to_csv(OUT/'comparison.csv',index=False)
    (OUT/'concentration.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    text=['# Open champion comparison and locked historical transfer','',f"Selected experimental candidate: **{winner}**. User-authorized exploratory selection prioritizes development Top20SIPXIRR and accepts tradeoffs. The two new risk-budgeted policies were compared with the two saved constrained candidates. The winner was locked before its later-period scores were computed.",'','## Comparison','','| Period | Policy | RankIC | IC delta | Professor gain pp | Goal hit gain pp | Top20XIRR gain pp | Top20DD gain pp | Matched dates |','|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:text.append(f"| {r['period']} | {r['model']} | {r['rank_ic']:.5f} | {r['ic_delta']:+.5f} | {r['professor_gain_pp']:+.2f} | {r['goal_gain_pp']:+.2f} | {r['xirr_gain_pp']:+.2f} | {r['dd_gain_pp']:+.2f} | {int(r['matched_dates'])} |")
    text+=['','Development is2020–2023. Transfer is2024–2025, with immature or action-blocked portfolios excluded symmetrically by matched dates. Positive DDgain means less severe drawdown. RankIC is sector/date-averaged Spearman correlation with12monthSIPXIRR. Portfolio gains are mean matched snapshot-cohortXIRR differences, not chainable realized strategy returns. The champion is evaluated on the same feature cohort. Top3 goal support is jointly complete across this round’s candidates and can differ from prior reports.','','## What changed','','Risk-constrained variants add a decision-time downside252sum bound to the existing five professor-factor bounds. The selected sectorTop3 must match or improve all five professor percentile sums and, for new variants, have no greater historical downside-volatility sum than champion. This is a new optimization constraint. It does not guarantee future drawdown. No predictive model was retrained and no weight grid was searched. The old two candidates reuse their saved rankings. All candidate outcomes are recomputed together only to ensure a common comparison.','','The old zero-goal-loss and fixedIC nomination cutoffs are no longer selection gates in this user-authorized round. They were not retroactively changed in old reports. The candidate is selected by the preference declared in the new protocol and all tradeoffs remain visible.','','## Concentration and uncertainty','']
    for a in audit:
        text.append(f"- **{a['period']}**, {a['matched_dates']} matched dates. Mean gain {100*a['mean']:+.2f}pp, median {100*a['median']:+.2f}pp, winsorized {100*a['winsor']:+.2f}pp. Worst leave-one-date-out {100*a['worst_leave_one_date_out']:+.2f}pp. Worst leave-one-security-out {100*a['worst_leave_one_security_out']:+.2f}pp. Descriptive365day-block95%interval [{100*a['low95']:+.2f},{100*a['high95']:+.2f}]pp. Security-deletion audit covered {a['securities_audited']} securities. Best date was {a['best_date']}.")
    text+=['','Single-stock terminal wealth was recovered from corrected SIP labels and verified to reproduce every matched portfolioXIRR to1e-8. Removing a security retains its allocation as0%cash in both models with no replacement and no recovery of originally blocked observations. Contribution shares in JSON refer to net sums and can exceed100%when other contributions offset gains. They are not probabilities or additive XIRR stock attribution.','','## Interpretation and verification','','Later dates were already used in older project research. This transfer check is a locked-model historical diagnostic, not an independent or prospective holdout. Selection and parameters were not changed after transfer. Publication must report losses as well as gains. The six-year historical sample, overlapping cohorts, survivor identities, retrospective sectors and five-year factor eligibility limit generalization. Younger listings such as Nykaa remain outside this factor-complete pilot. Results cannot establish superiority over proprietary market software without their matched dated predictions.','','Nine local tests passed, including exact small-case optimization, factor preservation, optional risk-budget enforcement, tie handling, missing-data rejection and feature prefix invariance. The selection lock pins code and development evidence hashes. One worker/thread,WindowsCPU12.5%cap and4sactive/2srest were used. The website and prospective-ledger streams retain their existing configuration.']
    report=ROOT/'research/reports/champion_open_search_20261105.md'
    report.write_text('\n'.join(text)+'\n',encoding='utf-8',newline='\n')
    shutil.copy2(report,Path('C:/Users/Harshil/Documents/Codex/2026-10-31/you/outputs')/report.name)
    files=[p for p in OUT.iterdir() if p.is_file() and p.name!='manifest.json']+[report,ROOT/'research/protocols/champion_open_search_20261105.md',ROOT/'research/research_variant_ledger.csv',ROOT/'src/stock_research/constrained_selection.py',ROOT/'research/runners/champion_open_search_20261105.py',Path(__file__)]
    (OUT/'manifest.json').write_text(json.dumps([dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files],indent=2),encoding='utf-8')
    print(pd.DataFrame(rows).to_string(index=False),flush=True)


if __name__=='__main__':main()
