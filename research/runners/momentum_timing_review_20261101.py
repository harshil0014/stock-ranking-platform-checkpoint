"""Review a single completed timing pilot; never retune or evaluate exposure."""
from pathlib import Path
import ast,datetime,hashlib,json,shutil
import numpy as np
import pandas as pd
from stock_research.momentum_timing import top_quartile
from delivery_probe_20261101 import BASE
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/momentum-timing-20261101';WORK=ROOT/'work/momentum-timing-20261101'


def table(z):
    return '| '+' | '.join(z.columns)+' |\n| '+' | '.join(['---']*len(z.columns))+' |\n'+''.join('| '+' | '.join(map(str,r))+' |\n' for r in z.itertuples(index=False,name=None))


def main():
    checks=[]
    def check(name,value):
        checks.append(dict(check=name,passed=bool(value)))
        if not value:raise AssertionError(name)
    for p,r in [('momentum_timing_20261101.md','protocol_receipt.json'),('momentum_timing_implementation_review_20261101.md','implementation_receipt.json')]:
        check('frozen protocol '+p,hashlib.sha256((ROOT/'research/protocols'/p).read_bytes()).hexdigest()==json.loads((OUT/r).read_text())['sha256'])
    gate=json.loads((OUT/'gate.json').read_text());folds=pd.read_csv(OUT/'annual_folds.csv')
    check('every annual training label matured',all(r.max_training_label_end<f'{r.year}-01-01' for r in folds.itertuples()))
    check('development stopped before exposed',gate['gates']['development']['status']=='KILLED' and not gate['exposed_evaluated'])
    z=pd.read_pickle(WORK/'development_memberships.pkl.gz',compression='gzip')
    valid=z.gross_ratio.notna()
    check('entry strictly after signal date',z.loc[valid,'entry'].gt(z.loc[valid,'decision_date']).all())
    check('one record per identity-date',not z.duplicated(['isin','decision_date']).any())
    for date,g in z.groupby('decision_date'):
        expected=set(top_quartile(g[g.dip],'timing_score')['isin'])
        check('overlay frozen before outcome availability '+date,expected==set(g.loc[g.overlay,'isin']))
    # Reconstruct the old global head's IC from saved coefficients, no new fits.
    panel=pd.read_pickle(ROOT/'work/new-information-20261101/delivery_panel.pkl.gz',compression='gzip')
    coefficients=pd.read_csv(OUT/'head_coefficients.csv');old=pd.read_csv(ROOT/'experiments/new-information-20261101/delivery_development_ic.csv')
    replay=[]
    for year,g in coefficients.groupby('year'):
        coef=g.set_index('feature').loc[BASE,'coefficient'].to_numpy()
        test=panel[panel.decision_date.str.startswith(str(year))].copy();test['score']=test[BASE].to_numpy()@coef
        for date,h in test.groupby('decision_date'):
            actual=float(h.score.corr(h.target,method='spearman'));expected=float(old.loc[old.decision_date.eq(date),'control_ic'].iloc[0])
            replay.append(dict(decision_date=date,replayed_control_ic=actual,original_control_ic=expected,error=abs(actual-expected)))
    replay=pd.DataFrame(replay);replay.to_csv(OUT/'head_reproduction.csv',index=False)
    check('unchanged short head reproduces original12date IC',len(replay)==12 and replay.error.max()<1e-12)
    check('short return coefficient negative each year',coefficients.loc[coefficients.feature.eq('return21'),'coefficient'].lt(0).all())
    dates=pd.read_csv(OUT/'development_date_returns.csv');annual=pd.read_csv(OUT/'development_year_returns.csv');pooled=pd.read_csv(OUT/'development_pooled_returns.csv')
    support=pd.read_csv(OUT/'development_support.csv')
    check('supported comparisons have no unknown outcomes',support.loc[support.eligible,'unknown_outcomes'].eq(0).all())
    check('matched date aggregates reproduce',np.allclose(dates.groupby(['liquidity_scope','cost_bps']).overlay_minus_dip.mean().to_numpy(),pooled.overlay_minus_dip.to_numpy()))
    check('failed year signs independently verified',((annual.year.eq(2021)&annual.overlay_minus_dip.lt(0)).sum()==4) and ((annual.year.eq(2023)&annual.dip_minus_non_dip.lt(0)).sum()==4))
    testlog=WORK/'low-load-tests.log'
    check('focused tests passed','14 passed' in testlog.read_text())
    (OUT/'integrity_checks.json').write_text(json.dumps(dict(all_passed=True,checks=checks),indent=2))
    (OUT/'test_receipt.json').write_text(json.dumps(dict(tests=14,passed=True,external_ci=False,log_sha256=hashlib.sha256(testlog.read_bytes()).hexdigest()),indent=2))
    def display(a):
        b=a.copy()
        for col in ['dip_net','non_dip_net','overlay_net','dip_minus_non_dip','overlay_minus_dip']:
            if col in b:b[col]=(b[col]*100).map(lambda v:f'{v:.3f}')
        return b
    intervals=pd.read_csv(OUT/'development_block_intervals.csv');ci=intervals[intervals.cost_bps.eq(100)].copy()
    for col in ['mean','low95','high95']:ci[col]=(ci[col]*100).map(lambda v:f'{v:.3f}')
    coefview=coefficients.pivot(index='feature',columns='year',values='coefficient').round(6).reset_index();coefview.columns=coefview.columns.astype(str)
    report=f'''# One-shot test: momentum selection plus reversal timing

**Decision: KILLED by the preregistered yearly-sign rule.** Pooled net returns and
incremental edges survive both cost stresses and removal of the least-liquid
quintile, but the timing overlay fails in 2021 and the plain dip rule fails in
2023. Exposed-period performance was not evaluated. No second threshold search,
new model family, production change, or ledger change followed this failure.

## What was fixed in advance

Start with the global top quartile of the unchanged **20% professor-factor lens**,
selected before joining the NSE source panel. That lens is still 80% champion plus
five 4% factor blocks, not majority weighting of Sir's factors. Compare selected
stocks at least 10% below their highest recorded adjusted closing price with
selected non-dip stocks. Within dips, the timing overlay takes the highest-scored
quartile from the previous price/volume Ridge head. No threshold optimization.

Three annual expanding fits, 2021–23, alpha10, the same eight globally normalized
features and original training support. Labels must mature before January1 of the
prediction year. Saved coefficients reproduce the original head's full-support
12-date IC exactly (maximum difference {replay.error.max():.2g}); no new comparison
model was selected. This is a test of combining an existing selection lens and
head, not a new head search.

Actual next-open entries, exit at the 21st observed session close including entry
session, fractional-return proxy. Buy and sell each incur 75bp or100bp. These are
**21-session net cohort returns**, not XIRR, annualized returns, a live portfolio,
or a simulation of the workbook's staggered 10–40% ladder and cash allocations.

Liquidity uses prior20sessions' average provider Close×Volume, strictly before
the signal date. Quintiles are defined on the full mapped NSE source support
before preference selection. The ex-bottom-quintile analysis retains the original
dip and overlay memberships; it does not refill slots from other stocks.

## Pooled result across all 12 development dates

All returns are percent; the final two columns are percentage-point differences.
Dates are equally weighted; stocks within each group/date are equally weighted.

{table(display(pooled))}

At100bp per side, the full-cohort non-dip mean is1.273%, plain dip1.733%, and
dip-plus-overlay2.663%. The overlay adds0.929pp versus the plain dip rule in the
pooled average. Removing the least-liquid fifth leaves an overlay increment of
1.108pp. **Cost or lowest-quintile dependence is not what kills this result.**

With the same holding horizon and proportional costs, return differences between
groups mainly scale with the fee factor. We therefore also required absolute net
dip and overlay returns to beat cash; merely preserving a relative edge after
cost would be too weak.

## The yearly rule kills it

At100bp per side, percent returns and percentage-point differences:

{table(display(annual[annual.cost_bps.eq(100)]))}

- In2021, the overlay trails plain dip by1.781pp; after excluding the least-liquid
  fifth it still trails by1.243pp.
- In2023, plain dip trails non-dip by0.970pp; after excluding that fifth it trails
  by1.327pp.
- The same two sign failures occur at75bp per side. All required sample-size
  checks passed: 12dates, at least2per year in both liquidity scopes. This is a
  demonstrated preregistered failure rather than a missing-data verdict.

The pooled result looks attractive. It still fails the exact rule requested.
Changing the years, dip threshold, overlay fraction, or lens weight now would
create another post-result search, so this candidate ends here.

## Uncertainty and the reversal hypothesis

365day block-bootstrap95% intervals at100bp, in percentage points:

{table(ci)}

There are only three development years and 12quarterly snapshots. The intervals
are descriptive and do not establish independence, stability or live execution.
This test reuses development dates that motivated the hypothesis.

The short head's standardized percentile-feature coefficients are:

{table(coefview)}

The return21coefficient is negative in all three annual fits, consistent with a
short-term reversal component. Correlated predictors make that an association,
not causal feature attribution. The full-universe IC advantage does not guarantee
timing reliability inside a long-term-winner/dip subset, as2021shows.

## Coverage, safeguards and limits

The source join supplies NSE EQ observations only; BSE-exclusive stocks are not
tested by this pilot. The selection cutoff was computed on all eligible lens
identities before the NSE join, so missing source coverage did not redefine the
quartile. Recorded closing highs depend on available provider history and price
adjustment vintages, not a certified exchange intraday ATH from IPO onward.
The mapped provider quote venue is not independently certified as an executable
NSE fill. Provider turnover is a liquidity proxy, not measured spread or capacity.

Current survivors, historical sector labels, and the previous source panel's
outcome-availability conditioning remain limitations. A sparse quarterly entry
study does not measure daily ladder fills, cash drag, circuit-lock fills,
suspensions, taxes, lot sizes or delisting proceeds. Corporate action flags block
unresolved holding windows; that is an exclusion safeguard, not repaired prices.

During pre-outcome review, the first worker was paused during cache preparation
and stopped before any fit or metric. A selection bug was corrected: overlay
membership is frozen before future-price/action failures; unknown future outcomes
block the comparison rather than cause replacement picks. As-of failures
quarantine the date. The original protocol and pause evidence were retained; no
weights, thresholds or scoring years changed. Aggregate coverage, failures,
liquidity counts, source hashes and training-fold receipts are included. Stock
identities and memberships remain local; no public stock-pick list was produced.

One research worker and compute thread, Windows CPUcap12.5%,4seconds active and
2seconds rest, no GPU. **14local tests and {len(checks)}integrity checks passed.**
This is local evidence, not a remote CI claim. The incumbent and prospective
ledger branches remain unchanged. There is no basis here to promote this timing
overlay, and the profitable pooled average does not override its failed gate.
'''
    import re
    report='\n'.join(line if line.startswith('|') else re.sub(r'(?<=\d)(?=[A-Za-z])',' ',re.sub(r'(?<=[A-Za-z])(?=\d)',' ',line)) for line in report.splitlines())+'\n'
    for a,b in {'21 st':'21st','alpha 10':'alpha=10','CPUcap':'CPU cap','January 1':'January 1','Close×Volume':'Close × Volume',
        'return 21':'return21','365 day':'365-day','-universe':'-universe','2 seconds':'2 seconds'}.items():report=report.replace(a,b)
    path=ROOT/'research/reports/momentum_timing_20261101.md';path.write_text(report,encoding='utf-8',newline='\n')
    output=Path(r'C:\Users\Harshil\Documents\Codex\2026-10-31\you\outputs')
    shutil.copyfile(path,output/'momentum_timing_20261101.md')
    files=[ROOT/'src/stock_research/momentum_timing.py',ROOT/'tests/test_momentum_timing_20261101.py',ROOT/'research/runners/momentum_timing_20261101.py',Path(__file__)]
    for p in files:ast.parse(p.read_text())
    pause=WORK/'implementation_pause_evidence.json'
    if pause.exists():shutil.copyfile(pause,OUT/'pre_outcome_pause_evidence.json')
    # Snapshot finished logs only, excluding this currently active review log.
    logs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in WORK.glob('*.log') if p.name!='low-load-review.log']
    (OUT/'log_inventory.json').write_text(json.dumps(logs,indent=2))
    files+=list((ROOT/'research/protocols').glob('momentum_timing*20261101.md'))+[path]
    files+=sorted(p for p in OUT.iterdir() if p.is_file() and p.name!='manifest.json')
    manifest=dict(created_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(set(files))])
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    shutil.copyfile(OUT/'manifest.json',output/'momentum_timing_20261101_manifest.json')
    print('REVIEW',len(checks),'checks;14tests; report and evidence complete',flush=True)


if __name__=='__main__':main()
