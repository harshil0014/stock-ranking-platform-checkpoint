"""Research-only, development-selected repairs of V17. Frozen inputs untouched."""
import sys,json,gc,importlib.util
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore',category=pd.errors.PerformanceWarning)
import lightgbm as lgb
import personalized_v18_20261003 as r
s=r.s;v=r.v;ROOT=r.ROOT;V17=r.V17;O=ROOT/'experiments/v17-refinement-20261004';O.mkdir(exist_ok=True)
def write(name,data,exclusive=False):
    with (O/name).open('x' if exclusive else 'w',encoding='utf-8') as f:json.dump(v.clean(data),f,indent=2,allow_nan=False)
def csv(name,x):x.to_csv(O/name,index=False,compression={'method':'gzip','mtime':0} if name.endswith('.gz') else None)
def now():return datetime.now(timezone.utc).isoformat()
def prepare():
    choices=[{'name':f'{family}_b{beta}_l{long}_g{gate}','family':family,'beta':beta,'long_scale':long,'gate':gate} for family in ['regime_utility','specialist_utility','robust_shallow'] for beta in [.025,.05,.10] for long in [.3333333333333333,.6666666666666666,1.] for gate in ['broad','volatility']]
    # The controls isolate stability repair without a new score contribution.
    choices += [{'name':'long_seedmean_'+str(long),'family':'none','beta':0.,'long_scale':long,'gate':'broad'} for long in [.3333333333333333,.6666666666666666,1.]]
    write('protocol_lock.json',{'locked_at':now(),'scope':'V17 repair first; no candidate receives V18 name until cleanly beating the repaired champion.','development_dates':v.protocol()['development_selection_dates'],'candidates':choices,'selection':'Unchanged V17 strict gates versus d499580; aggregate median XIRR >=original V17, NDCG>=original V17, achievement>=-0.005, shortfall<=+0.0025, drawdown>=original V17; every profile return>=-0.01 and drawdown>=-0.005 versusV17. High-volatility within-cohort drawdown>=V17 and return>=-0.01. Positive utility required. Mean XIRR zero. Eligible utility then smaller strength.','architecture':'Keep12M V17 score exactly. Average original V17 with independent seed20261004/05 scores for60M then shrink its correction toward champion using locked long_scale. Other profiles receive confidence-weighted correction from existing development-purged model percentiles. Broad gate1 or continuous high-vol gate clip((volatility_percentile-.5)*2,0,1). No identity or old-high threshold.','robustness':'Finalists must keep aggregate median and drawdown improvements versus matched V17 under alternate seed and per-date refits.60M return versus champion>=0 under each; high-volatility drawdown versus matchedV17>=0. Reject if currentTop20 overlap<85% in any profile after lock. Current is stability veto only, never weight tuning.','coverage':'Only executable AVAILABLE rows eligible; retain observed historical goal windows and shrink missing-window evidence toward contemporaneous median. No price/action imputation. Historical comparison separates common eligibility from expanded coverage.','corporate_actions':'Fetch official NSE/BSE records through2026-10-04; append dated normalized mechanics to isolated research ledger; unknown terms/failures stay explicit. Current evidence never copied into history.','evaluation':'2024–2025 exposed and contextual only; all44 trainable dates,9profiles,7cohorts, current4436 universe.','stop':'57 fixed repair configurations, then robustness; next architecture stage separately registered after repairs. Original V17 preserved if no passing model repair.'},True)
    write('baseline_hashes.json',{str(p.relative_to(ROOT)):v.sha(p) for p in [V17/'current_rankings.csv.gz',V17/'selection_lock.json',V17/'historical.pkl',r.O/'selection_lock.json',r.O/'protocol_lock.json',ROOT/'research/freezes/personalized-d499580/lambdarank.txt']},True)
    print('LOCKED',len(choices),flush=True)
def signals(dev):
    sig={}
    for family in ['regime_utility','specialist_utility','robust_shallow']:
        raw=dev[v.KEYS].merge(pd.read_csv(r.O/('predictions_'+family+'.csv.gz')),on=v.KEYS,validate='one_to_one').prediction;sig[family]=r.pct(dev,raw)
    sig['seedmean']=(dev.v17_score+r.v17_variant(dev,'seed20261004')[0]+r.v17_variant(dev,'seed20261005')[0])/3
    return sig
def prediction(dev,sig,choice):
    result=dev.v17_score.copy();long=dev.lookback_months.eq(60)
    if 'long_kind' in choice:
        if choice['long_kind']!='original':result.loc[long]=v.guided(dev,sig[choice['long_kind']],choice['long_alpha']).loc[long]
    else:result.loc[long]=(dev.champion_score+choice['long_scale']*(sig['seedmean']-dev.champion_score)).loc[long]
    if choice['family']!='none':
        vol=dev.groupby(['decision_date','profile_name']).realized_volatility_1y.rank(pct=True).fillna(.5);gate=((vol-.5)*2).clip(0,1) if choice['gate']=='volatility' else 1.;weight=choice['beta']*dev.evidence_confidence*gate;candidate=dev.v17_score*(1-weight)+sig[choice['family']]*weight;mask=dev.lookback_months.eq(36);result.loc[mask]=candidate.loc[mask]
    return result
def repair_search():
    x,dev=r.data();del x;gc.collect();sig=signals(dev);base=v.evaluate(dev,'champion_score');ref=v.evaluate(dev,'v17_score');vol=dev.realized_volatility_1y.ge(dev.groupby(['decision_date','profile_name']).realized_volatility_1y.transform('quantile',.75));hvref=v.evaluate(dev.loc[vol],'v17_score');choices=json.loads((O/'protocol_lock.json').read_text())['candidates'];rows=[];details={};pairs=[]
    for choice in choices:
        score=prediction(dev,sig,choice);st,ch,ag=r.assess(dev,score,base,ref);dd=st['v17_delta'];p=ag.groupby('profile')[[c+'_delta' for c in v.METRICS]].mean();hv=v.compare_metrics(v.evaluate(dev.loc[vol].assign(repair_score=score.loc[vol]),'repair_score'),hvref);hvdelta=hv[[c+'_delta' for c in v.METRICS]].mean();checks={'champion_strict':st['champion']['strong_eligible'],'return_preserved':dd['median_xirr_top20']>=0,'ndcg_preserved':dd['ndcg20']>=0,'achievement':dd['target_achievement_top20']>=-.005,'shortfall':dd['target_shortfall_top20']<=.0025,'drawdown':dd['mean_asset_drawdown_top20']>=0,'all_profile_return':p.median_xirr_top20_delta.min()>=-.01,'all_profile_drawdown':p.mean_asset_drawdown_top20_delta.min()>=-.005,'highvol_return':hvdelta.median_xirr_top20_delta>=-.01,'highvol_drawdown':hvdelta.mean_asset_drawdown_top20_delta>=0,'utility':st['utility_gain']>0};passed=all(checks.values());details[choice['name']]={'checks':checks,'base_stats':st,'highvol_delta':hvdelta.to_dict()};rows.append({**choice,'eligible':passed,'utility':st['utility_gain'],**dd,'highvol_return':hvdelta.median_xirr_top20_delta,'highvol_drawdown':hvdelta.mean_asset_drawdown_top20_delta});pairs.append(ag.assign(candidate=choice['name']));print('REPAIR',choice['name'],passed,round(st['utility_gain'],6),[k for k,val in checks.items() if not val],flush=True)
        csv('repair_trials.csv',pd.DataFrame(rows).sort_values(['eligible','utility'],ascending=False));write('repair_details.json',details);csv('repair_profile_date.csv',pd.concat(pairs,ignore_index=True))
    print('SEARCH COMPLETE',sum(row['eligible'] for row in rows),flush=True)
def coverage_audit():
    x=pd.read_csv(V17/'current_rankings.csv.gz',low_memory=False);missing=x.enhanced_carry_xirr_score.notna()&x.v17_score.isna();csv('available_unranked_before.csv',x.loc[missing]);csv('coverage_before.csv',x.groupby(['profile_name','status'],dropna=False).agg(rows=('isin','size'),ranked=('v17_score','count')).reset_index());write('coverage_root_cause.json',{'available_unranked':int(missing.sum()),'missing_goal_score':int(x.loc[missing,'enhanced_goal_score'].isna().sum()),'goal_windows':x.loc[missing,'goal_windows'].value_counts().to_dict(),'root_cause':'rank_executable requires all historical goal windows nonmissing, despite AVAILABLE current simulation. Missing scenario windows null enhanced_goal_score, then champion blend and V17 becomeNaN.','repair':'Recompute actual scenario shortfalls, retain valid windows, shrink mean squared shortfall toward same-profile contemporaneous full-window median by observed/expected count. Mark incomplete window evidence. Preserve all fully observed scores via original empirical-CDF anchors.'});print('COVERAGE',int(missing.sum()),flush=True)
def normalize_actions():
    from stock_research.personalized_official_actions import load_official_action_ledger
    facts=pd.read_csv(v.V7,low_memory=False);source=pd.read_csv(O/'actions/source_events.csv');source['ratio_numerator']=np.nan;source['ratio_denominator']=np.nan;source['total_share_multiplier']=np.nan;source['parse_status']=np.where(source.event_type.isin(['SPLIT','BONUS']),'PARSED','NON_AUTOMATIC_OR_TERMS_SEPARATE');csv('actions/source_events_for_normalization.csv',source)
    mapped,mapping=load_official_action_ledger(facts,O/'actions/source_events_for_normalization.csv',as_of_date='2026-10-04');old=pd.read_csv(v.ACTION,low_memory=False);new=mapped.loc[mapped.event_date.gt('2026-09-18')].copy();new['economic_policy']='OFFICIAL_MULTIPLIER_OR_EXISTING_BLOCK'
    for col in old:
        if col not in new:new[col]=None
    assert old.merge(new,on=['isin','event_date','event_type'],how='inner').empty;combined=pd.concat([old,new[old.columns]],ignore_index=True);csv('actions/normalized_ledger.csv.gz',combined);csv('actions/new_normalized_events.csv',new);write('actions/normalization_audit.json',{'old_rows':len(old),'new_rows':len(new),'mapping':mapping,'through':'2026-10-04','original_sha256':v.sha(v.ACTION),'no_original_rows_modified':True});print(new[['isin','event_date','event_type','mechanics_status','total_share_multiplier']].to_string(index=False),flush=True)

