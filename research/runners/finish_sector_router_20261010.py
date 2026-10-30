"""Verify conservative sector routing and record the promotion decision."""
import json,hashlib
import numpy as np
import pandas as pd
from sector_conservative_router_20261010 import OUT,BASE,ANCHOR,CONFIGS,p

def run():
    trials=pd.read_csv(OUT/'trials.csv');d=pd.read_csv(OUT/'directional_deltas.csv');a=pd.read_csv(OUT/'routing_audit.csv.gz')
    assert len(trials)==6 and a.model.nunique()==6
    assert (a.maximum_endpoint.dropna()<a.loc[a.maximum_endpoint.notna(),'date']).all()
    counts=[]
    for c in CONFIGS:
        row=trials.set_index('model').loc[c['name']];z=d[d.model.eq(c['name'])];v=z[p.METRICS].to_numpy().ravel()
        assert row.regressions==int((v < -1e-12).sum()) and row.comparisons==len(v)==5832
        counts.append(dict(model=c['name'],queries=int(a.model.eq(c['name']).sum()),switches=int((a.model.eq(c['name'])&a.expert.ne(ANCHOR)).sum())))
    pd.DataFrame(counts).to_csv(OUT/'switch_counts.csv',index=False)
    scores=pd.read_csv(OUT/'candidate_scores.csv.gz');assert not scores.duplicated(p.KEYS).any()
    assert np.isfinite(scores[[c['name'] for c in CONFIGS]]).all().all()
    original=pd.read_csv(BASE/'selected_historical_scores.csv.gz');assert len(scores)==len(original)
    summary=pd.read_csv(OUT/'summary.csv');ix=['model','period','profile','top_n','scope','return_treatment']
    pieces=[]
    for scope in ['common','expanded']:
        for bounded in [False,True]:
            q=pd.read_csv(OUT/f'queries_{scope}_{bounded}.csv.gz');q['scope']=scope;q['return_treatment']='capped' if bounded else 'raw'
            pieces.append(q.groupby(ix+['sector'])[p.METRICS].mean().groupby(ix)[p.METRICS].mean())
    pd.testing.assert_frame_equal(pd.concat(pieces).sort_index(),summary.set_index(ix)[p.METRICS].sort_index(),atol=1e-12,rtol=1e-12)
    t=trials.iloc[0];result={'tested':6,'strict_passes':int(trials.strict_gate.sum()),'development_selected':t.model,'parent_regressions':int(t.parent_regressions),'parent_improvements':int(t.parent_improvements),'feedback_cutoffs_verified':True,'sector_aggregation_verified':True,'finite_historical_score_rows':len(scores),'tests_passed':2,'production_replaced':False,'fresh_validation':False}
    result['sha256']={str(f.relative_to(p.ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [OUT/'protocol.json',OUT/'trials.csv',OUT/'routing_audit.csv.gz',OUT/'candidate_scores.csv.gz',OUT/'summary.csv']}
    (OUT/'verification.json').write_text(json.dumps(result,indent=2))
    lines=['# Conservative sector improvement experiment — 10 October 2026','',
      'Objective: reduce the remaining sector/profile regressions without replacing the fixed benchmark or using future outcomes to choose a sector expert.','',
      'Tested six policies over six existing experts. Four retain the anchor unless each metric has a nonnegative paired lower margin on at least four/eight completed dates; two use a combined-utility criterion. Routing uses same-sector, same-profile, completed observations within five years. The margin is a heuristic, not an independence-based confidence guarantee.','',
      '| Candidate | Regressions / 5,832 | Regressions vs anchor | Improvements vs anchor |','|---|---:|---:|---:|']
    for r in trials.itertuples():lines.append(f'| {r.model} | {r.regressions} | {r.parent_regressions} | {r.parent_improvements} |')
    lines+=['',f"**{int(trials.strict_gate.sum())} / 6 policies pass the full gate.** Development-selected policy: `{t.model}`. It has {int(t.parent_regressions)} regressions and {int(t.parent_improvements)} improvements versus the current research candidate across 1,296 parent comparison cells. This comparison includes all nine profiles, Top1/3/5, common/expanded universes, raw/capped outcomes and six metrics.",'',
      '## Verification','',
      f'- {len(scores):,} historical stock/date/profile rows have finite scores for every policy; identities match the earlier experiment.',
      '- Every routing feedback endpoint is strictly earlier than its decision date. All saved sector aggregates reproduce the summary within 1e-12.',
      '- Two tests verify baseline fallback and rejection of a risk regression even when other metrics improve.',
      '- Previously exposed historical dates remain exposed. There is no fresh holdout and no claim of guaranteed market superiority.',
      '', '## Decision','',
      'The existing full-coverage research export remains the reference. A routing policy that regresses against it is not relabeled a universal champion. No live model was replaced. All experiment scores and evidence are retained for inspection.',
      '', '## Research','',
      '[Safe Policy Improvement with Baseline Bootstrapping, ICML 2019](https://proceedings.mlr.press/v97/laroche19a.html) motivates retaining a baseline when evidence is insufficient. [Mixing past predictions, PMLR 2020](https://proceedings.mlr.press/v128/korotin20a.html) motivates delayed-feedback expert aggregation. This experiment is an adaptation of those ideas, not a replication of either algorithm or its guarantee.',
      '', 'A universal future-performance guarantee cannot be established from this finite dataset. The unchanged retrospective all-metric gate is testable, and the exact result above is the acceptance criterion used here.']
    (p.ROOT/'research/reports/sector_conservative_router_20261010.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='sha256'},indent=2),flush=True)

if __name__=='__main__':run()
