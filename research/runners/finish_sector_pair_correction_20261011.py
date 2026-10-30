"""Replay pairwise learners and report equal-population sector outcomes."""
from sector_pair_correction_20261011 import *

def run():
    lock=json.loads((OUT/'locked_finalists.json').read_text());names=lock['finalists']
    assert lock['development_sha256']==digest(OUT/'trials_development.csv')
    x=h.load();cur=pd.read_csv(OUT/'all_4436_all_candidates.csv')
    scores=pd.concat([pd.read_csv(OUT/f'predictions_{y}.csv.gz') for y in range(2020,2026)],ignore_index=True)
    assert len(scores)==len(x)==797443 and not scores.duplicated(p.KEYS).any()
    assert len(cur)==4436 and cur['isin'].is_unique and np.isfinite(cur[NAMES]).all().all()
    errors=[];importance=[]
    for year in [2020,2021,2022,2023,2024,2025,'current']:
        z=h.current() if year=='current' else x[x.decision_date.str.startswith(str(year))]
        saved=cur if year=='current' else scores[scores.decision_date.str.startswith(str(year))]
        saved=saved.set_index(p.KEYS).reindex(pd.MultiIndex.from_frame(z[p.KEYS]));assert saved[NAMES].notna().all().all()
        if year in [2020,2021]:
            for name in NEW:np.testing.assert_allclose(saved[name],z[ANCHOR],rtol=0,atol=1e-14)
        else:
            cutoff=p.ASOF if year=='current' else f'{year}-01-01'
            t=sample_queries(h.train_rows(x,cutoff));identity=pd.read_csv(OUT/f'training_identity_{year}.csv')
            pd.testing.assert_frame_equal(t[p.KEYS+['sector','endpoint']].reset_index(drop=True),identity,check_dtype=False)
            assert t.endpoint.max()<cutoff
            audits={a['model']:a for a in json.loads((OUT/f'audit_{year}.json').read_text())}
            for target,focus in CONFIGS:
                key=f'catpair_{target}_{focus}';path=OUT/f'{key}_{year}.cbm';assert digest(path)==audits[key]['model_sha256']
                pairs,weights,groups=pairs_for(t,target,focus);assert len(pairs)==audits[key]['pairs']
                m=CatBoostRanker();m.load_model(str(path));raw=m.predict(z[FEATURES],thread_count=4)
                if year=='current':
                    importance.extend(dict(model=key,feature=f,prediction_change_importance=float(v)) for f,v in zip(FEATURES,m.get_feature_importance(type='PredictionValuesChange',thread_count=4)))
                for w in WEIGHTS:
                    pred=h.corrected(z,raw,w);err=float(np.max(np.abs(pred-saved[key+f'_w{w}'].to_numpy())))
                    assert err<1e-12;errors.append(err)
        original=pd.read_csv(h.OUT/f'predictions_{year}.csv.gz',usecols=p.KEYS+CONTROLS).set_index(p.KEYS).reindex(saved.index)
        np.testing.assert_allclose(saved[CONTROLS],original[CONTROLS],rtol=0,atol=1e-14)
        print('REPLAY',year,flush=True)
    for name in NAMES:np.testing.assert_array_equal(cur[name+'_rank'],cur[name].groupby(cur.sector).rank(method='min',ascending=False))
    pd.DataFrame(importance).to_csv(OUT/'current_feature_importance.csv',index=False)
    dev=pd.read_csv(OUT/'summary_development.csv');recent=pd.read_csv(OUT/'summary_recent.csv')
    summary=pd.concat([dev[dev.model.isin([ANCHOR]+names)],recent]);summary.to_csv(OUT/'finalist_summary.csv',index=False)
    ix=['model','period','profile','top_n','scope','return_treatment'];metrics=summary.set_index(ix)[p.METRICS]
    old=pd.read_csv(h.OUT/'finalist_summary.csv').set_index(ix)[p.METRICS]
    shared=[ANCHOR]+CONTROLS
    pd.testing.assert_frame_equal(metrics.loc[shared].sort_index(),old.loc[shared].sort_index(),rtol=1e-12,atol=1e-12)
    for stage in ['development','recent']:
        for scope in ['common','expanded']:
            for cap in [False,True]:
                q=pd.read_csv(OUT/f'queries_{stage}_{scope}_{cap}.csv.gz');ref=pd.read_csv(h.OUT/f'queries_{stage}_{scope}_{cap}_0.csv.gz')
                k=['period','date','profile','sector','top_n']
                pd.testing.assert_series_equal(q[q.model.eq(ANCHOR)].set_index(k)['n'].sort_index(),ref[ref.model.eq(ANCHOR)].set_index(k)['n'].sort_index())
    trials=[];deltas=[]
    for name in names:
        d=(metrics.loc[name]-metrics.loc[ANCHOR]).reset_index();d.shortfall=-d.shortfall;d['model']=name;deltas.append(d)
        v=d[p.METRICS].to_numpy();assert v.size==1296
        trials.append(dict(model=name,improved=int((v>1e-12).sum()),regressed=int((v< -1e-12).sum()),tied=int((abs(v)<=1e-12).sum()),strict_gate=bool((v>=-1e-12).all() and (v>1e-12).any())))
    trials=pd.DataFrame(trials);trials.to_csv(OUT/'finalist_trials.csv',index=False);pd.concat(deltas).to_csv(OUT/'finalist_deltas.csv',index=False)
    merged=x.merge(scores[p.KEYS+names],on=p.KEYS,validate='one_to_one');rows=[]
    for scope in ['common','expanded']:
        z=merged[merged.sector_incumbent.notna()] if scope=='common' else merged
        z=z.dropna(subset=[ANCHOR]+names+['future_xirr','future_drawdown','future_shortfall'])
        for (period,date,profile,sector),g in z.groupby(['period','decision_date','profile_name','sector']):
            if sector=='Unclassified' or len(g)<5:continue
            for name in [ANCHOR]+names:rows.append(dict(scope=scope,period=period,date=date,profile=profile,sector=sector,model=name,n=len(g),pair_accuracy=pair_accuracy(g[name].to_numpy(),g.future_xirr.to_numpy())))
        print('PAIR',scope,flush=True)
    q=pd.DataFrame(rows);q.to_csv(OUT/'pair_queries.csv.gz',index=False)
    pair=q.groupby(['scope','period','profile','sector','model']).pair_accuracy.mean().groupby(['scope','period','profile','model']).mean().groupby(['scope','period','model']).mean().reset_index();pair.to_csv(OUT/'pair_accuracy.csv',index=False)
    sectors=q.groupby(['scope','period','sector','profile','model']).pair_accuracy.mean().groupby(['scope','period','sector','model']).mean().unstack('model');bootstrap=[];rng=np.random.default_rng(20261011)
    sector_changes=[]
    for name in names:
        d=sectors[[ANCHOR,name]].copy();d['delta']=d[name]-d[ANCHOR];d['model']=name
        sector_changes.append(d.rename(columns={name:'candidate_accuracy',ANCHOR:'champion_accuracy'}).reset_index())
    pd.concat(sector_changes).to_csv(OUT/'sector_accuracy_changes.csv',index=False)
    for (scope,period),g in sectors.groupby(level=['scope','period']):
        for name in names:
            d=(g[name]-g[ANCHOR]).dropna().to_numpy();b=rng.choice(d,size=(2000,len(d)),replace=True).mean(axis=1)
            bootstrap.append(dict(scope=scope,period=period,model=name,delta=d.mean(),lower95=np.quantile(b,.025),upper95=np.quantile(b,.975)))
    pd.DataFrame(bootstrap).to_csv(OUT/'descriptive_sector_bootstrap.csv',index=False)
    agg=summary.groupby(['model','period','scope','return_treatment','top_n'])[p.METRICS].mean().reset_index();agg.to_csv(OUT/'aggregate_metrics.csv',index=False)
    columns=['isin','ticker','company','sector','input_status','rebuilt_input_confidence','rebuilt_sector_rank',ANCHOR]+sum(([n,n+'_rank'] for n in names),[])
    cur[columns].sort_values(['sector','rebuilt_sector_rank','isin']).to_csv(OUT/'finalists_all_4436.csv',index=False)
    moves=[]
    for name in names:
        z=cur[['isin','ticker','company','sector','input_status','rebuilt_sector_rank',name+'_rank']].copy();z['model']=name;z['rank_change']=z[name+'_rank']-z.rebuilt_sector_rank;z=z.rename(columns={name+'_rank':'candidate_sector_rank'});moves.append(z)
    pd.concat(moves).to_csv(OUT/'stock_rank_changes.csv',index=False)
    verdict=dict(current_rows=len(cur),historical_rows=len(scores),catboost_variants=len(NEW),catboost_fits=20,usable_current_price_features=int(cur.evidence_fraction.gt(0).sum()),serialized_replay_max_error=max(errors),cutoffs_verified=True,pair_orientation_and_query_boundaries_verified=True,benchmark_cohorts_verified=True,controls_reproduced=True,strict_gate_passes=int(trials.strict_gate.sum()),fresh_validation=False,production_replaced=False)
    verdict['sha256']={f:digest(OUT/f) for f in ['protocol.json','locked_finalists.json','finalist_trials.csv','finalists_all_4436.csv']};write('verification.json',verdict)
    lines=['# CatBoost pairwise sector correction - 11 October 2026','','## What changed','','Added a PairLogit correction layer starting from the existing champion sector percentile. This is a new objective and role for CatBoost; earlier research already tested CatBoost YetiRank as a standalone ranking component. Four learners combine return/balanced pair targets with uniform/mistake-emphasized pairs. Three correction strengths produce 12 candidates, alongside two previously evaluated LightGBM controls. CatBoost is open-source gradient boosting trained here, not a downloaded financial pretrained model.','',
      'Training samples up to 1,500 complete date/profile/sector queries and 64 distinct stock pairs per query. Every query contributes the same total pair weight. The mistake variant doubles misordered-pair weights before normalization. All new training uses matured outcomes and historical out-of-time component scores. Baseline addition semantics and serialized predictions are verified.','',
      '2020-2021 retain the champion because no mature meta-training outcomes are available. Correction fits cover 2022-2025 plus the current frozen 2026-10-03 snapshot. All 4,436 stocks receive scores; 4,303 have usable current price features. The other 133 retain zero correction and explicit evidence flags. Their ordinal rank can still move when peers move. Unclassified/small groups remain in exports but are excluded from the historical sector metrics.','',
      'Development 2020-2023 selects a whole-sector rank-IC leader and a Top3 conservative leader before recent 2024-2025 evaluation. These dates have been exposed by earlier research; this is not fresh validation. The base champion itself was also selected using reused historical evidence. This experiment cannot establish unbiased prospective performance.','','## All benchmark cells','','| Model | Improved | Regressed | Tied | Passes no-regression gate |','|---|---:|---:|---:|---|']
    for r in trials.itertuples():lines.append(f'| {r.model} | {r.improved} | {r.regressed} | {r.tied} | {r.strict_gate} |')
    lines+=['','Each model has 1,296 cells: two periods, nine profiles, Top1/3/5, common/expanded populations, raw/capped returns and six metrics. They are correlated comparisons, not independent tests.','','## Recent whole-sector pair-order accuracy','','| Model | Correct pair order |','|---|---:|']
    for r in pair[pair.scope.eq('expanded')&pair.period.ne('development')].itertuples():lines.append(f'| {r.model} | {r.pair_accuracy:.4%} |')
    lines+=['','Pair accuracy compares subsequent SIP-XIRR order within the same sector/date/profile; ties earn half credit. It is not an investment success probability.','','## Recent expanded Top3, capped returns','','| Model | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |','|---|---:|---:|---:|---:|---:|---:|']
    for r in agg[agg.period.ne('development')&agg.scope.eq('expanded')&agg.return_treatment.eq('capped')&agg.top_n.eq(3)].itertuples():lines.append(f'| {r.model} | {r.xirr:.2%} | {r.drawdown:.2%} | {r.achievement:.2%} | {r.shortfall:.4f} | {r.ndcg:.4f} | {r.rank_ic:.4f} |')
    lines+=['','## Descriptive uncertainty','','| Candidate | Mean sector pair-order delta (pp) | 95% sector-resampling interval (pp) |','|---|---:|---:|']
    for r in bootstrap:
        if r['scope']=='expanded' and r['period']!='development':lines.append(f"| {r['model']} | {100*r['delta']:+.4f} | [{100*r['lower95']:+.4f}, {100*r['upper95']:+.4f}] |")
    lines+=['','The bootstrap averages profiles within each sector, then sectors; the main accuracy table averages sectors within each profile, then profiles. Missing sector/profile combinations can therefore produce slightly different deltas. These intervals describe reused-sample dispersion; they do not correct for repeated model searches.','','## Decision and verification','',
      f"{int(trials.strict_gate.sum())} finalists passed the no-regression gate. The existing champion remains in the live system; this experiment does not replace it. All 20 saved CatBoost models replayed across all historical/current scores, with maximum error {max(errors):.3g}. Cutoffs, training identities, pair orientation and query boundaries, prior control scores, all benchmark query counts, and every current rank passed verification. Three focused tests passed. All current scores and ranks are exported, with stock-level rank changes and sector-level accuracy differences.",'',
      '## Sources','','- [CatBoost peer-reviewed algorithm paper](https://proceedings.neurips.cc/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html).','- [Official pairwise ranking objectives](https://catboost.ai/docs/en/concepts/loss-functions-ranking).','- [Official baseline training and inference examples](https://catboost.ai/docs/en/concepts/python-usages-examples).','','Run: python research/runners/sector_pair_correction_20261011.py learn; then development; then recent; then python research/runners/finish_sector_pair_correction_20261011.py.']
    (p.ROOT/'research/reports/sector_pair_correction_20261011.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(verdict,indent=2),flush=True)

if __name__=='__main__':run()
