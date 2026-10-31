"""Locked scenario-probability and expected goal-shortfall research pilots.

The market component is explicitly a current-survivor cross-sectional SIP proxy,
not a certified historical index. Realized market conditioning is diagnostic only.
"""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
import pandas as pd
import lightgbm as lgb
import ten_hypotheses_20261031 as base

ROOT=base.ROOT
OUT=ROOT/'experiments/round2-goal-risk-20261031'
SEED=20261031
SCENARIOS={'bear':-.20,'flat':0.,'bull':.20}
FEATURES=[c for c in base.old.COLS if c!='target_cagr']

def save(name,obj):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/name).write_text(json.dumps(obj,indent=2,default=lambda a:a.item() if hasattr(a,'item') else str(a)),encoding='utf-8')

def protocol():
    doc=dict(version='round2_goal_risk_20261031_v1',baseline_commit='6e9bd620e4472c8280536b6120fe86d10dca65cb',seed=SEED,
        status='PREREGISTERED BEFORE NEW OUTCOME EVALUATION',
        population='Existing 44-date current-survivor panel is a retrospective prerequisite diagnostic. A survivorship-free panel is not yet available; no fresh validation or promotion is possible here.',
        periods={'development':'2020-2023','exposed':'2024-2025, previously exposed; each new locked analysis evaluated once after development lock'},
        market_component='Per-date median log(1+future_XIRR) among usable base7500 identities. This is a survivor-cohort SIP market proxy, not a NIFTY500 index return. It is an outcome component used in training labels and ex-post diagnostics, never an inference feature.',
        return_clipping='For relative-distribution fitting only, future XIRR clipped to[-.95,3] before log1p; raw labels retained for scoring.',
        relative_model='LGBM squared-error regression of log gross stock SIP XIRR minus market component. Existing price/profile features excluding target CAGR. 120 trees,15 leaves,maxdepth5,minchild150,lambda30,learning_rate.04,3threads,seed fixed.',
        temporal_split='Test-year Y: base training endpoint < Jan1(Y-2); calibration decisions >= Jan1(Y-2) and endpoints < Jan1Y. No target10/30 duplicate schedules in model/CDF training. Target10/30 use base7500 relative distribution.',
        relative_calibration='Weighted empirical survival CDF of errors on disjoint mature calibration windows, per contribution schedule. Equal date/sector query weights. No calibration fit on test outcomes.',
        forecast='P(goal | fixed market scenario) = survival_CDF(log1p(goal)-log1p(scenario)-relative_prediction). Bear/flat/bull are fixed -20%,0%,+20% SIP-XIRR scenarios, not forecasts of which market state occurs.',
        scenario_buckets='Realized proxy < -5% bear; -5% through+5% flat; >+5% bull. Bucket labels use future outcomes only for conditional scoring; unavailable at forecast time.',
        benchmarks='Conditional climatology from past mature calibration labels, matched schedule/target/profile and realized proxy bucket; require >=2 distinct calibration dates. Missing conditional benchmark remains missing, never silently replaced by unconditional frequency. Unconditional climatology separately reported.',
        scenario_pass='Fixed-scenario conditional Brier strictly below matching conditional climatology in each of bear/flat/bull in both periods; >=2 distinct scored dates per bin and >=80% conditional-benchmark row coverage per period. Report date-block uncertainty; oracle realized-market probability is diagnostic only and cannot pass the deployable scenario gate.',
        risk_candidates=['expected_goal_shortfall','goal_probability_below_median_downside'],
        expected_shortfall_definition='Stored future_shortfall=max(0,1-terminal_wealth/target_wealth), conditional-mean squared-error regression, not CVaR/financial expected shortfall. 120 trees/15leaves and same regularization; target_CAGR monotone increasing; annual training all outcomes ending strictly before test-year January1.',
        risk_probability='Reuse prior development-selected monotone goal_volume probability; no new selection on exposed data. Only stocks with decision-date downside252 <= same-query sector median can enter Top3. Missing risk excluded; query requires >=3 safe stocks.',
        risk_evaluation='Same query support for both candidates and incumbent. Top3 attainment and average selected-asset drawdown; score ties break incumbent score then ISIN. Risk selection only development: attainment delta>=0 and drawdown delta>=0; then greatest attainment, then drawdown, then name. If none pass, incumbent locked. Exposed repeats locked choices; all fixed candidates descriptive.',
        risk_pass='Attainment must not fall and drawdown must not worsen in BOTH periods; report paired date-block intervals, coverage and shortfall. No mean-return substitution.',
        uncertainty='4000 circular calendar-block resamples of paired per-date metrics,365-day blocks; dates/sectors/profiles remain jointly coupled. Small number of independent regimes is explicit.',
        source_semantics='src/stock_research/personalized_official_actions.py computes target_shortfall from terminal wealth, and recomputes whole-share cashflow XIRR. Relative proxy does not establish a causal explanation for base-rate/calibration shifts.',
        no_serving_changes=True,no_promotion=True,
        references=['https://scikit-learn.org/stable/modules/calibration.html','https://lightgbm.readthedocs.io/en/stable/Parameters.html'])
    p=OUT/'protocol.json';OUT.mkdir(parents=True,exist_ok=True)
    if p.exists():assert json.loads(p.read_text())==doc
    else:save('protocol.json',doc)
    return doc

