"""Verify and summarize the complete legacy/model/profile research campaign."""
import json,hashlib
from pathlib import Path
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'experiments/all-model-sector-audit-20261008'
NEW=ROOT/'experiments/full-coverage-open-models-20261008'
PROFILE=ROOT/'experiments/profile-aware-sector-20261008'
METRICS=['xirr','drawdown','achievement','shortfall','ndcg','rank_ic']

def run():
    protocol=json.loads((OLD/'protocol.json').read_text());specs=protocol['sources']
    pieces=[]
    for i,spec in enumerate(specs):
        path=OLD/f'comparison_{i:02}.csv';a=pd.read_csv(path)
        assert a.opponent.eq(spec['opponent']).all()
        ix=['period','profile','top_n','return_treatment']
        assert not a.duplicated(['model']+ix).any()
        assert set(a.model)=={'open_model','frozen_challenger','opponent_score'}
        assert np.isfinite(a[METRICS]).all().all()
        keys={n:set(map(tuple,g[ix].to_numpy())) for n,g in a.groupby('model')}
        assert keys['open_model']==keys['frozen_challenger']==keys['opponent_score']
        for treatment in ['raw','capped']:
            sector=pd.read_csv(OLD/f'sectors_{i:02}_{treatment}.csv.gz')
            expected=sector.groupby(['model','period','profile','top_n'])[METRICS].mean().sort_index()
            observed=a[a.return_treatment.eq(treatment)].set_index(['model','period','profile','top_n'])[METRICS].sort_index()
            pd.testing.assert_frame_equal(expected,observed,check_exact=False,atol=1e-12,rtol=1e-12)
        pieces.append(a)
    full=pd.concat(pieces,ignore_index=True);ix=['opponent','period','profile','top_n','return_treatment']
    matrix=full.set_index(['model']+ix)[METRICS];differences=[]
    for model in ['open_model','frozen_challenger']:
        d=matrix.loc[model]-matrix.loc['opponent_score'];d.shortfall=-d.shortfall;d['model']=model;differences.append(d.reset_index())
    delta=pd.concat(differences,ignore_index=True)
    saved=pd.read_csv(OLD/'all_profile_directional_deltas.csv').sort_values(['model']+ix).reset_index(drop=True)
    expected=delta.sort_values(['model']+ix).reset_index(drop=True)
    np.testing.assert_allclose(expected[METRICS],saved[METRICS],atol=1e-12,rtol=1e-12)
    summary=delta.groupby(['model','opponent','period','top_n','return_treatment'])[METRICS].mean().reset_index()
    summary['all_six_nonworse']=summary[METRICS].ge(-1e-12).all(axis=1)
    summary.to_csv(OLD/'equal_profile_summary.csv',index=False)
    training=pd.read_csv(PROFILE/'training_audit.csv')
    assert len(training)==24 and not training.duplicated(['year','model']).any()
    assert training.training_profiles.eq(9).all()
    assert (training.max_training_endpoint < training.year.astype(str)+'-01-01').all()
    profile=pd.read_csv(PROFILE/'summary.csv');trials=pd.read_csv(PROFILE/'trials.csv')
    assert len(trials)==24
    pa=profile.set_index(['model','period','profile','top_n','scope','return_treatment'])[METRICS]
    for row in trials.itertuples():
        all_values=[];top3=[]
        for ref in ['open_model','frozen_challenger','sector_incumbent']:
            d=(pa.loc[row.model]-pa.loc[ref]).dropna();d.shortfall=-d.shortfall
            all_values.extend(d.to_numpy().ravel());top3.extend(d.xs(3,level='top_n').to_numpy().ravel())
        assert len(all_values)==row.total_cells and sum(v < -1e-12 for v in all_values)==row.regressing_cells
        assert sum(v < -1e-12 for v in top3)==row.top3_regressing_cells
        assert bool(all(v>=-1e-12 for v in all_values) and any(v>1e-12 for v in all_values))==bool(row.strict_gate)
    current=pd.read_csv(NEW/'current_all_stock_rankings.csv').set_index('isin')
    historical_replay=json.loads((NEW/'historical_reproduction.json').read_text())
    assert historical_replay['match'] and historical_replay['annual_fits_replayed']==72
    replay=pd.read_csv(NEW/'inference_replay.csv').set_index('isin').reindex(current.index)
    assert len(current)==4436 and current.index.is_unique
    np.testing.assert_allclose(current.open_model_score,replay.open_model_score,atol=1e-12,rtol=0)
    np.testing.assert_array_equal(current.open_model_sector_rank,replay.open_model_sector_rank)
    identifiers=pd.read_csv(OLD/'model_identifier_registry_reviewed.csv')
    verification={'legacy_policy_labels_compared':len(specs),'legacy_sector_aggregation_verified':True,'legacy_metric_deltas_verified':True,
      'profile_aware_fits':24,'profile_aware_candidates':24,'profile_aware_strict_passes':int(trials.strict_gate.sum()),
      'current_stocks':4436,'current_inference_reproduced':True,'new_candidates_total':299,
      'artifact_identifiers':len(identifiers),'numeric_metadata_identifiers':int(identifiers.numeric_label.sum()),
      'all_50_initial_candidates_historically_reproduced':True,'fresh_validation':False,'production_replaced':False}
    hashpaths=[OLD/'protocol.json',OLD/'equal_profile_summary.csv',OLD/'all_profile_directional_deltas.csv',PROFILE/'protocol.json',PROFILE/'trials.csv',PROFILE/'training_audit.csv',NEW/'selection.json',NEW/'current_all_stock_rankings.csv']
    hashpaths+=list(NEW.glob('current_*.pkl'))+list((NEW/'frozen_anchor').glob('*.txt'))+[NEW/'historical_reproduction.json']
    verification['sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in hashpaths}
    (OLD/'verification.json').write_text(json.dumps(verification,indent=2))
    selected=json.loads((NEW/'selection.json').read_text())
    lines=['# Sector ranking: full research and previous-model audit — 8 October 2026','',
      '## Result','',
      '**A stronger base-profile Top-3 research challenger was built, but a universally superior replacement has not been established. Production remains unchanged.**',
      '',f"The frozen new candidate is `{selected['name']}`: 95% of the prior full-coverage challenger, 2.5% defensive CatBoost relevance rank and 2.5% defensive ridge relevance rank. It scores all **4,436 project stocks**, using the existing 3 October 2026 snapshot. Seventeen stocks lack usable price evidence and receive a neutral tied prior; coverage does not imply confident forecasts or trade eligibility.",
      '', 'At the base7500 profile and Top-3 cutoff, it improves all five outcome metrics against both prior references across 2020–2023/2024–2025, common/expanded universes and raw/capped returns: **zero regressions in 80 comparisons**. Broader Top-1/3/5 testing has **24 regressions in 240 base-profile cells**, and the nine-profile transfer test has **465 regressions in 2,160 cells** (125 of 720 at Top-3). Therefore the narrower win is not an all-profile or whole-ranking victory.',
      '', '## Research actually performed','',
      '- 50 CatBoost, XGBoost, Extra Trees, ridge and ensemble candidates; 72 annual endpoint-purged fits.',
      '- 27 sector-specific partially pooled ridge candidates; 18 annual global/local expert sets.',
      '- 198 small two-model blends, explicitly marked as adaptive after earlier results were seen.',
      '- Signals include closing-high proximity/age, 52-week-high freshness and support, 12–1 and six-month momentum, downside volatility/frequency, historical drawdown, history length, observed growth rates, trading continuity and observation count, plus sector-relative percentiles and missing-evidence indicators. Current fundamental statements were not inserted into historical training.',
      f'- 24 profile-aware LightGBM blends, trained on all nine settings with amount/lookback/interval/target inputs and equal date-sector-profile weights. 24 annual fits; strict passes: **{int(trials.strict_gate.sum())}**.',
      '- **299 new candidate configurations** in this campaign. These counts are not independent statistical trials or evidence that all possible algorithms have been exhausted.',
      '', '## Previous project models','',
      f'The retained evidence inventory covers 355 CSV evidence artifacts and {len(identifiers)} identifiers. {int(identifiers.numeric_label.sum())} are numeric metadata labels. Identifiers also include repeated builds, component names and trial settings, so they must not be described as that many distinct trained models.',
      '',f'**{len(specs)} recoverable policy labels were replayed** against the new and prior full-coverage challengers on matching sector/date/profile stocks. This covers up to 28 decision dates in 2020–2025; 2016–2019 data supplies earlier training rather than backcast predictions from a later fitted model. All nine profiles, Top-1/3/5, raw/capped returns and six metrics including rank IC are retained. Each comparison uses its own common population; different opponents can have different dates and stocks. Saved earlier scores are evaluated on one common outcome source, not falsely presented as full reproductions of their original trading pipelines.',
      '', 'Returns below are equal-profile/equal-sector averages of date-level median constituent SIP XIRRs. Drawdown is mean constituent drawdown. These are ranking diagnostics, not a realized portfolio XIRR, portfolio maximum drawdown or net-of-cost portfolio backtest.',
      '', '| Earlier policy | Recent raw Top-3 XIRR: new | Earlier | Recent capped Top-3 XIRR: new | Earlier |','|---|---:|---:|---:|---:|']
    means=full.groupby(['opponent','model','period','top_n','return_treatment'])[METRICS].mean()
    for spec in specs:
        name=spec['opponent']
        try:
            v=[means.loc[(name,m,'exposed',3,t),'xirr'] for t in ['raw','capped'] for m in ['open_model','opponent_score']]
            lines.append(f'| {name} | {v[0]:.2%} | {v[1]:.2%} | {v[2]:.2%} | {v[3]:.2%} |')
        except KeyError:lines.append(f'| {name} | No recent matched evidence | — | — | — |')
    lines+=['','Large raw-return advantages can depend on extreme cached outcomes. Both treatments are shown; capping is a sensitivity test, not a data repair. Drawdown, achievement, shortfall, NDCG, rank IC and every sector/profile result remain in the CSVs. No older model is declared defeated simply because another metric looks better.',
      '', '### Considered but not honestly comparable on this panel','',
      '| Family | Evidence treatment |','|---|---|',
      '| Original strict Baseline V1 / Research V2 | Different exact dates, dated fundamentals and original eligible cohorts. The separate four-factor formula replay is labeled as a replay, not a reproduction of Research V2. No blanket superiority claim. |',
      '| Early factor V1–V3, broad chronological price ML and V5 | Native chronological price-return studies retained; their original dates/labels do not match this SIP panel. Extra Trees, ridge and LightGBM algorithm families were also retested in the new campaign. |',
      '| Greenblatt India and complete-universe evidence tiers | Current screens/coverage policies; no matched point-in-time performance history supplied. |',
      '| Discarded history, hybrid, successor and fixed-blend trial settings | All retained identifiers/native results considered; not every discarded trial retained stock-level predictions. Missing results are not wins. |',
      '| Prospective protocols | Do not infer matured out-of-sample performance from a protocol or a sealed score file. |',
      '| Qlib TRA, DoubleEnsemble and metric-tool integrations | Synthetic/adaptor or infrastructure evidence is not an evaluated Indian-stock strategy. |',
      '', 'This is an inventory of retained local evidence and previously recovered Git archives. It cannot recover unrecorded or deleted work, and does not claim to have tested every published model.',
      '', '## Data and reasoning checks','',
      '- Current frozen scores and ranks were independently reproduced for all 4,436 identities. All 72 saved first-round annual fits were replayed and all 50 initial candidate metric tables reproduced to 1e-12, without retraining. Existing 34 regression tests plus the new batched-evaluator test passed.',
      '- Evidence confidence measures feature completeness only. HIGH is not calibrated forecast confidence or certification that corporate actions are fully reconciled. Unclassified stocks retain an explicit unclassified-pool scope rather than a verified sector rank.',
      '- The existing independent company-quality rubric was joined to every current stock. Its Top-3 means for production/prior/new are 0.557853/0.557300/0.557615 on common stocks and 0.557853/0.564227/0.567194 on the expanded universe. This rubric is a transparent evidence check, not human or AI ground truth about future returns.',
      '- A concrete corporate-action concern was found in Sejal Glass: its [2021–22 annual report](https://sejalglass.co.in/document/Annual%20Report%202021-2022.pdf) documents a major share consolidation within the window of an extreme cached outcome. Holdings/cash flows require reconciliation; source prices or labels were not silently changed.',
      '- All dates have been researched before. Annual endpoint purging prevents direct future-outcome training leakage, but it does not undo repeated model-selection exposure. Current sector classifications and a surviving universe also limit historical claims.',
      '', '## Research foundations','',
      '[CatBoost, NeurIPS 2018](https://proceedings.neurips.cc/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html), [XGBoost, KDD 2016](https://doi.org/10.1145/2939672.2939785), [Extra Trees, Machine Learning 2006](https://doi.org/10.1007/s10994-006-6226-1), and [LightGBM ranking documentation](https://lightgbm.readthedocs.io/en/latest/Parameters.html). These support methods, not a promise of profitable stock selection.',
      '', '## Saved deliverables','',
      '- `experiments/full-coverage-open-models-20261008/current_all_stock_rankings.csv`: complete new research ranking.',
      '- `experiments/full-coverage-open-models-20261008/current_sector_top3_review.csv`: company-evidence review.',
      '- `experiments/all-model-sector-audit-20261008/equal_profile_summary.csv`: previous-policy comparisons by period.',
      '- `experiments/all-model-sector-audit-20261008/sectors_*.csv.gz`: each sector/profile result.',
      '- `experiments/profile-aware-sector-20261008/trials.csv`: all profile-aware trials.',
      '- `experiments/all-model-sector-audit-20261008/verification.json`: independent arithmetic, temporal and reproduction checks.',
      '', 'Run `python research/runners/final_sector_research_audit_20261008.py` to regenerate this report after all experiment runners complete. Extra Trees fitted models were losslessly archived with hash verification to recover disk space. Disposable caches were temporarily removed; the primary prediction caches were subsequently restored from the saved fits and verified against all 50 original result tables. Model parameters, fitted artifacts and trial results remain reproducible.']
    if (ROOT/'experiments/sector-action-integrity-20261008/verification.json').exists():
        lines[2:2]=['> Superseded performance assessment: a corporate-action outcome defect was confirmed after this campaign. See `sector_champion_integrity_followup_20261008.md` for the simulator fix, guarded comparisons and final promotion decision. Earlier unfiltered wins below are retained for audit, not clean validation.','']
    (ROOT/'research/reports/sector_research_complete_20261008.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in verification.items() if k!='sha256'},indent=2),flush=True)

if __name__=='__main__':run()
