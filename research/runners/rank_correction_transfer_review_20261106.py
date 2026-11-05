"""Review the exact candidate's later-period returns and promotion readiness."""
from pathlib import Path
import json,hashlib,shutil,sys
import numpy as np
import pandas as pd
import open_search_review_20261105 as shared
from open_search_review_20261105 import portfolio_rate
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'work/rank-correction-transfer-20261106'
OUT=ROOT/'experiments/rank-correction-transfer-20261106'
NAME='error_corrected_professor'


def main():
    frame=pd.read_pickle(WORK/'transfer_scored.pkl.gz',compression='gzip')
    shared.OUT=OUT
    concentration=shared.concentration(frame,'transfer',NAME)
    (OUT/'concentration.json').write_text(json.dumps(concentration,indent=2),encoding='utf-8')
    summary=pd.read_csv(OUT/'transfer_summary.csv').set_index('model')
    pairs=pd.read_csv(OUT/'transfer_portfolio_pairs.csv')
    p=pairs[pairs.model.eq(NAME)&pairs.policy.eq('global_top20')].iloc[0]
    b=summary.loc['champion'];r=summary.loc[NAME]
    controls=[]
    for date,g in frame.groupby('decision_date'):
        end=str((pd.Timestamp(date)+pd.DateOffset(months=12)).date())
        deposits=np.arange(np.datetime64(date),np.datetime64(end),np.timedelta64(30,'D'))
        years=(np.datetime64(end)-deposits).astype(float)/365.25
        terminal=pd.Series({i:float(7500*np.sum((1+value)**years)) for i,value in zip(g['isin'],g.new_xirr) if np.isfinite(value)})
        for name,col in [(NAME,NAME),('champion_raw_global','champion_score')]:
            chosen=g.sort_values([col,'isin'],ascending=[False,True]).head(20)['isin']
            valid=all(i in terminal.index for i in chosen)
            value=portfolio_rate(terminal.loc[chosen].mean(),date,end) if valid else np.nan
            controls.append(dict(decision_date=date,model=name,xirr=value,valid=valid))
    control=pd.DataFrame(controls);control.to_csv(OUT/'raw_champion_control.csv',index=False)
    pair=control[control.model.eq(NAME)&control.valid].merge(control[control.model.eq('champion_raw_global')&control.valid],on='decision_date',suffixes=('_new','_old'))
    raw_delta=float((pair.xirr_new-pair.xirr_old).mean())
    folds=pd.read_csv(OUT/'folds.csv')
    assert all(folds.last_label_endpoint<folds.year.astype(str)+'-01-01')
    for _,f in folds.iterrows():assert hashlib.sha256((WORK/f"model_{f['year']}.txt").read_bytes()).hexdigest()==f.model_sha256
    solver=pd.read_csv(OUT/'solver_receipts.csv')
    assert solver.minimum_factor_gain.ge(-1e-7).all()
    receipt=dict(candidate=NAME,transfer_xirr_gain_pp=100*p.xirr_delta,transfer_dd_gain_pp=100*p.drawdown_delta,
        matched_dates=int(p.matched_dates),ic_delta=float(r.rank_ic-b.rank_ic),goal_delta_pp=float(100*(r.top3_goal_hit-b.top3_goal_hit)),
        professor_alignment_delta_pp=float(100*(r.alignment-b.alignment)),changed_sector_top3_fraction=float(r.changed),
        raw_champion_gain_pp=100*raw_delta,raw_champion_matched_dates=len(pair),
        parameters_changed=False,fresh_holdout=False,source_runtime_changed=False,tests_passed=9,
        promotion_status='REVIEW_REQUIRED',documented_attempts=len(pd.read_csv(ROOT/'research/research_variant_ledger.csv')))
    (OUT/'promotion_review.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    portfolio=pd.read_csv(OUT/'transfer_portfolios.csv')
    a=portfolio[portfolio.model.eq(NAME)&portfolio.policy.eq('global_top20')].merge(portfolio[portfolio.model.eq('champion')&portfolio.policy.eq('global_top20')],on='decision_date',suffixes=('_new','_old'))
    a['delta']=a.xirr_new-a.xirr_old
    annual=a.groupby(a.decision_date.str[:4]).delta.mean();annual.to_csv(OUT/'annual_portfolio_delta.csv')
    text=['# Exact rank-correction candidate, later-period test','',f"Candidate **{NAME}**, frozen November5algorithm, evaluated on2024–2025. Two annual models were fitted using only outcomes mature before each test year. Model parameters,0.25correction and professor constraints were held fixed.",'','| Metric | Development2020–2023 | Later2024–2025 |','|---|---:|---:|',
        f'| GlobalTop20SIPXIRR gain | +5.44pp | {100*p.xirr_delta:+.2f}pp |',
        f'| GlobalTop20drawdown gain | +0.60pp | {100*p.drawdown_delta:+.2f}pp |',
        f'| Sector/date rankIC gain | +0.000001 | {r.rank_ic-b.rank_ic:+.6f} |',
        f'| SectorTop3goalhit gain | +0.00pp | {100*(r.top3_goal_hit-b.top3_goal_hit):+.2f}pp |',
        f'| Professor alignment gain | +0.00pp | {100*(r.alignment-b.alignment):+.2f}pp |',
        f'| SectorTop3sets changed | 0% | {100*r.changed:.2f}% |',
        f'| MatchedTop20dates | 16 | {int(p.matched_dates)} |','',
        'Positive drawdown gain means a less severe drawdown. These are matched mean snapshot-cohort12monthSIPXIRRs using next adjustedOpen,100bp each side,fractionalshares and existing unresolved-action blocks. They are not chained strategy returns. Later outcomes were used by earlier research and are a historical transfer diagnostic, not fresh confirmation.','',
        '## Robustness','',
        f"Median date gain {100*concentration['median']:+.2f}pp,winsorized {100*concentration['winsor']:+.2f}pp,worst leave-one-date-out {100*concentration['worst_leave_one_date_out']:+.2f}pp,worst leave-one-security-out {100*concentration['worst_leave_one_security_out']:+.2f}pp. Descriptive365day-block95%interval[{100*concentration['low95']:+.2f},{100*concentration['high95']:+.2f}]pp.",
        f"Raw-score global champion control: candidate minus control {100*raw_delta:+.2f}pp on{len(pair)}matched dates. This avoids treating sector-normalization tie-breaking as the sole benchmark.",
        'Annual matchedTop20differences: '+', '.join(f'{year} {100*value:+.2f}pp' for year,value in annual.items())+'.','',
        'Stock deletion replaces that allocation by0%cash in both portfolios without refill. Corrected stock-label terminal wealth was checked to reproduce all portfolioXIRRs to1e-8. Individual stocks are not published.','',
        '## Deployment scope','',
        'The tested candidate primarily changes cross-sector globalTop20selection. The current website defaults to within-sector champion rankings, with4,436identities and profile-dependent SIP adjustments. This research cohort requires all five professor factors plus residual histories, so it does not cover all those identities. Promoting its name without delivering the tested global selection and honest coverage would misrepresent the model. Current input files are frozen October3,2026, and the daily champion-input pipeline remains unverified. The separate prospective ledger must not be relabeled as forecasts from this candidate.','',
        '## Verification','',
        'Nine feature/optimizer tests passed. Training maturity,fold-model hashes and every professor constraint were checked. The low-load governor enforced one worker/thread,12.5%CPUcap,4seconds active/2seconds rest. Raw inputs,protocol and scorer hashes are retained. There were no changes to coefficients or features after viewing transfer outcomes.']
    report=ROOT/'research/reports/rank_correction_transfer_20261106.md';report.write_text('\n'.join(text)+'\n',encoding='utf-8',newline='\n')
    shutil.copy2(report,Path('C:/Users/Harshil/Documents/Codex/2026-10-31/you/outputs')/report.name)
    files=[p for p in OUT.iterdir() if p.is_file() and p.name!='manifest.json']+[report,ROOT/'research/protocols/rank_correction_transfer_20261106.md',ROOT/'research/research_variant_ledger.csv',ROOT/'research/runners/rank_correction_transfer_20261106.py',Path(__file__)]
    (OUT/'manifest.json').write_text(json.dumps([dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files],indent=2),encoding='utf-8')
    print(json.dumps(receipt,indent=2),flush=True)


if __name__=='__main__':main()