def schedule(name):return 'base7500' if name in ['target10','target30'] else name

def scenario_name(market):
    return np.where(np.asarray(market)<-.05,'bear',np.where(np.asarray(market)>.05,'bull','flat'))

def weighted_survival(values,weights,threshold):
    order=np.argsort(values);v=np.asarray(values)[order];w=np.asarray(weights,float)[order]
    total=w.sum();cumulative=np.r_[0,np.cumsum(w)]
    return 1-cumulative[np.searchsorted(v,threshold,side='left')]/total

def query_weights(frame):
    w=1/frame.groupby(base.GROUP,observed=True)['isin'].transform('size')
    return w/w.mean()

def params():return dict(n_estimators=120,num_leaves=15,max_depth=5,min_child_samples=150,reg_lambda=30,learning_rate=.04,n_jobs=3,random_state=SEED,verbosity=-1,deterministic=True,force_col_wise=True)

def calendar_intervals(frame,replicates=4000,span=365):
    """Paired calendar-block means; preserve missing scenario support explicitly."""
    if frame.empty:return {'coverage':dict(status='NOT_ESTIMABLE_NO_SUPPORTED_SCENARIO_DATES',valid_draws=0)}
    days=pd.to_datetime(frame.index);offsets=(days-days[0]).days.to_numpy();duration=int((days[-1]-days[0]).days)+90
    if span>=duration:return {str(c):dict(lower=np.nan,upper=np.nan,status='block spans available period',valid_draws=0) for c in frame}
    x=frame.to_numpy(float);rng=np.random.default_rng(SEED);draw=[]
    for _ in range(replicates):
        ids=[]
        while len(ids)<len(x):
            start=int(rng.integers(len(x)));distance=(offsets-offsets[start])%duration
            block=np.flatnonzero(distance<span);ids.extend(block[np.argsort(distance[block])].tolist())
        sample=x[np.array(ids[:len(x)])];count=np.isfinite(sample).sum(axis=0)
        draw.append(np.divide(np.nansum(sample,axis=0),count,out=np.full(x.shape[1],np.nan),where=count>0))
    draw=np.asarray(draw);result={}
    for j,c in enumerate(frame):
        v=draw[np.isfinite(draw[:,j]),j]
        result[str(c)]=dict(lower=float(np.quantile(v,.025)) if len(v) else np.nan,upper=float(np.quantile(v,.975)) if len(v) else np.nan,valid_draws=len(v),status='conditional paired calendar-block interval')
    return result

