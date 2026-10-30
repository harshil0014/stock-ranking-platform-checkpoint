import json,hashlib
import numpy as np
import pandas as pd
import champion_double_emphasis_20261017 as r

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
    current=pd.read_csv(r.OUT/'current_all_4436_audit.csv');replay=r.candidates(current)
    for name in r.CONFIGS:np.testing.assert_allclose(current[name],replay[name],atol=1e-12,rtol=0)
    nykaa=current[current.ticker.eq('NYKAA')]
    lines=['# Stronger high-recency and SIP-profit emphasis','',
      f"Development-selected variant: `{d['selected']}`. Activation gate: **{'PASS' if d['accept_research_patch'] else 'DO NOT ACTIVATE'}**.",'',
      'Comparator: the active dual_w0.01 + sip_risk_confirmed_0.01 champion, not the original research baseline. All prior components remain fixed.','',
      '## Increased influence','',
      'The direct candidate doubles both overlays from coefficients .01 to .02. Each individual overlay can therefore move a score by at most ±.01, versus ±.005 previously. Risk/affordability and missing-data guards still apply. This does not make either factor dominant in the full model.','',
      'Other candidates double only when both existing signals agree in sign; scale that extra emphasis by the weaker signal; or require both agreeing adjustments to have magnitude at least .0025. They preserve existing weights elsewhere. No ticker-specific exceptions.','',
      '## Literature','',
      '[Bhootra and Hur (2013)](https://doi.org/10.1016/j.jbankfin.2013.05.025) motivates conditioning high-related signals on recency. [Grinblatt and Han (2005)](https://doi.org/10.1016/j.jfineco.2004.10.006) motivates gains relative to acquisition cost. The SIP proxy, confirmation gates and coefficients are engineering hypotheses, not exact paper replications or weights recommended by the papers.','',
      '## Selection and safeguards','',
      'Four candidates fixed before evaluation. Select by 2020–23 expanded/capped equal-sector/profile Top3 utility, lock one, then assess 2024–25. Utility weights: .4 rank IC, .25 NDCG, .15 achievement, .1 inverse shortfall, .1 drawdown; directional deltas/.01. Activation requires positive utility and no deterioration in any of the six primary aggregate measures in either period. This is an operational definition of no-degradation, not a universal guarantee. Raw/common and Top1/5 sensitivities are retained.','',
      '| Period | Model | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |','|---|---|---:|---:|---:|---:|---:|---:|']
    for t in a.itertuples():lines.append(f'| {t.stage} | {t.model} | {t.xirr:.3%} | {t.drawdown:.3%} | {t.achievement:.3%} | {t.shortfall:.6f} | {t.ndcg:.6f} | {t.rank_ic:.6f} |')
    lines+=['','## Current rankings and verification','',f'- All {len(current):,} stocks retain finite scores. Source SHA256 hashes and matched query populations verified; current exported scores reproduce to 1e-12.',
      '- Two tests cover exact doubling, bounds, agreement gates, zero corrections and independence from outcome/company fields.',
      '- NYKAA sector ranks: '+', '.join(f'{n}: {int(nykaa[n+"_rank"].iloc[0])}' for n in r.CONFIGS)+'.',
      '- Historical dates were previously researched; no fresh validation. Survivor/sector bias, incomplete action certification and gross outcomes remain. All inputs are frozen dated signals; this round does not fetch new stock prices.',
      '- Website unchanged by this experiment; existing user-approved recency/SIP champion remains active unless separately promoted.','',
      'Reproduce with `python research/runners/champion_double_emphasis_20261017.py` and `python research/runners/report_double_emphasis_20261017.py`. Detailed artifacts: `experiments/champion-double-emphasis-20261017/`.']
    dest=r.h.p.ROOT/'research/reports/champion_double_emphasis_20261017.md';dest.write_text('\n'.join(lines)+'\n',encoding='utf-8');print(a.to_string(index=False));print(dest)

if __name__=='__main__':main()
