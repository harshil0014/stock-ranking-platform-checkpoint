"""Full replay, stock evidence, sector robustness and research ledger."""
import sector_specialist_combinations_20261011 as c
from sector_accuracy_20261010 import pair_accuracy
import json,pickle,hashlib,gc
import numpy as np
import pandas as pd
from scipy.stats import rankdata
s=c.s;p=s.p;OUT=s.OUT;h=s.h;ANCHOR=h.ANCHOR

def paired_rank_stability(previous,current):
    """Vectorized Spearman/Top3 with the reference's shared-row tie order."""
    a=np.asarray(previous,dtype=float);b=np.asarray(current,dtype=float)
    assert a.shape==b.shape and a.ndim==2 and len(a)>=3
    assert np.isfinite(a).all() and np.isfinite(b).all()
    ar=rankdata(a,axis=0);br=rankdata(b,axis=0)
    ar-=ar.mean(axis=0);br-=br.mean(axis=0)
    denom=np.sqrt((ar*ar).sum(axis=0)*(br*br).sum(axis=0))
    corr=np.divide((ar*br).sum(axis=0),denom,out=np.full(a.shape[1],np.nan),where=denom>0)
    topa=np.argsort(-a,axis=0,kind='stable')[:3]
    topb=np.argsort(-b,axis=0,kind='stable')[:3]
    retained=np.array([len(set(topa[:,j])&set(topb[:,j]))/3 for j in range(a.shape[1])])
    return retained,corr

def replay():
    panel=s.panel();errors=[];audits=[]
    for year in c.YEARS:
        cutoff=p.ASOF if year=='current' else f'{year}-01-01'
        t=s.training(panel,cutoff);z=h.current() if year=='current' else panel[panel.decision_date.str.startswith(str(year))]
        path=OUT/f'training_identity_{year}.csv.gz';saved=pd.read_csv(path)
        pd.testing.assert_frame_equal(saved,t[p.KEYS+['endpoint','sector']],check_dtype=False)
        for family in s.FAMILIES:
            info=json.loads((OUT/f'audit_{family}_{year}.json').read_text());cols=s.FEATURES[family]
            assert info['training_identity_sha256']==s.digest(path) and info['maximum_endpoint']<info['cutoff']
            ext='pt' if family.startswith('tabm') else 'pkl';modelpath=OUT/f'{family}_{year}.{ext}'
            assert info['model_sha256']==s.digest(modelpath)
            output=OUT/f'raw_{family}_{year}.csv.gz';assert info['prediction_sha256']==s.digest(output)
            raw=pd.read_csv(output);pd.testing.assert_frame_equal(raw[p.KEYS],z[p.KEYS].reset_index(drop=True),check_dtype=False)
            if family.startswith('tabm'):
                s.torch.set_num_threads(4);m=s.torch_model(len(cols),family=='tabm_embedded');m.load_state_dict(s.torch.load(modelpath,weights_only=True))
                with (OUT/f'{family}_{year}_prep.pkl').open('rb') as f:prep=pickle.load(f)
                pred=s.neural_predict(m,prep,z[cols]);tol=1e-6
            else:
                with modelpath.open('rb') as f:m=pickle.load(f)
                pred=np.column_stack([a.predict(z[cols]) for a in m]) if family.startswith('ebm') else m.predict(z[cols]);tol=1e-12
            saved_values=raw[s.TARGETS].to_numpy()
            decimal_error=float(np.max(np.abs(pred-saved_values)))
            # float32 to_csv writes shortest native-precision decimals. Parsing
            # those as float64 introduces differences unrelated to model replay.
            native_saved=saved_values.astype(pred.dtype)
            error=float(np.max(np.abs(pred-native_saved)))
            if family=='ridge' and pred.dtype==np.float32:
                np.testing.assert_array_equal(pred,native_saved)
            assert error<=tol,(year,family,error)
            errors.append(error);audits.append(dict(year=year,family=family,rows=len(z),maximum_error=error,decimal_parse_error=decimal_error,prediction_dtype=str(pred.dtype),tolerance=tol,cutoff_verified=True,identity_verified=True))
            print('REPLAY',year,family,error,flush=True)
        gc.collect()
    pd.DataFrame(audits).to_csv(OUT/'serialized_replay.csv',index=False)
    s.write('replay_verification.json',dict(fits=len(audits),max_error=max(errors),source_identities_verified=True,cutoffs_verified=True))