def load():
    x=pd.read_pickle(base.OUT/'panel.pkl.gz',compression='gzip')
    keep=list(dict.fromkeys(base.KEYS+['sector','endpoint','future_xirr','future_shortfall','future_drawdown','goal_hit',base.ANCHOR]+base.old.COLS))
    x=base.valid(x[keep]).dropna(subset=['future_shortfall','future_drawdown']).copy()
    m=x[x.profile_name.eq('base7500')].groupby('decision_date',observed=True).future_xirr.median().clip(-.95,3)
    x['market_component']=x.decision_date.map(np.log1p(m))
    x['market_sip_proxy']=np.expm1(x.market_component)
    x['realized_scenario']=scenario_name(x.market_sip_proxy)
    x['relative_outcome']=np.log1p(x.future_xirr.clip(-.95,3))-x.market_component
    x['schedule']=x.profile_name.astype(str).map(schedule)
    return x

def scenario():
    protocol();x=load();audits=[];predictions=[]
    for year in range(2020,2026):
        cutoff=f'{year}-01-01';split=f'{year-2}-01-01'
        t=x[x.endpoint.lt(split)&~x.profile_name.isin(['target10','target30'])]
        cal=x[x.decision_date.ge(split)&x.endpoint.lt(cutoff)].copy()
        z=x[x.decision_date.str.startswith(str(year))].copy()
        model=lgb.LGBMRegressor(objective='regression',**params());model.fit(t[FEATURES],t.relative_outcome,sample_weight=query_weights(t))
        cal['relative_prediction']=model.predict(cal[FEATURES]);cal['error']=cal.relative_outcome-cal.relative_prediction
        z['relative_prediction']=model.predict(z[FEATURES])
        for name,value in SCENARIOS.items():z['p_'+name]=np.nan
        z['p_oracle_market']=np.nan;z['conditional_climatology']=np.nan;z['unconditional_climatology']=np.nan;z['benchmark_calibration_dates']=0
        for profile,g in z.groupby('profile_name',observed=True):
            cdf=cal[cal.profile_name.eq(schedule(str(profile)))].copy();weights=query_weights(cdf).to_numpy()
            for name,value in SCENARIOS.items():
                threshold=np.log1p(g.target_cagr.to_numpy())-np.log1p(value)-g.relative_prediction.to_numpy()
                z.loc[g.index,'p_'+name]=weighted_survival(cdf.error.to_numpy(),weights,threshold)
            threshold=np.log1p(g.target_cagr.to_numpy())-g.market_component.to_numpy()-g.relative_prediction.to_numpy()
            z.loc[g.index,'p_oracle_market']=weighted_survival(cdf.error.to_numpy(),weights,threshold)
            own=cal[cal.profile_name.eq(profile)];w=query_weights(own)
            z.loc[g.index,'unconditional_climatology']=np.average(own.goal_hit,weights=w)
            for case,gg in g.groupby('realized_scenario'):
                cohort=own[own.realized_scenario.eq(case)];dates=cohort.decision_date.nunique()
                z.loc[gg.index,'benchmark_calibration_dates']=dates
                if dates>=2:z.loc[gg.index,'conditional_climatology']=np.average(cohort.goal_hit,weights=query_weights(cohort))
        z['p_fixed_scenario']=np.select([z.realized_scenario.eq(n) for n in SCENARIOS],[z['p_'+n] for n in SCENARIOS])
        assert (z.p_bear<=z.p_flat+1e-12).all() and (z.p_flat<=z.p_bull+1e-12).all()
        model.booster_.save_model(str(OUT/f'relative_{year}.txt'))
        audits.append(dict(year=year,training_rows=len(t),max_training_endpoint=t.endpoint.max(),max_calibration_endpoint=cal.endpoint.max(),features=FEATURES))
        predictions.append(z[base.KEYS+['sector','goal_hit','target_cagr','future_xirr','market_sip_proxy','relative_outcome','realized_scenario','relative_prediction','p_bear','p_flat','p_bull','p_oracle_market','p_fixed_scenario','conditional_climatology','unconditional_climatology','benchmark_calibration_dates']])
        print('SCENARIO FIT',year,len(t),len(cal),len(z),flush=True)
    z=pd.concat(predictions,ignore_index=True)
    dev=evaluate_scenarios(z[z.decision_date.lt('2024-01-01')],'development')
    save('scenario_development_lock.json',dict(forecast='fixed scenarios, no model choice',development=dev.to_dict('records'),exposed_not_yet_evaluated=True))
    recent=evaluate_scenarios(z[z.decision_date.ge('2024-01-01')],'exposed')
    result=pd.concat([dev,recent],ignore_index=True);result.to_csv(OUT/'scenario_summary.csv',index=False)
    z.to_pickle(OUT/'scenario_predictions.pkl.gz',compression='gzip')
    pd.DataFrame(audits).to_json(OUT/'scenario_training_audit.json',orient='records',indent=2)
    coverage=z.assign(period=np.where(z.decision_date.lt('2024-01-01'),'development','exposed')).groupby('period').conditional_climatology.apply(lambda s:s.notna().mean())
    passed=bool(len(result)==6 and result.dates.ge(2).all() and result.delta_brier.lt(0).all() and coverage.ge(.8).all())
    save('scenario_decision.json',dict(pass_preregistered_gate=passed,conditional_benchmark_coverage=coverage.to_dict(),oracle_is_not_deployable=True,market_proxy_is_survivor_based=True,fresh_validation=False))
    intervals={}
    for period,g in z.groupby(np.where(z.decision_date.lt('2024-01-01'),'development','exposed')):
        g=g[g.conditional_climatology.notna()].copy();g['paired_brier_delta']=(g.p_fixed_scenario-g.goal_hit.astype(float))**2-(g.conditional_climatology-g.goal_hit.astype(float))**2
        matrix=g.groupby(['decision_date','realized_scenario']).paired_brier_delta.mean().unstack('realized_scenario')
        intervals[period]=calendar_intervals(matrix)
    save('scenario_brier_intervals.json',intervals)
    frequencies=z.groupby(['decision_date','realized_scenario'],observed=True).agg(actual_goal_frequency=('goal_hit','mean'),market_sip_proxy=('market_sip_proxy','first'),relative_mean=('relative_outcome','mean'),relative_std=('relative_outcome','std')).reset_index()
    frequencies.to_csv(OUT/'base_rate_decomposition.csv',index=False)
    print('SCENARIO COMPLETE',result.to_dict('records'),flush=True)

