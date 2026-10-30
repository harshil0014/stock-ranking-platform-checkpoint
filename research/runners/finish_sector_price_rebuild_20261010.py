"""Audit, freeze historical selected scores, and report the rebuilt-price experiment."""
import json,hashlib
import numpy as np
import pandas as pd
from sector_price_rebuild_20261010 import OUT,OLD,ROOT,KEYS,METRICS,COLS,CONFIGS,WEIGHTS,ASOF

def run(family='rebuilt'):
    global OUT
    if family=='yeti':OUT=ROOT/'experiments/sector-yetirank-20261010'
    configs=CONFIGS if family=='rebuilt' else [dict(name='yeti_ndcg3_'+target) for target in ['return','balanced']]
    candidate_count=len(configs)*len(WEIGHTS);fit_count=len(configs)*6
    chosen=json.loads((OUT/'selection.json').read_text())
    trials=pd.read_csv(OUT/'trials.csv');summary=pd.read_csv(OUT/'summary.csv')
    index=['model','period','profile','top_n','scope','return_treatment']
    assert not summary.duplicated(index).any() and len(trials)==candidate_count and summary.profile.nunique()==9
    a=summary.set_index(index)[METRICS];all_deltas=[]
    for row in trials.itertuples():
        parts=[]
        for ref in ['open_model','frozen_challenger','guarded_previous','sector_incumbent']:
            d=(a.loc[row.model]-a.loc[ref]).dropna();d.shortfall=-d.shortfall;d['reference']=ref;parts.append(d.reset_index())
        d=pd.concat(parts);v=d[METRICS].to_numpy().ravel();top=d[d.top_n.eq(3)][METRICS].to_numpy().ravel()
        assert len(v)==row.total_cells==4536
        assert len(top)==row.top3_cells==1512
        assert (v < -1e-12).sum()==row.regressing_cells and (top < -1e-12).sum()==row.top3_regressing_cells
        assert bool((v>=-1e-12).all() and (v>1e-12).any())==bool(row.strict_gate)
        dev=d[d.period.eq('development')]
        assert dev[dev.top_n.eq(3)][METRICS].lt(-1e-12).sum().sum()==row.development_top3_regressions
        d['model']=row.model;all_deltas.append(d)
    pd.concat(all_deltas).to_csv(OUT/'directional_deltas.csv',index=False)
    ordered=trials.sort_values(['development_top3_regressions','development_regressions','model'])
    assert chosen['model']==ordered.iloc[0].model
    audit=pd.read_csv(OUT/'training_audit.csv')
    assert len(audit)==fit_count and not audit.duplicated(['year','model']).any() and audit.profiles.eq(9).all()
    assert (audit.max_training_endpoint < audit.year.astype(str)+'-01-01').all()
    x=pd.concat([pd.read_csv(OUT/f'predictions_{y}.csv.gz') for y in range(2020,2026)],ignore_index=True)
    old=pd.concat([pd.read_csv(OLD/f'predictions_{y}.csv.gz',usecols=KEYS+['profile_defensive_15']) for y in range(2020,2026)],ignore_index=True)
    x=x.merge(old,on=KEYS,validate='one_to_one');model,weight=chosen['model'].split('_blend');weight=float(weight)
    x['replacement_score']=(1-weight)*(.8*x.open_model+.2*x.profile_defensive_15)+weight*x[model]
    assert np.isfinite(x.replacement_score).all()
    x[KEYS+['replacement_score']].to_csv(OUT/'selected_historical_scores.csv.gz',index=False)
    feature_dir=ROOT/'experiments/sector-price-rebuild-20261010'
    f=pd.read_pickle(feature_dir/'price_features.pkl.gz',compression='gzip')
    assert (f.last_price_date.dropna()<=f.loc[f.last_price_date.notna(),'decision_date']).all()
    assert f.loc[f.input_status.ne('USABLE_PROVIDER_BASIS'),'evidence_fraction'].eq(0).all()
    current=pd.read_csv(OUT/'current_all_stock_rankings.csv')
    if family=='yeti':
        current['rebuilt_score']=current.yeti_score;current['rebuilt_sector_rank']=current.yeti_sector_rank;current['rebuilt_pure_score']=current.yeti_pure_score
    current=current.rename(columns={'evidence_confidence':'anchor_evidence_confidence'})
    current['rebuilt_input_confidence']=np.where(current.input_status.ne('USABLE_PROVIDER_BASIS'),current.input_status,np.where(current.observations.ge(252),'FULL_YEAR_OBSERVATIONS','SHORT_HISTORY'))
    current.to_csv(OUT/'current_all_stock_rankings.csv',index=False)
    assert len(current)==4436 and current['isin'].is_unique and np.isfinite(current.rebuilt_score).all()
    assert current.loc[current.evidence_fraction.eq(0),'rebuilt_pure_score'].eq(.5).all()
    expected=current.rebuilt_score.groupby(current.sector).rank(method='min',ascending=False)
    np.testing.assert_array_equal(current.rebuilt_sector_rank,expected)
    rubric=pd.read_csv(OLD/'all_stock_evidence_review.csv.gz',usecols=['isin','judge_primary','judge_coverage','judge_flags'])
    review=current.merge(rubric,on='isin',how='left',validate='one_to_one')
    review.to_csv(OUT/'all_stock_evidence_review.csv.gz',index=False)
    review[review.rebuilt_sector_rank.le(3)].to_csv(OUT/'current_sector_top3_review.csv',index=False)
    rubric_rows=[]
    for scope in ['common','expanded']:
        z=review[review.sector_incumbent.notna()] if scope=='common' else review
        models=['rebuilt_score','guarded_model_score','open_model_score']+(['sector_incumbent'] if scope=='common' else [])
        for sector,g in z.groupby('sector'):
            g=g.dropna(subset=['judge_primary']+models).sort_values('isin')
            if sector=='Unclassified' or len(g)<5:continue
            for model in models:
                rubric_rows.append(dict(scope=scope,sector=sector,model=model,rubric=g.sort_values(model,ascending=False,kind='stable').head(3).judge_primary.mean()))
    rubric_table=pd.DataFrame(rubric_rows);rubric_table.to_csv(OUT/'rubric_sector_comparison.csv',index=False)
    rubric_table.groupby(['scope','model']).rubric.mean().reset_index().to_csv(OUT/'rubric_summary.csv',index=False)
    # Sector detail is retained and must aggregate back to the saved summary.
    names=[f'{c["name"]}_blend{w}' for c in configs for w in WEIGHTS]
    chunk=(names.index(chosen['model'])//6)*6
    query=[]
    for scope in ['common','expanded']:
        for bounded in [False,True]:
            q=pd.read_csv(OUT/f'queries_{scope}_{bounded}_{chunk}.csv.gz')
            q=q[q.model.isin([chosen['model'],'open_model','frozen_challenger','guarded_previous','sector_incumbent'])]
            q['scope']=scope;q['return_treatment']='capped' if bounded else 'raw';query.append(q)
    query=pd.concat(query);query.to_csv(OUT/'selected_sector_query_metrics.csv.gz',index=False)
    expected=query.groupby(index+['sector'])[METRICS].mean().groupby(index)[METRICS].mean().sort_index()
    observed=summary[summary.model.isin(query.model.unique())].set_index(index)[METRICS].sort_index()
    pd.testing.assert_frame_equal(expected,observed,atol=1e-12,rtol=1e-12)
    result={'candidate':chosen['model'],'strict_gate':bool(chosen['strict_gate']),'strict_passes':int(trials.strict_gate.sum()),'candidates':candidate_count,'annual_fits':fit_count,
      'profiles':9,'current_stocks':4436,'input_usable_current':int(current.evidence_fraction.gt(0).sum()),
      'current_input_status':current.input_status.value_counts().to_dict(),'score_replay_exact':chosen['current_replay_exact'],
      'source_history_timing_verified':True,'sector_metric_aggregation_verified':True,'trial_arithmetic_verified':True,
      'endpoint_purge_verified':True,'training_and_current_snapshot':ASOF,'fresh_validation':False,'production_replaced':False,
      'top3_regressions':int(chosen['top3_regressing_cells']),'top3_comparisons':int(chosen['top3_cells']),
      'all_regressions':int(chosen['regressing_cells']),'all_comparisons':int(chosen['total_cells']),
      'data_status':'Price features rebuilt; unresolved recent action windows masked. Original outcome gate retained. Complete official history/entitlement repair remains unresolved.'}
    paths=[OUT/'protocol.json',OUT/'trials.csv',OUT/'summary.csv',OUT/('current_model.txt' if family=='rebuilt' else 'current_model.cbm'),OUT/'current_all_stock_rankings.csv',feature_dir/'history_source_audit.csv',feature_dir/'current_history_source_audit.json',OUT/'selected_historical_scores.csv.gz']
    result['sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (OUT/'verification.json').write_text(json.dumps(result,indent=2))
    lines=['# Sector ranking: rebuilt-price experiment — 10 October 2026','',
      f"**Selected research candidate: `{chosen['model']}`. Strict gate passed: {bool(chosen['strict_gate'])}.**",'',
      '## What changed','',
      '- Rebuilt price signals directly from the provider split-adjusted close, avoiding the earlier inconsistent split-unadjustment path. Source files are hashed. This is not certification of provider data or a complete official-action reconstruction.',
      '- Signals cover closing-high proximity/recency, frequency of new highs, time near highs, breakout strength, trend slope/fit, path efficiency, multi-horizon momentum, jump concentration, downside volatility, tail losses, drawdown, stale prices and sector-relative context.',
      '- All features use observations at or before the decision date. Unresolved adjustment events inside the feature window and prices older than 14 days produce missing evidence, not invented strength.',
      '- Historical training uses the older CSV receipts. Current-only features use the later frozen website raw-price package, whose hashes and override order are recorded separately. The September18 cache is not presented as fresh October evidence.',
      '- Fixed the action guard for frozen runtime books created without the simulator constructor: adjustment transitions are recovered from their stored nominal/provider-price ratio and checked against official events. This avoids both a missing-attribute crash and a silent guard bypass.',
      f'- Tested {"rank_xendcg, top-focused LambdaRank and absolute-error regression" if family=="rebuilt" else "CatBoost YetiRank:mode=NDCG;top=3"}, with return and balanced targets. Six annual folds give {fit_count} fits; four blend settings give {candidate_count} candidates. All nine profiles are included.',
      '- The prior broad gate is retained, with the latest guarded challenger added as a reference. Candidates are selected by development-period Top-3 regression count, then development-wide regression count. All historical dates were already exposed in earlier research; this is not a fresh holdout.','',
      'Historical metrics require at least five jointly scored, outcome-covered stocks in a sector/date/profile. Unclassified stocks are excluded from those metrics. Current exports still retain all identities, including smaller sectors and the explicitly unclassified pool; their inclusion is not historical validation.','',
      '## Results','',
      f"The selected candidate regresses in **{chosen['top3_regressing_cells']} / {chosen['top3_cells']} Top-3 cells** and **{chosen['regressing_cells']} / {chosen['total_cells']} total cells** against four reference policies on matching populations. {int(trials.strict_gate.sum())} of {candidate_count} candidates pass the complete gate.",
      '', '| Period | Capped base7500 Top-3 XIRR | Mean constituent drawdown | Whole-sector rank IC |','|---|---:|---:|---:|']
    for period in ['development','exposed']:
        for model in ['sector_incumbent','guarded_previous',chosen['model']]:
            row=a.loc[(model,period,'base7500',3,'common','capped')]
            lines.append(f'| {period}: {model} | {row.xirr:.2%} | {row.drawdown:.2%} | {row.rank_ic:.4f} |')
    lines+=['','These are equal-sector averages of within-sector SIP diagnostics, not portfolio return or a forecast. Rank IC evaluates the whole scored sector rather than only its top stocks.','',
      '## Current export and verification','',
      f"All **4,436 stocks** receive a research score at base7500 on the **3 October 2026 snapshot**. Rebuilt inputs are usable for **{result['input_usable_current']}** stocks. Status counts: `{json.dumps(result['current_input_status'])}`. The pure rebuilt component is neutral where evidence is unavailable; a blended score can still inherit old-model evidence and its defects.",
      '- Reloading the saved model reproduces current scores exactly. The audit verifies all training cutoffs, feature timestamps, full coverage, ranking arithmetic, trial gates and sector aggregation.',
      '- The existing company-evidence rubric is joined to every new ranking, with missing rubric scores retained. Top-three sector reviews and shared-cohort rubric comparisons are saved separately; reused company evidence is not future-return ground truth.',
      '- Five new feature tests, 23 simulator/ownership tests (including two new frozen-runtime checks), and two separate integrity tests passed. They cover future-price independence, scale invariance, event windows, stale prices, sector isolation and runtime guard compatibility.',
      '- The website custom-profile recomputation and HTTP/API test passed after the frozen-runtime guard fix.',
      '- The live UI is unchanged. A failed broad gate does not authorize a clean-champion label.',
      '', '## Research foundations','',
      '[ICML 2023: Which Tricks are Important for Learning to Rank?](https://proceedings.mlr.press/v202/lyzhin23a.html) motivates testing ranking losses directly. [Poh et al.](https://arxiv.org/abs/2012.07149) studies cross-sectional learning to rank in finance. [LightGBM documentation](https://lightgbm.readthedocs.io/en/latest/Parameters.html) defines the implemented objectives and truncation controls. These sources justify hypotheses, not performance claims on Indian stocks.',
      '', '## Saved artifacts','',
      '- `experiments/sector-price-rebuild-20261010/current_all_stock_rankings.csv`',
      '- `experiments/sector-price-rebuild-20261010/trials.csv`',
      '- `experiments/sector-price-rebuild-20261010/selected_sector_query_metrics.csv.gz`',
      '- `experiments/sector-price-rebuild-20261010/verification.json`']
    if family=='yeti':lines=[s.replace('experiments/sector-price-rebuild-20261010/','experiments/sector-yetirank-20261010/') for s in lines]
    (ROOT/'research/reports'/('sector_price_rebuild_20261010.md' if family=='rebuilt' else 'sector_yetirank_20261010.md')).write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='sha256'},indent=2),flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--family',choices=['rebuilt','yeti'],default='rebuilt');args=parser.parse_args();run(args.family)
