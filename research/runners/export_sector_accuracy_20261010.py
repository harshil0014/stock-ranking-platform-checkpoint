"""Freeze the development-selected whole-sector accuracy candidate and its limits."""
import json,hashlib,shutil
import numpy as np
import pandas as pd
import lightgbm as lgb
import sector_price_rebuild_20261010 as p
from sector_accuracy_20261010 import OUT,SOURCES

def run():
    selected=json.loads((OUT/'selection.json').read_text());folder=SOURCES[selected['family']]
    name,weight=selected['model'].split('_blend');weight=float(weight)
    trial=pd.read_csv(folder/'trials.csv').set_index('model').loc[selected['model']].to_dict()
    selected.update(trial)
    family_selected=json.loads((folder/'selection.json').read_text())
    extension='txt' if selected['family']=='rebuilt' else 'cbm'
    path=OUT/f'current_model.{extension}'
    if selected['family']=='yeti':
        from sector_yetirank_20261010 import CatBoostRanker,fit,CONFIGS
    else:fit,CONFIGS=p.fit,p.CONFIGS
    if family_selected['model'].split('_blend')[0]==name:
        shutil.copyfile(folder/f'current_model.{extension}',path)
        training_endpoint=family_selected['max_training_endpoint']
    else:
        x=pd.read_pickle(SOURCES['rebuilt']/'prepared.pkl.gz',compression='gzip')
        m,t=fit(x[x.endpoint.lt(p.ASOF)],next(c for c in CONFIGS if c['name']==name))
        if extension=='txt':m.booster_.save_model(str(path))
        else:m.save_model(str(path))
        training_endpoint=t.endpoint.max()
        del x,t,m
    model=lgb.Booster(model_file=str(path)) if extension=='txt' else CatBoostRanker()
    if extension=='cbm':model.load_model(str(path))
    current=pd.read_csv(p.OLD/'current_all_stock_rankings.csv')
    features=pd.read_pickle(SOURCES['rebuilt']/'price_features.pkl.gz',compression='gzip')
    features=features[features.decision_date.eq(p.ASOF)]
    z=current.drop(columns=[c for c in p.COLS if c in current and c not in p.PARAMS]+['input_status','last_price_date'],errors='ignore').merge(features.drop(columns='sector'),on=['isin','decision_date'],validate='one_to_one')
    z[p.COLS]=z[p.COLS].astype('float32');pure=p.rank_prediction(model,z)
    z['accuracy_pure_score']=pure;z['accuracy_score']=(1-weight)*z.guarded_model_score+weight*pure
    z['accuracy_sector_rank']=z.accuracy_score.groupby(z.sector).rank(method='min',ascending=False)
    z=z.rename(columns={'evidence_confidence':'anchor_evidence_confidence'})
    z['rebuilt_input_confidence']=np.where(z.input_status.ne('USABLE_PROVIDER_BASIS'),z.input_status,np.where(z.observations.ge(252),'FULL_YEAR_OBSERVATIONS','SHORT_HISTORY'))
    z=z.sort_values(['sector','accuracy_sector_rank','isin'])
    assert len(z)==4436 and z['isin'].is_unique and np.isfinite(z.accuracy_score).all()
    assert z.loc[z.evidence_fraction.eq(0),'accuracy_pure_score'].eq(.5).all()
    z.to_csv(OUT/'current_all_stock_rankings.csv',index=False)
    # Validate the actual CSV and reloaded model, rather than only the in-memory fit.
    replay=pd.read_csv(OUT/'current_all_stock_rankings.csv');replay[p.COLS]=replay[p.COLS].astype('float32')
    np.testing.assert_allclose(p.rank_prediction(model,replay),replay.accuracy_pure_score,atol=1e-15,rtol=0)
    np.testing.assert_allclose((1-weight)*replay.guarded_model_score+weight*replay.accuracy_pure_score,replay.accuracy_score,atol=1e-15,rtol=0)
    rubric=pd.read_csv(p.OLD/'all_stock_evidence_review.csv.gz',usecols=['isin','judge_primary','judge_coverage','judge_flags'])
    review=z.merge(rubric,on='isin',how='left',validate='one_to_one');review.to_csv(OUT/'all_stock_evidence_review.csv.gz',index=False)
    review[review.accuracy_sector_rank.le(3)].to_csv(OUT/'current_sector_top3_review.csv',index=False)
    rows=[]
    for scope in ['common','expanded']:
        zz=review[review.sector_incumbent.notna()] if scope=='common' else review
        models=['accuracy_score','guarded_model_score','open_model_score']+(['sector_incumbent'] if scope=='common' else [])
        for sector,g in zz.groupby('sector'):
            g=g.dropna(subset=['judge_primary']+models).sort_values('isin')
            if sector=='Unclassified' or len(g)<5:continue
            for m in models:rows.append(dict(scope=scope,sector=sector,model=m,rubric=g.sort_values(m,ascending=False,kind='stable').head(3).judge_primary.mean()))
    r=pd.DataFrame(rows);r.to_csv(OUT/'rubric_sector_comparison.csv',index=False)
    r.groupby(['scope','model']).rubric.mean().reset_index().to_csv(OUT/'rubric_summary.csv',index=False)
    selected.update(current_rows=len(z),input_usable=int(z.evidence_fraction.gt(0).sum()),current_snapshot=p.ASOF,max_training_endpoint=training_endpoint,current_replay_tolerance=1e-15)
    (OUT/'selection.json').write_text(json.dumps(selected,indent=2))
    verification=dict(candidate=selected['model'],family=selected['family'],strict_gate=bool(selected['strict_gate']),current_stocks=len(z),input_usable_current=selected['input_usable'],current_input_status=z.input_status.value_counts().to_dict(),current_model_and_csv_replay=True,current_snapshot=p.ASOF,fresh_validation=False,production_replaced=False)
    paths=[OUT/'protocol.json',OUT/'selection.json',path,OUT/'current_all_stock_rankings.csv',OUT/'selected_historical_scores.csv.gz',OUT/'pair_accuracy_summary.csv']
    verification['sha256']={str(f.relative_to(p.ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in paths}
    (OUT/'verification.json').write_text(json.dumps(verification,indent=2))
    shutil.copyfile(SOURCES['rebuilt']/'test_results.json',OUT/'test_results.json')
    pairs=pd.read_csv(OUT/'pair_accuracy_summary.csv');means=pd.read_csv(OUT/'all_candidate_accuracy.csv')
    relevant=means[means.family.eq(selected['family'])&means.model.isin([selected['model'],'open_model','guarded_previous','sector_incumbent'])]
    lines=['# Full-coverage sector ranking accuracy — 10 October 2026','',f"Research accuracy leader: **{selected['model']}** ({selected['family']}). Selected by development-period whole-sector rank correlation across nine profiles, with equal sector/date weighting and both comparison scopes. The original multi-metric promotion gate is unchanged.",'',
      f"Scores cover **4,436 / 4,436 stocks**. Usable rebuilt price inputs cover **{selected['input_usable']} / 4,436** on the **3 October 2026 snapshot**. The remaining stocks have explicitly marked missing/unsafe inputs and a neutral new-model component; blended rankings can inherit older model evidence. A finite score is not complete data coverage.",'',
      '## Whole-sector ordering accuracy','',
      'Pair accuracy is the fraction of within-sector stock pairs correctly ordered by their later SIP XIRR, awarding half credit to ties. It is not the probability of a stock gaining. Common scope uses the production-scored cohort; expanded scope compares the full-coverage policies on identical outcome-covered peers. Sectors need at least five peers; unclassified stocks are excluded from historical metrics.','',
      '| Scope | Period | Model | Pair accuracy |','|---|---|---|---:|']
    for row in pairs.itertuples():lines.append(f'| {row.scope} | {row.period} | {row.model} | {row.pair_accuracy:.2%} |')
    lines+=['','## Rank correlation and Top-3 outcomes','',
      'These aggregate development/recent summaries average both scopes for full-coverage models; production has common scope only. Use the paired scope-specific files for direct comparisons. XIRR here is an equal-sector SIP diagnostic, not a realizable portfolio return.','',
      '| Period | Model | Rank IC | Top-3 XIRR (raw) | Drawdown |','|---|---|---:|---:|---:|']
    for row in relevant.itertuples():lines.append(f'| {row.period} | {row.model} | {row.rank_ic:.4f} | {row.xirr:.2%} | {row.drawdown:.2%} |')
    lines+=['','## Broad gate and interpretation','',f"This accuracy leader has **{selected['top3_regressing_cells']} / {selected['top3_cells']} Top-3 regressions**, and **{selected['regressing_cells']} / {selected['total_cells']} total regressions** against four references over profiles, scopes, periods, raw/capped returns and six metrics. Strict gate: **{selected['strict_gate']}**. Accuracy selection does not erase those tradeoffs.",'',
      'All historical dates have been exposed in earlier research; neither recent performance nor this development-selected result is a fresh holdout. Financial data adjustments remain partially unresolved and affected input/outcome windows are excluded. The company-evidence rubric is reused diagnostic evidence, not an independent oracle. Professor-formula comparisons are in the separate older-policy audit.',
      '', '## Research and reproducibility','',
      'The continuation evaluates 24 LightGBM blend configurations and eight CatBoost configurations from 48 annual fits. Features include closing-high persistence/recency, breakout strength, momentum, trend consistency, jump concentration, downside risk and sector-relative strength. Training outcomes must finish before each annual test fold.',
      '', '[ICML 2023 ranking research](https://proceedings.mlr.press/v202/lyzhin23a.html), [cross-sectional financial learning to rank](https://arxiv.org/abs/2012.07149), [LightGBM parameters](https://lightgbm.readthedocs.io/en/latest/Parameters.html), and [CatBoost ranking objectives](https://catboost.ai/docs/en/concepts/loss-functions-ranking?lang=en) motivated the tested objectives. They do not certify this market or dataset.',
      '', 'The saved model and exported CSV reproduce scores within 1e-15. Full rankings, input-confidence labels, all-stock company-evidence reviews, sector Top-3 reviews, per-profile accuracy, all 32 candidate summaries and artifact hashes are retained in `experiments/sector-accuracy-20261010/`. The live ranking model has not been switched.']
    (p.ROOT/'research/reports/sector_accuracy_20261010.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(selected,indent=2),flush=True)

if __name__=='__main__':run()