def evaluate_scenarios(z,period):
    rows=[]
    for case in SCENARIOS:
        g=z[z.realized_scenario.eq(case)]
        available=g[g.conditional_climatology.notna()];y=available.goal_hit.astype(float)
        if len(available):
            scored=available.assign(brier=(available.p_fixed_scenario-y)**2,oracle_brier=(available.p_oracle_market-y)**2,baseline_brier=(available.conditional_climatology-y)**2,unconditional_brier=(available.unconditional_climatology-y)**2)
            daily=scored.groupby('decision_date')[['brier','oracle_brier','baseline_brier','unconditional_brier']].mean()
            row=daily.mean().to_dict();row['delta_brier']=row['brier']-row['baseline_brier']
        else:row=dict(brier=np.nan,oracle_brier=np.nan,baseline_brier=np.nan,unconditional_brier=np.nan,delta_brier=np.nan)
        rows.append(dict(period=period,scenario=case,rows=len(available),total_rows=len(g),dates=available.decision_date.nunique(),**row))
    return pd.DataFrame(rows)

def top3_metrics(z,columns):
    records=[]
    for key,g in z.sort_values('isin').groupby(base.GROUP,observed=True,sort=True):
        if len(g)<5:continue
        scores=g[columns].to_numpy(dtype=float);counts=np.isfinite(scores).sum(axis=0)
        if counts.min()<3:continue
        anchor=g[base.ANCHOR].to_numpy(dtype=float);hits=g.goal_hit.to_numpy(dtype=float)
        risk=g.future_drawdown.to_numpy(dtype=float);short=g.future_shortfall.to_numpy(dtype=float);returns=g.future_xirr.to_numpy(dtype=float)
        for j,name in enumerate(columns):
            eligible=np.flatnonzero(np.isfinite(scores[:,j]));order=np.lexsort((eligible,-anchor[eligible],-scores[eligible,j]))[:3];ids=eligible[order]
            records.append(dict(zip(base.GROUP,key),model=name,achievement=float(hits[ids].mean()),drawdown=float(risk[ids].mean()),shortfall=float(short[ids].mean()),xirr=float(np.median(returns[ids])),eligible=int(counts[j])))
    return pd.DataFrame(records)

