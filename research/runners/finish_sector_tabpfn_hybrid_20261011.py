"""Audit hybrid students, matched controls, temporal sources and full-sector accuracy."""
import json,hashlib
import numpy as np
import pandas as pd
import lightgbm as lgb
from sector_tabpfn_hybrid_20261011 import p,OUT,FEATURES,CONFIGS,WEIGHTS,NAMES,TEACHERS,ANCHOR,load,current,train_rows,corrected,write
from sector_accuracy_20261010 import pair_accuracy

def run():
    locked=json.loads((OUT/'locked_finalists.json').read_text());names=locked['finalists']
    assert locked['development_trials_sha256']==hashlib.sha256((OUT/'trials_development.csv').read_bytes()).hexdigest()
    x=load();errors=[];teacher_audit=[];context_rows=0;importance=[]
    checkpoint_hash=hashlib.sha256((p.ROOT/'experiments/sector-learned-blend-20261010/tabpfn-v2-regressor.ckpt').read_bytes()).hexdigest()
    scores=pd.concat([pd.read_csv(OUT/f'predictions_{y}.csv.gz') for y in range(2020,2026)],ignore_index=True)
    assert len(scores)==len(x)==797443 and not scores.duplicated(p.KEYS).any()
    cur=pd.read_csv(OUT/'all_4436_all_candidates.csv');assert len(cur)==4436 and cur['isin'].is_unique
    assert np.isfinite(cur[NAMES]).all().all()
    for year in [2020,2021,2022,2023,2024,2025,'current']:
        z=current() if year=='current' else x[x.decision_date.str.startswith(str(year))]
        saved=(cur if year=='current' else scores[scores.decision_date.str.startswith(str(year))]).set_index(p.KEYS)
        source=z.set_index(p.KEYS);saved=saved.reindex(source.index);assert saved[NAMES].notna().all().all()
        if year in [2020,2021]:
            for name in NAMES:np.testing.assert_allclose(saved[name],source[ANCHOR],rtol=0,atol=1e-14)
            continue
        cutoff=p.ASOF if year=='current' else f'{year}-01-01';t=train_rows(x,cutoff).set_index(p.KEYS)
        pool=pd.read_csv(OUT/f'pool_identity_{year}.csv').set_index(p.KEYS);assert pool.index.is_unique and pool.endpoint.max()<cutoff
        pool_source=t.loc[pool.index]
        for teacher in TEACHERS:
            prefix=OUT/f'{teacher}_{year}';identity=pd.read_csv(str(prefix)+'_identity.csv').set_index(p.KEYS)
            assert identity.index.is_unique and identity.endpoint.max()<cutoff and len(identity.index.intersection(pool.index))==0
            context=pd.read_csv(str(prefix)+'_context.csv');inputs=pd.read_csv(str(prefix)+'_inputs.csv')
            np.testing.assert_allclose(inputs.to_numpy(),pool_source[FEATURES].to_numpy(),equal_nan=True,rtol=1e-6,atol=1e-7)
            truth=t.loc[identity.index];np.testing.assert_allclose(context[FEATURES],truth[FEATURES],equal_nan=True,rtol=1e-6,atol=1e-7)
            label=teacher.split('_')[0]+('_target' if teacher.endswith('absolute') else '_residual')
            np.testing.assert_allclose(context.teacher_target,truth[label],rtol=0,atol=1e-14)
            receipt=json.loads((OUT/f'{teacher}_{year}_audit.json').read_text())
            assert receipt['checkpoint_sha256']==checkpoint_hash
            for kind in ['inputs','context']:assert receipt[kind+'_sha256']==hashlib.sha256((OUT/f'{teacher}_{year}_{kind}.csv').read_bytes()).hexdigest()
            assert receipt['replay_256_max_error']<=1e-7 and receipt['rows']==len(pool)
            with np.load(prefix.with_suffix('.npz')) as f:assert len(f['predictions'])==len(pool) and np.isfinite(f['predictions']).all()
            context_rows+=len(context);teacher_audit.append(dict(year=year,teacher=teacher,**receipt))
        for c in CONFIGS:
            m=lgb.Booster(model_file=str(OUT/f'{c["name"]}_{year}.txt'));raw=m.predict(z[FEATURES],num_threads=3)
            if year=='current':
                gains=m.feature_importance(importance_type='gain');total=max(float(gains.sum()),1e-30)
                importance.extend(dict(model=c['name'],feature=f,gain=float(v),gain_fraction=float(v/total)) for f,v in zip(FEATURES,gains))
            for w in WEIGHTS:
                name=c['name']+f'_w{w}';pred=corrected(z,raw,w)
                error=float(np.max(np.abs(pred-saved[name].to_numpy())));assert error<=1e-12,(year,name,error);errors.append(error)
                if year=='current':np.testing.assert_array_equal(saved[name+'_rank'],saved[name].groupby(saved.sector).rank(method='min',ascending=False))
        print('REPLAY VERIFIED',year,flush=True)
    training=pd.read_csv(OUT/'training_audit.csv');valid=training.maximum_endpoint.notna();assert (training.loc[valid,'maximum_endpoint']<training.loc[valid,'cutoff']).all()
    pd.DataFrame(teacher_audit).to_json(OUT/'teacher_receipts.json',orient='records',indent=2)
    pd.DataFrame(importance).to_csv(OUT/'current_feature_importance.csv',index=False)
    dev=pd.read_csv(OUT/'summary_development.csv');recent=pd.read_csv(OUT/'summary_recent.csv');summary=pd.concat([dev[dev.model.isin([ANCHOR]+names)],recent])
    summary.to_csv(OUT/'finalist_summary.csv',index=False)
    keys=['model','period','profile','top_n','scope','return_treatment'];old=pd.read_csv(p.ROOT/'experiments/sector-learned-blend-20261010/summary.csv')
    aa=summary[summary.model.eq(ANCHOR)].set_index(keys)[p.METRICS].sort_index();bb=old[old.model.eq(ANCHOR)].set_index(keys)[p.METRICS].sort_index();pd.testing.assert_frame_equal(aa,bb,atol=1e-12,rtol=1e-12)
    # Audit stock counts for every query, not just the aggregate reference result.
    active=[]
    for stage in ['development','recent']:
        for scope in ['common','expanded']:
            for cap in [False,True]:
                paths=sorted(OUT.glob(f'queries_{stage}_{scope}_{cap}_*.csv.gz'))
                ref=pd.read_csv(p.ROOT/f'experiments/sector-learned-blend-20261010/queries_{scope}_{cap}.csv.gz')
                ref=ref[ref.model.eq(ANCHOR)&(ref.period.eq('development') if stage=='development' else ref.period.ne('development'))]
                k=['period','date','profile','sector','top_n']
                for path in paths:
                    q=pd.read_csv(path);base=q[q.model.eq(ANCHOR)]
                    pd.testing.assert_series_equal(base.set_index(k)['n'].sort_index(),ref.set_index(k)['n'].sort_index())
                    if cap:
                        active.append(q[q.model.isin([ANCHOR]+names)&q.date.ge('2022-01-01')].assign(scope=scope))
    active=pd.concat(active).drop_duplicates(['period','date','profile','sector','top_n','model','scope'])
    active.groupby(['model','period','profile','top_n','sector','scope'])[p.METRICS].mean().groupby(['model','period','profile','top_n','scope']).mean().reset_index().to_csv(OUT/'active_years_summary.csv',index=False)
    ix=summary.set_index(keys)[p.METRICS];trials=[];ds=[]
    for name in names:
        d=(ix.loc[name]-ix.loc[ANCHOR]).reset_index();d.shortfall=-d.shortfall;d['model']=name;ds.append(d);v=d[p.METRICS].to_numpy()
        assert v.size==1296
        trials.append(dict(model=name,improvements=int((v>1e-12).sum()),regressions=int((v< -1e-12).sum()),comparisons=v.size,strict_gate=bool((v>=-1e-12).all() and (v>1e-12).any())))
    trials=pd.DataFrame(trials);trials.to_csv(OUT/'finalist_trials.csv',index=False);pd.concat(ds).to_csv(OUT/'finalist_deltas.csv',index=False)
    merged=x.merge(scores[p.KEYS+names],on=p.KEYS,validate='one_to_one');rows=[]
    for scope in ['common','expanded']:
        z=merged[merged.sector_incumbent.notna()] if scope=='common' else merged
        z=z.dropna(subset=[ANCHOR]+names+['future_xirr','future_drawdown','future_shortfall'])
        for (period,day,profile,sector),g in z.groupby(['period','decision_date','profile_name','sector']):
            if sector=='Unclassified' or len(g)<5:continue
            for name in [ANCHOR]+names:rows.append(dict(scope=scope,period=period,day=day,profile=profile,sector=sector,model=name,pair_accuracy=pair_accuracy(g[name].to_numpy(),g.future_xirr.to_numpy())))
        print('PAIR VERIFIED',scope,flush=True)
    q=pd.DataFrame(rows);q.to_csv(OUT/'pair_queries.csv.gz',index=False)
    pair=q.groupby(['scope','period','profile','sector','model']).pair_accuracy.mean().groupby(['scope','period','profile','model']).mean().groupby(['scope','period','model']).mean().reset_index();pair.to_csv(OUT/'pair_accuracy.csv',index=False)
    # Descriptive paired sector dispersion; preserves all dates/profiles per sector.
    sectors=q.groupby(['scope','period','sector','profile','model']).pair_accuracy.mean().groupby(['scope','period','sector','model']).mean().unstack('model');bootstrap=[];rng=np.random.default_rng(20261011)
    for (scope,period),g in sectors.groupby(level=['scope','period']):
        for name in names:
            d=(g[name]-g[ANCHOR]).dropna().to_numpy();b=rng.choice(d,size=(2000,len(d)),replace=True).mean(axis=1)
            bootstrap.append(dict(scope=scope,period=period,model=name,delta=d.mean(),lower95=np.quantile(b,.025),upper95=np.quantile(b,.975),sectors=len(d)))
    pd.DataFrame(bootstrap).to_csv(OUT/'descriptive_sector_bootstrap.csv',index=False)
    totals=summary.groupby(['model','period','scope','return_treatment','top_n'])[p.METRICS].mean().reset_index();totals.to_csv(OUT/'aggregate_metrics.csv',index=False)
    contribution=[]
    for hybrid,control in locked['matched_teacher_controls'].items():
        d=(ix.loc[hybrid]-ix.loc[control]).reset_index();d.shortfall=-d.shortfall;d['hybrid']=hybrid;d['matched_control']=control;contribution.append(d)
    pd.concat(contribution).to_csv(OUT/'teacher_contribution_deltas.csv',index=False)
    cols=['isin','ticker','company','decision_date','sector','input_status','rebuilt_input_confidence',ANCHOR,'rebuilt_sector_rank']+sum(([n,n+'_rank'] for n in names),[])
    cur[cols].sort_values(['sector','rebuilt_sector_rank','isin']).to_csv(OUT/'finalists_all_4436.csv',index=False)
    selected=names[0];passed=bool(trials.set_index('model').loc[selected,'strict_gate'])
    verdict={'variants_development':len(NAMES),'finalists_recent':len(names),'accuracy_leaders':locked['accuracy_leaders'],'teacher_fits':len(teacher_audit),'student_control_fits':len(CONFIGS)*5,'historical_rows':len(scores),'current_rows':len(cur),'usable_current_price_inputs':int(cur.evidence_fraction.gt(0).sum()),'selected_hybrid':selected,'strict_gate_passes':int(trials.strict_gate.sum()),'retained_champion':selected if passed else 'rank_xendcg_balanced_blend0.25','max_student_replay_error':max(errors),'teacher_context_rows_audited':context_rows,'teacher_context_pool_disjoint':True,'teacher_input_label_sources_verified':True,'training_cutoffs_verified':True,'benchmark_populations_verified':True,'fresh_validation':False,'production_replaced':False}
    verdict['sha256']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [OUT/'protocol.json',OUT/'locked_finalists.json',OUT/'finalist_trials.csv',OUT/'finalists_all_4436.csv']};write('verification.json',verdict)
    lines=['# TabPFN + LightGBM sector-ranking research — 11 October 2026','', 'Built with PriorLabs-TabPFN. Internal research experiment; weights license is retained alongside the artifacts.','',
     'This round expands the original two-score TabPFN experiment to 18 price/profile/component inputs and two-member TabPFN ensembles. TabPFN predicts historical outcomes or residual errors; LightGBM students learn mixtures of these soft predictions and observed outcomes. There is no gradient fine tuning of the TabPFN checkpoint.','',
     '## Design','',
     '- 60 predeclared candidates: 36 TabPFN/LightGBM hybrids and 24 matched pool/full-data LightGBM controls. Two student depths, three correction strengths and two soft-label proportions are tested. All teacher models use local v2 pretrained weights.',
     '- Each teacher uses 768 mature historical context rows. Teachers directly score a disjoint 4,096-row past-data pool; no approximation grid is used. LightGBM students then score the entire historical and current universe. Student rankings are their own models, not a claim of exact TabPFN equivalence.',
     '- Outcome targets remain within-sector return percentile or the existing balanced return/downside/shortfall percentile target. Residual correction starts from the champion sector percentile. No usable feature evidence means zero correction.',
     '- Meta-training uses completed out-of-time component predictions. 2020–2021 retain the champion; actual replacement fits cover 2022–2025 and the current snapshot. Development selects three finalists based on regression counts, plus the highest whole-sector rank-IC hybrid and control and exact target/depth/correction-weight pool controls for the selected hybrids (deduplicated). The accuracy-leader/matched-control amendment was recorded before any development metrics were calculated. All finalists are locked before later-period metrics are calculated. Earlier research has already exposed these historical dates.',
     '', '## Selected finalists','', '| Model | Improved cells | Regressed cells | Total | No-regression gate |','|---|---:|---:|---:|---|']
    for r in trials.itertuples():lines.append(f'| {r.model} | {r.improvements} | {r.regressions} | {r.comparisons} | {r.strict_gate} |')
    lines+=['','Cells span two periods, nine profiles, common/expanded universes, raw/capped returns, Top1/3/5 and six metrics. Counts are not independent statistical tests.','', '## Recent expanded-universe accuracy','', '| Model | Correct stock-pair order |','|---|---:|']
    for r in pair[pair.scope.eq('expanded')&pair.period.ne('development')].itertuples():lines.append(f'| {r.model} | {r.pair_accuracy:.2%} |')
    lines+=['','Pair accuracy is later SIP-XIRR ordering, with ties given half credit; not a probability of investment gains.','', '## Recent expanded Top 3, capped XIRR','', '| Model | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |','|---|---:|---:|---:|---:|---:|---:|']
    table=totals[totals.period.ne('development')&totals.scope.eq('expanded')&totals.return_treatment.eq('capped')&totals.top_n.eq(3)]
    for r in table.itertuples():lines.append(f'| {r.model} | {r.xirr:.2%} | {r.drawdown:.2%} | {r.achievement:.2%} | {r.shortfall:.4f} | {r.ndcg:.4f} | {r.rank_ic:.4f} |')
    lines+=['','## Does the teacher help its matched control?','', '| Hybrid | Matched control | Improved cells | Regressed cells |','|---|---|---:|---:|']
    for d in contribution:
        v=d[p.METRICS].to_numpy()
        lines.append(f"| {d.hybrid.iloc[0]} | {d.matched_control.iloc[0]} | {int((v>1e-12).sum())} | {int((v< -1e-12).sum())} |")
    lines+=['','These comparisons use the same teaching pool, student depth, hard-label target and correction strength. The only target difference is the TabPFN soft-label signal. Performance gains are specific to these tested variants; this does not establish a general advantage for or against TabPFN.',
      '', '## Size and uncertainty of the accuracy gains','', '| Accuracy leader | Recent expanded pair-order delta | Descriptive sector-resampling 95% interval |','|---|---:|---:|']
    for row in bootstrap:
        if row['model'] in locked['accuracy_leaders'] and row['scope']=='expanded' and row['period']!='development':
            lines.append(f"| {row['model']} | {row['delta']*100:+.4f} percentage points | [{row['lower95']*100:+.4f}, {row['upper95']*100:+.4f}] |")
    lines+=['','The resampling statistic equally weights sectors after averaging available profiles and dates. It can differ slightly from the headline statistic, which averages sectors within each profile first. An interval spanning zero does not establish a clear accuracy gain. Neither calculation corrects for repeated research on these dates.']
    lines+=['', '## Decision and audit','',f"Retained model: `{verdict['retained_champion']}`. All 60 variants have finite scores for 4,436 stocks; only 4,303 have usable rebuilt price evidence. The snapshot is still 3 October 2026. The live UI was not changed.",
     f"Verified all {verdict['student_control_fits']} saved student/control fits by replaying complete historical/current inputs (maximum error {max(errors):.3g}). All 15 teacher contexts, labels and disjoint teaching pools were checked against their source rows and strict outcome cutoffs. Each teacher repeated its first 256 direct predictions; full neural teacher pools were not all independently refitted.",
     'Matched cohort stock counts and champion benchmark metrics reproduce the preceding evaluation. Active-year results, sector bootstrap dispersion, all development candidates and every current stock rank are exported separately. The bootstrap is descriptive on reused data; it is not fresh validation.',
     'The saved missing-data, corporate-action and historical outcome limitations remain. A pretrained model does not repair incomplete evidence, guarantee future performance, or establish an objectively correct ranking.',
     '', '## Research foundations','',
     '[TabPFN, Nature 2025](https://www.nature.com/articles/s41586-024-08328-6), [official TabPFN implementation](https://github.com/PriorLabs/TabPFN), [knowledge distillation](https://arxiv.org/abs/1503.02531), [LightGBM](https://lightgbm.readthedocs.io/en/latest/Parameters.html). The teacher/student residual combination is a project-specific adaptation, not a published finance strategy or the proprietary Prior Labs distillation engine.',
     '', 'Run `sector_tabpfn_hybrid_20261011.py` with steps `protocol`, `learn`, `development`, `recent`, then `finish_sector_tabpfn_hybrid_20261011.py`. All scripts are in `research/runners`; checkpoint and isolated dependency versions are inherited from the completed 10 October experiment.']
    (p.ROOT/'research/reports/sector_tabpfn_hybrid_20261011.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(verdict,indent=2),flush=True);print(table.to_string(index=False),flush=True)

if __name__=='__main__':run()
