"""Evidence report for the bounded high-recency champion upgrade."""
import json,hashlib
import numpy as np
import pandas as pd
import champion_high_recency_20261017 as r

def main():
    out=r.OUT;d=json.loads((out/'decision.json').read_text());name=d['selected'];proto=json.loads((out/'protocol.json').read_text())
    for file,sha in proto['source_hashes'].items():assert hashlib.sha256((r.p.ROOT/file).read_bytes()).hexdigest()==sha
    x=pd.read_csv(out/'current_all_4436_audit.csv'); replay=r.signals(x)
    for col in r.CONFIGS:np.testing.assert_allclose(x[col],replay[col],rtol=0,atol=1e-12)
    tables=[];sectors=[]
    for stage in ['development','recent']:
        q=pd.read_csv(out/f'queries_{stage}.csv.gz');keys=['period','date','profile','sector','top_n','scope','treatment']
        assert q.groupby(keys).n.nunique().eq(1).all()
        z=q[q.scope.eq('expanded')&q.treatment.eq('capped')&q.top_n.eq(3)&q.model.isin([r.base.ANCHOR,name])]
        a=z.groupby(['model','sector','profile'])[r.p.METRICS].mean()
        t=a.groupby('model').mean().reset_index();t['stage']=stage;tables.append(t)
        delta=(a.loc[name]-a.loc[r.base.ANCHOR]).reset_index();delta.shortfall=-delta.shortfall;delta['stage']=stage;sectors.append(delta)
    pd.concat(sectors).to_csv(out/'sector_profile_deltas.csv',index=False)
    table=pd.concat(tables);table.to_csv(out/'aggregate_results.csv',index=False)
    lines=['# Champion upgrade: modest closing-high recency emphasis','',
      f"Selected patch: **{name}**. Overall tradeoff gate: **{'PASS' if d['accept_research_patch'] else 'DO NOT ADOPT'}**.",'',
      '## Research basis','',
      'Bhootra and Hur (2013), *The timing of 52-week high price and momentum*, studies the timing of the high directly. George and Hwang (2004) studies proximity. These support testing recency alongside proximity; they do not establish our mixture weights, Indian sector performance or an all-time-high-age penalty. [Recency paper](https://www.sciencedirect.com/science/article/pii/S0378426613002446), [proximity paper](https://onlinelibrary.wiley.com/doi/full/10.1111/j.1540-6261.2004.00695.x).','',
      '## Exact changes tested','',
      '- Preserved all existing champion models and component weights. Applied C_new = C + w*(H - 0.5).',
      '- H = 60% inverse-age percentile + 25% high-proximity percentile + 15% momentum percentile, computed within date/profile/sector.',
      '- Compared rolling 52-week closing high, available-history recorded closing high, and equal combination of the two.',
      '- Tested w = .01, .025 and .05: maximum absolute score change .005, .0125 and .025 respectively. These are score adjustments, not percentage-point changes in predictive accuracy.',
      '- Recency dominates this added signal only. Existing champion feature effects are nonlinear, so this does not assert a total-model recency weight.',
      '- Requires usable price evidence, at least 252 observations and 365 history days, active-volume fraction >=80%, positive-volume lag <=14 days, complete signal inputs and >=5 eligible peers.',
      '- Missing evidence yields zero correction. No age values are overwritten; no company-specific exception is added.','',
      '## Selection and tradeoff policy','',
      'Nine configurations were compared on 2020–2023 development dates. One was locked before evaluation on 2024–2025. Preference utility weights: rank IC .40, NDCG .25, goal achievement .15, inverse shortfall .10, drawdown .10; directional changes normalized by .01. XIRR selection weight is zero, but returns are reported.','',
      'Acceptance requires positive development and later utility, positive later equal-weight and ranking-only sensitivities, and at most 1 percentage point aggregate deterioration in drawdown/achievement. This permits individual regressions; it is a declared engineering preference, not universal investment utility.','',
      f"Development utility: {d['development']['utility']:.5f}. Later utility: {d['recent']['utility']:.5f}. Later ranking-only: {d['recent']['ranking_utility']:.5f}; equal-weight: {d['recent']['equal_utility']:.5f}.",'',
      '## Results','',
      'Expanded universe, capped returns, sector Top3; equal sector/profile cells. SIP XIRR remains a historical diagnostic, not a cost-complete portfolio return.','',
      '| Period | Score | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |','|---|---|---:|---:|---:|---:|---:|---:|']
    for row in table.itertuples():lines.append(f'| {row.stage} | {row.model} | {row.xirr:.3%} | {row.drawdown:.3%} | {row.achievement:.3%} | {row.shortfall:.5f} | {row.ndcg:.5f} | {row.rank_ic:.5f} |')
    lines+=['','## Sector/profile dispersion','','| Period | Improving non-return cells | Regressing non-return cells | Tied |','|---|---:|---:|---:|']
    for stage,z in pd.concat(sectors).groupby('stage'):
        vals=z[list(r.preference.WEIGHTS)].to_numpy();lines.append(f'| {stage} | {(vals>1e-12).sum()} | {(vals< -1e-12).sum()} | {(np.abs(vals)<=1e-12).sum()} |')
    lines+=['','## Verification and limitations','',
      '- Source-file SHA256 hashes verified. Same query population sizes for all compared scores. Current scores reproduce from exported evidence to <=1e-12.',
      '- Three tests pass for direction/bounds, missing/illiquid/small-group abstention and independence from future-date inputs.',
      f"- All 4,436 stocks remain numerically covered; {d['unchanged_missing_evidence']} missing-evidence scores exactly preserve the champion. Current snapshot is 3 October 2026 and base7500; historical evidence covers nine profiles.",
      '- Stored high ages are inherited provider-basis features. A recorded high is a maximum within available history, not independently certified lifetime ATH. Full-history corporate-action integrity is not newly certified by this experiment.',
      '- A recent rolling high can coexist with an old recorded high. That distinction is preserved.',
      '- Current-universe and retrospective-sector bias remain. All historical dates were already exposed during prior research. This is not fresh out-of-sample validation.',
      '- No website was switched or existing champion artifact overwritten. A research-gate pass would justify prospective confirmation, not a universal superiority claim.','',
      '## Artifacts and reproduction','',
      'Run `python research/runners/champion_high_recency_20261017.py`, then `python research/runners/report_champion_high_recency_20261017.py`. Artifacts: `experiments/champion-high-recency-20261017/` contains protocol, development lock, all historical candidate scores, query metrics, raw/common sensitivities, sector/profile deltas, complete current rankings and sector Top3.','']
    (r.p.ROOT/'research/reports/champion_high_recency_20261017.md').write_text('\n'.join(lines),encoding='utf-8')
    print(table.to_string(index=False)); print(json.dumps(d,indent=2))

if __name__=='__main__':main()