def risk():
    protocol();x=load();prob=pd.read_pickle(base.OUT/'monotone_round/goal_predictions.pkl.gz',compression='gzip')[base.KEYS+['goal_volume']]
    x=x.merge(prob,on=base.KEYS,how='left',validate='one_to_one');pred=[];audit=[]
    for year in range(2020,2026):
        cutoff=f'{year}-01-01';t=x[x.endpoint.lt(cutoff)].copy();z=x[x.decision_date.str.startswith(str(year))].copy()
        constraints=[1 if name=='target_cagr' else 0 for name in base.old.COLS]
        model=lgb.LGBMRegressor(objective='regression',monotone_constraints=constraints,**params());model.fit(t[base.old.COLS],t.future_shortfall,sample_weight=query_weights(t))
        z['expected_goal_shortfall']=-np.clip(model.predict(z[base.old.COLS]),0,1)
        median=z.downside252.groupby([z[k] for k in base.GROUP]).transform('median')
        z['goal_probability_below_median_downside']=z.goal_volume.where(z.downside252.le(median))
        pred.append(z[base.KEYS+['sector','goal_hit','future_xirr','future_drawdown','future_shortfall',base.ANCHOR,'expected_goal_shortfall','goal_probability_below_median_downside']])
        model.booster_.save_model(str(OUT/f'shortfall_{year}.txt'))
        audit.append(dict(year=year,training_rows=len(t),max_training_endpoint=t.endpoint.max()))
        print('RISK FIT',year,len(t),len(z),flush=True)
    z=pd.concat(pred,ignore_index=True);names=[base.ANCHOR,'expected_goal_shortfall','goal_probability_below_median_downside']
    dev=top3_metrics(z[z.decision_date.lt('2024-01-01')],names)
    daily=dev.groupby(['model','decision_date'])[['achievement','drawdown']].mean().groupby('model').mean();d=daily.subtract(daily.loc[base.ANCHOR])
    candidates=d.drop(index=base.ANCHOR);passing=candidates[candidates.achievement.ge(0)&candidates.drawdown.ge(0)]
    chosen=base.ANCHOR if passing.empty else passing.sort_values(['achievement','drawdown'],ascending=False,kind='stable').index[0]
    save('risk_development_lock.json',dict(selected=chosen,development_deltas=d.to_dict('index'),exposed_not_yet_evaluated=True))
    recent=top3_metrics(z[z.decision_date.ge('2024-01-01')],names);q=pd.concat([dev,recent],ignore_index=True)
    q.to_csv(OUT/'risk_queries.csv.gz',index=False)
    summary=q.assign(period=np.where(q.decision_date.lt('2024-01-01'),'development','exposed')).groupby(['period','model','decision_date'])[['achievement','drawdown','shortfall','xirr']].mean().groupby(['period','model']).mean().reset_index();summary['selected']=summary.model.eq(chosen);summary.to_csv(OUT/'risk_summary.csv',index=False)
    decisions=[]
    for model in names[1:]:
        ok=True;ds={}
        for period in ['development','exposed']:
            a=summary[summary.period.eq(period)].set_index('model');delta=a.loc[model,['achievement','drawdown']]-a.loc[base.ANCHOR,['achievement','drawdown']];ok &=bool(delta.ge(0).all());ds[period]=delta.to_dict()
        decisions.append(dict(model=model,pass_point_gate=ok,deltas=ds))
    pd.DataFrame(audit).to_csv(OUT/'risk_training_audit.csv',index=False)
    save('risk_decision.json',dict(selected=chosen,candidates=decisions,fresh_validation=False,population='current-survivor retrospective diagnostic'))
    intervals={}
    for period,g in q.groupby(np.where(q.decision_date.lt('2024-01-01'),'development','exposed')):
        frames=[]
        for metric in ['achievement','drawdown']:
            m=g.pivot(index=base.GROUP,columns='model',values=metric).dropna()
            d=m[names[1:]].subtract(m[base.ANCHOR],axis=0).groupby('decision_date').mean();d.columns=[metric+'__'+s for s in d];frames.append(d)
        intervals[period]=calendar_intervals(pd.concat(frames,axis=1))
    save('risk_paired_intervals.json',intervals)
    print('RISK COMPLETE',summary.to_dict('records'),flush=True)

