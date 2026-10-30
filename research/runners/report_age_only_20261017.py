import json,hashlib
import numpy as np
import pandas as pd
import champion_age_only_20261017 as r

def main():
    p=json.loads((r.OUT/'protocol.json').read_text());d=json.loads((r.OUT/'decision.json').read_text())
    for path,digest in p['source_hashes'].items():assert hashlib.sha256((r.h.p.ROOT/path).read_bytes()).hexdigest()==digest
    rows=[]
    for stage in ['development','recent']:
        q=pd.read_csv(r.OUT/f'queries_{stage}.csv.gz')
        keys=['date','profile','sector','n','top_n','scope','treatment']
        anchor=q[q.model.eq(r.h.base.ANCHOR)][keys].sort_values(keys).reset_index(drop=True)
        for model in q.model.unique():pd.testing.assert_frame_equal(anchor,q[q.model.eq(model)][keys].sort_values(keys).reset_index(drop=True))
        z=q[q.scope.eq('expanded')&q.treatment.eq('capped')&q.top_n.eq(3)]
        a=z.groupby(['model','sector','profile'])[r.h.p.METRICS].mean().groupby('model').mean()
        for model in a.index:rows.append(dict(stage=stage,model=model,**a.loc[model].to_dict()))
    a=pd.DataFrame(rows);a.to_csv(r.OUT/'aggregate_results.csv',index=False)
    current=pd.read_csv(r.OUT/'current_all_4436_audit.csv');replay=r.signals(current)
    for name in r.CONFIGS:np.testing.assert_allclose(current[name],replay[name],atol=1e-12,rtol=0)
    nykaa=current[current.ticker.eq('NYKAA')]
    lines=['# High-age-only optimization; SIP weight fixed','',
      f"Development-selected variant: `{d['selected']}`. Activation gate: **{'PASS' if d['accept_research_patch'] else 'DO NOT ACTIVATE'}**.",'',
      'Comparator: the active dual_w0.01 + sip_risk_confirmed_0.01 champion, not the original research baseline. All prior components remain fixed.','',
      '## Increased influence','',
      'Only high-age influence increases; SIP and all existing components stay fixed. Each of four signal variants is tested at incremental coefficients 0.001, 0.002, 0.004 and 0.008, bounding the extra score contribution at +/-0.0005, +/-0.001, +/-0.002 and +/-0.004 respectively. These are score coefficients, not percentages of total model importance.','',
      'Four signal variants: inverse rolling-52-week high age, inverse available-history recorded-high age, their equal combination, and rolling-high age scaled by proximity (full increment at the high, zero at 20% below). All are within-sector percentiles with the existing activity/history guards. No ticker-specific exceptions.','',
      '## Literature','',
      '[Bhootra and Hur (2013)](https://doi.org/10.1016/j.jbankfin.2013.05.025) studies 52-week-high recency. [George and Hwang (2004)](https://doi.org/10.1111/j.1540-6261.2004.00695.x) studies proximity to the 52-week high. These motivate the rolling-age and proximity-conditioned hypotheses; neither establishes a lifetime-high-age penalty or recommends our coefficients. This is an adaptation, not an exact replication.','',
      '## Selection and safeguards','',
      'Sixteen candidates fixed before evaluation. Select by 2020-2023 expanded/capped equal-sector/profile Top3 utility, lock one, then assess 2024-2025. Utility weights: .4 rank IC, .25 NDCG, .15 achievement, .1 inverse shortfall, .1 drawdown; directional deltas/.01. Activation allows tradeoffs: positive weighted utility, ranking-only and equal-five sensitivities in BOTH periods; losses in XIRR, drawdown, achievement and directional shortfall must each stay within 0.1 percentage point. This is the predeclared net-benefit rule, not a universal guarantee. Raw/common and Top1/5 sensitivities are retained.','',
      '| Period | Model | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |','|---|---|---:|---:|---:|---:|---:|---:|']
    for t in a.itertuples():lines.append(f'| {t.stage} | {t.model} | {t.xirr:.3%} | {t.drawdown:.3%} | {t.achievement:.3%} | {t.shortfall:.6f} | {t.ndcg:.6f} | {t.rank_ic:.6f} |')
    lines+=['','## Current rankings and verification','',f'- All {len(current):,} stocks retain finite scores. Source SHA256 hashes and matched query populations verified; current exported scores reproduce to 1e-12.',
      '- Two tests cover recency direction, incremental bounds, proximity gating, missing-data abstention and independence from future dates.',
      '- NYKAA sector ranks: '+', '.join(f'{n}: {int(nykaa[n+"_rank"].iloc[0])}' for n in r.CONFIGS)+'.',
      '- Historical dates were previously researched; no fresh validation. Survivor/sector bias, incomplete action certification and gross outcomes remain. All inputs are frozen dated signals; this round does not fetch new stock prices.',
      '- Website unchanged by this experiment; existing user-approved recency/SIP champion remains active unless separately promoted.','',
      'Reproduce with `python research/runners/champion_age_only_20261017.py` and `python research/runners/report_age_only_20261017.py`. Detailed artifacts: `experiments/champion-age-only-20261017/`.']
    dest=r.h.p.ROOT/'research/reports/champion_age_only_20261017.md';dest.write_text('\n'.join(lines)+'\n',encoding='utf-8');print(a.to_string(index=False));print(dest)

if __name__=='__main__':main()
