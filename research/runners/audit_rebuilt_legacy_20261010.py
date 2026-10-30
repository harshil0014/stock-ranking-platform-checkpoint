"""Verify all previous-policy comparisons for the new rebuilt-price candidate."""
import json,hashlib
import numpy as np
import pandas as pd
from sector_price_rebuild_20261010 import OUT,ROOT,METRICS

def run(family='rebuilt'):
    global OUT
    if family=='accuracy':OUT=ROOT/'experiments/sector-accuracy-20261010'
    elif family=='yeti':OUT=ROOT/'experiments/sector-yetirank-20261010'
    folder=OUT/'legacy-comparison';protocol=json.loads((folder/'protocol.json').read_text())
    assert protocol['outcome_guard'] and len(protocol['sources'])==37
    pieces=[]
    for i,spec in enumerate(protocol['sources']):
        a=pd.read_csv(folder/f'comparison_{i:02}.csv');assert a.opponent.eq(spec['opponent']).all()
        assert set(a.model)=={'open_model','frozen_challenger','opponent_score'}
        ix=['model','period','profile','top_n','return_treatment'];assert not a.duplicated(ix).any()
        for treatment in ['raw','capped']:
            sector=pd.read_csv(folder/f'sectors_{i:02}_{treatment}.csv.gz')
            expected=sector.groupby(ix[:-1])[METRICS].mean().sort_index()
            observed=a[a.return_treatment.eq(treatment)].set_index(ix[:-1])[METRICS].sort_index()
            pd.testing.assert_frame_equal(expected,observed,atol=1e-12,rtol=1e-12)
        pieces.append(a)
    full=pd.concat(pieces);ix=['opponent','period','profile','top_n','return_treatment']
    a=full.set_index(['model']+ix)[METRICS];differences=[]
    for model in ['open_model','frozen_challenger']:
        d=a.loc[model]-a.loc['opponent_score'];d.shortfall=-d.shortfall;d['model']=model;differences.append(d.reset_index())
    d=pd.concat(differences).sort_values(['model']+ix).reset_index(drop=True)
    saved=pd.read_csv(folder/'all_profile_directional_deltas.csv').sort_values(['model']+ix).reset_index(drop=True)
    pd.testing.assert_frame_equal(d,saved,check_dtype=False,atol=1e-12,rtol=1e-12)
    new=d[d.model.eq('open_model')];counts=[]
    for opponent,g in new.groupby('opponent'):
        v=g[METRICS].to_numpy().ravel();t=g[g.top_n.eq(3)][METRICS].to_numpy().ravel()
        counts.append(dict(opponent=opponent,regressions=int((v < -1e-12).sum()),comparisons=len(v),top3_regressions=int((t < -1e-12).sum()),top3_comparisons=len(t),all_cells_nonworse=bool((v>=-1e-12).all())))
    counts=pd.DataFrame(counts);counts.to_csv(folder/'verified_opponent_gates.csv',index=False)
    selected=json.loads((OUT/'selection.json').read_text());verification=json.loads((OUT/'verification.json').read_text())
    verification.update(legacy_policies_compared=37,legacy_arithmetic_verified=True,legacy_policy_gates_nonworse=int(counts.all_cells_nonworse.sum()),
      selected_candidate_legacy_regressions=int(counts.regressions.sum()),selected_candidate_legacy_comparisons=int(counts.comparisons.sum()),
      promotion_status='NOT_APPROVED' if not selected['strict_gate'] or not counts.all_cells_nonworse.all() else 'RETROSPECTIVE_GATE_PASS_REQUIRES_SOURCE_AND_FRESH_VALIDATION')
    verification['sha256'].update({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [folder/'protocol.json',folder/'all_profile_directional_deltas.csv',folder/'verified_opponent_gates.csv',OUT/'test_results.json']})
    (OUT/'verification.json').write_text(json.dumps(verification,indent=2))
    (OUT/'promotion_decision.json').write_text(json.dumps({k:v for k,v in verification.items() if k!='sha256'},indent=2))
    lines=['','## All earlier-policy comparisons — completed','',
      f"All **37 recoverable earlier policy labels** were compared to **{selected['model']}** on matching finite stocks and guarded outcome labels. These comparisons use the newly selected model, not the preceding challenger. The audit verified every sector aggregation and all directional deltas.",'',
      f"The candidate is nonworse in every recorded cell against **{int(counts.all_cells_nonworse.sum())} of 37 policies**. Across the complete older-policy panel there are **{int(counts.regressions.sum())} regressions in {int(counts.comparisons.sum())} comparisons**. Missing original model evidence is not treated as a victory.",'',
      'Recent (2024–2025), capped Top-3 metrics below average sectors and profiles equally. Opponent populations can differ; this is a paired comparison per row, not one cross-opponent league table.','',
      '| Earlier policy | New XIRR | Earlier XIRR | New drawdown | Earlier drawdown |','|---|---:|---:|---:|---:|']
    recent=full[full.period.eq('exposed')&full.return_treatment.eq('capped')&full.top_n.eq(3)]
    for spec in protocol['sources']:
        g=recent[recent.opponent.eq(spec['opponent'])].groupby('model')[METRICS].mean()
        if g.empty:continue
        n=g.loc['open_model'];o=g.loc['opponent_score']
        lines.append(f'| {spec["opponent"]} | {n.xirr:.2%} | {o.xirr:.2%} | {n.drawdown:.2%} | {o.drawdown:.2%} |')
    lines+=['',f'All comparisons and per-sector files are in `{OUT.relative_to(ROOT).as_posix()}/legacy-comparison/`. The previous inventory of non-comparable native studies and missing score policies still applies; this does not claim to have recreated every discarded or unpublished model.',
      '',f"**Final promotion status: {verification['promotion_status']}.** No live ranking-model switch was made."]
    report=ROOT/'research/reports'/({'rebuilt':'sector_price_rebuild','accuracy':'sector_accuracy','yeti':'sector_yetirank'}[family]+'_20261010.md')
    text=report.read_text(encoding='utf-8').split('\n## All earlier-policy comparisons')[0]
    report.write_text(text.rstrip()+'\n'+'\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in verification.items() if k!='sha256'},indent=2),flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--family',choices=['rebuilt','accuracy','yeti'],default='rebuilt');a=parser.parse_args();run(a.family)