def review():
    """Post-fit audits and paired uncertainty; no fitting or candidate selection."""
    protocol();x=load();z=pd.read_pickle(OUT/'scenario_predictions.pkl.gz',compression='gzip');q=pd.read_csv(OUT/'risk_queries.csv.gz')
    intervals={}
    for period,g in z.groupby(np.where(z.decision_date.lt('2024-01-01'),'development','exposed')):
        g=g[g.conditional_climatology.notna()].copy();g['paired_brier_delta']=(g.p_fixed_scenario-g.goal_hit.astype(float))**2-(g.conditional_climatology-g.goal_hit.astype(float))**2
        matrix=g.groupby(['decision_date','realized_scenario']).paired_brier_delta.mean().unstack('realized_scenario')
        intervals[period]=calendar_intervals(matrix)
    save('scenario_brier_intervals.json',intervals)
    intervals={};names=[base.ANCHOR,'expected_goal_shortfall','goal_probability_below_median_downside']
    for period,g in q.groupby(np.where(q.decision_date.lt('2024-01-01'),'development','exposed')):
        frames=[]
        for metric in ['achievement','drawdown']:
            m=g.pivot(index=base.GROUP,columns='model',values=metric).dropna();d=m[names[1:]].subtract(m[base.ANCHOR],axis=0).groupby('decision_date').mean();d.columns=[metric+'__'+s for s in d];frames.append(d)
        intervals[period]=calendar_intervals(pd.concat(frames,axis=1))
    save('risk_paired_intervals.json',intervals)
    # Exact arithmetic decomposition, not a causal explanation of market shifts.
    rate=[]
    for key,g in x[x.decision_date.ge('2020-01-01')].sort_values('isin').groupby(base.GROUP,observed=True):
        top=g.sort_values([base.ANCHOR,'isin'],ascending=[False,True]).head(3)
        rate.append(dict(zip(base.GROUP,key),universe_hit_frequency=float(g.goal_hit.mean()),top3_hit_frequency=float(top.goal_hit.mean())))
    rate=pd.DataFrame(rate);rate['selection_lift']=rate.top3_hit_frequency-rate.universe_hit_frequency
    rate_summary=rate.assign(period=np.where(rate.decision_date.lt('2024-01-01'),'development','exposed')).groupby(['period','decision_date'])[['universe_hit_frequency','top3_hit_frequency','selection_lift']].mean().groupby('period').mean().reset_index();rate_summary.to_csv(OUT/'ranker_base_rate_lift.csv',index=False)
    p=pd.read_pickle(base.OUT/'monotone_round/goal_predictions.pkl.gz',compression='gzip');brier=[]
    for period,g in p.groupby(np.where(p.decision_date.lt('2024-01-01'),'development','exposed')):
        y=g.goal_hit.to_numpy(float)
        for model in ['goal_volume','climatology']:
            prob=g[model].to_numpy();bias=(prob.mean()-y.mean())**2;varp=np.var(prob);vary=np.var(y);cov=np.mean((prob-prob.mean())*(y-y.mean()));score=np.mean((prob-y)**2)
            assert abs(score-(bias+varp+vary-2*cov))<1e-10
            brier.append(dict(period=period,model=model,brier=score,mean_probability=prob.mean(),actual_frequency=y.mean(),squared_mean_bias=bias,prediction_variance=varp,outcome_variance=vary,minus_two_covariance=-2*cov,oracle_test_rate_constant_brier=vary))
    pd.DataFrame(brier).to_csv(OUT/'brier_base_rate_decomposition.csv',index=False)
    # Numerical replay uses stored weights only, never retrains on exposed data.
    test=x[x.decision_date.str.startswith('2025')].head(500);stored=z.set_index(base.KEYS).relative_prediction.reindex(pd.MultiIndex.from_frame(test[base.KEYS]))
    model=lgb.Booster(model_file=str(OUT/'relative_2025.txt'));replay=model.predict(test[FEATURES],num_threads=3);error=float(np.max(np.abs(stored.to_numpy()-replay)));assert error<1e-12
    s=lgb.Booster(model_file=str(OUT/'shortfall_2025.txt'));low=test[base.old.COLS].copy();high=low.copy();low.target_cagr=.1;high.target_cagr=.3
    assert (s.predict(low,num_threads=3)<=s.predict(high,num_threads=3)+1e-12).all()
    target=z[z.profile_name.isin(['base7500','target10','target30'])].pivot(index=['isin','decision_date'],columns='profile_name',values=['p_bear','p_flat','p_bull']).dropna()
    for name in ['p_bear','p_flat','p_bull']:assert (target[name].target10+1e-12>=target[name].base7500).all() and (target[name].base7500+1e-12>=target[name].target30).all()
    for a in json.loads((OUT/'scenario_training_audit.json').read_text()):assert a['max_training_endpoint']<f'{a["year"]-2}-01-01' and a['max_calibration_endpoint']<f'{a["year"]}-01-01'
    for a in pd.read_csv(OUT/'risk_training_audit.csv').itertuples():assert a.max_training_endpoint<f'{a.year}-01-01'
    latest=z[z.decision_date.eq(z.decision_date.max())];examples=latest[latest['isin'].isin(sorted(latest['isin'].unique())[:5])&latest.profile_name.isin(['base7500','target10','target30'])]
    examples[base.KEYS+['target_cagr','p_bear','p_flat','p_bull']].to_csv(OUT/'scenario_forecast_examples.csv',index=False)
    coverage=[]
    for key,g in x[x.decision_date.ge('2020-01-01')].groupby(base.GROUP,observed=True):
        safe=g.downside252.le(g.downside252.median())
        coverage.append(dict(zip(base.GROUP,key),stocks=len(g),safe_stocks=int(safe.sum()),scorable=bool(safe.sum()>=3)))
    pd.DataFrame(coverage).to_csv(OUT/'risk_coverage.csv',index=False)
    save('verification.json',dict(strict_outcome_maturity=True,relative_model_replay_rows=500,relative_model_max_error=error,scenario_target_monotonic_matched_cases=len(target),shortfall_target_monotonic_probe_rows=500,scenario_assumption_ordering=True,source_population='current-survivor retrospective diagnostic',no_serving_changes=True))
    source=[Path(__file__),ROOT/'tests/test_round2_goal_risk_20261031.py']
    files=source+[p for p in OUT.iterdir() if p.suffix in ['.json','.csv','.txt'] and p.name!='manifest.json']
    save('manifest.json',{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    print('REVIEW',dict(error=error,matched_targets=len(target)),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('stage',choices=['protocol','scenario','risk','review']);args=a.parse_args();globals()[args.stage]()