def stable60_train():
    write('stable60_protocol.json',{'locked_at':now(),'hypothesis':'Long-lookback instability is amplified by feature subsampling in the raw ranker. Remove feature subsampling and average nested tree counts80/100/140 without changing labels orATH constraints. This removes random seed dependence of the specialist. Test independently from coverage/actions.','labels':'Original V17 balanced ordinal utility','params':'Original V17 ATH-constrained60M specialist, colsample_bytree1.0,140trees; predictions at80/100/140.','future_search':'Original60M control plus stable100 and stable nested-average corrections, at alpha0.1/0.2/0.3. Other lookbacks12 unchanged,36 blends regime utility at beta0/.025/.05/.10, broad or volatility gate. At most63 configurations; same acceptance gates.','no_current_or_exposed_training_selection':True},True)
    x,dev=r.data();outputs=[];audits=[]
    for year in ['2020','2021','2022','2023']:
        test=dev.loc[dev.decision_date.str.startswith(year)&dev.lookback_months.eq(60)];t=x.loc[x.endpoint.lt(test.decision_date.min())&x.lookback_months.eq(60)].dropna(subset=v.OUTCOME+['enhanced_carry_xirr_score']).sort_values(v.KEYS[1:]+v.KEYS[:1]);params={**v.PARAMS,'n_estimators':140,'colsample_bytree':1.,'n_jobs':4,'verbosity':-1,'random_state':20261004,'deterministic':True,'force_col_wise':True};signs={'days_since_recorded_high':-1,'current_drawdown_duration_days':-1,'distance_from_recorded_high':1,'old_high_depth':-1,'underwater_depth':-1,'recovery_vs_old_high':-1};params.update(monotone_constraints=[signs.get(c,0) for c in s.RAW],monotone_constraints_method='advanced');m=lgb.LGBMRanker(objective='lambdarank',**params);labels=np.minimum(np.floor(s.target(t,True)*8),7).astype('int8');m.fit(t[s.RAW],labels,group=t.groupby(['decision_date','profile_name'],sort=False).size().tolist());m.booster_.save_model(str(O/('stable60_'+year+'.txt')));out=test[v.KEYS].copy();valid=test.champion_score.notna()
        for iteration in [80,100,140]:out['raw'+str(iteration)]=np.nan;out.loc[valid,'raw'+str(iteration)]=m.predict(test.loc[valid,s.RAW],num_iteration=iteration,num_threads=4)
        outputs.append(out);audits.append({'max_endpoint':t.endpoint.max(),'min_decision':test.decision_date.min(),'rows':len(t),'model':'stable60_'+year});print('STABLE60',year,flush=True)
    csv('stable60_predictions.csv.gz',pd.concat(outputs));write('stable60_training_audit.json',audits)

def stable_signals(dev):
    pp=dev[v.KEYS].merge(pd.read_csv(O/'stable60_predictions.csv.gz'),on=v.KEYS,how='left',validate='one_to_one');rawmono=dev[v.KEYS].merge(pd.read_csv(V17/'round1_predictions_monotone_utility.csv.gz'),on=v.KEYS,validate='one_to_one').prediction;mono=r.pct(dev,rawmono);parts={n:r.pct(dev,pp['raw'+str(n)]) for n in [80,100,140]};return {'stable100':(mono+parts[100])/2,'stableavg':(mono+(parts[80]+parts[100]+parts[140])/3)/2}
def stable_search():
    x,dev=r.data();del x;gc.collect();sig=signals(dev);sig.update(stable_signals(dev));base=v.evaluate(dev,'champion_score');ref=v.evaluate(dev,'v17_score');vol=dev.realized_volatility_1y.ge(dev.groupby(['decision_date','profile_name']).realized_volatility_1y.transform('quantile',.75));hvref=v.evaluate(dev.loc[vol],'v17_score');choices=[]
    for kind,alpha in [('original',.3)]+[(k,a) for k in ['stable100','stableavg'] for a in [.1,.2,.3]]:
        for beta,gate in [(0.,'broad')]+[(b,g) for b in [.025,.05,.10] for g in ['broad','volatility']]:choices.append({'name':f'{kind}_a{alpha}_b{beta}_{gate}','long_kind':kind,'long_alpha':alpha,'family':'regime_utility' if beta else 'none','beta':beta,'gate':gate})
    write('stable_search_lock.json',{'locked_at':now(),'choices':choices,'unchanged_gates':True},True);rows=[];details={};pairs=[]
    for choice in choices:
        score=prediction(dev,sig,choice);st,ch,ag=r.assess(dev,score,base,ref);dd=st['v17_delta'];p=ag.groupby('profile')[[c+'_delta' for c in v.METRICS]].mean();hv=v.compare_metrics(v.evaluate(dev.loc[vol].assign(repair_score=score.loc[vol]),'repair_score'),hvref);hd=hv[[c+'_delta' for c in v.METRICS]].mean();checks={'champion_strict':st['champion']['strong_eligible'],'return_preserved':dd['median_xirr_top20']>=0,'ndcg_preserved':dd['ndcg20']>=0,'achievement':dd['target_achievement_top20']>=-.005,'shortfall':dd['target_shortfall_top20']<=.0025,'drawdown':dd['mean_asset_drawdown_top20']>=0,'all_profile_return':p.median_xirr_top20_delta.min()>=-.01,'all_profile_drawdown':p.mean_asset_drawdown_top20_delta.min()>=-.005,'highvol_return':hd.median_xirr_top20_delta>=-.01,'highvol_drawdown':hd.mean_asset_drawdown_top20_delta>=0,'utility':st['utility_gain']>0};passed=all(checks.values());details[choice['name']]={'checks':checks,'base_stats':st,'highvol_delta':hd.to_dict()};rows.append({**choice,'eligible':passed,'utility':st['utility_gain'],**dd,'highvol_return':hd.median_xirr_top20_delta,'highvol_drawdown':hd.mean_asset_drawdown_top20_delta});pairs.append(ag.assign(candidate=choice['name']));print('STABLE SEARCH',choice['name'],passed,round(st['utility_gain'],6),[k for k,val in checks.items() if not val],flush=True);csv('stable_trials.csv',pd.DataFrame(rows).sort_values(['eligible','utility'],ascending=False));write('stable_details.json',details);csv('stable_profile_date.csv',pd.concat(pairs,ignore_index=True))
    print('STABLE SEARCH COMPLETE',sum(row['eligible'] for row in rows),flush=True)

def bag60_train():
    write('bag60_protocol.json',{'locked_at':now(),'hypothesis':'Full-feature deterministic specialist loses risk quality. Preserve the V17 ATH-constrained recipe and average a larger fixed seed set to reduce feature-subsampling variance.','seeds':list(range(20261003,20261010)),'aggregations':['mean','median'],'new_share':[.5,.75,1.],'lookback60_correction_alpha':.3,'lookback36_regime_beta':[.05,.10],'lookback12':'unchanged','candidate_count':12,'acceptance':'Same return/profile/highvol gates. Additionally every leave-one-seed-out60M result must retain nonnegative medianreturn vs champion and no more than0.005 drawdown regression vs originalV17. Per-date refits for finalists. No current or exposed outcome selection.'},True)
    x,dev=r.data();out=dev.loc[dev.lookback_months.eq(60),v.KEYS].copy();audits=[]
    for seed in range(20261003,20261010):
        raw=pd.Series(np.nan,index=dev.index)
        for year in ['2020','2021','2022','2023']:
            test=dev.loc[dev.decision_date.str.startswith(year)&dev.lookback_months.eq(60)];path=V17/('model_ath_specialist_'+year+'_look60.txt') if seed==20261003 else V17/('model_final_robust_seed'+str(seed)+'_'+year+'_look60.txt')
            if path.exists():m=lgb.Booster(model_file=str(path))
            else:
                train=x.loc[x.endpoint.lt(test.decision_date.min())&x.lookback_months.eq(60)].dropna(subset=v.OUTCOME+['enhanced_carry_xirr_score']).sort_values(v.KEYS[1:]+v.KEYS[:1]);params={**v.PARAMS,'n_jobs':4,'verbosity':-1,'random_state':seed,'deterministic':True,'force_col_wise':True};signs={'days_since_recorded_high':-1,'current_drawdown_duration_days':-1,'distance_from_recorded_high':1,'old_high_depth':-1,'underwater_depth':-1,'recovery_vs_old_high':-1};params.update(monotone_constraints=[signs.get(c,0) for c in s.RAW],monotone_constraints_method='advanced');model=lgb.LGBMRanker(objective='lambdarank',**params);labels=np.minimum(np.floor(s.target(train,True)*8),7).astype('int8');model.fit(train[s.RAW],labels,group=train.groupby(['decision_date','profile_name'],sort=False).size().tolist());m=model.booster_;m.save_model(str(O/('bag60_'+str(seed)+'_'+year+'.txt')));audits.append({'seed':seed,'max_endpoint':train.endpoint.max(),'min_decision':test.decision_date.min(),'rows':len(train)})
            valid=test.champion_score.notna();raw.loc[test.index[valid]]=m.predict(test.loc[valid,m.feature_name()],num_threads=4)
        out['seed'+str(seed)]=raw.loc[out.index];csv('bag60_predictions.csv.gz',out);write('bag60_training_audit.json',audits);print('BAG60',seed,flush=True)
    print('BAG60 TRAINED',flush=True)

def bag60_search(extended=False):
    x,dev=r.data();del x;gc.collect();sig=signals(dev);pp=dev[v.KEYS].merge(pd.read_csv(O/'bag60_predictions.csv.gz'),on=v.KEYS,how='left');seedcols=[c for c in pp if c.startswith('seed')];pr=pd.DataFrame({c:r.pct(dev,pp[c]) for c in seedcols});mono=dev[v.KEYS].merge(pd.read_csv(V17/'round1_predictions_monotone_utility.csv.gz'),on=v.KEYS).prediction;mono=r.pct(dev,mono);base=v.evaluate(dev,'champion_score');ref=v.evaluate(dev,'v17_score');long=dev.lookback_months.eq(60);vol=dev.realized_volatility_1y.ge(dev.groupby(['decision_date','profile_name']).realized_volatility_1y.transform('quantile',.75));hvref=v.evaluate(dev.loc[vol],'v17_score');rows=[];details={};pairs=[]
    suffix='extended_' if extended else ''
    if extended:write('bag60_extended_protocol.json',{'locked_at':now(),'hypothesis':'The fixed champion contribution may dominate the 60M specialist. Test stronger confidence-weighted learned correction after averaging seeds; no new inputs or age penalties.','alphas':[.35,.4,.5],'aggregations':['mean','median'],'share':1.,'regime_beta':[.05,.10],'configurations':12,'same_gates_and_leave_one_seed_out':True,'stop':'End60M score-weight search after this extension; do not relax gates.'},True)
    for aggregation in ['mean','median']:
        for share,alpha in ([(1.,a) for a in [.35,.4,.5]] if extended else [(share,.3) for share in [.5,.75,1.]]):
            corr=(mono+getattr(pr,aggregation)(axis=1))/2;bag=v.guided(dev,corr,alpha);longpred=dev.v17_score*(1-share)+bag*share;dropout=[]
            for seed in seedcols:
                altcorr=(mono+getattr(pr.drop(columns=seed),aggregation)(axis=1))/2;alt=dev.v17_score*(1-share)+v.guided(dev,altcorr,alpha)*share;met=v.evaluate(dev.loc[long].assign(alternative=alt.loc[long]),'alternative');dc=v.compare_metrics(met,base.loc[base.profile.eq('lookback60')]);dv=v.compare_metrics(met,ref.loc[ref.profile.eq('lookback60')]);dropout.append({'omitted':seed,'return_vs_champion':dc.median_xirr_top20_delta.mean(),'drawdown_vs_v17':dv.mean_asset_drawdown_top20_delta.mean()})
            stable=all(d['return_vs_champion']>=0 and d['drawdown_vs_v17']>=-.005 for d in dropout)
            for beta in [.05,.10]:
                choice={'name':f'{suffix}bag60_{aggregation}_{share}_a{alpha}_regime_{beta}','aggregation':aggregation,'share':share,'family':'regime_utility','beta':beta,'gate':'broad','long_kind':'original','long_alpha':alpha};pred=prediction(dev,sig,choice);pred.loc[long]=longpred.loc[long];st,ch,ag=r.assess(dev,pred,base,ref);dd=st['v17_delta'];p=ag.groupby('profile')[[c+'_delta' for c in v.METRICS]].mean();hv=v.compare_metrics(v.evaluate(dev.loc[vol].assign(repair_score=pred.loc[vol]),'repair_score'),hvref);hd=hv[[c+'_delta' for c in v.METRICS]].mean();checks={'champion_strict':st['champion']['strong_eligible'],'return_preserved':dd['median_xirr_top20']>=0,'ndcg_preserved':dd['ndcg20']>=0,'achievement':dd['target_achievement_top20']>=-.005,'shortfall':dd['target_shortfall_top20']<=.0025,'drawdown':dd['mean_asset_drawdown_top20']>=0,'all_profile_return':p.median_xirr_top20_delta.min()>=-.01,'all_profile_drawdown':p.mean_asset_drawdown_top20_delta.min()>=-.005,'highvol_return':hd.median_xirr_top20_delta>=-.01,'highvol_drawdown':hd.mean_asset_drawdown_top20_delta>=0,'utility':st['utility_gain']>0,'leave_one_seed_out':stable};passed=all(checks.values());details[choice['name']]={'checks':checks,'base_stats':st,'highvol_delta':hd.to_dict(),'leave_one_seed_out':dropout};rows.append({**choice,'eligible':passed,'utility':st['utility_gain'],**dd,'highvol_return':hd.median_xirr_top20_delta,'highvol_drawdown':hd.mean_asset_drawdown_top20_delta});pairs.append(ag.assign(candidate=choice['name']));print('BAG SEARCH',choice['name'],passed,round(st['utility_gain'],6),[k for k,val in checks.items() if not val],flush=True);csv(suffix+'bag_trials.csv',pd.DataFrame(rows).sort_values(['eligible','utility'],ascending=False));write(suffix+'bag_details.json',details);csv(suffix+'bag_profile_date.csv',pd.concat(pairs,ignore_index=True))
    print('BAG SEARCH COMPLETE',sum(row['eligible'] for row in rows),flush=True)