def ledger():
    rows=[]
    for folder in sorted((p.ROOT/'experiments').iterdir()):
        if not folder.is_dir() or not (folder.name.startswith('sector-') or folder.name.startswith('full-coverage-')):continue
        for name in ['trials.csv','pair_trials.csv','trials_development.csv','trials_recent.csv','finalist_trials.csv']:
            path=folder/name
            if not path.exists():continue
            df=pd.read_csv(path);sha=s.digest(path)
            for record in df.to_dict('records'):
                rows.append(dict(experiment=folder.name,source=name,source_sha256=sha,scope='Source-specific; comparison cells/cohorts differ',**record))
    pd.DataFrame(rows).to_csv(OUT/'research_experiment_ledger.csv',index=False)

def evaluate():
    lock=json.loads((OUT/'locked_finalists.json').read_text());names=lock['finalists']
    assert lock['development_sha256']==s.digest(OUT/'trials_development.csv')
    # Preserve last-bit differences: default CSV parsing can collapse near-ties
    # and make exact stored rank verification disagree with the written scores.
    cur=pd.read_csv(OUT/'all_4436_all_candidates.csv',float_precision='round_trip');assert len(cur)==4436 and cur['isin'].is_unique
    assert np.isfinite(cur[c.NAMES]).all().all()
    for n in c.NAMES:np.testing.assert_array_equal(cur[n+'_rank'],cur[n].groupby(cur.sector).rank(method='min',ascending=False))
    dev=pd.read_csv(OUT/'summary_development.csv');recent=pd.read_csv(OUT/'summary_recent.csv')
    summary=pd.concat([dev[dev.model.isin([ANCHOR]+names)],recent]);summary.to_csv(OUT/'finalist_summary.csv',index=False)
    ix=['model','period','profile','top_n','scope','return_treatment'];metrics=summary.set_index(ix)[p.METRICS]
    prior=pd.read_csv(h.OUT/'finalist_summary.csv').set_index(ix)[p.METRICS]
    pd.testing.assert_frame_equal(metrics.loc[ANCHOR].sort_index(),prior.loc[ANCHOR].sort_index(),atol=1e-12,rtol=1e-12)
    allq=[]
    for stage in ['development','recent']:
        for scope in ['common','expanded']:
            for cap in [False,True]:
                reference=pd.read_csv(h.OUT/f'queries_{stage}_{scope}_{cap}_0.csv.gz');reference=reference[reference.model.eq(ANCHOR)]
                k=['period','date','profile','sector','top_n']
                for path in OUT.glob(f'queries_{stage}_{scope}_{cap}_*.csv.gz'):
                    q=pd.read_csv(path);base=q[q.model.eq(ANCHOR)]
                    pd.testing.assert_series_equal(base.set_index(k)['n'].sort_index(),reference.set_index(k)['n'].sort_index())
                    allq.append(q[q.model.isin([ANCHOR]+names)].assign(scope=scope,return_treatment='capped' if cap else 'raw'))
    q=pd.concat(allq).drop_duplicates(['model','period','date','profile','sector','top_n','scope','return_treatment'])
    q.to_csv(OUT/'finalist_queries.csv.gz',index=False)
    q.groupby(['model','period','sector','profile','top_n','scope','return_treatment'])[p.METRICS].mean().reset_index().to_csv(OUT/'sector_profile_metrics.csv',index=False)
    delta=[];trials=[]
    for name in names:
        d=(metrics.loc[name]-metrics.loc[ANCHOR]).reset_index();d.shortfall=-d.shortfall;d['model']=name;delta.append(d)
        v=d[p.METRICS].to_numpy();assert v.size==1296
        trials.append(dict(model=name,improved=int((v>1e-12).sum()),regressed=int((v< -1e-12).sum()),ties=int((abs(v)<=1e-12).sum()),strict_gate=bool((v>=-1e-12).all() and (v>1e-12).any())))
    trials=pd.DataFrame(trials);trials.to_csv(OUT/'finalist_trials.csv',index=False);pd.concat(delta).to_csv(OUT/'finalist_deltas.csv',index=False)
    keys=['period','date','profile','sector','top_n','scope','return_treatment'];qi=q.set_index(['model']+keys)[p.METRICS];worst=[]
    for name in names:
        d=(qi.loc[name]-qi.loc[ANCHOR]);d.shortfall=-d.shortfall
        for metric in p.METRICS:
            a=d[metric].nsmallest(20).reset_index().rename(columns={metric:'oriented_delta'});a['model']=name;a['metric']=metric;worst.append(a)
    pd.concat(worst).to_csv(OUT/'worst_query_regressions.csv',index=False)
    x=h.load();scores=pd.concat([pd.read_csv(OUT/f'combined_{y}.csv.gz',usecols=p.KEYS+names) for y in range(2020,2026)],ignore_index=True)
    assert len(scores)==len(x)==797443 and not scores.duplicated(p.KEYS).any()
    x=x.merge(scores,on=p.KEYS,validate='one_to_one');pairs=[];stability=[]
    for scope in ['common','expanded']:
        z=x[x.sector_incumbent.notna()] if scope=='common' else x
        z=z.dropna(subset=[ANCHOR]+names+['future_xirr','future_drawdown','future_shortfall'])
        for (period,date,profile,sector),g in z.groupby(['period','decision_date','profile_name','sector']):
            if sector=='Unclassified' or len(g)<5:continue
            for name in [ANCHOR]+names:pairs.append(dict(scope=scope,period=period,date=date,profile=profile,sector=sector,model=name,n=len(g),accuracy=pair_accuracy(g[name].to_numpy(),g.future_xirr.to_numpy())))
        print('PAIR',scope,flush=True)
    pq=pd.DataFrame(pairs);pq.to_csv(OUT/'pair_queries.csv.gz',index=False)
    pa=pq.groupby(['scope','period','profile','sector','model']).accuracy.mean().groupby(['scope','period','profile','model']).mean().groupby(['scope','period','model']).mean().reset_index();pa.to_csv(OUT/'pair_accuracy.csv',index=False)
    for (profile,sector),g in x.groupby(['profile_name','sector']):
        if sector=='Unclassified':continue
        dates=sorted(g.decision_date.unique());previous=None
        for day in dates:
            now=g[g.decision_date.eq(day)].set_index('isin')
            if previous is not None:
                shared=now.index.intersection(previous.index)
                if len(shared)>=5:
                    columns=[ANCHOR]+names
                    retained,correlations=paired_rank_stability(previous.loc[shared,columns].to_numpy(),now.loc[shared,columns].to_numpy())
                    for j,name in enumerate(columns):
                        stability.append(dict(profile=profile,sector=sector,date=day,period=now.period.iloc[0],model=name,shared_stocks=len(shared),top3_retention=retained[j],rank_stability=float(correlations[j])))
            previous=now
    st=pd.DataFrame(stability);st.to_csv(OUT/'rank_stability_queries.csv.gz',index=False)
    st.groupby(['model','period','profile','sector'])[['top3_retention','rank_stability']].mean().groupby(['model','period','profile']).mean().groupby(['model','period']).mean().reset_index().to_csv(OUT/'rank_stability_summary.csv',index=False)
    sectors=pq.groupby(['scope','period','sector','profile','model']).accuracy.mean().groupby(['scope','period','sector','model']).mean().unstack('model');boot=[];rng=np.random.default_rng(20261011)
    for (scope,period),g in sectors.groupby(level=['scope','period']):
        for name in names:
            d=(g[name]-g[ANCHOR]).dropna().to_numpy();bb=rng.choice(d,(2000,len(d)),replace=True).mean(axis=1)
            boot.append(dict(scope=scope,period=period,model=name,mean_sector_delta=d.mean(),lower95=np.quantile(bb,.025),upper95=np.quantile(bb,.975),sector_win_fraction=np.mean(d>1e-12)))
    pd.DataFrame(boot).to_csv(OUT/'descriptive_sector_bootstrap.csv',index=False)
    summary.groupby(['model','period','scope','return_treatment','top_n'])[p.METRICS].mean().reset_index().to_csv(OUT/'aggregate_metrics.csv',index=False)
    cols=['isin','ticker','company','sector','input_status','rebuilt_input_confidence','rebuilt_sector_rank',ANCHOR]+sum(([n,n+'_rank'] for n in names),[])
    cur[cols].sort_values(['sector','rebuilt_sector_rank','isin']).to_csv(OUT/'finalists_all_4436.csv',index=False)
    s.write('evaluation_verification.json',dict(current_rows=len(cur),historical_rows=len(x),benchmark_cohorts_verified=True,champion_reference_reproduced=True,current_ranks_verified=True,strict_gate_passes=int(trials.strict_gate.sum()),fresh_validation=False,production_replaced=False))
    ledger()

