"""Review fixed majority-factor architectures and publish aggregate evidence only."""
from pathlib import Path
import ast,datetime,hashlib,json,shutil
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/professor-frontier-20261101';WORK=ROOT/'work/professor-frontier-20261101'


def table(z):
    return '| '+' | '.join(map(str,z.columns))+' |\n| '+' | '.join(['---']*len(z.columns))+' |\n'+''.join('| '+' | '.join(map(str,r))+' |\n' for r in z.itertuples(index=False,name=None))


def main():
    checks=[]
    def check(name,value):
        checks.append(dict(check=name,passed=bool(value)))
        if not value:raise AssertionError(name)
    protocol=ROOT/'research/protocols/professor_frontier_20261101.md'
    check('protocol unchanged',hashlib.sha256(protocol.read_bytes()).hexdigest()==json.loads((OUT/'protocol_receipt.json').read_text())['sha256'])
    receipts=json.loads((OUT/'input_receipts.json').read_text())
    for row in receipts:check('input hash '+row['path'],hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest()==row['sha256'])
    panel=pd.read_pickle(WORK/'corrected_panel.pkl.gz',compression='gzip')
    valid=panel.new_xirr.notna()
    check('all valid first fills after decision',panel.loc[valid,'first_fill'].gt(panel.loc[valid,'decision_date']).all())
    check('unknown labels retained with reason',panel.loc[~valid,'error'].ne('').all())
    check('unique stock-date input panel',not panel.duplicated(['isin','decision_date']).any())
    decision=json.loads((OUT/'decision.json').read_text());winner=decision['locked_preference_candidate']
    for path in sorted(OUT.glob('folds_*.csv')):
        folds=pd.read_csv(path)
        check('strict mature labels '+path.name,all(r.latest_label_endpoint<f'{r.year}-01-01' for r in folds.itertuples()))
    check('exposed only for locked preference candidate',decision['exposed_evaluated']==bool(winner))
    stock_support=[];correlations=[]
    for period in ['development']+(['exposed'] if winner else []):
        x=pd.read_pickle(WORK/f'{period}_scored.pkl.gz',compression='gzip')
        metrics=pd.read_csv(OUT/f'{period}_sector_metrics.csv');names=sorted(metrics.model.unique())
        check('all models have identical feature support '+period,len(metrics)==x.groupby(['decision_date','sector']).ngroups*len(names))
        check('Top3 availability is common to all models '+period,metrics.groupby(['decision_date','sector']).top3_complete.nunique().eq(1).all())
        for (date,sector),g in x.groupby(['decision_date','sector']):
            for name in names:
                correlations.append(dict(period=period,decision_date=date,sector=sector,model=name,rho=float(g[name].corr(g.champion,method='spearman'))))
        support=metrics[metrics.model.eq('champion')].groupby('decision_date').agg(sectors=('sector','size'),complete_top3=('top3_complete','sum'))
        support['period']=period;stock_support.append(support.reset_index())
        if period=='exposed':check('no exposed loser exploration',set(names)=={'champion','lens20','linear75',winner})
    pd.concat(stock_support).to_csv(OUT/'matched_sector_support.csv',index=False)
    corr=pd.DataFrame(correlations).groupby(['period','decision_date','model']).rho.mean().groupby(['period','model']).mean().reset_index()
    corr.to_csv(OUT/'rank_correlation.csv',index=False)
    summary=pd.read_csv(OUT/'development_summary.csv');pairs=pd.read_csv(OUT/'development_portfolio_pairs.csv')
    check('decision candidates exactly three',set(r['model'] for r in decision['candidates'])=={'balanced75','outrank75','tail75'})
    check('decision pass requires every registered check',all(r['pass_preference_budget']==all(r['checks'].values()) for r in decision['candidates']))
    eligible=[r for r in decision['candidates'] if r['pass_preference_budget']]
    expected=sorted(eligible,key=lambda r:(-r['alignment_gain'],r['model']))[0]['model'] if eligible else None
    check('development choice follows frozen rule',winner==expected)
    tests=WORK/'low-load-tests.log';check('focused tests pass','14 passed' in tests.read_text())
    (OUT/'integrity_checks.json').write_text(json.dumps(dict(all_passed=True,checks=checks),indent=2))
    (OUT/'test_receipt.json').write_text(json.dumps(dict(tests=14,passed=True,external_ci=False,log_sha256=hashlib.sha256(tests.read_bytes()).hexdigest()),indent=2))
    private_files=list(WORK.glob('*.pkl.gz'))+list((WORK/'labels').glob('*.pkl.gz'))+list((WORK/'models').glob('*.txt'))
    (OUT/'private_artifact_inventory.json').write_text(json.dumps([dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(private_files)],indent=2))
    view=summary[['model','alignment','rank_ic','top3_goal_hit','top3_stock_dd','changed','overlap']].copy()
    baseline=summary.set_index('model').loc['champion']
    view['IC_delta']=view.rank_ic-baseline.rank_ic
    for col in ['alignment','top3_goal_hit','top3_stock_dd','changed','overlap']:view[col]=(view[col]*100).map(lambda v:f'{v:.3f}')
    for col in ['rank_ic','IC_delta']:view[col]=view[col].map(lambda v:f'{v:.5f}')
    p=pairs.copy()
    tail_pair=pairs[pairs.model.eq('tail75')&pairs.policy.eq('global_top20')].iloc[0]
    tail_stock=summary.set_index('model').loc['tail75']
    for col in ['xirr_delta','drawdown_delta']:p[col]=(p[col]*100).map(lambda v:f'{v:.3f}')
    gate_rows=pd.DataFrame([dict(model=r['model'],pass_preference_budget=r['pass_preference_budget'],failed_checks=', '.join(k for k,v in r['checks'].items() if not v)) for r in decision['candidates']])
    uncertainty=pd.read_csv(OUT/'development_ic_uncertainty.csv')
    for col in ['ic_delta','low95','high95','familywise_ic_hurdle']:uncertainty[col]=uncertainty[col].map(lambda v:f'{v:.5f}')
    correlation=corr.copy();correlation.rho=correlation.rho.map(lambda v:f'{v:.5f}')
    exposed='Not evaluated: no candidate passed the registered development preference/risk budget.'
    if winner:
        es=pd.read_csv(OUT/'exposed_summary.csv');ep=pd.read_csv(OUT/'exposed_portfolio_pairs.csv')
        for c in ['alignment','top3_goal_hit','top3_stock_dd','changed','overlap']:es[c]=(es[c]*100).round(3)
        for c in ['xirr_delta','drawdown_delta']:ep[c]=(ep[c]*100).round(3)
        exposed=f'Only the locked candidate **{winner}** and references were evaluated, once. No reselection followed. These dates were already exposed in the broader project.\n\n'+table(es)+'\n'+table(ep)
    report=f'''# Professor-factor frontier: three larger departures

Three fixed candidates assign **75% of their score to the five measured professor
factor blocks**, against the champion, the20%lens and a plain linear75%control.
Locked preference candidate: **{winner or 'none'}**. No automatic production
promotion, fresh prospective holdout, or investment-superiority claim is made.

## What actually changed

- **balanced75:** geometric five-factor core. One very weak block cannot be fully
  compensated by four strong ones. Equal log elasticities; this is a joint75%
  nonlinear score component, not literal15%linear weight per factor.
- **outrank75:** sector peers vote across five factors. A stock must beat a peer
  in at least three blocks; a deficit larger than0.40in any block vetoes that win.
  Wins minus losses become a sector percentile.75%joint factor-voting component,
  with25%champion. This is a project-specific voting rule, not a replicated paper.
- **tail75:**75%arithmetic factor core,25%upper-quantile learned SIP forecast.
  The small LightGBM head has100trees,7leaves,depth3,quantile0.80and one thread,
  with no tuning. Five factor percentiles plus three price/risk inputs; annual
  training uses only corrected outcomes matured before January1. Its target is
  log1p(annual SIP XIRR clipped[-.95,3]), not calibrated goal probability or a
  prediction of2xreturns. [LightGBM's quantile objective and alpha parameter](https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html).

The five blocks remain annual-return consistency,3YCAGR,5YCAGR, recorded closing
high recency, and historical whole-share SIP profit. This is a preference derived
from the workbook, not weights prescribed by Sir's paper. Fundamental/earnings
fields have not been invented. All source features remain price/SIP oriented.
Nominal score mass is not independent influence, predictive accuracy, or profit.

## New outcome basis and explicit larger risk budget

The earlier training labels could start at the signal close. This batch generated
new per-stock12monthSIP outcomes:7500every30calendar days, cash until the first
observed open strictly after each deposit date, actual Open×AdjClose/Close,
100bp per buy and terminal sale, fractional shares, terminal last close at/before
the known horizon with maximum7day gaps. Unresolved provider/official action
windows and missing prices remain unknown. Old labels and old tables are intact.
The learned tail head trains on these corrected labels, not the old cashflows.

This intentionally allows a wider preference/risk tradeoff than the old20%lens:
alignment gain at least5percentile points, IC loss at most0.02, Top3goal-hit loss
at most3pp, average selected-stock drawdown at most5pp worse, and at least25%of
sectorTop3sets changed. Actual globalTop20portfolio XIRR must be no more than3pp
lower and drawdown no more than5pp worse, on at least8matched dates. These are
fixed retrospective research budgets, not a risk policy chosen by the professor.
At least8dates must each have20complete matched sector queries. No missing
selected-stock replacement. Highest alignment among passers, fixed name tie break.

## Development: preference and stock outcome comparison

2020–23; equal sector then date weighting. Alignment, hit rate, drawdown, changed
fraction and overlap are percent. IC and IC_delta are correlations. Alignment
compares the same input factors being weighted and is mechanically circular;
it measures preference fit, not an independent financial win.

{table(view)}

Top3sets are chosen before outcome filtering. If any model's selected stock has
an unknown label, the sector/date's Top3outcome statistics are unavailable for
every model. IC uses common valid stocks, at least5per sector. Alignment and
overlap use the full as-of feature cohort, independently of future labels.
The plain linear75%control shows whether nonlinear or learned complexity earns
anything beyond simply increasing the factor share. It is a reference, not an
extra candidate selected after results.

## Actual portfolio cashflows versus champion

100bp per side. XIRR and drawdown differences below are model minus champion,
in percentage points, on identical valid dates. Negative drawdown delta means
worse loss. GlobalTop20and equal-sectorTop3hold selection/weights fixed for the
12monthcohort and use the same monthly next-open contributions. These overlapping
cohort means are not a chainable strategy CAGR or a live SIP ladder simulation.

{table(p)}

The notable risky tradeoff is **tail75**: globalTop20mean XIRR exceeds the champion
by **{tail_pair.xirr_delta*100:.3f}pp** on **{int(tail_pair.matched_dates)}matched dates**,
but average portfolio drawdown is **{-tail_pair.drawdown_delta*100:.3f}pp worse**.
Its sectorTop3goal-hit rate is **{tail_stock.top3_goal_hit*100:.3f}%**, versus
**{baseline.top3_goal_hit*100:.3f}%** for champion, and broad rank IC is
**{tail_stock.rank_ic:.5f}**. This can be a different right-tail/risk exposure,
not a general ranking improvement. No volatility-matched tail control was in this
experiment, so the Top20gain is not established as stock-selection alpha. The
sectorTop3portfolio comparison has only two matched dates and cannot support a
performance claim. No public top picks or changed model result from this finding.

Only globalTop20is in the frozen pass gate; sectorTop3is a reported diagnostic.
Portfolio failures block complete observations; they do not remove stocks and
redistribute their weight. Missingness can bias the surviving observations.

## Frozen budget decision

{table(gate_rows)}

Passing this budget, if any candidate does, means only a candidate for preference
research. It does not establish improved investment performance. A permitted IC
loss can even produce negative IC; positive IC and a familywise hurdle are
separately required for a predictive-win claim.

365day centered block-bootstrap95% intervals for development IC differences,
with a max-statistic hurdle over the three new challengers,2000fixed-seed draws:

{table(uncertainty)}

## How different are the rankings?

Mean within-sector/date Spearman correlation with champion, equal dates:

{table(correlation)}

Changed sets and average membership overlap are reported above. A75%factor
component still shares information with the champion; this is not75%new signal.

## Locked exposed diagnostic

{exposed}

## Coverage, verification, and limitations

Corrected label cache: **{len(panel):,}stock-date rows**, **{int(valid.sum()):,}valid**,
**{int((~valid).sum()):,}unknown**, across{panel.decision_date.nunique()}dates.
Pre2020mature dates train the tail head;2020–23is development. All policies use
the same complete factor/price-input population. The model covers mapped NSE/BSE
identities with data, but provider quote venue and historical executions are not
independently certified. It does not constitute full NSE/BSE coverage.

The code fixes score architectures before looking, checkpoints labels per date,
pins protocol/input/model hashes, preserves unknowns, and locks development
selection before any exposed result. **14local tests and{len(checks)}integrity checks
passed.** Full scored memberships and trained models remain local; compact
aggregate outcomes, coverage, overlaps, failures and chronology receipts are
versioned. Local checks do not imply external CI or an investment audit passed.

Current-survivor identities, retrospective sector labels, provider adjustment
vintages, sparse overlapping horizons, and reused development periods remain
material limits. Archived factor input vintages and corporate-action knowledge
are not newly certified. The historical SIP-profit input still follows the
workbook's invested-capital convention; new outcome cashflows include all
scheduled deposits and idle cash. The two quantities are not interchangeable.
No circuit, suspension, market impact, tax or nominal whole-share execution
simulation is claimed. Guarding unresolved corporate actions is not repairing
their historical prices. There is still no fresh complete daily champion input
pipeline eligible to start the12monthholdout.

One research worker and compute thread, Windows CPUcap12.5%,4seconds active and
2seconds rest, no GPU,20minute worker watchdog. The champion, UI, both prospective
ledger branches, and daily ledger automation are unchanged. No stock-pick list,
real-money position, or regulatory performance claim was published.
'''
    import re
    report='\n'.join(line if line.startswith('|') or 'http' in line else re.sub(r'(?<=\d)(?=[A-Za-z])',' ',re.sub(r'(?<=[A-Za-z])(?=\d)',' ',line)) for line in report.splitlines())+'\n'
    report=report.replace('Top 3','Top-3').replace('Top 20','Top-20').replace('CPUcap','CPU cap').replace('3 Y','3Y').replace('5 Y','5Y')
    for a,b in {'balanced 75':'balanced75','outrank 75':'outrank75','tail 75':'tail75','linear 75':'linear75','the 20%lens':'the 20% lens','20%lens':'20% lens','75%control':'75% control','75%joint':'75% joint','25%champion':'25% champion'}.items():report=report.replace(a,b)
    for a,b in {'linear75% control':'linear 75% control','15%linear':'15% linear','percentile.75%':'percentile. 75%',
        '**tail75:**75%arithmetic':'**tail75:** 75% arithmetic','core,25%upper':'core, 25% upper',
        'trees,7 leaves,depth 3,quantile':'trees, 7 leaves, depth 3, quantile','log 1 p':'log1p',
        'prediction of2xreturns':'prediction of doubling returns','consistency,3YCAGR,5YCAGR':'consistency, 3Y CAGR, 5Y CAGR',
        'globalTop-20':'global Top-20','sectorTop-3':'sector Top-3','12 monthcohort':'12-month cohort',
        '12 monthholdout':'12-month holdout','%,4 seconds':'%, 4 seconds','GPU,20 minute':'GPU, 20-minute',
        '12 monthSIP':'12-month SIP','every 30 calendar':'every 30 calendar','7 day gaps':'7-day gaps'}.items():report=report.replace(a,b)
    reportpath=ROOT/'research/reports/professor_frontier_20261101.md';reportpath.write_text(report,encoding='utf-8',newline='\n')
    output=Path(r'C:\Users\Harshil\Documents\Codex\2026-10-31\you\outputs');shutil.copyfile(reportpath,output/'professor_frontier_20261101.md')
    files=[ROOT/'src/stock_research/professor_frontier.py',ROOT/'tests/test_professor_frontier_20261101.py',ROOT/'research/runners/professor_frontier_20261101.py',Path(__file__)]
    for p in files:ast.parse(p.read_text())
    logs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in WORK.glob('*.log') if p.name!='low-load-review.log']
    (OUT/'log_inventory.json').write_text(json.dumps(logs,indent=2))
    files+=[protocol,reportpath]+sorted(p for p in OUT.iterdir() if p.is_file() and p.name!='manifest.json')
    manifest=dict(created_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(set(files))])
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2));shutil.copyfile(OUT/'manifest.json',output/'professor_frontier_20261101_manifest.json')
    print('REVIEW',len(checks),'checks;14tests; report complete',flush=True)


if __name__=='__main__':main()
