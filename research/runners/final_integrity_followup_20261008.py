"""Independent checks and final promotion decision after the action audit."""
import json, hashlib, gc
from pathlib import Path
import numpy as np
import pandas as pd
from sector_championship_20261005 import KEYS, METRICS, ROOT

ACTION=ROOT/'experiments/sector-action-integrity-20261008'
GUARD=ROOT/'experiments/action-guarded-sector-20261008'
LEGACY=ROOT/'experiments/action-guarded-legacy-sector-20261008'
ROUTER=ROOT/'experiments/sector-expert-router-20261008'
NEW=ROOT/'experiments/full-coverage-open-models-20261008'

def verify_trials(directory, expected):
    summary=pd.read_csv(directory/'summary.csv')
    trials=pd.read_csv(directory/'trials.csv')
    assert len(trials)==expected
    index=['model','period','profile','top_n','scope','return_treatment']
    assert not summary.duplicated(index).any()
    assert summary.profile.nunique()==9
    a=summary.set_index(index)[METRICS]
    for row in trials.itertuples():
        name=getattr(row,'model',None) or row.name
        values=[];top3=[]
        for ref in ['open_model','frozen_challenger','sector_incumbent']:
            d=(a.loc[name]-a.loc[ref]).dropna();d.shortfall=-d.shortfall
            values.extend(d.to_numpy().ravel());top3.extend(d.xs(3,level='top_n').to_numpy().ravel())
        assert len(values)==row.total_cells==3240
        assert len(top3)==row.top3_cells==1080
        assert sum(v < -1e-12 for v in values)==row.regressing_cells
        assert sum(v < -1e-12 for v in top3)==row.top3_regressing_cells
        assert bool(all(v>=-1e-12 for v in values) and any(v>1e-12 for v in values))==bool(row.strict_gate)
    return trials