def company_audit():
    names=json.loads((OUT/'locked_finalists.json').read_text())['finalists'];cur=pd.read_csv(OUT/'finalists_all_4436.csv',float_precision='round_trip')
    source=p.ROOT/'experiments/champion-sir-judgment-20261010/all_4436_stock_audit.csv';facts=pd.read_csv(source)
    keep=['isin','sir_score','sir_sector_rank','sir_status','sir_price_observations','sir_quote_lag_days','judge_coverage','judge_flags','judge_primary','judge_variant_quality','judge_variant_growth','judge_variant_value','paired_comparison','judge_input_roe','judge_input_roce','judge_input_sales_growth','judge_input_profit_growth','judge_input_debt','judge_input_pledge','judge_input_cash_conversion','judge_input_earnings_yield','judge_profitability','judge_growth','judge_safety','judge_cash','judge_valuation','screener_source_observed_at','review_flags','evidence_reason']
    z=cur.merge(facts[keep],on='isin',validate='one_to_one');assert len(z)==4436
    z.to_csv(OUT/'all_4436_financial_evidence.csv',index=False);rows=[]
    for rubric in ['judge_primary','judge_variant_quality','judge_variant_growth','judge_variant_value']:
        paired=z[z.paired_comparison&z[rubric].notna()].copy()
        for sector,g in paired.groupby('sector'):
            if sector=='Unclassified' or len(g)<5:continue
            for name in [ANCHOR,'sir_score']+names:
                ordered=g.sort_values(['isin']).sort_values(name,ascending=False,kind='stable')
                rows.append(dict(rubric=rubric,sector=sector,model=name,stocks=len(g),pair_agreement=pair_accuracy(g[name].to_numpy(),g[rubric].to_numpy()),top3_rubric=ordered.head(3)[rubric].mean()))
    audit=pd.DataFrame(rows);audit.to_csv(OUT/'financial_sector_comparison.csv',index=False)
    audit.groupby(['rubric','model'])[['pair_agreement','top3_rubric']].mean().reset_index().to_csv(OUT/'financial_comparison.csv',index=False)
    exports=[]
    for name in [ANCHOR]+names:
        a=z.copy();a['evaluated_model']=name;a['candidate_sector_rank']=a[name].groupby(a.sector).rank(method='min',ascending=False)
        a['rank_change_vs_champion']=a.candidate_sector_rank-a.rebuilt_sector_rank
        a['review_note']=a.apply(lambda r:f"Sector rank {int(r.candidate_sector_rank)}; champion {int(r.rebuilt_sector_rank)}; fundamental coverage {r.judge_coverage:.0%}. Saved evidence: {r.evidence_reason}. Price-input status: {r.input_status}. This is snapshot evidence, not a fresh company investigation.",axis=1)
        exports.append(a[['isin','ticker','company','sector','evaluated_model','candidate_sector_rank','rank_change_vs_champion','sir_sector_rank','judge_primary','judge_coverage','judge_flags','review_flags','input_status','review_note']])
    allr=pd.concat(exports);allr.to_csv(OUT/'all_stock_explanations.csv',index=False)
    for n in [1,3,20,100]:allr[allr.candidate_sector_rank.le(n)].sort_values(['evaluated_model','sector','candidate_sector_rank','isin']).to_csv(OUT/f'current_sector_top{n}.csv',index=False)
    s.write('financial_audit_sources.json',dict(source=str(source),sha256=s.digest(source),rows=len(z),snapshot='2026-10-03',current_fundamentals_used_in_historical_training=False,independent_future_truth=False,fresh_company_investigations=False))

if __name__=='__main__':
    import sys
    {'replay':replay,'evaluate':evaluate,'company':company_audit,'ledger':ledger}[sys.argv[1]]()
