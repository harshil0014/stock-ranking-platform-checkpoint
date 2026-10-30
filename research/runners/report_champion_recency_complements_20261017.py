import json
import numpy as np
import pandas as pd
import champion_recency_complements_20261017 as r

def main():
    decision=json.loads((r.OUT/'decision.json').read_text())
    name=decision['selected'];tables=[]
    for stage in ['development','recent']:
        q=pd.read_csv(r.OUT/f'queries_{stage}.csv.gz')
        # Query membership must be identical, not merely aggregate row counts.
        keys=[c for c in ['decision_date','date','profile','sector','n','top_n','scope','treatment'] if c in q]
        anchor=q[q.model.eq(r.h.base.ANCHOR)]
        for model in q.model.unique():
            other=q[q.model.eq(model)]
            pd.testing.assert_frame_equal(anchor[keys].sort_values(keys).reset_index(drop=True),other[keys].sort_values(keys).reset_index(drop=True))
        q=q[q.scope.eq('expanded')&q.treatment.eq('capped')&q.top_n.eq(3)]
        a=q.groupby(['model','sector','profile'])[r.h.p.METRICS].mean().groupby('model').mean()
        for model in [r.h.base.ANCHOR,name]:
            tables.append(dict(stage=stage,model=model,**a.loc[model].to_dict()))
    a=pd.DataFrame(tables);a.to_csv(r.OUT/'aggregate_results.csv',index=False)
    d=pd.read_csv(r.OUT/'deltas_development.csv');d=d[d.scope.eq('expanded')&d.treatment.eq('capped')&d.top_n.eq(3)].sort_values('utility',ascending=False)
    lines=['# Fixed recency weight: complementary signal experiment','',
      f"Decision: **{'RESEARCH CANDIDATE; prospective confirmation required' if decision['accept_research_patch'] else 'REVERT EXPERIMENT; retain unchanged champion'}**. Development-selected configuration: `{name}`.",'',
      '## What stayed fixed','',
      'The previous dual-high adjustment remains exactly C + .01 × (.60 recency + .25 proximity + .15 momentum − .5). Recency uses the equal combination of inverse ages of the 52-week closing high and available-history recorded closing high. Its .006 coefficient was not reduced, normalized away or retuned. It is the largest coefficient in the added signal, not a claim about total nonlinear champion importance.','',
      '## Literature and adaptations','',
      '- [Da, Gurun and Warachka (2014), Frog in the Pan](https://doi.org/10.1093/rfs/hhu003): motivated continuity proxies (trend efficiency, fit quality, inverse largest-jump share). This is not the exact paper estimator.',
      '- [Daniel and Moskowitz (2016), Momentum crashes](https://doi.org/10.1016/j.jfineco.2015.12.002): motivated downside/volatility controls. Our within-sector stock-level proxies are not a replication of their portfolio strategy.',
      '- Continuity, risk, and their equal combination were each tested with weight .001 or .003. The entire complement remains smaller than the .006 recency coefficient. Existing champion components remain frozen.','',
      '## Selection and evidence','',
      'Six predefined configurations, selected on 2020–2023 before evaluating the selected candidate on 2024–2025. Equal-sector/profile Top3 utility: 40% rank IC, 25% NDCG, 15% achievement, 10% inverse shortfall, 10% drawdown, each change divided by .01. XIRR reported but not optimized. Same population and nine historical profiles. Acceptance also requires positive development/recent utility and positive recent ranking-only/equal-five sensitivities; individual regressions are allowed.','',
      '| Candidate | Development utility |','|---|---:|']
    for row in d.itertuples():lines.append(f'| {row.model} | {row.utility:.6f} |')
    lines+=['','| Period | Score | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |','|---|---|---:|---:|---:|---:|---:|---:|']
    for row in a.itertuples():lines.append(f'| {row.stage} | {row.model} | {row.xirr:.3%} | {row.drawdown:.3%} | {row.achievement:.3%} | {row.shortfall:.6f} | {row.ndcg:.6f} | {row.rank_ic:.6f} |')
    lines+=['',f"Recent weighted utility: {decision['recent']['utility']:.6f}; ranking-only: {decision['recent']['ranking_utility']:.6f}; equal-five: {decision['recent']['equal_utility']:.6f}. These preference scores are not percentage accuracy gains.",'',
      '## Verification and limits','',
      '- All 4,436 current stocks have finite scores; missing-evidence fallback remains exactly unchanged. Current snapshot remains 3 October 2026.',
      '- Exported current scores reproduced within 1e-12. Bounds, fixed age coefficient, missing-data abstention and future-date independence covered by two passing tests. Historical query membership matched across compared scores.',
      '- Provider-basis prices and available-history highs are inherited; no new corporate-action certification. Retrospective sector/current-survivor bias remains.',
      '- All historical periods were previously researched. This is exploratory evidence, not fresh validation. No single overall improvement percentage or universal superiority claim is justified.',
      '- Website and existing champion artifacts unchanged. Rejected experimental outputs retained for reproducibility, not used in production.','',
      '## Reproduction','',
      '`python research/runners/champion_recency_complements_20261017.py` then `python research/runners/report_champion_recency_complements_20261017.py`. Outputs under `experiments/champion-recency-complements-20261017/`.']
    path=r.h.p.ROOT/'research/reports/champion_recency_complements_20261017.md'
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(a.to_string(index=False));print(path)

if __name__=='__main__':main()