def run():
    guard=verify_trials(GUARD,28);router=verify_trials(ROUTER,16)
    training=pd.read_csv(GUARD/'training_audit.csv')
    assert len(training)==24 and training.training_profiles.eq(9).all()
    assert (training.max_training_endpoint < training.year.astype(str)+'-01-01').all()
    feedback=pd.read_csv(ROUTER/'feedback_audit.csv')
    assert feedback.profile.nunique()==9
    assert (feedback.max_feedback_endpoint.dropna() < feedback.loc[feedback.max_feedback_endpoint.notna(),'decision_date']).all()
    source=pd.read_pickle(ROOT/'experiments/profile-aware-sector-20261008/prepared.pkl.gz',compression='gzip')[KEYS+['future_xirr','future_drawdown','future_shortfall']]
    guarded=pd.read_pickle(GUARD/'prepared.pkl.gz',compression='gzip')[KEYS+['future_xirr','future_drawdown','future_shortfall']]
    flags=pd.read_csv(ACTION/'unreconciled_outcome_windows.csv.gz',usecols=KEYS).drop_duplicates();flags['flag']=True
    merged=source.merge(flags,on=KEYS,how='left',validate='one_to_one');mask=merged.flag.eq(True)
    pd.testing.assert_frame_equal(source[KEYS],guarded[KEYS])
    labels=['future_xirr','future_drawdown','future_shortfall']
    assert guarded.loc[mask,labels].isna().all().all()
    np.testing.assert_allclose(source.loc[~mask,labels],guarded.loc[~mask,labels],equal_nan=True,atol=0,rtol=0)
    del source,guarded,merged;gc.collect()
    protocol=json.loads((LEGACY/'protocol.json').read_text());assert protocol['outcome_guard']
    specs=protocol['sources'];assert len(specs)==37
    pieces=[]
    for i,spec in enumerate(specs):
        a=pd.read_csv(LEGACY/f'comparison_{i:02}.csv');assert a.opponent.eq(spec['opponent']).all()
        ix=['model','period','profile','top_n','return_treatment'];assert not a.duplicated(ix).any()
        for treatment in ['raw','capped']:
            s=pd.read_csv(LEGACY/f'sectors_{i:02}_{treatment}.csv.gz')
            expected=s.groupby(ix[:-1])[METRICS].mean().sort_index()
            actual=a[a.return_treatment.eq(treatment)].set_index(ix[:-1])[METRICS].sort_index()
            pd.testing.assert_frame_equal(expected,actual,atol=1e-12,rtol=1e-12)
        pieces.append(a)
    full=pd.concat(pieces);ix=['opponent','period','profile','top_n','return_treatment']
    a=full.set_index(['model']+ix)[METRICS];deltas=[]
    for model in ['open_model','frozen_challenger']:
        d=a.loc[model]-a.loc['opponent_score'];d.shortfall=-d.shortfall;d['model']=model;deltas.append(d.reset_index())
    delta=pd.concat(deltas).sort_values(['model']+ix).reset_index(drop=True)
    saved=pd.read_csv(LEGACY/'all_profile_directional_deltas.csv').sort_values(['model']+ix).reset_index(drop=True)
    pd.testing.assert_frame_equal(delta,saved,check_dtype=False,atol=1e-12,rtol=1e-12)
    integrity=json.loads((ACTION/'verification.json').read_text())
    selection=json.loads((GUARD/'current_selection.json').read_text())
    assert selection['saved_model_inference_reproduced_exactly'] and selection['stocks']==4436
    assert selection['max_training_endpoint'] < selection['as_of']
    export=pd.read_csv(GUARD/'current_all_stock_rankings.csv')
    assert len(export)==4436 and export['isin'].is_unique and np.isfinite(export.guarded_model_score).all()
    assert export.loc[export.evidence_fraction.eq(0),'guarded_model_score'].eq(.5).all()
    replay=pd.read_csv(ACTION/'sejal_simulation_replay.csv')
    corrected=replay[replay.variant.eq('retained_ledger_with_guard')]
    assert len(corrected)==1 and corrected.status.eq('UNRESOLVED_CORPORATE_ACTION').all() and corrected.xirr.isna().all()
    result={'status':'NOT_APPROVED_FOR_PROMOTION','reason':'No evaluated challenger satisfies the declared broad comparison gate. Historical labels have confirmed action defects; exclusion is a sensitivity analysis, not complete source repair.',
      'new_candidate_configurations':343,'router_candidates':16,'guarded_blends_and_pure_models':28,
      'guarded_strict_passes':int(guard.strict_gate.sum()),'router_strict_passes':int(router.strict_gate.sum()),
      'legacy_policy_labels_recompared_with_guard':37,'all_nine_profiles':True,
      'label_mask_verified':True,'legacy_sector_aggregations_verified':True,'trial_arithmetic_verified':True,
      'guarded_training_fits':24,'training_endpoints_purged':True,'router_feedback_matured':True,
      'fresh_holdout':False,'feature_history_fully_repaired':False,'production_replaced':False,'simulator_guard_enabled_by_default':True,
      'current_full_coverage_candidate_stocks':4436,'current_snapshot':'2026-10-03','current_guarded_export_reproduced':True,
      'unreconciled_provider_events':integrity['unreconciled_events'],'finite_outcome_rows_excluded':integrity['finite_outcome_windows_flagged']}
    paths=[GUARD/'trials.csv',GUARD/'training_audit.csv',ROUTER/'trials.csv',ROUTER/'feedback_audit.csv',LEGACY/'protocol.json',LEGACY/'all_profile_directional_deltas.csv',ACTION/'verification.json',ROOT/'src/stock_research/personalized_official_actions.py',ACTION/'sejal_simulation_replay.csv']
    result['sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    result['sha256'].update({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [GUARD/'current_selection.json',GUARD/'current_all_stock_rankings.csv',GUARD/'current_guarded_ranker.txt']})
    (ACTION/'final_verification.json').write_text(json.dumps(result,indent=2))
    (NEW/'promotion_decision.json').write_text(json.dumps(result,indent=2))
    (GUARD/'promotion_decision.json').write_text(json.dumps(result,indent=2))
    best=guard.iloc[0];pure=guard[guard.model.str.endswith('_blend1.0')].iloc[0];route=router.iloc[0]
    lines=['# Sector championship: completed integrity follow-up — 8 October 2026','',
      '**Promotion decision: no clean replacement has been established. The frozen full-coverage candidate remains research-only.**','',
      'This follow-up supersedes performance conclusions in the earlier campaign report wherever they rely on the unfiltered outcome labels. It does not delete prior evidence or redefine a failed gate as success.','',
      '## Work completed','',
      '- 343 new candidate configurations across the campaign: 299 previous, 16 delayed-feedback sector selectors, and 28 action-guarded blends/pure rankers. Candidate configurations are correlated and adaptively researched, not independent validation trials.',
      '- Recompared all 37 recoverable earlier policy labels, including V17, the baseline formula replay and professor whole-share policy, after applying the same outcome exclusions to both sides. All nine profiles, within-sector Top-1/3/5, raw/capped returns and six metrics are retained.',
      '- All 24 new annual fits exclude outcome endpoints on or after their test-year start. All selector feedback matured before the ranking date. Arithmetic, sector aggregation and identical label masking were verified.',
      '- Four pure learned rankers were also evaluated without blending the old anchor into their predictions. Their price-derived input features still require a complete source-history audit.','',
      f"The closest guarded candidate, **{selection['name']}**, has been fitted on all nine profiles using only matured, unflagged outcomes, frozen and exported for **4,436 stocks at base7500**. Reloading the saved model reproduces every score exactly. This is a concrete research deliverable, not a promotion or an all-profile current export.",'',
      '## Confirmed data defect','',
      'Sejal Glass has a retained 2021–2022 annualized SIP-return label of approximately **908,601%**. Replaying the old ledger reproduces it. The provider ledger includes a consolidation absent from the official ledger, so the simulator reverses a price adjustment without the corresponding holdings adjustment.',
      'The [issuer annual report](https://sejalglass.co.in/document/Annual%20Report%202021-2022.pdf) documents 33,550,000 existing shares becoming 100,000. Inserting that event makes the simulator correctly stop with unresolved fractional entitlement; a corrected economic return cannot be asserted until entitlement mechanics are resolved.','',
      '**Implemented source fix:** `OfficialActionHistoryBook` now checks provider/official multiplier alignment by default and withholds metrics for investment windows crossing a mismatch. The real Sejal replay verifies that the original bad ledger now produces an unresolved-action status and no XIRR. The old result is reproducible only with an explicit forensic opt-out. Existing saved historical labels are not silently rewritten.','',
      f"The alignment screen found **{integrity['unreconciled_events']} unresolved provider events** and excluded **{integrity['finite_outcome_windows_flagged']:,} finite outcome rows** across profiles. These are not unique stock counts. Not every mismatch is a proven error; dates, identity mappings and multipliers need adjudication. Matching events do not certify that all remaining data is correct.",
      '', '## Final experiment results','',
      '| Family | Closest configuration by Top-3 gate | Top-3 regressions | All comparisons regressing |','|---|---|---:|---:|',
      f"| Action-guarded blends/pure models | {best.model} | {best.top3_regressing_cells}/1080 | {best.regressing_cells}/3240 |",
      f"| Pure guarded rankers only | {pure.model} | {pure.top3_regressing_cells}/1080 | {pure.regressing_cells}/3240 |",
      f"| Delayed-feedback sector selector | {route['name']} | {route.top3_regressing_cells}/1080 | {route.regressing_cells}/3240 |",
      '', 'At base7500 on common stocks, the guarded 20% blend has capped Top-3 XIRR of 31.11% (2020–2023) and 0.51% (2024–2025), versus production at 30.83% and -0.79%. The older full-coverage open-model candidate has 31.35% and 0.83% on those same guarded cells. Thus the retrained model improves on production here but does not dominate its immediate predecessor. Recent mean constituent drawdown improves to -30.99%, versus production -33.16% and the earlier candidate -31.50%. These are retrospective diagnostics, not expected returns.',
      '', 'Selectors used the original outcome source and are retained as contaminated diagnostic experiments, not promotion evidence. Guarded models exclude unresolved labels during training and evaluation. Older anchor scores and historical input features were not rebuilt; blends can inherit those defects.',
      '', '## Guarded comparisons with earlier policies','',
      'The following recent-period Top-3 values compare the earlier frozen CatBoost/ridge open-model candidate with each older policy; they are not results for the newly retrained 20% blend. Values average profiles and sectors equally. Each opponent has its own matched stock/date population. SIP constituent-median XIRR is a ranking diagnostic, not portfolio return. Capping each stock outcome to [-100%, +100%] is an additional sensitivity check.',
      '', '| Earlier policy | New candidate, raw | Earlier, raw | New candidate, capped | Earlier, capped |','|---|---:|---:|---:|---:|']
    assert set(full.period)=={'development','exposed'}
    recent=full[(full.top_n==3)&full.period.eq('exposed')]
    means=recent.groupby(['opponent','return_treatment','model']).xirr.mean()
    for spec in specs:
        name=spec['opponent'];v=[means.loc[(name,t,m)] for t in ['raw','capped'] for m in ['open_model','opponent_score']]
        lines.append('| '+name+' | '+' | '.join(f'{100*n:.2f}%' for n in v)+' |')
    lines += ['', '## Interpretation and remaining promotion requirements','',
      'The full-coverage export contains 4,436 identities and reproduces exactly, but 17 have no usable price evidence and receive a neutral tied prior. Full coverage is not a reliability guarantee. The professor spreadsheet and the company-quality reasoning rubric are useful comparators, not ground truth about future performance.',
      'The company-evidence rubric was rejoined to all 4,436 newly ranked identities; 4,316 have a finite rubric score and 120 remain unscored by that rubric. On common stocks its mean sector Top-3 score is 0.560270 for the guarded candidate versus 0.557853 for production and 0.557615 for the earlier open-model candidate. On the expanded cohort it is 0.575085 versus the earlier candidate at 0.576227. Expanded review admits sectors with five evidence-covered stocks even when production has fewer than five; it is not directly comparable to earlier reports restricting expanded sectors to production-covered groups. This rubric also shows tradeoffs, not universal improvement.',
      'A clean promotion requires adjudicated corporate actions, rebuilt affected price features and outcome labels, and a predeclared evaluation on genuinely unexposed outcomes. The current-survivor universe, retrospective sector mapping and repeated historical model selection remain limitations. No amount of additional search on this panel removes them.',
      '', '## Artifacts','',
      '- `experiments/sector-action-integrity-20261008/final_verification.json`: final evidence checks.',
      '- `experiments/action-guarded-sector-20261008/trials.csv`: all 28 guarded candidates.',
      '- `experiments/action-guarded-sector-20261008/current_all_stock_rankings.csv`: latest guarded challenger, all stocks, base7500.',
      '- `experiments/action-guarded-sector-20261008/current_selection.json`: frozen fit, exact replay and explicit limitations.',
      '- `experiments/action-guarded-sector-20261008/all_stock_evidence_review.csv.gz`: company-evidence rubric joined to all current rankings; `rubric_protocol.json` defines comparison populations.',
      '- `experiments/action-guarded-legacy-sector-20261008/`: all 37 paired comparisons and sector-level details.',
      '- `experiments/full-coverage-open-models-20261008/promotion_decision.json`: explicit no-promotion decision; frozen ranking and model bytes preserved.',
      '- `experiments/full-coverage-open-models-20261008/current_all_stock_rankings.csv`: reproducible research ranking, not a certified champion.',
      '', 'Research methods include [CatBoost](https://proceedings.neurips.cc/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html), [XGBoost](https://doi.org/10.1145/2939672.2939785), [Extra Trees](https://doi.org/10.1007/s10994-006-6226-1), LightGBM, ridge and [delayed-feedback expert aggregation](https://proceedings.mlr.press/v128/korotin20a.html). These experiments do not exhaust every published model.']
    (ROOT/'research/reports/sector_champion_integrity_followup_20261008.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='sha256'},indent=2),flush=True)

if __name__=='__main__':run()