def bag60_extended():bag60_search(True)

def isolated_v15():
    spec=importlib.util.spec_from_file_location('isolated_v17_refinement_inputs',ROOT/'research/runners/personalized_v15_20261003.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);mod.OUT=O/'replay';mod.OUT.mkdir(exist_ok=True);return mod
def own_train(train,test,family,tag,seed=20261004):
    import types
    namespace=dict(r.__dict__);namespace['O']=O;fn=types.FunctionType(r.train_predict.__code__,namespace,argdefs=r.train_predict.__defaults__);namespace['train_predict']=fn;return fn(train,test,family,tag,seed)
def fit_stable60(train,test,tag,seed=20261004,original=False):
    t=train.loc[train.lookback_months.eq(60)].dropna(subset=v.OUTCOME+['enhanced_carry_xirr_score']).sort_values(v.KEYS[1:]+v.KEYS[:1]);params={**v.PARAMS,'n_estimators':100 if original else 140,'colsample_bytree':.9 if original else 1.,'n_jobs':4,'verbosity':-1,'random_state':seed,'deterministic':True,'force_col_wise':True};signs={'days_since_recorded_high':-1,'current_drawdown_duration_days':-1,'distance_from_recorded_high':1,'old_high_depth':-1,'underwater_depth':-1,'recovery_vs_old_high':-1};params.update(monotone_constraints=[signs.get(c,0) for c in s.RAW],monotone_constraints_method='advanced');m=lgb.LGBMRanker(objective='lambdarank',**params);labels=np.minimum(np.floor(s.target(t,True)*8),7).astype('int8');m.fit(t[s.RAW],labels,group=t.groupby(['decision_date','profile_name'],sort=False).size().tolist());m.booster_.save_model(str(O/('model_'+tag+'.txt')));out=test[v.KEYS].copy();valid=test.champion_score.notna()&test.lookback_months.eq(60)
    for n in [80,100,140]:out['raw'+str(n)]=np.nan;out.loc[valid,'raw'+str(n)]=m.predict(test.loc[valid,s.RAW],num_iteration=n,num_threads=4)
    return out,{'tag':tag,'max_endpoint':t.endpoint.max(),'min_decision':test.decision_date.min(),'seed':seed,'rows':len(t)}
def repair_robustness():
    trials=pd.concat([pd.read_csv(O/'repair_trials.csv'),pd.read_csv(O/'stable_trials.csv')],ignore_index=True);candidates=trials.loc[trials.eligible].sort_values(['utility','beta'],ascending=[False,True]);x,dev=r.data();base=v.evaluate(dev,'champion_score');results={};audit=[];winner=None
    for _,row in candidates.iterrows():
        choice=row.dropna().to_dict();passed=True;results[choice['name']]={}
        for variant,seed in [('seed20261004',20261004),('per_date',20261003)]:
            z=dev.copy();z['v17_score'],a,b=r.v17_variant(z,variant);sig={};blocks=sorted(z.decision_date.unique()) if variant=='per_date' else ['2020','2021','2022','2023']
            for family in ([choice['family']] if choice['family']!='none' else []):
                cache=O/('robust_'+variant+'_'+family+'.csv.gz')
                if cache.exists():raw=z[v.KEYS].merge(pd.read_csv(cache),on=v.KEYS).prediction
                else:
                    raw=pd.Series(np.nan,index=z.index)
                    for block in blocks:
                        test=z.loc[z.decision_date.eq(block) if variant=='per_date' else z.decision_date.str.startswith(block)];train=x.loc[x.endpoint.lt(test.decision_date.min())];p,au=own_train(train,test,family,'robust_'+variant+'_'+family+'_'+block,seed);raw.loc[test.index]=p;audit.append(au);print('REPAIR ROBUST TRAIN',variant,family,block,flush=True)
                    csv(cache.name,z[v.KEYS].assign(prediction=raw));write('repair_robustness_training_audit.json',audit)
                sig[family]=r.pct(z,raw)
            kind=choice.get('long_kind')
            if kind and kind!='original':
                cache=O/('robust_'+variant+'_stable60.csv.gz')
                if cache.exists():pp=z[v.KEYS].merge(pd.read_csv(cache),on=v.KEYS)
                else:
                    parts=[]
                    for block in blocks:
                        test=z.loc[z.decision_date.eq(block) if variant=='per_date' else z.decision_date.str.startswith(block)];train=x.loc[x.endpoint.lt(test.decision_date.min())];pp,au=fit_stable60(train,test,'robust_'+variant+'_stable60_'+block,seed);parts.append(pp);audit.append(au)
                    pp=pd.concat(parts);csv(cache.name,pp);pp=z[v.KEYS].merge(pp,on=v.KEYS);write('repair_robustness_training_audit.json',audit)
                raw=r.pct(z,pp.raw100) if kind=='stable100' else sum(r.pct(z,pp['raw'+str(n)]) for n in [80,100,140])/3;sig[kind]=(r.pct(z,a)+raw)/2
            elif not kind:sig['seedmean']=(z.v17_score+r.v17_variant(z,'seed20261005')[0]+dev.v17_score)/3
            pred=prediction(z,sig,choice);st,ch,ag=r.assess(z,pred,base,v.evaluate(z,'v17_score'));p=ch.groupby('profile')[[c+'_delta' for c in v.METRICS]].mean();vol=z.realized_volatility_1y.ge(z.groupby(['decision_date','profile_name']).realized_volatility_1y.transform('quantile',.75));hv=v.compare_metrics(v.evaluate(z.loc[vol].assign(repair_score=pred.loc[vol]),'repair_score'),v.evaluate(z.loc[vol],'v17_score'));checks={'aggregate_return':st['v17_delta']['median_xirr_top20']>=0,'aggregate_drawdown':st['v17_delta']['mean_asset_drawdown_top20']>=0,'long_return_vs_champion':p.loc['lookback60','median_xirr_top20_delta']>=0,'highvol_drawdown':hv.mean_asset_drawdown_top20_delta.mean()>=0,'original_gates':st['champion']['eligible']};results[choice['name']][variant]={'checks':checks,'stats':st,'long_return':p.loc['lookback60','median_xirr_top20_delta'],'highvol_drawdown':hv.mean_asset_drawdown_top20_delta.mean()};write('repair_robustness.json',results);csv('robust_'+choice['name']+'_'+variant+'_metrics.csv',ag);print('REPAIR ROBUST RESULT',choice['name'],variant,checks,flush=True)
            if not all(checks.values()):passed=False;break
        if passed:winner=choice;break
    write('model_repair_lock.json',{'locked_at':now(),'choice':winner,'accepted_model_repair':winner is not None,'tested':len(trials),'eligible_development':len(candidates),'originalV17_unchanged':True,'current_stability_veto_pending':winner is not None,'remaining_if_none':'Coverage and action repairs survive independently; further architecture challenge uses same gates.'},True);print('MODEL REPAIR LOCK',winner,flush=True)
def anchored_percentile(ref,values):
    arr=np.sort(pd.Series(ref).dropna().to_numpy());values=np.asarray(values);result=np.full(values.shape,.5,dtype=float) if not len(arr) else np.clip((np.searchsorted(arr,values,side='left')+np.searchsorted(arr,values,side='right')+1)/(2*len(arr)),0,1);return np.where(pd.isna(values),np.nan,result)
def recover_goal_windows():
    mod=isolated_v15();facts=pd.read_csv(v.V7,low_memory=False);x=pd.read_csv(V17/'current_rankings.csv.gz',low_memory=False);missing=x.enhanced_carry_xirr_score.notna()&x.v17_score.isna();rows=pd.read_csv(O/'goal_window_receipts.csv').to_dict('records') if (O/'goal_window_receipts.csv').exists() else [];done={row['profile_name'] for row in rows};book=mod.load_current_book(facts) if len(rows)<int(missing.sum()) else None
    # Only fill a missing summary when the current executable plan is already valid.
    for name,p in v.profiles().items():
        if name in done:continue
        target=x.loc[missing&x.profile_name.eq(name)];ids=set(target['isin']);offsets=sorted(set(np.linspace(0,p.lookback_months-p.horizon_months,4).astype(int)));short=[]
        if not ids:continue
        for offset in offsets:
            frame=book.simulate(p,pd.Timestamp('2026-10-03')-pd.DateOffset(months=int(offset)),months=p.horizon_months,mode='enhanced_carry',include_journal=False);short.append(frame.set_index('isin').target_shortfall.rename(str(offset)))
        sf=pd.concat(short,axis=1).reindex(target['isin']);full=x.loc[x.profile_name.eq(name)&x.enhanced_goal_score.notna(),'enhanced_goal_score'];prior=float((-full).median());observed=sf.notna().sum(axis=1);fraction=observed/len(offsets);summary=-(sf.pow(2).mean(axis=1)*fraction+prior*(1-fraction))
        for isin in sf.index:rows.append({'isin':isin,'profile_name':name,'observed_windows':int(observed.loc[isin]),'expected_windows':len(offsets),'window_confidence':fraction.loc[isin],'observed_goal_score':-float(sf.loc[isin].pow(2).mean()),'repaired_goal_score':summary.loc[isin],'prior_loss':prior,**{'shortfall_offset_'+c:sf.loc[isin,c] for c in sf.columns}})
        print('GOAL RECOVERY',name,len(target),flush=True);csv('goal_window_receipts.csv',pd.DataFrame(rows));book.cache.clear()
    receipts=pd.DataFrame(rows);assert len(receipts)==int(missing.sum());z=x.merge(receipts,on=['isin','profile_name'],how='left',validate='one_to_one');z['original_v17_score']=z.v17_score;mask=z.repaired_goal_score.notna();z.loc[mask,'enhanced_goal_score']=z.loc[mask,'repaired_goal_score'];model=lgb.Booster(model_file=str(v.FREEZE/'lambdarank.txt'))
    for _,g in z.groupby('profile_name'):
        ix=g.index[g.repaired_goal_score.notna()]
        if len(ix)==0:continue
        ref=x.loc[x.profile_name.eq(g.profile_name.iloc[0])];raw=model.predict(z.loc[ix,v.CORE],num_threads=4);goalpct=anchored_percentile(ref.enhanced_goal_score,z.loc[ix,'enhanced_goal_score']);rawpct=anchored_percentile(ref.champion_raw_model,raw);z.loc[ix,'champion_raw_model']=raw;z.loc[ix,'champion_score']=.67*goalpct+.33*rawpct
    z[v.FEATURES+['evidence_confidence']]=z[v.FEATURES+['evidence_confidence']].astype('float32');normalized=s.normalize(z)
    # Keep all preexisting feature percentiles and scores exactly. New rows use original reference CDFs.
    original=s.normalize(x)
    for _,g in z.groupby('profile_name'):
        ix=g.index[g.repaired_goal_score.notna()];ref=original.loc[original.profile_name.eq(g.profile_name.iloc[0])]
        for c in s.POS+s.NEG:
            values=anchored_percentile(ref[c],z.loc[ix,c]);normalized.loc[ix,'q_'+c]=np.where(z.loc[ix,c].isna(),.5,values if c in s.POS else 1-values).astype('float32')
    a,b=s.predict_models(normalized,V17/'model_current_monotone.txt',{look:V17/('model_current_partner_look'+str(look)+'.txt') for look in [12,36,60]});oa,ob=s.predict_models(original,V17/'model_current_monotone.txt',{look:V17/('model_current_partner_look'+str(look)+'.txt') for look in [12,36,60]})
    for _,g in z.groupby('profile_name'):
        ix=g.index[g.repaired_goal_score.notna()];ref=original.index[original.profile_name.eq(g.profile_name.iloc[0])];corr=(anchored_percentile(oa.loc[ref],a.loc[ix])+anchored_percentile(ob.loc[ref],b.loc[ix]))/2;eff=.3*z.loc[ix,'evidence_confidence'];z.loc[ix,'v17_score']=z.loc[ix,'champion_score']*(1-eff)+eff*corr
    assert (z.loc[z.original_v17_score.notna(),'v17_score']-z.loc[z.original_v17_score.notna(),'original_v17_score']).abs().max()==0
    z['repaired_rank']=v.ranked(z,'v17_score');csv('coverage_repaired_current.csv.gz',z);turn=[]
    for profile,g in z.groupby('profile_name'):
        old=set(g.loc[g.v17_rank.le(20),'isin']);new=set(g.loc[g.repaired_rank.le(20),'isin']);turn.append({'profile':profile,'before':int(g.original_v17_score.notna().sum()),'after':int(g.v17_score.notna().sum()),'top20_overlap':len(old&new)/20,'newly_ranked_top20':int((g.repaired_rank.le(20)&g.original_v17_score.isna()).sum())})
    csv('coverage_repair_effect.csv',pd.DataFrame(turn));write('coverage_repair_validation.json',{'recovered_rows':int((z.original_v17_score.isna()&z.v17_score.notna()).sum()),'original_scores_unchanged':True,'missing_goal_windows_imputed':False,'missing_window_uncertainty_shrinkage':True,'current_only_no_backfill':True});print('COVERAGE REPAIRED',flush=True)

def refreshed_replay():
    mod=isolated_v15();mod.ACTION=O/'actions/normalized_ledger.csv.gz';mod.SPLITS=O/'provider_splits';facts=pd.read_csv(v.V7,low_memory=False);book=mod.load_current_book(facts);parts=[];evidence=pd.DataFrame({'isin':facts['isin'],'global_existing_score':np.nan})
    for name,p in v.profiles().items():
        print('FRESH REPLAY',name,flush=True);row=mod.rank_executable(book,p,'2026-10-03',evidence);row['profile_name']=name;row['decision_date']='2026-10-03';offsets=sorted(set(np.linspace(0,p.lookback_months-p.horizon_months,4).astype(int)));short=[]
        for offset in offsets:short.append(book.simulate(p,pd.Timestamp('2026-10-03')-pd.DateOffset(months=int(offset)),months=p.horizon_months,mode='enhanced_carry',include_journal=False).set_index('isin').target_shortfall.rename(str(offset)))
        sf=pd.concat(short,axis=1).reindex(row['isin']);confidence=sf.notna().mean(axis=1).to_numpy();prior=float((-row.enhanced_goal_score).median());partial=row.status.eq('AVAILABLE')&row.enhanced_carry_xirr_score.notna()&row.enhanced_goal_score.isna()&(confidence>0);recovered=-(sf.pow(2).mean(axis=1).to_numpy()*confidence+prior*(1-confidence));row['goal_window_confidence']=confidence;row['partial_goal_recovery']=partial;row.loc[partial,'enhanced_goal_score']=recovered[partial];parts.append(row);book.cache.clear()
    rows=mod.current_features(pd.concat(parts,ignore_index=True),facts);metadata=facts[['isin','ticker','company','yahoo_history_end_date','latest_price','current_has_true_5y']];rows=rows.merge(metadata,on='isin',how='left',validate='many_to_one');csv('refreshed_current_features.csv.gz',rows);write('refreshed_replay_audit.json',{'rows':len(rows),'universe':rows['isin'].nunique(),'decision_date':'2026-10-03','action_checked_through':'2026-10-04','prices':'Frozen V7 observed closes through latest trading date; no future prices','partial_goal_recovered':int(rows.partial_goal_recovery.sum()),'available':int(rows.status.eq('AVAILABLE').sum()),'carry_present':int(rows.enhanced_carry_xirr_score.notna().sum()),'goal_present':int(rows.enhanced_goal_score.notna().sum()),'actions_sha256':v.sha(mod.ACTION),'split_ledger_sha256':v.sha(mod.SPLITS/'split_ledger.csv')});print('FRESH REPLAY COMPLETE',flush=True)

def score_refreshed():
    x=pd.read_csv(O/'refreshed_current_features.csv.gz',low_memory=False);ref=pd.read_csv(V17/'current_rankings.csv.gz',low_memory=False)
    for frame in [x,ref]:frame[v.FEATURES+['evidence_confidence']]=frame[v.FEATURES+['evidence_confidence']].astype('float32')
    ref=s.normalize(ref);x=s.normalize(x);m=lgb.Booster(model_file=str(v.FREEZE/'lambdarank.txt'));valid=x.enhanced_carry_xirr_score.notna()&x.enhanced_goal_score.notna();x['champion_raw_model']=np.nan;x.loc[valid,'champion_raw_model']=m.predict(x.loc[valid,v.CORE],num_threads=4);x['champion_score']=np.nan
    for profile,g in x.groupby('profile_name'):
        old=ref.loc[ref.profile_name.eq(profile)];ix=g.index[valid.loc[g.index]];x.loc[ix,'champion_score']=.67*anchored_percentile(old.enhanced_goal_score,x.loc[ix,'enhanced_goal_score'])+.33*anchored_percentile(old.champion_raw_model,x.loc[ix,'champion_raw_model'])
        for col in s.POS+s.NEG:
            values=anchored_percentile(old[col],x.loc[g.index,col]);n=old[col].notna().sum();x.loc[g.index,'q_'+col]=np.where(x.loc[g.index,col].isna(),.5,values if col in s.POS else np.minimum(1,1-values+1/n)).astype('float32')
    mono=V17/'model_current_monotone.txt';paths={look:V17/('model_current_partner_look'+str(look)+'.txt') for look in [12,36,60]};a,b=s.predict_models(x,mono,paths);ra,rb=s.predict_models(ref,mono,paths);x['v17_refreshed_score']=np.nan
    for profile,g in x.groupby('profile_name'):
        old=ref.index[ref.profile_name.eq(profile)];ix=g.index[valid.loc[g.index]];corr=(anchored_percentile(ra.loc[old],a.loc[ix])+anchored_percentile(rb.loc[old],b.loc[ix]))/2;x.loc[ix,'v17_refreshed_score']=v.guided(x.loc[ix],corr,.3)
    frozen=ref[v.KEYS+['v17_score','v17_rank','champion_score','status']].rename(columns={'v17_score':'original_v17_score','v17_rank':'original_v17_rank','champion_score':'original_champion_score','status':'original_status'});x=x.merge(frozen,on=v.KEYS,validate='one_to_one');x['v17_refreshed_rank']=v.ranked(x,'v17_refreshed_score');csv('refreshed_current_rankings.csv.gz',x);rows=[]
    for profile,g in x.groupby('profile_name'):
        old=set(g.loc[g.original_v17_rank.le(20),'isin']);new=set(g.loc[g.v17_refreshed_rank.le(20),'isin']);rows.append({'profile':profile,'old_scored':int(g.original_v17_score.notna().sum()),'new_scored':int(g.v17_refreshed_score.notna().sum()),'recovered':int((g.original_v17_score.isna()&g.v17_refreshed_score.notna()).sum()),'newly_quarantined':int((g.original_v17_score.notna()&g.v17_refreshed_score.isna()).sum()),'top20_overlap':len(old&new)/20,'mean_rank_move':(g.original_v17_rank-g.v17_refreshed_rank).abs().mean()})
    csv('refreshed_coverage_stability.csv',pd.DataFrame(rows));csv('newly_quarantined.csv',x.loc[x.original_v17_score.notna()&x.v17_refreshed_score.isna()]);print(pd.DataFrame(rows).to_string(index=False),flush=True)

def bag_robustness():
    trials=pd.concat([pd.read_csv(O/'bag_trials.csv'),pd.read_csv(O/'extended_bag_trials.csv')],ignore_index=True);candidates=trials.loc[trials.eligible].sort_values('utility',ascending=False);x,dev=r.data();base=v.evaluate(dev,'champion_score');results={};audit=[];winner=None
    for _,row in candidates.iterrows():
        choice=row.to_dict();results[choice['name']]={};passed=True
        for variant,seed in [('seed20261004',20261004),('per_date',20261003)]:
            z=dev.copy();z['v17_score'],a,b=r.v17_variant(z,variant);blocks=sorted(z.decision_date.unique()) if variant=='per_date' else ['2020','2021','2022','2023'];cache=O/('robust_'+variant+'_regime_utility.csv.gz')
            if cache.exists():raw=z[v.KEYS].merge(pd.read_csv(cache),on=v.KEYS).prediction
            else:
                raw=pd.Series(np.nan,index=z.index)
                for block in blocks:
                    test=z.loc[z.decision_date.eq(block) if variant=='per_date' else z.decision_date.str.startswith(block)];train=x.loc[x.endpoint.lt(test.decision_date.min())];p,au=own_train(train,test,'regime_utility','robust_'+variant+'_regime_utility_'+block,seed);raw.loc[test.index]=p;audit.append(au);print('BAG ROBUST REGIME',block,flush=True)
                csv(cache.name,z[v.KEYS].assign(prediction=raw))
            sig={'regime_utility':r.pct(z,raw)};pp=z[v.KEYS].merge(pd.read_csv(O/'bag60_predictions.csv.gz'),on=v.KEYS,how='left')
            if variant=='per_date':
                cache=O/'per_date_bag60_predictions.csv.gz'
                if cache.exists():pp=z[v.KEYS].merge(pd.read_csv(cache),on=v.KEYS,how='left')
                else:
                    pp=z[v.KEYS].copy()
                    for member in range(20261003,20261010):
                        pp['seed'+str(member)]=np.nan
                        for block in blocks:
                            test=z.loc[z.decision_date.eq(block)&z.lookback_months.eq(60)];train=x.loc[x.endpoint.lt(block)];pred,au=fit_stable60(train,test,'bag_per_date_'+str(member)+'_'+block,member,original=True);pp.loc[test.index,'seed'+str(member)]=pred.raw100;audit.append(au)
                        print('BAG PER DATE',member,flush=True);write('bag_robustness_training_audit.json',audit)
                    csv(cache.name,pp)
            # Omit the original seed during the alternate-seed check to avoid relying on it.
            cols=[c for c in pp if c.startswith('seed') and (variant!='seed20261004' or c!='seed20261003')];pr=pd.DataFrame({c:r.pct(z,pp[c]) for c in cols});corr=(r.pct(z,a)+getattr(pr,choice['aggregation'])(axis=1))/2;pred=prediction(z,sig,choice);long=z.lookback_months.eq(60);pred.loc[long]=(z.v17_score*(1-choice['share'])+v.guided(z,corr,choice['long_alpha'])*choice['share']).loc[long];st,ch,ag=r.assess(z,pred,base,v.evaluate(z,'v17_score'));p=ch.groupby('profile')[[c+'_delta' for c in v.METRICS]].mean();vol=z.realized_volatility_1y.ge(z.groupby(['decision_date','profile_name']).realized_volatility_1y.transform('quantile',.75));hv=v.compare_metrics(v.evaluate(z.loc[vol].assign(repair_score=pred.loc[vol]),'repair_score'),v.evaluate(z.loc[vol],'v17_score'));checks={'aggregate_return':st['v17_delta']['median_xirr_top20']>=0,'aggregate_drawdown':st['v17_delta']['mean_asset_drawdown_top20']>=0,'long_return_vs_champion':p.loc['lookback60','median_xirr_top20_delta']>=0,'highvol_drawdown':hv.mean_asset_drawdown_top20_delta.mean()>=0,'original_gates':st['champion']['eligible']};results[choice['name']][variant]={'checks':checks,'stats':st,'long_return':p.loc['lookback60','median_xirr_top20_delta'],'highvol_drawdown':hv.mean_asset_drawdown_top20_delta.mean()};write('bag_robustness.json',results);csv('bag_robust_'+variant+'_metrics.csv',ag);csv('bag_robust_'+variant+'_scores.csv.gz',z[v.KEYS].assign(repair_score=pred));print('BAG ROBUST RESULT',variant,checks,flush=True)
            if not all(checks.values()):passed=False;break
        if passed:winner=choice;break
    write('refinement_selection_lock.json',{'locked_at':now(),'choice':winner,'accepted_model_repair':winner is not None,'repair_trials':57+49+12+12,'current_stability_veto_pending':winner is not None,'fallback':'Original V17 scores with validated coverage and action repairs.','no_exposed_selection':True},True);print('REFINEMENT LOCK',winner,flush=True)

def assembled_score(test,choice,regime,mono,members,reference=None):
    def transform(raw,refraw=None):
        if reference is None:return r.pct(test,raw)
        out=pd.Series(np.nan,index=test.index)
        for profile,g in test.groupby('profile_name'):
            ids=g.index[g.champion_score.notna()];refids=reference.index[reference.profile_name.eq(profile)];out.loc[ids]=anchored_percentile(refraw.loc[refids],raw.loc[ids])
        return out
    # Current anchoring is supplied as (new_prediction, original_universe_prediction).
    if reference is None:rp=transform(regime);mp=transform(mono);bp=pd.DataFrame({str(k):transform(p) for k,p in members.items()})
    else:rp=transform(*regime);mp=transform(*mono);bp=pd.DataFrame({str(k):transform(*p) for k,p in members.items()})
    pred=test.v17_score.copy();mask=test.lookback_months.eq(36);effective=choice['beta']*test.evidence_confidence;pred.loc[mask]=(test.v17_score*(1-effective)+rp*effective).loc[mask];mask=test.lookback_months.eq(60);corr=(mp+getattr(bp,choice['aggregation'])(axis=1))/2;pred.loc[mask]=(test.v17_score*(1-choice['share'])+v.guided(test,corr,choice['long_alpha'])*choice['share']).loc[mask];return pred
def development_repair_scores(choice):
    x,dev=r.data()
    if choice is None:return x,dev.assign(repair_score=dev.v17_score)
    rawreg=dev[v.KEYS].merge(pd.read_csv(r.O/'predictions_regime_utility.csv.gz'),on=v.KEYS).prediction;rawmono=dev[v.KEYS].merge(pd.read_csv(V17/'round1_predictions_monotone_utility.csv.gz'),on=v.KEYS).prediction;pp=dev[v.KEYS].merge(pd.read_csv(O/'bag60_predictions.csv.gz'),on=v.KEYS,how='left');dev['repair_score']=assembled_score(dev,choice,rawreg,rawmono,{k:pp[k] for k in pp if k.startswith('seed')});return x,dev
def postlock_predict(train,test,choice,tag,mono_path):
    if choice is None:return test.v17_score.copy(),[]
    cache=O/(tag+'_predictions.csv.gz');audit=[]
    if cache.exists():p=test[v.KEYS].merge(pd.read_csv(cache),on=v.KEYS,validate='one_to_one');return p.repair_score.set_axis(test.index),audit
    regime,au=own_train(train,test,'regime_utility',tag+'_regime',20261003);audit.append(au);m=lgb.Booster(model_file=str(mono_path));mono=pd.Series(np.nan,index=test.index);valid=test.champion_score.notna();mono.loc[valid]=m.predict(test.loc[valid,m.feature_name()],num_threads=4);members={}
    for seed in range(20261003,20261010):p,au=fit_stable60(train,test,tag+'_bag60_'+str(seed),seed,original=True);members[seed]=p.raw100;audit.append(au)
    pred=assembled_score(test,choice,regime,mono,members);csv(cache.name,test[v.KEYS].assign(repair_score=pred));return pred,audit
def current_repair():
    lock=json.loads((O/'refinement_selection_lock.json').read_text());choice=lock['choice'];x=pd.read_csv(O/'refreshed_current_rankings.csv.gz',low_memory=False);x['v17_score']=x.v17_refreshed_score;x[v.FEATURES+['evidence_confidence']+s.NORM]=x[v.FEATURES+['evidence_confidence']+s.NORM].astype('float32');reference=pd.read_csv(V17/'current_rankings.csv.gz',low_memory=False);reference[v.FEATURES+['evidence_confidence']]=reference[v.FEATURES+['evidence_confidence']].astype('float32');reference=r.features(reference)
    for out,c in zip(r.REGIME,['strict_cagr_1y','realized_volatility_1y','distance_from_recorded_high','momentum_6m']):x[out]=x.groupby('decision_date')[c].transform('median').fillna(0).astype('float32')
    audit=[]
    if choice:
        train=r.features(v.load_historical(True));train=train.loc[train.endpoint.lt('2026-10-03')];reg,au=own_train(train,x,'regime_utility','refined_current_regime',20261003);audit.append(au)
        def modelpredict(path,frame,look=None):
            m=lgb.Booster(model_file=str(path));p=pd.Series(np.nan,index=frame.index);mask=frame.champion_score.notna()
            if look:mask&=frame.lookback_months.eq(look)
            p.loc[mask]=m.predict(frame.loc[mask,m.feature_name()],num_threads=4);return p
        regime=(reg,modelpredict(O/'model_refined_current_regime.txt',reference));mono=(modelpredict(V17/'model_current_monotone.txt',x),modelpredict(V17/'model_current_monotone.txt',reference));members={}
        for seed in range(20261003,20261010):p,au=fit_stable60(train,x,'refined_current_bag60_'+str(seed),seed,original=True);members[seed]=(p.raw100,modelpredict(O/('model_refined_current_bag60_'+str(seed)+'.txt'),reference,60));audit.append(au)
        x['proposed_repair_score']=assembled_score(x,choice,regime,mono,members,reference);del train;gc.collect()
    else:x['proposed_repair_score']=x.v17_score
    x['proposed_repair_rank']=v.ranked(x,'proposed_repair_score');rows=[]
    for profile,g in x.groupby('profile_name'):
        original=set(g.loc[g.v17_refreshed_rank.le(20),'isin']);candidate=set(g.loc[g.proposed_repair_rank.le(20),'isin']);rows.append({'profile':profile,'top20_overlap':len(original&candidate)/20,'mean_absolute_rank_change':(g.v17_refreshed_rank-g.proposed_repair_rank).abs().mean()})
    stability=pd.DataFrame(rows);accepted=bool(choice is not None and stability.top20_overlap.min()>=.85);x['winner_score']=x.proposed_repair_score if accepted else x.v17_score;x['winner_rank']=v.ranked(x,'winner_score');csv('final_current_rankings.csv.gz',x);csv('model_only_current_stability.csv',stability);write('refined_current_training_audit.json',audit);write('refinement_final_lock.json',{'locked_at':now(),'choice':choice if accepted else None,'accepted_model_repair':accepted,'stability_pass':bool(stability.top20_overlap.min()>=.85),'data_repairs_accepted':True,'name':'V17 refined ensemble' if accepted else 'V17 with coverage and corporate-action repairs','newV18_earned':False,'current_stability_veto_only':True},True)
    for n in [20,50,100]:csv('current_top'+str(n)+'.csv',x.loc[x.winner_rank.le(n)].sort_values(['profile_name','winner_rank']))
    csv('nykaa_diagnostic.csv',x.loc[x['isin'].eq('INE388Y01029')]);print('CURRENT ACCEPTED',accepted,stability.to_string(index=False),flush=True)
def historical_final():
    lock=json.loads((O/'refinement_final_lock.json').read_text());choice=lock['choice'];x,dev=development_repair_scores(choice);csv('development_refined_scores.csv.gz',dev[v.KEYS+v.OUTCOME+['champion_score','v17_score','repair_score']]);outputs=[];audit=[]
    early=x.merge(pd.read_csv(r.O/'early_scores.csv.gz'),on=v.KEYS,validate='one_to_one')
    for day,g in early.groupby('decision_date'):
        g=g.copy();g['repair_score'],au=postlock_predict(x.loc[x.endpoint.lt(day)],g,choice,'early_refined_'+day,r.O/('model_early_'+day+'_mono.txt'));audit.extend(au);outputs.append(g[v.KEYS+v.OUTCOME+['champion_score','v17_score','repair_score']]);print('FINAL EARLY',day,flush=True);write('historical_final_training_audit.json',audit)
    csv('early_refined_scores.csv.gz',pd.concat(outputs,ignore_index=True));del early,x,dev;gc.collect();x=r.features(v.load_historical(True));outputs=[]
    for year in ['2024','2025']:
        g=x.loc[x.decision_date.str.startswith(year)].merge(pd.read_csv(V17/('exposed_'+year+'_scores.csv.gz'),usecols=v.KEYS+['champion_score','v17_score']),on=v.KEYS,validate='one_to_one');g['repair_score'],au=postlock_predict(x.loc[x.endpoint.lt(g.decision_date.min())],g,choice,'exposed_refined_'+year,V17/('model_exposed_'+year+'_monotone.txt'));audit.extend(au);outputs.append(g[v.KEYS+v.OUTCOME+['champion_score','v17_score','repair_score']]);write('historical_final_training_audit.json',audit)
    csv('exposed_refined_scores.csv.gz',pd.concat(outputs,ignore_index=True));print('HISTORICAL FINAL COMPLETE',flush=True)

def challenger_search():
    lock=json.loads((O/'refinement_final_lock.json').read_text());choice=lock['choice'];candidates=[{'family':f,'beta':b,'gate':g,'name':f+'_'+str(b)+'_'+g} for f in ['neural_moe','huber_return','return_ranker','xendcg','specialist_utility'] for b in [.025,.05] for g in ['broad','volatility']];write('challenger_protocol.json',{'locked_at':now(),'benchmark':lock['name'],'candidates':candidates,'architecture':'Incremental confidence-weighted expert blend for36M only; retained12M and repaired60M exact. Reuse honestly purged family training from first tournament, no exposed retraining for selection.','clean_win':'Original strict champion gates; medianXIRR,NDCG,drawdown and achievement nonnegative vs refinedV17; shortfall nonpositive; every profile medianreturn>=-0.005 and drawdown>=-0.005; highvolreturn/drawdown nonnegative; utility>=.002 and3of4yearspositive. Alternate seed/perdate checks same aggregate directions; currentTop20 overlap>=.85.','mean_xirr_weight':0,'stop':'20 complementary residual configurations then stop; no exposed-driven changes.','conditional':'Only candidates passing all checks may be calledV18.'},True);x,dev=development_repair_scores(choice);del x;gc.collect();dev['original_v17_score']=dev.v17_score;dev['v17_score']=dev.repair_score;base=v.evaluate(dev,'champion_score');ref=v.evaluate(dev,'v17_score');volpct=dev.groupby(['decision_date','profile_name']).realized_volatility_1y.rank(pct=True).fillna(.5);vol=volpct.ge(.75);hvref=v.evaluate(dev.loc[vol],'v17_score');rows=[];details={};sig={};metrics=[]
    for candidate in candidates:
        family=candidate['family']
        if family not in sig:sig[family]=r.pct(dev,dev[v.KEYS].merge(pd.read_csv(r.O/('predictions_'+family+'.csv.gz')),on=v.KEYS).prediction)
        gate=((volpct-.5)*2).clip(0,1) if candidate['gate']=='volatility' else 1.;weight=candidate['beta']*dev.evidence_confidence*gate;pred=dev.v17_score.copy();mask=dev.lookback_months.eq(36);pred.loc[mask]=(dev.v17_score*(1-weight)+sig[family]*weight).loc[mask];st,ch,ag=r.assess(dev,pred,base,ref);d=st['v17_delta'];p=ag.groupby('profile')[[c+'_delta' for c in v.METRICS]].mean();hv=v.compare_metrics(v.evaluate(dev.loc[vol].assign(challenger=pred.loc[vol]),'challenger'),hvref);checks={'strict_champion':st['champion']['strong_eligible'],'return':d['median_xirr_top20']>=0,'ndcg':d['ndcg20']>=0,'drawdown':d['mean_asset_drawdown_top20']>=0,'achievement':d['target_achievement_top20']>=0,'shortfall':d['target_shortfall_top20']<=0,'profile_return':p.median_xirr_top20_delta.min()>=-.005,'profile_drawdown':p.mean_asset_drawdown_top20_delta.min()>=-.005,'highvol_return':hv.median_xirr_top20_delta.mean()>=0,'highvol_drawdown':hv.mean_asset_drawdown_top20_delta.mean()>=0,'utility':st['utility_gain']>=.002,'three_years':st['checks']['three_years']};passed=all(checks.values());rows.append({**candidate,'eligible':passed,'utility':st['utility_gain'],**d});details[candidate['name']]={'checks':checks,'stats':st};metrics.append(ag.assign(candidate=candidate['name']));print('NEW CHALLENGER',candidate['name'],passed,round(st['utility_gain'],6),[k for k,val in checks.items() if not val],flush=True);csv('challenger_trials.csv',pd.DataFrame(rows).sort_values(['eligible','utility'],ascending=False));write('challenger_details.json',details);csv('challenger_profile_date.csv',pd.concat(metrics,ignore_index=True))
    write('challenger_development_lock.json',{'locked_at':now(),'candidates':pd.DataFrame(rows).loc[lambda q:q.eligible].sort_values('utility',ascending=False).to_dict('records'),'count':len(rows),'none_passed':not any(row['eligible'] for row in rows)},True);print('CHALLENGER SEARCH COMPLETE',flush=True)
def evaluate_refinement():
    import types
    out=O/'evaluation';out.mkdir(exist_ok=True)
    for source,dest in [('development_refined_scores.csv.gz','development_scores.csv.gz'),('early_refined_scores.csv.gz','early_all_scores.csv.gz'),('exposed_refined_scores.csv.gz','exposed_scores.csv.gz')]:pd.read_csv(O/source).rename(columns={'repair_score':'new_score'}).to_csv(out/dest,index=False,compression={'method':'gzip','mtime':0})
    (out/'selection_lock.json').write_text((O/'refinement_final_lock.json').read_text());(out/'early_unavailable.json').write_text((r.O/'early_unavailable.json').read_text());namespace=dict(r.__dict__);namespace['O']=out;namespace['csv']=lambda name,frame:frame.to_csv(out/name,index=False,compression={'method':'gzip','mtime':0} if name.endswith('.gz') else None)
    def writeout(name,obj,exclusive=False):
        with (out/name).open('x' if exclusive else 'w',encoding='utf-8') as f:json.dump(v.clean(obj),f,indent=2,allow_nan=False)
    namespace['write']=writeout;types.FunctionType(r.evaluation.__code__,namespace)()

def current_loaded_predict(x,reference,choice):
    def pp(path,z,look=None):
        m=lgb.Booster(model_file=str(path));p=pd.Series(np.nan,index=z.index);mask=z.champion_score.notna()
        if look:mask&=z.lookback_months.eq(look)
        p.loc[mask]=m.predict(z.loc[mask,m.feature_name()],num_threads=4);return p
    def anchor(a,b):
        out=pd.Series(np.nan,index=x.index)
        for profile,g in x.groupby('profile_name'):
            ids=g.index[g.champion_score.notna()];old=reference.index[reference.profile_name.eq(profile)];out.loc[ids]=anchored_percentile(b.loc[old],a.loc[ids])
        return out
    a=pp(V17/'model_current_monotone.txt',x);ar=pp(V17/'model_current_monotone.txt',reference);b=pd.Series(np.nan,index=x.index);br=pd.Series(np.nan,index=reference.index)
    for look in [12,36,60]:
        path=V17/('model_current_partner_look'+str(look)+'.txt');q=pp(path,x,look);qr=pp(path,reference,look);b.loc[q.notna()]=q.loc[q.notna()];br.loc[qr.notna()]=qr.loc[qr.notna()]
    z=x.copy();z['v17_score']=v.guided(x,(anchor(a,ar)+anchor(b,br))/2,.3)
    if choice is None:return z.v17_score
    path=O/'model_refined_current_regime.txt';reg=(pp(path,x),pp(path,reference));members={}
    for seed in range(20261003,20261010):path=O/('model_refined_current_bag60_'+str(seed)+'.txt');members[seed]=(pp(path,x,60),pp(path,reference,60))
    return assembled_score(z,choice,reg,(a,ar),members,reference)
def final_diagnostics():
    choice=json.loads((O/'refinement_final_lock.json').read_text())['choice'];x=pd.read_csv(O/'final_current_rankings.csv.gz',low_memory=False);reference=pd.read_csv(V17/'current_rankings.csv.gz',low_memory=False)
    for frame in [x,reference]:frame[v.FEATURES+['evidence_confidence']+s.NORM]=frame[v.FEATURES+['evidence_confidence']+s.NORM].astype('float32')
    reference=r.features(reference)
    for out,c in zip(r.REGIME,['strict_cagr_1y','realized_volatility_1y','distance_from_recorded_high','momentum_6m']):x[out]=x.groupby('decision_date')[c].transform('median').fillna(0).astype('float32')
    reproduced=current_loaded_predict(x,reference,choice);error=float((reproduced-x.winner_score).abs().max());assert error<1e-9,error
    def anchored_features(z,columns):
        for profile,g in z.groupby('profile_name'):
            old=reference.loc[reference.profile_name.eq(profile)]
            for col in columns:
                if col in s.POS+s.NEG:
                    vals=anchored_percentile(old[col],z.loc[g.index,col]);z.loc[g.index,'q_'+col]=np.where(z.loc[g.index,col].isna(),.5,vals if col in s.POS else np.minimum(1,1-vals+1/old[col].notna().sum())).astype('float32')
        return z
    scenarios={};ath=[]
    for name,days,depth in [('recent_near',30,-.05),('old_near',1825,-.05),('old_deep',1825,-.7)]:
        z=x.copy();z['days_since_recorded_high']=days;z['current_drawdown_duration_days']=days;z['distance_from_recorded_high']=depth;z['old_high_depth']=np.log1p(days/365)*(-depth);z['underwater_depth']=z.old_high_depth;z['recovery_vs_old_high']=z.recovery_from_worst_trough.clip(-1,10)*(-depth);z=anchored_features(z,['distance_from_recorded_high','old_high_depth','underwater_depth']);scenarios[name]=current_loaded_predict(z,reference,choice)
    for profile,g in x.groupby('profile_name'):
        for name in ['old_near','old_deep']:
            d=(scenarios[name]-scenarios['recent_near']).loc[g.index].dropna();ath.append({'profile':profile,'scenario':name,'mean_score_change':d.mean(),'negative_fraction':d.lt(-1e-8).mean(),'positive_fraction':d.gt(1e-8).mean()})
    csv('final_ath_behavior.csv',pd.DataFrame(ath));effects=[]
    for family,cols in v.FAMILIES.items():
        if family=='history':continue
        z=x.copy()
        for c in cols:
            if c in z:z[c]=z.groupby('profile_name')[c].transform('median')
        z=anchored_features(z,cols);alt=current_loaded_predict(z,reference,choice);rank=v.ranked(z.assign(alternative=alt),'alternative')
        for profile,g in x.groupby('profile_name'):
            before=set(g.loc[g.winner_rank.le(20),'isin']);after=set(g.loc[rank.loc[g.index].le(20),'isin']);effects.append({'profile':profile,'family':family,'top20_replacements':20-len(before&after),'mean_absolute_score_change':(alt.loc[g.index]-g.winner_score).abs().mean(),'mean_absolute_rank_change':(rank.loc[g.index]-g.winner_rank).abs().mean()})
        print('FINAL SENSITIVITY',family,flush=True)
    csv('final_family_sensitivity.csv',pd.DataFrame(effects));composition=[];personal=[];extreme=[]
    for profile,g in x.groupby('profile_name'):
        top=g.loc[g.winner_rank.le(20)];composition.append({'profile':profile,'missing_true_5y_top20':top.has_true_5y.eq(False).mean(),'median_1y_growth':top.strict_cagr_1y.median(),'median_3y_growth':top.cagr_3y.median(),'median_ath_days':top.days_since_recorded_high.median(),'median_ath_depth':top.distance_from_recorded_high.median(),'median_underwater_days':top.current_drawdown_duration_days.median(),'mean_asset_historical_drawdown':top.full_history_max_drawdown.mean(),'median_volatility':top.realized_volatility_1y.median(),'median_confidence':top.evidence_confidence.median()});base=x.loc[x.profile_name.eq('base7500')];a=base[['isin','winner_rank']].merge(g[['isin','winner_rank']],on='isin',suffixes=('_base','_profile'));personal.append({'profile':profile,'top20_overlap_with_base':len(set(base.loc[base.winner_rank.le(20),'isin'])&set(top['isin']))/20,'mean_rank_change':(a.winner_rank_base-a.winner_rank_profile).abs().mean()});mask=(g.strict_cagr_1y.ge(1)|g.cagr_3y.ge(1))&(g.days_since_recorded_high.ge(1095)|g.distance_from_recorded_high.le(-.5));extreme.append(g.loc[mask].sort_values('winner_rank').head(30))
    csv('final_composition.csv',pd.DataFrame(composition));csv('final_personalization.csv',pd.DataFrame(personal));csv('extreme_growth_ath_cases.csv',pd.concat(extreme));z=x.copy();z['isin']='ANONYMOUS';z['history_months']=0;z['has_true_5y']=False;identity_error=float((current_loaded_predict(z,reference,choice)-reproduced).abs().max());assert identity_error<1e-9;write('final_validation.json',{'reproduction_max_error':error,'identity_and_age_label_only_max_error':identity_error,'all4436':x['isin'].nunique()==4436,'all9profiles':x.profile_name.nunique()==9,'unique_keys':not x.duplicated(v.KEYS).any(),'scored_rows':int(x.winner_score.notna().sum()),'available_unranked':int((x.status.eq('AVAILABLE')&x.winner_score.isna()).sum()),'no_hard_ath_age_penalty':True,'counterfactuals':'Original reference empirical-CDF anchors; champion/confidence/regime held fixed. Conditional sensitivity, not causal or necessarily realizable.'});print('FINAL DIAGNOSTICS COMPLETE',flush=True)

def challenger_robustness():
    candidates=json.loads((O/'challenger_development_lock.json').read_text())['candidates'];x,dev=r.data();base=v.evaluate(dev,'champion_score');results={};audit=[];winner=None
    for choice in candidates:
        passed=True;results[choice['name']]={}
        for variant,seed in [('seed20261004',20261004),('per_date',20261003)]:
            z=dev.copy();z['v17_score']=z[v.KEYS].merge(pd.read_csv(O/('bag_robust_'+variant+'_scores.csv.gz')),on=v.KEYS).repair_score;raw=pd.Series(np.nan,index=z.index);blocks=sorted(z.decision_date.unique()) if variant=='per_date' else ['2020','2021','2022','2023'];family=choice['family'];cache=O/('challenger_'+variant+'_'+family+'.csv.gz')
            if cache.exists():raw=z[v.KEYS].merge(pd.read_csv(cache),on=v.KEYS).prediction
            else:
                for block in blocks:
                    test=z.loc[z.decision_date.eq(block) if variant=='per_date' else z.decision_date.str.startswith(block)];train=x.loc[x.endpoint.lt(test.decision_date.min())];p,au=own_train(train,test,family,'challenger_'+variant+'_'+family+'_'+block,seed);raw.loc[test.index]=p;audit.append(au);print('CHALLENGER ROBUST TRAIN',variant,block,flush=True);write('challenger_robustness_training_audit.json',audit)
                csv(cache.name,z[v.KEYS].assign(prediction=raw))
            volpct=z.groupby(['decision_date','profile_name']).realized_volatility_1y.rank(pct=True).fillna(.5);gate=((volpct-.5)*2).clip(0,1) if choice['gate']=='volatility' else 1.;weight=choice['beta']*z.evidence_confidence*gate;pred=z.v17_score.copy();mask=z.lookback_months.eq(36);pred.loc[mask]=(z.v17_score*(1-weight)+r.pct(z,raw)*weight).loc[mask];st,ch,ag=r.assess(z,pred,base,v.evaluate(z,'v17_score'));d=st['v17_delta'];p=ag.groupby('profile')[[c+'_delta' for c in v.METRICS]].mean();vol=volpct.ge(.75);hv=v.compare_metrics(v.evaluate(z.loc[vol].assign(challenger=pred.loc[vol]),'challenger'),v.evaluate(z.loc[vol],'v17_score'));checks={'original_champion':st['champion']['eligible'],'return':d['median_xirr_top20']>=0,'ndcg':d['ndcg20']>=0,'drawdown':d['mean_asset_drawdown_top20']>=0,'achievement':d['target_achievement_top20']>=0,'shortfall':d['target_shortfall_top20']<=0,'profile_return':p.median_xirr_top20_delta.min()>=-.005,'profile_drawdown':p.mean_asset_drawdown_top20_delta.min()>=-.005,'highvol_return':hv.median_xirr_top20_delta.mean()>=0,'highvol_drawdown':hv.mean_asset_drawdown_top20_delta.mean()>=0};results[choice['name']][variant]={'checks':checks,'stats':st,'highvol_return':hv.median_xirr_top20_delta.mean(),'highvol_drawdown':hv.mean_asset_drawdown_top20_delta.mean()};write('challenger_robustness.json',results);csv('challenger_'+variant+'_metrics.csv',ag);print('CHALLENGER ROBUST RESULT',variant,checks,flush=True)
            if not all(checks.values()):passed=False;break
        if passed:winner=choice;break
    write('challenger_selection_lock.json',{'locked_at':now(),'choice':winner,'newV18_earned_pending_current_stability':winner is not None,'tested_development':20,'robustness':results,'fallback':'V17 refined ensemble'},True)

def delivery_report():
    challenger=json.loads((O/'challenger_selection_lock.json').read_text());assert challenger['choice'] is None,'Complete accepted challenger inference before delivery';lock=json.loads((O/'refinement_final_lock.json').read_text());choice=lock['choice'];metrics=pd.read_csv(O/'evaluation/aggregate_metrics.csv').replace({'model':{'new':'V17 refined','v17':'V17','champion':'d499580'}});coh=pd.read_csv(O/'evaluation/all_cohorts.csv').replace({'model':{'new':'V17 refined','v17':'V17','champion':'d499580'}});delta=pd.read_csv(O/'evaluation/all_comparison_deltas.csv');profiles=delta.groupby(['period','model','reference','profile'])[[c+'_delta' for c in v.METRICS]].mean().reset_index();csv('final_profile_deltas.csv',profiles);csv('final_comparison.csv',metrics);current=pd.read_csv(O/'final_current_rankings.csv.gz',low_memory=False);ny=pd.read_csv(O/'nykaa_diagnostic.csv');validation=json.loads((O/'final_validation.json').read_text());dates=json.loads((O/'evaluation/date_coverage.json').read_text());stability=pd.read_csv(O/'model_only_current_stability.csv');coverage=pd.read_csv(O/'refreshed_coverage_stability.csv');robust=json.loads((O/'bag_robustness.json').read_text());actions=json.loads((O/'actions/summary.json').read_text());trials=pd.concat([pd.read_csv(O/n).assign(round=n) for n in ['repair_trials.csv','stable_trials.csv','bag_trials.csv','extended_bag_trials.csv','challenger_trials.csv']],ignore_index=True);csv('research_ledger.csv',trials);peers=pd.read_csv(V17/'current_peer_diagnostics.csv');csv('current_peer_diagnostics.csv',peers);csv('nykaa_peer_context.csv',peers.loc[peers['isin'].eq('INE388Y01029')]);csv('current_top100_peer_context.csv',current.loc[current.winner_rank.le(100),['isin','profile_name','winner_rank']].merge(peers,on='isin',validate='many_to_one'))
    intervals=[];rng=np.random.default_rng(20261004)
    for keys,g in delta.groupby(['period','model','reference','profile']):
        annual=g.assign(year=g.decision_date.str[:4]).groupby('year')[[c+'_delta' for c in v.METRICS]].mean();arr=annual.to_numpy();boot=arr[rng.integers(0,len(arr),(2000,len(arr)))].mean(axis=1)
        for j,c in enumerate(v.METRICS):intervals.append(dict(zip(['period','model','reference','profile'],keys),metric=c,delta=g[c+'_delta'].mean(),p025=np.quantile(boot[:,j],.025),p975=np.quantile(boot[:,j],.975),calendar_blocks=len(arr)))
    csv('year_block_intervals.csv',pd.DataFrame(intervals));dep=profiles.loc[profiles.period.eq('development_2020_2023')&profiles.model.eq('new')&profiles.reference.eq('v17')];weak=coh.loc[coh.profile.eq('ALL')&coh.cohort.eq('high_volatility'),['period','model','median_xirr_top20','mean_asset_drawdown_top20']];summary={'completed_at':now(),'winner':'V17 refined ensemble','verdict':'PROMISING CHALLENGER','V18_earned':False,'production_champion':'d4995807163bef1ec4b297179e6c54a59c71f390','production_deployed':False,'refinement':choice,'development_vs_v17':{c:dep[c+'_delta'].mean() for c in v.METRICS},'repair_trials':130,'final_challenger_trials':20,'prior_v18_research_trials':34,'dates':dates,'current_validation':validation,'actions':{k:value for k,value in actions.items() if k!='raw_hashes'},'current_coverage_before':29295,'current_coverage_after':int(current.winner_score.notna().sum()),'coverage_only_top20_unchanged':True,'model_top20_min_overlap':stability.top20_overlap.min(),'worst_weakness':'High-volatility drawdown improves versus V17 but remains worse than d499580 in development; no untouched validation and fixed-universe survivorship remain.','fundamentals_industry':'Current diagnostic context only; no safe dated historical data available.','mean_xirr_selection_weight':0};write('decision_summary.json',summary)
    modelpaths=[V17/'model_current_monotone.txt']+[V17/('model_current_partner_look'+str(look)+'.txt') for look in [12,36,60]]+[O/'model_refined_current_regime.txt']+[O/('model_refined_current_bag60_'+str(seed)+'.txt') for seed in range(20261003,20261010)]
    write('model_definition.json',{'name':'V17 refined ensemble','research_only':True,'production_champion_unchanged':True,'choice':choice,'12M':'Exact V17 scoring architecture; data repairs may expand eligibility.','36M':'Original V17*(1-0.10*evidence_confidence) + regime utility prediction percentile*(0.10*evidence_confidence).','60M':'Champion*(1-0.35*evidence_confidence) +0.35*evidence_confidence*(monotone utility percentile+mean of seven ATH specialist prediction percentiles)/2.','normalization':'Historical within-date/profile ranks. Current new stocks and updated evidence use original V17 empirical CDF anchors to avoid renormalization churn. Missing normalized inputs0.5; no prescribed history-age deduction.','current_goal_recovery':'Only current executable AVAILABLE rows with at least one observed goal window; mean observed squared shortfall shrunk toward contemporaneous complete-window median by observed/expected windows. Missing window outcomes are not fabricated.','current_scoring_entrypoint':'current_loaded_predict; final_current_rankings includes precomputed corrected champion and anchored features.','historical_coverage_repair':'Not retroactively applied to the historical panel; all historical model comparisons use identical frozen eligibility.','features':{'raw':s.RAW,'normalized':s.NORM,'regime':r.REGIME},'current_model_hashes':{str(p.relative_to(ROOT)):v.sha(p) for p in modelpaths},'reference_current_scores_sha256':v.sha(V17/'current_rankings.csv.gz'),'current_prices_v7_sha256':v.sha(v.V7),'excluded':'Identity, future outcomes, present-day fundamentals and industry labels never model predictors.'})
    repairs=[{'issue':'Available but unranked','result':'161/161 recovered;0 AVAILABLE rows unranked; original scored values and coverage-onlyTop20 preserved.'},{'issue':'Corporate-action freshness','result':'Public NSE catalogue and1861/1861 BSE receipts through2026-10-04;7 new actions;5 automatic and2 blocked pending mechanics.4346/4436 exact-symbol provider split receipts. Source coverage is verified, not a guarantee of unreported-event completeness.'},{'issue':'60M instability','result':'Seven-seed ATH-constrained ensemble with confidence-weighted35% correction; leave-one-seed-out, alternate-seed and per-date returns abovechampion.'},{'issue':'High-volatility drawdown','result':'Development improves0.377percentage points versusV17; remains weaker thand499580. Per-date and alternate-seed direction survives.'},{'issue':'Extreme ATH/growth','result':'Retained growth signal and conditional ATH logic; all profiles have negative average old/deep-high sensitivity, with a small12M exception fraction; no company-specific or hard age penalty.'}]
    display=['period','model','median_xirr_top20','target_achievement_top20','target_shortfall_top20','mean_asset_drawdown_top20','ndcg20'];base=current.loc[current.profile_name.eq('base7500')&current.winner_rank.le(20),['winner_rank','ticker','company']].sort_values('winner_rank');ncols=['profile_name','original_v17_rank','v17_refreshed_rank','winner_rank','days_since_recorded_high','distance_from_recorded_high','strict_cagr_1y','cagr_3y','evidence_confidence'];lines=['# V17 refined — final research result','','## Decision','','**PROMISING CHALLENGER: V17 refined ensemble wins this research round.** No subsequent candidate earnedV18: one specialist addition passed development but failed the locked robustness checks. d499580 remains frozen production. Nothing deployed.','','## What changed','',s.md(pd.DataFrame(repairs)),'','## Original V17 vs refined V17 vs d499580','','Equal-weight averages across date/profile baskets. MedianXIRR is the average of each Top20 basket median, not portfolio CAGR. Drawdown is average selected-asset drawdown, not a portfolio backtest. Rates below are decimals; less negative drawdown is better. MeanXIRR has zero selection weight.','',s.md(metrics[display]),'','### Every development profile: refined minus originalV17','',s.md(dep[['profile','median_xirr_top20_delta','target_achievement_top20_delta','target_shortfall_top20_delta','mean_asset_drawdown_top20_delta','ndcg20_delta']]),'','## Robustness and remaining weakness','','All44 trainable dates and9 profiles were evaluated;6 initial2015 dates have no matured prior labels. All7 cohorts are evaluated for each profile in each period. Full per-date, profile and cohort tables are in evaluation/.2024–2025 was already exposed and never selected weights. Earlier2016–2019 is contextual evaluation. Nested calendar-year bootstrap intervals are conditional and do not correct for adaptive selection.','',s.md(weak),'', 'The high-volatility drawdown weakness is reduced, not eliminated relative to d499580. Development gains are not prospective evidence. Both frozen-universe survivorship and provider revision timing remain limitations. Current fundamentals and peers are diagnostic-only because dated historical snapshots are unavailable. No present-day values were backfilled.','', 'Robustness details:','',s.md(pd.DataFrame([{'variant':variant,'60M_median_return_vs_champion':item['long_return'],'highvol_drawdown_vs_matched_V17':item['highvol_drawdown'],'aggregate_median_return_vs_matched_V17':item['stats']['v17_delta']['median_xirr_top20'],'passed':all(item['checks'].values())} for variants in robust.values() for variant,item in variants.items()])),'','## Current4,436-stock universe','','39,924 rows retain all4,436 stocks and9 profiles.29,817 are ranked; unresolved price/action/history cases keep explicit reasons. Freshness repair adds540 previously unranked rows and blocks18 formerly ranked rows (two identities across9 profiles), net+522. The repaired model is applied to observed V7 prices at the frozen2026-10-03 decision, with official-action retrieval through2026-10-04.','','Model-onlyTop20 stability is measured against the same corrected data. Data-driven entries are reported separately: the12M Top20 retains15/20 after newly verified stocks enter, while its model scores receive no new correction. Base profile retains18/20 after model refinement.','',s.md(stability),'',s.md(coverage),'','### Base profileTop20','',s.md(base),'','Top20/50/100 for all profiles: current_top20.csv, current_top50.csv, current_top100.csv. Full coverage/reasons: final_current_rankings.csv.gz.','','## NYKAA','',s.md(ny[ncols]),'','NYKAA moves from original base rank5 to refined rank4. This was not a target. Its strong recent growth and goal fit coexist with an old high and missing true5Y history.60M remains insufficient-history; no price history is fabricated. Current fundamental/peer evidence is in nykaa_peer_context.csv and current_peer_diagnostics.csv.','','## Search scope and reproducibility','','130 repair configurations,20 subsequent challenger configurations, and the earlier34-candidate tournament are preserved. Failed candidates and exact gates remain in research_ledger.csv and per-round details. Current stability was a veto after development/robustness selection, never a weight-fitting target. There is no claim of having proved a global optimum.','','Runners: research/runners/v17_refinement_20261004.py and v17_refinement_actions_20261004.py. Immutable protocols, selection locks, model weights, raw public-source receipts, maturity audits, numerical score reproduction, feature-family sensitivities, peer diagnostics and a SHA256 manifest accompany this report. Coverage repair writes research artifacts only; production application code is untouched.','','Sources: [NSE corporate actions](https://www.nseindia.com/companies-listing/corporate-filings-actions), [BSE corporate actions](https://www.bseindia.com/corporates/corporates_act.html). Exact API URLs and raw-response hashes are recorded in actions/summary.json.']
    text='\n'.join(lines)
    for before,after in {'earnedV18':'earned V18','1861/1861':'1,861/1,861','catalogue and1861':'catalogue and 1861','through2026':'through 2026',';7 new':'; 7 new',';5 automatic and2':'; 5 automatic and 2','4346/4436':'4,346/4,436','confidence-weighted35%':'confidence-weighted 35%','abovechampion':'above champion','improves0.377percentage':'improves 0.377 percentage','versusV17':'versus V17','thand499580':'than d499580','small12M':'small 12M','Top20':'Top 20','MeanXIRR':'Mean XIRR','MedianXIRR':'Median XIRR','medianXIRR':'median XIRR','originalV17':'original V17','All44':'All 44','and9 profiles':'and 9 profiles','initial2015':'initial 2015','All7':'All 7','period.2024':'period. 2024','Earlier2016':'Earlier 2016','Current4,436':'Current 4,436','all4,436':'all 4,436','profiles.29,817':'profiles. 29,817','adds540':'adds 540','blocks18':'blocks 18','across9':'across 9','net+522':'net +522','frozen2026':'frozen 2026','the12M':'the 12M','retains15/20':'retains 15/20','retains18/20':'retains 18/20','rank5':'rank 5','rank4':'rank 4','true5Y':'true 5Y','history.60M':'history. 60M','configurations,20':'configurations, 20','earlier34-candidate':'earlier 34-candidate','may be calledV18':'may be called V18'}.items():text=text.replace(before,after)
    text+='\n\nThe legacy personalized-v18-20261003 directory names an earlier tournament, not an awarded V18 model. Historical coverage stays frozen for fair comparisons; the goal-window coverage repair applies to current inference only.\n'
    (ROOT/'research/reports/v17_refinement_20261004.md').write_text(text,encoding='utf-8');print('DELIVERY REPORT COMPLETE',flush=True)
def final_audit():
    from concurrent.futures import ThreadPoolExecutor
    import subprocess
    before=json.loads((r.O/'protected_before.json').read_text());before.update(json.loads((O/'baseline_hashes.json').read_text()));oldmanifest=json.loads((r.O/'manifest.json').read_text());before.update(oldmanifest)
    def check(item):
        path,digest=item;return path if not (ROOT/path).is_file() or v.sha(ROOT/path)!=digest else None
    changed=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i,p in enumerate(pool.map(check,before.items())):
            if p:changed.append(p)
            if i%4000==0:print('FINAL AUDIT',i,flush=True)
    assert not changed,changed;maturity=[]
    def visit(obj):
        if isinstance(obj,list):
            for z in obj:visit(z)
        elif isinstance(obj,dict):
            if 'max_endpoint' in obj:
                cutoff=obj.get('min_decision',obj.get('min_scored_date'));assert obj['max_endpoint']<cutoff,obj;maturity.append(obj['max_endpoint'])
            for z in obj.values():
                if isinstance(z,(dict,list)):visit(z)
    for p in O.glob('*training_audit.json'):visit(json.loads(p.read_text()))
    forbidden={'isin','ticker','company','company_name','future_xirr','future_shortfall','future_drawdown','endpoint','history_months','has_true_5y'};models=0
    for p in O.glob('*.txt'):
        if p.name.startswith(('model_','bag60_','stable60_')):m=lgb.Booster(model_file=str(p));assert not forbidden.intersection(m.feature_name()),p;models+=1
    current=pd.read_csv(O/'final_current_rankings.csv.gz',usecols=v.KEYS+['winner_score','winner_rank','status']);assert len(current)==39924 and current['isin'].nunique()==4436 and current.profile_name.nunique()==9;assert not current.duplicated(v.KEYS).any();assert current.loc[current.status.eq('AVAILABLE'),'winner_score'].notna().all();validation=json.loads((O/'final_validation.json').read_text());assert validation['reproduction_max_error']<1e-9 and validation['identity_and_age_label_only_max_error']==0;coverage=json.loads((O/'evaluation/date_coverage.json').read_text());assert coverage['scored_date_count']==44
    actions=json.loads((O/'actions/summary.json').read_text());assert actions['failed']==0
    for path,digest in actions['raw_hashes'].items():assert v.sha(O/'actions'/path)==digest
    receipts=pd.read_csv(O/'provider_splits/acquisition_audit.csv');accepted=receipts.loc[receipts.status.eq('SUCCESS')]
    for row in accepted.itertuples(index=False):assert v.sha(O/'provider_splits/raw'/f'{row.isin}.json')==row.response_sha256
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();assert head=='c12dd9b189bc71684bfac52606eb89abd5e383c7';write('audit.json',{'completed_at':now(),'protected_files':len(before),'changed_protected':changed,'maturity_records':len(maturity),'models_checked':models,'official_receipts':len(actions['raw_hashes']),'provider_receipts':len(accepted),'current_rows':len(current),'available_unranked':0,'historical_dates':44,'production_HEAD':head,'deployed':False,'all_checks_passed':True});paths=sorted(p for p in O.rglob('*') if p.is_file() and p.name!='manifest.json')+[ROOT/'research/runners/v17_refinement_20261004.py',ROOT/'research/runners/v17_refinement_actions_20261004.py',ROOT/'research/reports/v17_refinement_20261004.md'];write('manifest.json',{str(p.relative_to(ROOT)):v.sha(p) for p in paths});print('FINAL AUDIT PASSED',len(paths),flush=True)

if __name__=='__main__':globals()[sys.argv[1]]()
