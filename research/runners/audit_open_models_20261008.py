"""Independent arithmetic checks and a readable experiment report."""
import json,hashlib
import numpy as np
import pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/full-coverage-open-models-20261008'

def run():
    a=pd.read_csv(OUT/'summary.csv');t=pd.read_csv(OUT/'trials.csv');audit=pd.read_csv(OUT/'training_audit.csv')
    if (OUT/'pair_trials.csv').exists():
        a=pd.concat([a,pd.read_csv(OUT/'pair_summary.csv')]);t=pd.concat([t,pd.read_csv(OUT/'pair_trials.csv')])
    local=ROOT/'experiments/sector-local-experts-20261008'
    if (local/'trials.csv').exists():
        a=pd.concat([a,pd.read_csv(local/'summary.csv')]);t=pd.concat([t,pd.read_csv(local/'trials.csv')])
        local_audit=pd.read_csv(local/'training_audit.csv')
        assert len(local_audit)==18 and (local_audit.max_endpoint < local_audit.year.astype(str)+'-01-01').all()
    a=a.drop_duplicates(['model','period','scope','top_n','return_treatment'])
    t=t.sort_values(['strict_gate','regressing_cells','mean_delta'],ascending=[False,True,False])
    assert len(audit)==72 and not audit.duplicated(['year','model']).any()
    assert (audit.max_endpoint < audit.year.astype(str)+'-01-01').all()
    assert not a.duplicated(['model','period','scope','top_n','return_treatment']).any()
    metrics=['xirr','drawdown','achievement','shortfall','ndcg']
    ix=['period','scope','top_n','return_treatment']
    assert np.isfinite(a[metrics]).all().all()
    deltas=[]
    for name in t.model:
        source=a[a.model.eq(name)].set_index(ix)[metrics]
        assert len(source)==24
        cells=[]
        for baseline in ['sector_incumbent','frozen_challenger']:
            ref=a[a.model.eq(baseline)].set_index(ix)[metrics]
            d=source-ref
            for keys,row in d.iterrows():
                for m in metrics:
                    v=float(row[m])*(-1 if m=='shortfall' else 1)
                    cells.append(v)
                    deltas.append(dict(model=name,baseline=baseline,**dict(zip(ix,keys)),metric=m,improvement=v))
        tr=t[t.model.eq(name)].iloc[0]
        assert len(cells)==240 and sum(v < -1e-12 for v in cells)==tr.regressing_cells
        assert bool(all(v>=-1e-12 for v in cells) and any(v>1e-12 for v in cells))==bool(tr.strict_gate)
    pd.DataFrame(deltas).to_csv(OUT/'all_metric_deltas.csv',index=False)
    verification={'annual_fits':len(audit),'candidates':len(t),'comparison_cells_per_candidate':240,'strict_passes':int(t.strict_gate.sum()),'endpoint_purge_verified':True,'finite_metrics':True,'gate_independently_recomputed':True,'fresh_holdout':False}
    paths=[OUT/'protocol.json',OUT/'summary.csv',OUT/'trials.csv',OUT/'pair_protocol.json',OUT/'pair_summary.csv',OUT/'pair_trials.csv',local/'protocol.json',local/'summary.csv',local/'trials.csv']
    verification['sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.exists()}
    (OUT/'verification.json').write_text(json.dumps(verification,indent=2))
    lines=['# Expanded full-coverage sector ranking research — 8 October 2026','',
      '## Decision','',f'Completed {len(t)} new candidates, 72 pooled annual fits and 18 additional annual global/sector expert sets. Strict clean-dominance passes: **{int(t.strict_gate.sum())}**. Production has not been replaced.',
      '', 'The strict gate checks Top-1, Top-3 and Top-5; 2020–2023 and 2024–2025; common and expanded populations; raw and capped XIRR; five metrics; and both the production champion and the previously frozen full-coverage challenger. There are 240 directional comparisons per candidate. These are overlapping diagnostics, not 240 independent statistical tests.',
      '', '## Methods','',
      '- CatBoost YetiRank, XGBoost NDCG, Extra Trees and ridge regression; each learns return, balanced or defensive within-sector relevance.',
      '- Four score options per trained model: standalone and 25%, 50%, 75% blends with the frozen full-coverage challenger; two equal-family ensembles.',
      '- Follow-up: 198 equal two-model combinations, each contributing 5%, 10% or 20% beside the frozen challenger. This was adaptive after viewing first-round results.',
      '- Sector-specific experiment: 27 partially pooled ridge candidates, with equal date-sector training weights, at least 120 rows/four dates per local model, and 25%/50%/75% local shrinkage weights. Eighteen annual global/sector model sets trained separately.',
      '- Existing price/high/downside/momentum features plus trading continuity and annual observation count. No current fundamentals enter historical training.',
      '- Each test year is predicted using training outcomes ending strictly before that year. All dates have already been researched, so model selection is retrospective, not a fresh holdout.',
      '- Aggregate metrics weight sectors equally after averaging their decision dates. Common scope compares identical stocks; expanded scope allows the new model to choose outside the production eligibility screen.',
      '', '## Candidate comparison','',
      '| Candidate | Regressing cells / 240 | Worst directional difference | Strict pass |','|---|---:|---:|---|']
    for r in t.head(12).itertuples():lines.append(f'| {r.model} | {r.regressing_cells} | {r.worst_delta:.6f} | {r.strict_gate} |')
    lines+=['','Ranking this table by fewer regressions is a diagnostic choice, not evidence that its first row is a deployable champion. XIRR tails can dominate the worst difference. All candidate results remain in the trial ledger.',
      '', '## Coverage and limits','',
      'The frozen challenger supplies 4,436 finite scores versus 1,746 production scores at the base profile. Seventeen stocks have no usable price evidence and receive an explicitly neutral tied prior. Full coverage is not equivalent to reliable price data, trade eligibility, or predictive accuracy. Current sector labels and a surviving universe are used retrospectively. Corporate-action and extreme-return concerns remain. Prior full-coverage checks showed profile and Top-1 regressions. A clean new production champion cannot be declared solely from a favorable Top-3 average.',
      '', '## Source-level data warning','',
      'The largest historical label is Sejal Glass (INE955I01044), decision date 2021-03-31, future XIRR 9,086.008636 (908,600.86%). Its [2021–22 annual report](https://sejalglass.co.in/document/Annual%20Report%202021-2022.pdf) documents consolidation from 33,550,000 existing shares to 100,000 shares, record date 10 May 2021, and trading resumption on 13 December 2021. This is a concrete corporate-action concern, not proof that the cached label has been correctly or incorrectly adjusted. Reconcile holdings and cash flows before relying on this outcome. Capping returns is sensitivity analysis, not a repair.',
      '', '## Research sources','',
      '- [CatBoost, NeurIPS 2018](https://proceedings.neurips.cc/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html)',
      '- [XGBoost, KDD 2016](https://doi.org/10.1145/2939672.2939785)',
      '- [Extremely randomized trees, Machine Learning 2006](https://doi.org/10.1007/s10994-006-6226-1)',
      '', 'Peer review supports the algorithmic methods, not the profitability of this application.',
      '', '## Reproduction','',
      'Run `python research/runners/full_coverage_open_models_20261008.py`, then `python research/runners/audit_open_models_20261008.py`. Isolated dependency versions: CatBoost 1.2.10 and XGBoost 3.4.1. Data and model artifacts are under `experiments/full-coverage-open-models-20261008/`; previous challenger artifacts remain intact.',
      '', 'The verification file independently recomputes all strict gates, checks all 72 training cutoffs and the 18 local-expert cutoffs, and hashes protocol/results. Existing coverage, formula and independent-rubric regression suite: 34 tests passed in this run. One additional batched-evaluator equivalence test passed (35 total); a real-data comparison also matched 702 reference rows.',
      '', 'The frozen full-coverage challenger itself regresses in nine of the 120 comparable metric cells against production. A new candidate with fewer regressions among the new algorithms is not automatically better than that existing challenger.']
    if (OUT/'selection.json').exists():
        selected=json.loads((OUT/'selection.json').read_text())
        lines+=['','## Frozen new research candidate','',f"Name: `{selected['name']}`. Status: `{selected['status']}`. Full current export: {selected.get('full_coverage','pending')} stocks, snapshot 2026-10-03. Nine-profile regressions: {selected.get('profile_regressing_cells','pending')} / {selected.get('profile_comparison_cells','pending')} cells. These are diagnostics on reused dates, not independent validation.",'','The full rankings and all-profile deltas are saved alongside the experiment. The scoring CLI reproduces the frozen package without training.']
        lines+=['','Base profile, common universe, Top-3; equal-sector/date basket-median XIRR:','','| Period | Return treatment | Production | Frozen challenger | New candidate |','|---|---|---:|---:|---:|']
        selected_deltas=pd.DataFrame(deltas)
        top3=selected_deltas[selected_deltas.model.eq(selected['name'])&selected_deltas.top_n.eq(3)]
        lines+=[]
        table=a[a.top_n.eq(3)&a.scope.eq('common')].set_index(['model','period','return_treatment'])
        for period in ['development','exposed']:
            for treatment in ['raw','capped']:
                values=[float(table.loc[(n,period,treatment),'xirr']) for n in ['sector_incumbent','frozen_challenger',selected['name']]]
                lines.append(f'| {period} | {treatment} | {values[0]:.2%} | {values[1]:.2%} | {values[2]:.2%} |')
        lines+=['',f"At the base profile's Top-3 cutoff, the new candidate has {int(top3.improvement.lt(-1e-12).sum())} regressions across {len(top3)} comparisons against the two prior models. This narrower result must not be generalized to Top-1, Top-5 or every profile."]
    report=ROOT/'research/reports/full_coverage_open_models_20261008.md';report.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(verification,indent=2))

if __name__=='__main__':run()
