"""Replay saved replacements and report comparison to retained champion."""
import json,hashlib
import numpy as np
import pandas as pd
from scipy.interpolate import RegularGridInterpolator
from sector_learned_blend_20261010 import p,BASE,OUT,ANCHOR,CONFIGS,load,infer_nnls
from sector_accuracy_20261010 import pair_accuracy

def run():
    names=[c['name'] for c in CONFIGS];chosen=json.loads((OUT/'selection.json').read_text());selected=chosen['model']
    x=load();scores=pd.concat([pd.read_csv(OUT/f'predictions_{y}.csv.gz') for y in range(2020,2026)],ignore_index=True)
    assert len(scores)==len(x)==797443 and not scores.duplicated(p.KEYS).any()
    merged=x.merge(scores[p.KEYS+names],on=p.KEYS,validate='one_to_one')
    current=pd.read_csv(OUT/'current_all_4436_rankings.csv')
    assert len(current)==4436 and current['isin'].is_unique and np.isfinite(current[names]).all().all()
    np.testing.assert_allclose(current[ANCHOR],.75*current.guarded_previous+.25*current.rank_xendcg_balanced,atol=1e-15,rtol=0)
    errors=[];grid=[];weights=[];direct_replays=[]
    for year in [2020,2021,2022,2023,2024,2025,'current']:
        z=current if year=='current' else merged[merged.decision_date.str.startswith(str(year))]
        for c in CONFIGS:
            name=c['name'];prefix=OUT/f'{name}_{year}'
            if year in [2020,2021]:pred=z[ANCHOR].to_numpy()
            elif c['kind']=='nnls':
                model=json.loads(prefix.with_suffix('.json').read_text());pred=infer_nnls(z,model)
                assert min(model['weights'])>=0 and abs(sum(model['weights'])-1)<1e-12
                weights.extend(dict(year=year,model=name,component=f,weight=w) for f,w in zip(model['features'],model['weights']))
            else:
                audit=json.loads((OUT/f'{name}_{year}_audit.json').read_text());grid.append(dict(model=name,year=year,mode=audit['mode'],rows=audit['rows'],**audit['grid_trials'][-1],seconds=audit['seconds']))
                assert audit['context_sha256']==hashlib.sha256((OUT/f'{name}_{year}_context.csv').read_bytes()).hexdigest()
                assert audit['inputs_sha256']==hashlib.sha256((OUT/f'{name}_{year}_inputs.csv').read_bytes()).hexdigest()
                if year=='current':
                    direct_receipt=json.loads((OUT/f'{name}_{year}_direct_replay.json').read_text())
                    with np.load(OUT/f'{name}_{year}_direct_replay.npz') as direct_file:
                        direct_error=float(np.max(np.abs(direct_file['predictions']-z[name].to_numpy())))
                        assert direct_error<1e-7
                        direct_replays.append(dict(model=name,rows=len(z),maximum_replay_error=direct_error))
                context=pd.read_csv(str(prefix)+'_context_identity.csv')
                cutoff=p.ASOF if year=='current' else f'{year}-01-01';assert context.endpoint.max()<cutoff
                with np.load(prefix.with_suffix('.npz')) as f:
                    if audit['mode']=='BILINEAR_GRID':
                        fn=RegularGridInterpolator((f['axis0'],f['axis1']),f['values'],bounds_error=True)
                        inputs=pd.read_csv(str(prefix)+'_inputs.csv').to_numpy()
                        np.testing.assert_allclose(inputs,z[['guarded_previous','rank_xendcg_balanced']],atol=1e-15,rtol=0)
                        inside=f['inside'];pred=f['predictions'].copy();pred[inside]=fn(inputs[inside])
                        e=np.abs(fn(f['probes'])-f['direct']);assert e.mean()<=.003 and e.max()<=.02
                    else:pred=f['predictions']
            error=float(np.max(np.abs(pred-z[name].to_numpy())))
            if c['kind']=='tabpfn' and year not in [2020,2021] and audit['mode']=='DIRECT_GRID_REJECTED':
                # Neural output is float32; pandas writes shortest round-trip decimal.
                # Require bit-exact reconstruction at source precision, not float64
                # identity to the decimal spelling of a binary float32 value.
                np.testing.assert_array_equal(pred.astype(np.float32),z[name].to_numpy(dtype=np.float32))
                assert error<6e-8
            else:assert error<1e-14,(year,name,error)
            errors.append(error)
            if year=='current':np.testing.assert_array_equal(z[name+'_sector_rank'],z[name].groupby(z.sector).rank(method='min',ascending=False))
    pd.DataFrame(grid).to_csv(OUT/'tabpfn_approximation_audit.csv',index=False)
    pd.DataFrame(weights).to_csv(OUT/'learned_weights.csv',index=False)
    a=pd.read_csv(OUT/'training_audit.csv');m=a.maximum_endpoint.notna();assert (a.loc[m,'maximum_endpoint']<a.loc[m,'cutoff']).all()
    for record in grid:a.loc[a.model.eq(record['model'])&a.year.astype(str).eq(str(record['year'])),'status']=record['mode']
    a.to_csv(OUT/'training_audit.csv',index=False)
    s=pd.read_csv(OUT/'summary.csv');old=pd.read_csv(BASE/'summary.csv')
    keys=['period','profile','top_n','scope','return_treatment']
    aa=s[s.model.eq(ANCHOR)].set_index(keys)[p.METRICS].sort_index();bb=old[old.model.eq('rank_xendcg_balanced_blend0.25')].set_index(keys)[p.METRICS].sort_index()
    pd.testing.assert_frame_equal(aa,bb,atol=1e-12,rtol=1e-12)
    # Explicit benchmark population audit: keys and stock counts, every query.
    for scope in ['common','expanded']:
        for bounded in [False,True]:
            q=pd.read_csv(OUT/f'queries_{scope}_{bounded}.csv.gz');ref=pd.read_csv(BASE/f'queries_{scope}_{bounded}_0.csv.gz')
            k=['period','date','profile','sector','top_n']
            aq=q[q.model.eq(ANCHOR)].set_index(k)['n'].sort_index();bq=ref[ref.model.eq('guarded_previous')].set_index(k)['n'].sort_index();pd.testing.assert_series_equal(aq,bq)
    # Active years separated from the two predeclared fallback years.
    active=[]
    for scope in ['common','expanded']:
        q=pd.read_csv(OUT/f'queries_{scope}_True.csv.gz');q=q[q.date.ge('2022-01-01')]
        v=q.groupby(['model','period','profile','top_n','sector'])[p.METRICS].mean().groupby(['model','period','profile','top_n']).mean().reset_index();v['scope']=scope;active.append(v)
    pd.concat(active).to_csv(OUT/'active_years_summary.csv',index=False)
    diagnostic=list(dict.fromkeys([ANCHOR,selected,'tabpfn_v2_context256','tabpfn_v2_context768']))
    rows=[]
    for scope in ['common','expanded']:
        z=merged[merged.sector_incumbent.notna()] if scope=='common' else merged
        z=z.dropna(subset=diagnostic+['future_xirr','future_drawdown','future_shortfall'])
        for (period,day,profile,sector),g in z.groupby(['period','decision_date','profile_name','sector']):
            if sector=='Unclassified' or len(g)<5:continue
            for name in diagnostic:rows.append(dict(scope=scope,period=period,day=day,profile=profile,sector=sector,model=name,pair_accuracy=pair_accuracy(g[name].to_numpy(),g.future_xirr.to_numpy())))
        print('PAIR AUDIT',scope,flush=True)
    q=pd.DataFrame(rows);q.to_csv(OUT/'pair_accuracy_queries.csv.gz',index=False)
    pair=q.groupby(['scope','period','profile','sector','model']).pair_accuracy.mean().groupby(['scope','period','profile','model']).mean().groupby(['scope','period','model']).mean().reset_index();pair.to_csv(OUT/'pair_accuracy_summary.csv',index=False)
    totals=s.groupby(['model','period','scope','return_treatment','top_n'])[p.METRICS].mean().reset_index();totals.to_csv(OUT/'aggregate_metrics.csv',index=False)
    curcols=['isin','ticker','company','sector','decision_date','input_status','rebuilt_input_confidence',ANCHOR,'rebuilt_sector_rank',selected,selected+'_sector_rank']
    current[curcols].sort_values(['sector',selected+'_sector_rank','isin']).to_csv(OUT/'selected_current_all_4436.csv',index=False)
    trials=pd.read_csv(OUT/'trials.csv');assert trials.comparisons.eq(1296).all()
    verdict={'current_rows':4436,'historical_rows':len(scores),'variants':6,'fitted_replacements':30,'anchor_fallback_years':[2020,2021],'usable_current_price_inputs':int(current.evidence_fraction.gt(0).sum()),'development_selected':selected,'strict_gate_passes':int(trials.strict_gate.sum()),'score_replay_max_error':max(errors),'training_cutoffs_verified':True,'same_benchmark_population_verified':True,'fresh_validation':False,'production_replaced':False,'retained_champion':'rank_xendcg_balanced_blend0.25' if not chosen['strict_gate'] else selected}
    verdict['current_neural_replays']=direct_replays
    verdict['tabpfn_fit_modes']=pd.DataFrame(grid)['mode'].value_counts().to_dict()
    verdict['sha256']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [OUT/'protocol.json',OUT/'trials.csv',OUT/'selected_current_all_4436.csv',OUT/'tabpfn-v2-regressor.ckpt']}
    (OUT/'verification.json').write_text(json.dumps(verdict,indent=2))
    lines=['# Learned replacements for the current champion — completed 11 October 2026','',
      'Six replacements were tested within the retained champion: four nonnegative learned blends and two pretrained TabPFN v2 outer-blend replacements. Existing price engineering, stock identity, action checks and base components remain. This is a component replacement experiment, not a claim that every hand-written line has been replaced.','',
      '## What was learned','',
      '- Outer NNLS replaces the 75/25 guarded/LightGBM blend. Nested NNLS also replaces the guarded layer’s 80/20 weights. Targets are return percentile or the existing balanced return/drawdown/shortfall target.',
      '- TabPFN uses the original v2 pretrained regressor checkpoint and two champion-component inputs. Context sizes 256/768 are sampled with equal query weighting. We adapt through in-context examples, without gradient fine tuning or finance-specific pretrained weights. One ensemble member is a CPU feasibility choice.',
      '- Annual fits use completed, out-of-time component predictions only. 2020–2021 use the unchanged champion because mature out-of-time meta-training labels do not exist. Active replacement years are 2022–2025. Current models use mature feedback before 3 October 2026.',
      '- TabPFN first attempts an audited bilinear grid approximation. Bounds and probe inputs use training-time information only. Fits failing the approximation check use direct neural inference for every test row. Five fits use the grid and five use direct inference, including both current 4,436-stock exports. Probe accuracy is not an exact guarantee for every interpolated row.','',
      '## Comparison with the current champion','',
      f'Development-selected replacement: `{selected}`. Selection uses development Top-3 regression counts, then all development counts. Recent results are not used for selection.',
      '', '| Replacement | Improved cells | Regressed cells | Total | Passes all cells? |','|---|---:|---:|---:|---|']
    for r in trials.itertuples():lines.append(f'| {r.model} | {r.improvements} | {r.regressions} | {r.comparisons} | {r.strict_gate} |')
    lines+=['','Each cell is a period/profile/scope/return-treatment/Top-N/metric combination. Six metrics cover XIRR, drawdown, achievement, shortfall, NDCG and rank correlation. These cell counts are not independent statistical tests.','',
      '### Recent 2024–2025 expanded-universe Top 3, capped returns','', '| Model | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |','|---|---:|---:|---:|---:|---:|---:|']
    tab=totals[totals.period.eq('recent')&totals.scope.eq('expanded')&totals.return_treatment.eq('capped')&totals.top_n.eq(3)]
    # Period labels are inherited from the frozen benchmark.
    if tab.empty:tab=totals[totals.period.ne('development')&totals.scope.eq('expanded')&totals.return_treatment.eq('capped')&totals.top_n.eq(3)]
    for r in tab.itertuples():lines.append(f'| {r.model} | {r.xirr:.2%} | {r.drawdown:.2%} | {r.achievement:.2%} | {r.shortfall:.4f} | {r.ndcg:.4f} | {r.rank_ic:.4f} |')
    lines+=['','### Whole-sector pair ordering','', '| Scope | Period | Model | Correct pair order, ties half credit |','|---|---|---|---:|']
    for r in pair.itertuples():lines.append(f'| {r.scope} | {r.period} | {r.model} | {r.pair_accuracy:.2%} |')
    lines+=['','Pair accuracy concerns later SIP XIRR ordering; it is not a probability of making money.','', '## Decision and verification','',
      f"Retained model: `{verdict['retained_champion']}`. {verdict['strict_gate_passes']} of six replacements satisfy every comparison against the champion. No live UI switch was made.",
      f"All six current variants score 4,436 unique stocks; {verdict['usable_current_price_inputs']} have usable rebuilt price inputs. Scoring coverage does not fill the remaining data gaps. All exports retain input-status flags.",
      f"Reconstructed learned linear scores and interpolated scores and checked saved direct predictions across all 797,443 historical rows and current exports; maximum score error {max(errors):.3g}. Both current TabPFN models were also independently refitted from their saved contexts and rerun directly for all 4,436 stocks. Historical direct predictions were not all independently rerun. Verified temporal cutoffs, current sector ranks, identical benchmark populations and unchanged champion metrics.",
      '', 'These dates and historical datasets have been researched repeatedly. This is not fresh holdout validation. Base components retain previously documented price/outcome limitations. The snapshot remains 3 October 2026. The new pretrained model cannot repair missing source data or make current ranking judgments objectively true.',
      '', '## Sources and reproducibility','',
      '[TabPFN Nature paper](https://www.nature.com/articles/s41586-024-08328-6), [official implementation and v2 licensing](https://github.com/PriorLabs/TabPFN), [Super Learner](https://biostats.bepress.com/ucbbiostat/paper222/), [scikit-learn nonnegative regression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LinearRegression.html). The temporal stacking here is inspired by Super Learner; its original theoretical guarantees are not asserted.',
      '', 'Local TabPFN package 2.2.1 uses v2 weights under the Prior Labs License (Apache 2.0 plus attribution). Local isolated dependencies avoid changing application libraries. Telemetry is disabled. The checkpoint hash, contexts, fitted weights, inference grids, cutoff audits and protocol are retained in the experiment directory.',
      '', 'Run `python research/runners/sector_learned_blend_20261010.py learn`, then `evaluate`, then `python research/runners/finish_sector_learned_blend_20261010.py`. Dependencies for the worker are isolated in `experiments/premodel_dependencies_20261010`.']
    report='\n'.join(lines)+'\n'
    report=report.replace('Historical direct predictions were not all independently rerun.','Historical direct predictions were not all independently rerun. Direct neural CSV scores reproduce bit-for-bit at their original float32 precision; the roughly 3e-8 float64 difference is decimal serialization, not a model discrepancy.')
    (p.ROOT/'research/reports/sector_learned_blend_20261010.md').write_text(report,encoding='utf-8')
    print(json.dumps(verdict,indent=2),flush=True);print(tab.to_string(index=False),flush=True)

if __name__=='__main__':run()
