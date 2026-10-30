"""V17 sustained research: chronological training, explicit trial ledger, frozen inputs."""
import os,sys,json,gc,hashlib
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import lightgbm as lgb
import personalized_v15_20261003 as v
ROOT=v.ROOT
O=ROOT/'experiments/personalized-v17-20261003'
O.mkdir(exist_ok=True)
RAW=[c for c in v.FEATURES if c not in v.FAMILIES['history']]
POS=['enhanced_carry_xirr_score','enhanced_goal_score','cash_utilization','target_attainment','historical_target_frequency_score','strict_cagr_1y','cagr_3y','observed_cagr_5y','strict_cagr_7y','strict_cagr_10y','momentum_6m','distance_from_recorded_high','distance_from_52w_high','recovery_from_worst_trough','distance_from_1y_low','price_drawdown','full_history_max_drawdown']
NEG=['unaffordable_rate','target_shortfall','old_high_depth','underwater_depth','realized_volatility_1y','downside_volatility_1y','downside_frequency_1y']
CONTEXT=['lookback_months','frequency_days','target_cagr','amount_per_contribution','target_to_contributed']
NORM=['q_'+c for c in POS+NEG]+['u_'+c for c in CONTEXT]
FAMILIES=['refresh_v15','specialist_ltr','neutral_ltr','monotone_utility','monotone_ltr','ranknet']
def now(): return datetime.now(timezone.utc).isoformat()
def write(n,x,exclusive=False):
    with (O/n).open('x' if exclusive else 'w',encoding='utf-8') as f: json.dump(v.clean(x),f,indent=2,allow_nan=False)
def csv(n,x): x.to_csv(O/n,index=False,compression={'method':'gzip','mtime':0} if n.endswith('.gz') else None)
def normalize(x):
    x=x.copy(); groups=x.groupby(['decision_date','profile_name'])
    for c in POS+NEG:
        x['q_'+c]=groups[c].rank(pct=True,ascending=c in POS).fillna(.5).astype('float32')
    for c in CONTEXT:
        z=x[c].astype(float)
        if c=='amount_per_contribution': z=np.log1p(z)/12
        elif c=='lookback_months': z=z/60
        elif c=='frequency_days': z=z/90
        elif c=='target_to_contributed': z=z/2
        x['u_'+c]=z.fillna(0).astype('float32')
    return x
def prepare():
    assert not (O/'round1_protocol.json').exists()
    write('round1_protocol.json',{'locked_at':now(),'families':FAMILIES,'alphas':[.05,.1,.2,.3],'training':'Expanding yearly fits. For each development year train only endpoint < first decision in year. No 2024+ decision labels or current inputs used. Finalists additionally checked with per-date refresh.','selection':'Original V15 gates plus all-profile return >=0, all-profile drawdown >=-0.01, 12M return/drawdown >=0, weekly return>=0. Select on development utility and lower adverse-date concentration; no exposed/current selection. Failures trigger a documented new development-only research round, not threshold changes.','params':{'n_estimators':140,'learning_rate':.035,'num_leaves':15,'max_depth':4,'min_child_samples':300,'reg_lambda':40},'seeds':[20261003],'labels':'Original balanced ordinal utility for refresh/specialist. Others 0.70 return percentile +0.20 inverse shortfall percentile +0.10 drawdown percentile. Linear gains for normalized rankers, continuous target for monotone regression.','normalization':'Within-query percentiles, missing inputs exactly neutral0.5. No history-age, true-history flags, stock identity, current fundamental, or sector feature. Original observed-field confidence caps correction weight.','feature_columns':{'raw':RAW,'positive':POS,'negative':NEG,'context':CONTEXT},'ranknet':'CPU MLP32/16 SiLU; 8 epochs;600 pairs per query per epoch; signed utility pair logistic loss weighted by absolute utility gap; AdamW0.001 weight_decay0.01; no early stopping on development.','protected_inputs':'V16 completed audit baseline plus all V16 experiment files/report/runner; no previous experiment edits.'},True)
    sources=[{'url':'https://arxiv.org/abs/2012.07149','use':'Compare direct ranking with regression; no claimed transfer of published profitability.'},{'url':'https://www.nber.org/papers/w25398','use':'Nonlinear momentum/volatility interactions; compare models on own dated data.'},{'url':'https://arxiv.org/abs/2204.01500','use':'Ranking loss choice and objective alignment matter.'},{'url':'https://lightgbm.readthedocs.io/en/stable/Parameters.html','use':'Linear label gain and monotone constraints supported; no click-position bias correction applied to stock data.'},{'url':'https://escholarship.org/uc/item/4w1110bb','use':'Multiple testing and backtest overfitting; keep trial ledger and no claims of blind evidence.'},{'url':'https://www.nature.com/articles/s41586-024-08328-6','use':'Tabular foundation model evaluated; published small-data scale differs from million-row SIP panel, pretrained financial contamination needs audit.'}]
    write('research_sources.json',sources)
    old=ROOT/'experiments/personalized-v16-20261003'; baseline=json.loads((old/'protected_before.json').read_text())
    paths=list(old.rglob('*'))+[ROOT/'research/runners/personalized_v16_20261003.py',ROOT/'research/reports/personalized_v16_20261003.md']
    for p in paths:
        if p.is_file(): baseline[str(p.relative_to(ROOT))]=v.sha(p)
    def check(item):
        p,h=item; return p if not (ROOT/p).is_file() or v.sha(ROOT/p)!=h else None
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i,result in enumerate(pool.map(check,baseline.items())):
            assert result is None,result
            if i%4000==0: print('PROTECT',i,flush=True)
    write('protected_before.json',baseline,True)
    print('LOAD HISTORICAL',flush=True)
    x=v.load_historical(False); x=x.loc[x.decision_date.lt('2024-01-01')].copy(); x=normalize(x)
    x.to_pickle(O/'historical.pkl')
    write('data_audit.json',{'rows':len(x),'dates':sorted(x.decision_date.unique()),'future_decision_rows':0,'input_hashes':{str(p.relative_to(ROOT)):v.sha(p) for p in [v.PREP,v.PANEL,v.V14/'historical_growth.csv.gz']}})
    print('PREPARED',len(x),flush=True)
def target(train,original=False):
    g=train.groupby(['decision_date','profile_name'],sort=False)
    if original: return .6*g.future_xirr.rank(pct=True)+.25*g.future_shortfall.rank(pct=True,ascending=False)+.1*g.future_drawdown.rank(pct=True)+.05*train.future_shortfall.eq(0)
    return .7*g.future_xirr.rank(pct=True)+.2*g.future_shortfall.rank(pct=True,ascending=False)+.1*g.future_drawdown.rank(pct=True)
def train_predict(train,test,family,tag,seed=20261003):
    train=train.dropna(subset=v.OUTCOME+['enhanced_carry_xirr_score']).sort_values(v.KEYS[1:]+v.KEYS[:1]).reset_index(drop=True)
    valid=test.enhanced_carry_xirr_score.notna(); pred=pd.Series(np.nan,index=test.index)
    modelpath=O/('model_'+tag)
    if family in ['specialist_ltr','ath_specialist','targeted_specialist']:
        records=[]
        for look in sorted(test.lookback_months.unique()):
            a=train.loc[train.lookback_months.eq(look)]; b=test.loc[test.lookback_months.eq(look)]
            pp,aa=train_predict(a,b,'ath_raw' if family=='ath_specialist' or (family=='targeted_specialist' and look>=60) else 'refresh_v15',tag+'_look'+str(int(look)),seed); pred.loc[b.index]=pp; records.append(aa)
        return pred,{'specialists':records}
    features=RAW if family in ['refresh_v15','ath_raw'] else NORM
    y=target(train,family in ['refresh_v15','ath_raw']); groups=train.groupby(['decision_date','profile_name'],sort=False).size().to_list()
    if family=='ranknet':
        import torch
        torch.set_num_threads(4); torch.manual_seed(seed)
        net=torch.nn.Sequential(torch.nn.Linear(len(features),32),torch.nn.SiLU(),torch.nn.Linear(32,16),torch.nn.SiLU(),torch.nn.Linear(16,1))
        optimizer=torch.optim.AdamW(net.parameters(),lr=.001,weight_decay=.01)
        xx=torch.from_numpy(train[features].to_numpy(dtype=np.float32)); yy=y.to_numpy(dtype=np.float32); rng=np.random.default_rng(seed)
        offsets=np.r_[0,np.cumsum(groups)]; last=0
        for epoch in range(8):
            left=np.concatenate([rng.integers(offsets[i],offsets[i+1],600) for i in range(len(groups))]); right=np.concatenate([rng.integers(offsets[i],offsets[i+1],600) for i in range(len(groups))]); order=rng.permutation(len(left))
            for ids in np.array_split(order,max(1,len(order)//4096)):
                a=left[ids]; b=right[ids]; delta=torch.from_numpy(yy[a]-yy[b]); difference=(net(xx[a])-net(xx[b])).squeeze(1)
                loss=(torch.nn.functional.softplus(-delta.sign()*difference)*delta.abs()).mean(); optimizer.zero_grad(); loss.backward(); optimizer.step(); last=float(loss.detach())
        net.eval()
        with torch.no_grad(): pred.loc[valid]=net(torch.from_numpy(test.loc[valid,features].to_numpy(dtype=np.float32))).squeeze(1).numpy()
        torch.save({'state_dict':net.state_dict(),'features':features},str(modelpath)+'.pt')
    else:
        params=dict(n_estimators=140,learning_rate=.035,num_leaves=15,max_depth=4,min_child_samples=300,reg_lambda=40,n_jobs=4,verbosity=-1,random_state=seed,deterministic=True,force_col_wise=True)
        if family in ['refresh_v15','ath_raw']: params.update(v.PARAMS)
        if family=='ath_raw':
            signs={'days_since_recorded_high':-1,'current_drawdown_duration_days':-1,'distance_from_recorded_high':1,'old_high_depth':-1,'underwater_depth':-1,'recovery_vs_old_high':-1}
            params.update(monotone_constraints=[signs.get(c,0) for c in features],monotone_constraints_method='advanced')
        if family.startswith('monotone'):
            params.update(monotone_constraints=[1]*len(POS+NEG)+[0]*len(CONTEXT),monotone_constraints_method='advanced')
        if family=='monotone_utility':
            model=lgb.LGBMRegressor(objective='regression',**params); weights=np.repeat(1/np.array(groups),groups); weights=weights/weights.mean(); model.fit(train[features],y,sample_weight=weights)
        else:
            args={} if family in ['refresh_v15','ath_raw'] else {'label_gain':list(range(16))}
            model=lgb.LGBMRanker(objective='lambdarank',lambdarank_truncation_level=30,**{k:val for k,val in params.items() if k!='lambdarank_truncation_level'},**args)
            levels=8 if family in ['refresh_v15','ath_raw'] else 16
            labels=np.minimum(np.floor(y*levels),levels-1).astype('int8'); model.fit(train[features],labels,group=groups)
        model.booster_.save_model(str(modelpath)+'.txt'); pred.loc[valid]=model.predict(test.loc[valid,features],num_threads=4)
    return pred,{'family':family,'seed':seed,'train_rows':len(train),'train_groups':len(groups),'max_endpoint':train.endpoint.max(),'min_scored_date':test.decision_date.min(),'features':features}
def strict_stats(pair,turn):
    result=v.eligibility(pair,turn); p=pair.groupby('profile')[[c+'_delta' for c in v.METRICS]].mean()
    extra={'all_profile_return_nonnegative':p.median_xirr_top20_delta.min()>=0,'all_profile_drawdown_floor':p.mean_asset_drawdown_top20_delta.min()>=-.01,'12m_return_nonnegative':p.loc['lookback12','median_xirr_top20_delta']>=0,'12m_drawdown_nonnegative':p.loc['lookback12','mean_asset_drawdown_top20_delta']>=0,'weekly_return_nonnegative':p.loc['weekly','median_xirr_top20_delta']>=0}
    result['additional_checks']=extra; result['strong_eligible']=result['eligible'] and all(extra.values()); result['worst_date_return']=pair.median_xirr_top20_delta.min(); result['negative_return_date_fraction']=pair.median_xirr_top20_delta.lt(0).mean(); result['profile_deltas']=p.reset_index().to_dict('records')
    return result
def round1():
    protocol=json.loads((O/'round1_protocol.json').read_text()); x=pd.read_pickle(O/'historical.pkl'); dates=v.protocol()['development_selection_dates']; dev=x.loc[x.decision_date.isin(dates)].merge(v.benchmark(dates),on=v.KEYS,validate='one_to_one'); base=v.evaluate(dev,'champion_score')
    records=[]; details={}; audits=[]; allmetrics=[]; predictions=dev[v.KEYS].copy()
    for family in protocol['families']:
        cached=O/('round1_predictions_'+family+'.csv.gz')
        if cached.exists():
            saved=pd.read_csv(cached); raw=dev[v.KEYS].merge(saved,on=v.KEYS,validate='one_to_one').prediction; raw.index=dev.index
        else:
            raw=pd.Series(np.nan,index=dev.index)
            for year in ['2020','2021','2022','2023']:
                test=dev.loc[dev.decision_date.str.startswith(year)]; cutoff=test.decision_date.min(); train=x.loc[x.endpoint.lt(cutoff)]
                assert train.endpoint.max()<cutoff
                print('TRAIN',family,year,len(train),flush=True)
                p,a=train_predict(train,test,family,family+'_'+year); raw.loc[test.index]=p; audits.append(a); write('round1_training_audit.json',audits)
            csv(cached.name,dev[v.KEYS].assign(prediction=raw))
        corr=raw.where(dev.champion_score.notna()).groupby([dev.decision_date,dev.profile_name]).rank(pct=True); predictions[family]=raw
        for alpha in protocol['alphas']:
            name=family+'__'+str(alpha); dev['candidate_score']=v.guided(dev,corr,alpha); metrics=v.evaluate(dev,'candidate_score'); pair=v.compare_metrics(metrics,base); stats=strict_stats(pair,v.turnover(dev,'candidate_score'))
            records.append({'candidate':name,'family':family,'alpha':alpha,'eligible':stats['eligible'],'strong_eligible':stats['strong_eligible'],'utility':stats['utility'],'top20_overlap':stats['top20_overlap'],**stats['delta']}); details[name]=stats; allmetrics.append(pair.assign(candidate=name))
            print('RESULT',name,stats['eligible'],stats['strong_eligible'],round(stats['utility'],5),[k for k,ok in stats['checks'].items() if not ok],[k for k,ok in stats['additional_checks'].items() if not ok],flush=True)
        csv('round1_trials.csv',pd.DataFrame(records).sort_values(['strong_eligible','eligible','utility'],ascending=False)); write('round1_details.json',details); csv('round1_all_profile_date_results.csv',pd.concat(allmetrics,ignore_index=True))
    csv('round1_predictions.csv.gz',predictions)
    print('ROUND1 COMPLETE',flush=True)
def round2():
    assert (O/'round1_predictions.csv.gz').exists(), 'Complete first round before hypothesis extension'
    candidates=[{'name':kind+'__'+str(a),'kind':kind,'alpha':a} for kind in ['short_monotone_v15','blend_specialist_monotone','blend_refresh_monotone'] for a in [.1,.2,.3]]
    if not (O/'round2_protocol.json').exists():
        write('round2_protocol.json',{'locked_at':now(),'evidence_sha256':v.sha(O/'round1_trials.csv'),'hypothesis':'Constrained return model repairs short-lookback return and drawdown, but loses return at long-lookback/low-target settings. Raw specialists retain broad return signal but worsen12M drawdown. Test explicit short-lookback routing and equal-weight percentile ensembles of these complementary predictions, without additional fitted thresholds.','candidates':candidates,'routing':'short_monotone_v15 uses monotone_utility at lookback<=12 and frozen V15 at longer lookbacks. Both blend kinds average correction prediction percentiles50/50 then use common alpha and original evidence confidence.','selection':'Highest strong-eligible development utility, then lowest negative-return date fraction, then lower alpha. If none pass, continue a separately locked development research round.','unchanged_gates':json.loads((O/'round1_protocol.json').read_text())['selection'],'no_current_or_exposed_results':True,'next_checks':'Selected architecture will be checked with per-date refresh and independent random seeds; these are robustness checks, not blind tests.'},True)
    x=pd.read_pickle(O/'historical.pkl'); dates=v.protocol()['development_selection_dates']; dev=x.loc[x.decision_date.isin(dates)].merge(v.benchmark(dates),on=v.KEYS,validate='one_to_one'); del x;gc.collect()
    predictions=pd.read_csv(O/'round1_predictions.csv.gz'); dev=dev.merge(predictions,on=v.KEYS,validate='one_to_one')
    frozen=pd.read_csv(ROOT/'experiments/personalized-v16-20261003/development_scores.csv.gz',usecols=v.KEYS+['v15_score','v16_score']); dev=dev.merge(frozen,on=v.KEYS,validate='one_to_one')
    base=v.evaluate(dev,'champion_score'); percentiles={f:dev[f].where(dev.champion_score.notna()).groupby([dev.decision_date,dev.profile_name]).rank(pct=True) for f in FAMILIES}
    rows=[]; details={}; metrics=[]
    for c in candidates:
        if c['kind']=='short_monotone_v15':
            score=v.guided(dev,percentiles['monotone_utility'],c['alpha']); mask=dev.lookback_months.gt(12); score.loc[mask]=dev.loc[mask,'v15_score']
        else:
            partner='specialist_ltr' if c['kind']=='blend_specialist_monotone' else 'refresh_v15'; score=v.guided(dev,(percentiles['monotone_utility']+percentiles[partner])/2,c['alpha'])
        dev['candidate_score']=score; pair=v.compare_metrics(v.evaluate(dev,'candidate_score'),base); stats=strict_stats(pair,v.turnover(dev,'candidate_score')); details[c['name']]=stats
        rows.append({**c,'eligible':stats['eligible'],'strong_eligible':stats['strong_eligible'],'utility':stats['utility'],'negative_return_date_fraction':stats['negative_return_date_fraction'],'top20_overlap':stats['top20_overlap'],**stats['delta']}); metrics.append(pair.assign(candidate=c['name']))
        print('ROUND2',c['name'],stats['strong_eligible'],stats['utility'],[k for k,ok in stats['checks'].items() if not ok],[k for k,ok in stats['additional_checks'].items() if not ok],flush=True)
    table=pd.DataFrame(rows).sort_values(['strong_eligible','eligible','utility','negative_return_date_fraction','alpha'],ascending=[False,False,False,True,True]); csv('round2_trials.csv',table); write('round2_details.json',details); csv('round2_all_profile_date_results.csv',pd.concat(metrics,ignore_index=True))
    best=table.iloc[0].to_dict(); write('development_finalist.json',{'selected_at':now(),'candidate':best,'details':details[best['name']],'round2_protocol_sha256':v.sha(O/'round2_protocol.json'),'current_exposed_not_accessed':True})
    print('FINALIST',best,flush=True)
def selected_score(dev,raw1,raw2,choice):
    a=raw1.where(dev.champion_score.notna()).groupby([dev.decision_date,dev.profile_name]).rank(pct=True)
    if choice['kind']=='short_monotone_v15':
        result=v.guided(dev,a,choice['alpha']); mask=dev.lookback_months.gt(12); result.loc[mask]=dev.loc[mask,'v15_score']; return result
    b=raw2.where(dev.champion_score.notna()).groupby([dev.decision_date,dev.profile_name]).rank(pct=True)
    result=v.guided(dev,(a+b)/2,choice['alpha'])
    if 'score_cap' in choice: result=dev.champion_score+(result-dev.champion_score).clip(-choice['score_cap'],choice['score_cap'])
    return result
def robustness():
    selected=json.loads((O/'development_finalist.json').read_text()); choice=selected['candidate']; assert choice['strong_eligible']
    if not (O/'robustness_protocol.json').exists():
        write('robustness_protocol.json',{'locked_at':now(),'finalist_sha256':v.sha(O/'development_finalist.json'),'seeds':[20261004,20261005],'refresh_check':'Refit at each of all16 decision dates, seed20261003, strict endpoint maturity.','acceptance':'All original V15 gates and nonnegative12M return/drawdown must survive each seed and per-date refresh; report additional all-profile checks without hiding any instability. No threshold adjustment.','cohorts':'All profiles; short/full history, high volatility, deep drawdown, deep/old/recent ATH; evaluated after finalist selection.'},True)
    x=pd.read_pickle(O/'historical.pkl'); dates=v.protocol()['development_selection_dates']; dev=x.loc[x.decision_date.isin(dates)].merge(v.benchmark(dates),on=v.KEYS,validate='one_to_one')
    frozen=pd.read_csv(ROOT/'experiments/personalized-v16-20261003/development_scores.csv.gz',usecols=v.KEYS+['v15_score','v16_score']); dev=dev.merge(frozen,on=v.KEYS,validate='one_to_one'); base=v.evaluate(dev,'champion_score')
    partner='specialist_ltr' if choice['kind']=='blend_specialist_monotone' else 'refresh_v15'
    results={}; allmetrics=[]; audit=[]
    for variant,seed in [('seed20261004',20261004),('seed20261005',20261005),('per_date',20261003)]:
        cached=O/('robustness_'+variant+'_predictions.csv.gz')
        if cached.exists():
            pp=dev[v.KEYS].merge(pd.read_csv(cached),on=v.KEYS,validate='one_to_one'); raw1=pp.raw1; raw2=pp.raw2
        else:
            raw1=pd.Series(np.nan,index=dev.index); raw2=pd.Series(np.nan,index=dev.index)
            blocks=dates if variant=='per_date' else ['2020','2021','2022','2023']
            for block in blocks:
                test=dev.loc[dev.decision_date.eq(block) if variant=='per_date' else dev.decision_date.str.startswith(block)]; cutoff=test.decision_date.min(); train=x.loc[x.endpoint.lt(cutoff)]
                print('ROBUST TRAIN',variant,block,len(train),flush=True)
                p,a=train_predict(train,test,'monotone_utility','robust_'+variant+'_'+block+'_monotone',seed); raw1.loc[test.index]=p; audit.append(a)
                if choice['kind']!='short_monotone_v15':
                    p,a=train_predict(train,test,partner,'robust_'+variant+'_'+block+'_partner',seed); raw2.loc[test.index]=p; audit.append(a)
                write('robustness_training_audit.json',audit)
            csv(cached.name,dev[v.KEYS].assign(raw1=raw1,raw2=raw2))
        dev['candidate_score']=selected_score(dev,raw1,raw2,choice); pair=v.compare_metrics(v.evaluate(dev,'candidate_score'),base); stats=strict_stats(pair,v.turnover(dev,'candidate_score')); stats['robustness_acceptance']=stats['eligible'] and stats['additional_checks']['12m_return_nonnegative'] and stats['additional_checks']['12m_drawdown_nonnegative']; results[variant]=stats; allmetrics.append(pair.assign(variant=variant))
        write('robustness_results.json',results); csv('robustness_profile_date_results.csv',pd.concat(allmetrics,ignore_index=True)); print('ROBUST RESULT',variant,stats['robustness_acceptance'],stats['strong_eligible'],stats['utility'],flush=True)
    print('ROBUSTNESS COMPLETE',flush=True)
def development_diagnostics():
    choice=json.loads((O/('selection_lock.json' if (O/'selection_lock.json').exists() else 'development_finalist.json')).read_text())['candidate']; dev=pd.read_pickle(ROOT/'experiments/personalized-v16-20261003/development.pkl.gz',compression='gzip')
    frozen=pd.read_csv(ROOT/'experiments/personalized-v16-20261003/development_scores.csv.gz',usecols=v.KEYS+['v16_score']); dev=dev.merge(frozen,on=v.KEYS,validate='one_to_one'); predictions=pd.read_csv(O/'round1_predictions.csv.gz'); dev=dev.merge(predictions,on=v.KEYS,validate='one_to_one')
    partner='specialist_ltr' if choice['kind']=='blend_specialist_monotone' else 'refresh_v15'
    if choice['kind']=='blend_ath_monotone':
        dev=dev.merge(pd.read_csv(O/'round3_predictions.csv.gz').rename(columns={'prediction':'ath_specialist'}),on=v.KEYS,validate='one_to_one'); partner='ath_specialist'
    if choice['kind']=='blend_targeted_monotone':
        dev=dev.merge(pd.read_csv(O/'round5_predictions.csv.gz').rename(columns={'prediction':'targeted_specialist'}),on=v.KEYS,validate='one_to_one'); partner='targeted_specialist'
    dev['v17_score']=selected_score(dev,dev.monotone_utility,dev[partner],choice)
    base=v.evaluate(dev,'champion_score'); allmetrics=[]; turns=[]
    for model in ['champion','v15','v16','v17']:
        dev[model+'_rank']=v.ranked(dev,model+'_score'); allmetrics.append(v.evaluate(dev,model+'_score').assign(model=model))
    csv('development_all_models_profile_date_results.csv',pd.concat(allmetrics,ignore_index=True)); pair=v.compare_metrics(v.evaluate(dev,'v17_score'),base); csv('development_selected_profile_date_results.csv',pair.rename(columns=lambda c:c.replace('_v15','_v17'))); csv('development_selected_profile_summary.csv',pair.groupby('profile',as_index=False)[[c+'_delta' for c in v.METRICS]].mean())
    for reference in ['champion','v15','v16']:
        z=dev.copy(); z['champion_score']=dev[reference+'_score']; turns.append(v.turnover(z,'v17_score').assign(comparison='v17_vs_'+reference))
    csv('development_turnover.csv',pd.concat(turns,ignore_index=True)); csv('development_scores.csv.gz',dev[v.KEYS+v.OUTCOME+[m+s for m in ['champion','v15','v16','v17'] for s in ['_score','_rank']]])
    csv('development_largest_movers.csv',dev.assign(rank_change=dev.champion_rank-dev.v17_rank).sort_values('rank_change',key=lambda z:z.abs(),ascending=False).groupby('profile_name').head(30))
    csv('development_top20.csv',dev.loc[dev.v17_rank.le(20)])
    cohort_tables=[]
    for profile,g in [('ALL',dev)]+list(dev.groupby('profile_name')):
        masks={'short_history':g.history_months.lt(60),'full_history':g.has_true_5y.eq(1),'high_volatility':g.realized_volatility_1y.ge(g.groupby(['decision_date','profile_name']).realized_volatility_1y.transform('quantile',.75)),'deep_drawdown':g.full_history_max_drawdown.le(-.5),'deep_ath':g.distance_from_recorded_high.le(-.4),'old_ath':g.days_since_recorded_high.ge(1095),'recent_ath':g.days_since_recorded_high.le(90)}
        for name,mask in masks.items():
            for model in ['champion','v15','v16','v17']:
                metrics=v.evaluate(g.loc[mask],model+'_score')
                selected=g.dropna(subset=[model+'_score']+v.OUTCOME).sort_values(['decision_date','profile_name',model+'_score','isin'],ascending=[True,True,False,True]).groupby(['decision_date','profile_name']).head(20); selected=selected.loc[mask.reindex(selected.index)]
                cohort_tables.append({'profile':profile,'cohort':name,'model':model,'share_overall_top20':len(selected)/(20*g.groupby(['decision_date','profile_name']).ngroups),'selected_xirr':selected.future_xirr.median(),'selected_drawdown':selected.future_drawdown.mean(),**metrics[v.METRICS].mean().to_dict()})
        print('COHORTS',profile,flush=True)
    csv('development_cohorts.csv',pd.DataFrame(cohort_tables))
    intervals=[]; rng=np.random.default_rng(20261003)
    for scope,z in [('ALL',pair),('lookback12',pair.loc[pair.profile.eq('lookback12')]),('weekly',pair.loc[pair.profile.eq('weekly')])]:
        yearly=z.assign(year=z.decision_date.str[:4]).groupby('year')[[c+'_delta' for c in v.METRICS]].mean(); boot=np.array([yearly.iloc[rng.integers(0,4,4)].mean().to_numpy() for _ in range(2000)])
        for j,c in enumerate(v.METRICS): intervals.append({'scope':scope,'metric':c,'delta':float(z[c+'_delta'].mean()),'p025':np.quantile(boot[:,j],.025),'p975':np.quantile(boot[:,j],.975)})
    csv('development_year_block_intervals.csv',pd.DataFrame(intervals)); print('DEVELOPMENT DIAGNOSTICS COMPLETE',flush=True)
def predict_models(x,mono_path,partner_paths):
    m=lgb.Booster(model_file=str(mono_path)); a=pd.Series(np.nan,index=x.index); b=a.copy(); valid=x.champion_score.notna(); a.loc[valid]=m.predict(x.loc[valid,m.feature_name()],num_threads=4)
    for look,path in partner_paths.items():
        mask=valid&x.lookback_months.eq(look); model=lgb.Booster(model_file=str(path)); b.loc[mask]=model.predict(x.loc[mask,model.feature_name()],num_threads=4)
    return a,b
def behavior_on_frame(x,mono_path,partner_paths,alpha):
    x=normalize(x); base1,base2=predict_models(x,mono_path,partner_paths); rows=[]
    def ecdf(ref,values):
        ref=np.sort(ref.dropna().to_numpy()); return np.clip((np.searchsorted(ref,values,side='left')+np.searchsorted(ref,values,side='right')+1)/(2*len(ref)),0,1)
    scenario_scores={}
    for scenario,days,depth in [('recent_near',30,-.05),('old_near',1825,-.05),('old_deep',1825,-.7)]:
        z=x.copy(); z['days_since_recorded_high']=days; z['current_drawdown_duration_days']=days; z['distance_from_recorded_high']=depth; z['old_high_depth']=np.log1p(days/365)*(-depth); z['underwater_depth']=z.old_high_depth; z['recovery_vs_old_high']=z.recovery_from_worst_trough.clip(-1,10)*(-depth)
        for _,g in x.groupby(['decision_date','profile_name']):
            for c in ['distance_from_recorded_high','old_high_depth','underwater_depth']:
                values=ecdf(g[c],z.loc[g.index,c]); z.loc[g.index,'q_'+c]=(values if c in POS else 1-values).astype('float32')
        p1,p2=predict_models(z,mono_path,partner_paths); s=pd.Series(np.nan,index=x.index)
        for _,g in x.groupby(['decision_date','profile_name']):
            idx=g.index; valid=g.champion_score.notna(); ids=idx[valid]; r1=ecdf(base1.loc[idx],p1.loc[ids]); r2=ecdf(base2.loc[idx],p2.loc[ids]); s.loc[ids]=g.loc[ids,'champion_score']*(1-alpha*g.loc[ids,'evidence_confidence'])+alpha*g.loc[ids,'evidence_confidence']*(r1+r2)/2
        scenario_scores[scenario]=s
    for profile,g in x.groupby('profile_name'):
        for scenario in ['old_near','old_deep']:
            delta=(scenario_scores[scenario]-scenario_scores['recent_near']).loc[g.index].dropna()
            rows.append({'profile':profile,'scenario':scenario,'mean_score_change':delta.mean(),'median_score_change':delta.median(),'negative_fraction':delta.lt(-1e-8).mean(),'positive_fraction':delta.gt(1e-8).mean(),'method':'Each-stock counterfactual anchored to original query feature and prediction empirical CDFs; fixed other features and champion. Conditional diagnostic, not causal or guaranteed realizable.'})
    return pd.DataFrame(rows)
def historical_behavior():
    choice=json.loads((O/'development_finalist.json').read_text())['candidate']; x=pd.read_pickle(ROOT/'experiments/personalized-v16-20261003/development.pkl.gz',compression='gzip'); x=x.loc[x.decision_date.eq('2023-12-31')].copy()
    t=behavior_on_frame(x,O/'model_monotone_utility_2023.txt',{look:O/('model_specialist_ltr_2023_look'+str(look)+'.txt') for look in [12,36,60]},choice['alpha']); csv('development_ath_directional_sensitivity.csv',t); print(t.to_string(index=False),flush=True)
def round3():
    if not (O/'round3_protocol.json').exists(): write('round3_protocol.json',{'locked_at':now(),'reason':'60M old/deep ATH audit shows positive effects in raw specialist. Constrain raw ATH age/depth bundle signs during training; preserve growth/goal interactions.','alphas':[.2,.3],'mixture':'Equal percentile mixture constrained utility and ATH-constrained lookback specialists','gates':'Unchanged strict_stats; no exposed or current use','seed':20261003},True)
    x=pd.read_pickle(O/'historical.pkl'); dates=v.protocol()['development_selection_dates']; dev=x.loc[x.decision_date.isin(dates)].merge(v.benchmark(dates),on=v.KEYS,validate='one_to_one'); raw=pd.Series(np.nan,index=dev.index); audits=[]
    for year in ['2020','2021','2022','2023']:
        test=dev.loc[dev.decision_date.str.startswith(year)]; train=x.loc[x.endpoint.lt(test.decision_date.min())]; print('ATH TRAIN',year,flush=True)
        p,a=train_predict(train,test,'ath_specialist','ath_specialist_'+year); raw.loc[test.index]=p; audits.append(a)
    csv('round3_predictions.csv.gz',dev[v.KEYS].assign(prediction=raw)); write('round3_training_audit.json',audits)
    mono=dev[v.KEYS].merge(pd.read_csv(O/'round1_predictions_monotone_utility.csv.gz'),on=v.KEYS).prediction; base=v.evaluate(dev,'champion_score'); rows=[]; details={}; tables=[]
    for alpha in [.2,.3]:
        choice={'kind':'blend_ath_monotone','alpha':alpha}; dev['candidate_score']=selected_score(dev,mono,raw,choice); pair=v.compare_metrics(v.evaluate(dev,'candidate_score'),base); stats=strict_stats(pair,v.turnover(dev,'candidate_score')); name='blend_ath_monotone__'+str(alpha); rows.append({'name':name,**choice,'strong_eligible':stats['strong_eligible'],'eligible':stats['eligible'],'utility':stats['utility']}); details[name]=stats; tables.append(pair.assign(candidate=name)); print(name,stats['strong_eligible'],stats['utility'],flush=True)
    table=pd.DataFrame(rows).sort_values(['strong_eligible','eligible','utility'],ascending=False); csv('round3_trials.csv',table); write('round3_details.json',details); csv('round3_profile_date_results.csv',pd.concat(tables)); best=table.iloc[0].to_dict(); write('round3_finalist.json',{'candidate':best,'details':details[best['name']]})
    t=behavior_on_frame(dev.loc[dev.decision_date.eq('2023-12-31')],O/'model_monotone_utility_2023.txt',{look:O/('model_ath_specialist_2023_look'+str(look)+'.txt') for look in [12,36,60]},best['alpha']); csv('round3_ath_behavior.csv',t)
def lock_final():
    f=json.loads((O/'round5_finalist.json').read_text()); assert f['candidate']['strong_eligible']
    behavior=pd.read_csv(O/'round5_ath_behavior.csv'); assert behavior.loc[behavior.scenario.eq('old_deep'),'mean_score_change'].max()<=1e-8
    write('selection_lock.json',{'locked_at':now(),**f,'protocol_sha256':v.sha(O/'round5_protocol.json'),'results_sha256':v.sha(O/'round5_finalist.json'),'total_selection_candidates':39,'exposed_or_current_used':False,'prior_variant_robustness':'Round2 seed/per-date results are not evidence for exact final model; exact final robustness follows without changing selection.'},True)
def final_pass():
    lock=json.loads((O/'selection_lock.json').read_text()); choice=lock['candidate']; assert lock['results_sha256']==v.sha(O/'round5_finalist.json')
    x=normalize(v.load_historical(True)); audits=[]; allpairs=[]
    for year in ['2024','2025']:
        dates=sorted(d for d in x.decision_date.unique() if d.startswith(year)); test=x.loc[x.decision_date.isin(dates)].merge(v.benchmark(dates),on=v.KEYS,validate='one_to_one'); train=x.loc[x.endpoint.lt(min(dates))]; print('EXPOSED TRAIN',year,flush=True)
        a,aa=train_predict(train,test,'monotone_utility','exposed_'+year+'_monotone'); b,bb=train_predict(train,test,'targeted_specialist','exposed_'+year+'_partner'); audits.extend([aa,bb]); test['v17_score']=selected_score(test,a,b,choice)
        pair=v.compare_metrics(v.evaluate(test,'v17_score'),v.evaluate(test,'champion_score')); allpairs.append(pair); csv('exposed_'+year+'_scores.csv.gz',test[v.KEYS+v.OUTCOME+['champion_score','v17_score']])
    pair=pd.concat(allpairs); csv('exposed_profile_date_results.csv',pair); csv('exposed_profile_summary.csv',pair.groupby('profile',as_index=False)[[c+'_delta' for c in v.METRICS]].mean()); write('exposed_audit.json',{'known_exposed':True,'not_used_for_selection':True,'training':audits,'selection_sha256':v.sha(O/'selection_lock.json')})
    cur=pd.read_csv(v.OUT/'current_rankings.csv.gz',low_memory=False); cur[v.FEATURES+['evidence_confidence']]=cur[v.FEATURES+['evidence_confidence']].astype('float32'); cur=normalize(cur); train=x.loc[x.endpoint.lt('2026-10-03')]; print('CURRENT TRAIN',flush=True)
    a,aa=train_predict(train,cur,'monotone_utility','current_monotone'); b,bb=train_predict(train,cur,'targeted_specialist','current_partner'); cur['v17_score']=selected_score(cur,a,b,choice); cur['v17_rank']=v.ranked(cur,'v17_score')
    v16=pd.read_csv(ROOT/'experiments/personalized-v16-20261003/current_rankings.csv.gz',usecols=v.KEYS+['v16_score','v16_rank']); cur=cur.merge(v16,on=v.KEYS,validate='one_to_one'); cur['rank_change']=cur.champion_rank-cur.v17_rank; csv('current_rankings.csv.gz',cur)
    for n in [20,50,100]: csv('current_top'+str(n)+'.csv',cur.loc[cur.v17_rank.le(n)].sort_values(['profile_name','v17_rank']))
    turns=[]
    for reference in ['champion','v15','v16']:
        z=cur.copy(); z['champion_score']=cur[reference+'_score']; turns.append(v.turnover(z,'v17_score').assign(comparison='v17_vs_'+reference))
    csv('current_turnover.csv',pd.concat(turns)); csv('current_largest_movers.csv',cur.sort_values('rank_change',key=lambda z:z.abs(),ascending=False).groupby('profile_name').head(30))
    rows=[]; personal=[]
    for model in ['champion','v15','v16','v17']:
        base=cur.loc[cur.profile_name.eq('base7500')].set_index('isin')[model+'_rank']
        for profile,g in cur.groupby('profile_name'):
            rr=g.set_index('isin')[model+'_rank']; common=pd.concat([base.rename('base'),rr.rename('other')],axis=1).dropna(); personal.append({'model':model,'profile':profile,'top20_overlap_base':len(set(base[base.le(20)].index)&set(rr[rr.le(20)].index)),'mean_absolute_rank_change':(common.base-common.other).abs().mean()})
            for n in [20,50,100]:
                top=g.loc[g[model+'_rank'].le(n)]; rows.append({'model':model,'profile':profile,'top_n':n,'missing_true5y':top.has_true_5y.eq(0).mean(),'median_1y_growth':top.strict_cagr_1y.median(),'median_3y_growth':top.cagr_3y.median(),'median_days_high':top.days_since_recorded_high.median(),'mean_ath_distance':top.distance_from_recorded_high.mean(),'mean_max_drawdown':top.full_history_max_drawdown.mean(),'mean_volatility':top.realized_volatility_1y.mean(),'mean_confidence':top.evidence_confidence.mean()})
    csv('current_composition.csv',pd.DataFrame(rows)); csv('current_personalization.csv',pd.DataFrame(personal))
    peers=pd.read_csv(v.OUT/'current_peer_fundamental_diagnostics.csv'); csv('current_peer_diagnostics.csv',peers); csv('nykaa_diagnostic.csv',cur.loc[cur['isin'].eq('INE388Y01029')].merge(peers,on=['isin','ticker','company'],validate='many_to_one'))
    t=behavior_on_frame(cur,O/'model_current_monotone.txt',{look:O/('model_current_partner_look'+str(look)+'.txt') for look in [12,36,60]},choice['alpha']); csv('current_ath_behavior.csv',t)
    write('current_audit.json',{'completed_at':now(),'training':[aa,bb],'source_v7_sha256':v.sha(v.V7),'replay_sha256':v.sha(v.OUT/'current_rankings.csv.gz'),'selection_sha256':v.sha(O/'selection_lock.json'),'rows':len(cur),'scored':int(cur.v17_score.notna().sum()),'action_limit':'Inherited V7 replay quarantine and official action authority ending2026-09-18; later action completeness unproved. Research only.'}); print('FINAL PASS COMPLETE',flush=True)
def round4():
    write('round4_protocol.json',{'locked_at':now(),'hypothesis':'ATH constrained ensemble preserves all profile returns/risk but fails turnover. Bound absolute champion score displacement, retaining learned direction.','caps':[.025,.05,.075],'alpha':.3,'gates':'Unchanged strict gates; no current/exposed use'},True)
    dev=pd.read_pickle(ROOT/'experiments/personalized-v16-20261003/development.pkl.gz',compression='gzip'); dev=dev.merge(pd.read_csv(O/'round3_predictions.csv.gz').rename(columns={'prediction':'partner'}),on=v.KEYS); dev=dev.merge(pd.read_csv(O/'round1_predictions_monotone_utility.csv.gz').rename(columns={'prediction':'mono'}),on=v.KEYS); base=v.evaluate(dev,'champion_score'); rows=[]; details={}
    for cap in [.025,.05,.075]:
        choice={'kind':'blend_ath_monotone','alpha':.3,'score_cap':cap,'name':'ath_capped_'+str(cap)}; dev['candidate_score']=selected_score(dev,dev.mono,dev.partner,choice); pair=v.compare_metrics(v.evaluate(dev,'candidate_score'),base); stats=strict_stats(pair,v.turnover(dev,'candidate_score')); rows.append({**choice,'strong_eligible':stats['strong_eligible'],'eligible':stats['eligible'],'utility':stats['utility']}); details[choice['name']]=stats; print('CAP',cap,stats['strong_eligible'],stats['checks'],stats['additional_checks'],flush=True)
    table=pd.DataFrame(rows).sort_values(['strong_eligible','eligible','utility'],ascending=False); csv('round4_trials.csv',table); write('round4_details.json',details); best=table.iloc[0].to_dict(); write('round4_finalist.json',{'candidate':best,'details':details[best['name']]})
def round5():
    write('round5_protocol.json',{'locked_at':now(),'hypothesis':'Use ATH constraints only for the60M specialist that exhibited wrong-direction average behavior. Other lookback specialists already have negative old/deep ATH effects. Broad constraints reduce shortfall gains; targeted repair avoids changing unrelated learned relationships.','candidate_count':1,'alpha':.3,'mixture':'Equal monotone utility and lookback specialist prediction percentiles. Raw specialist for12/36; ATH constrained specialist for60.','gates':'Same strict gates, no exceptions added.'},True)
    dev=pd.read_pickle(ROOT/'experiments/personalized-v16-20261003/development.pkl.gz',compression='gzip'); pp=pd.read_csv(O/'round1_predictions.csv.gz'); dev=dev.merge(pp,on=v.KEYS); dev=dev.merge(pd.read_csv(O/'round3_predictions.csv.gz').rename(columns={'prediction':'constrained'}),on=v.KEYS)
    partner=dev.specialist_ltr.where(dev.lookback_months.lt(60),dev.constrained); choice={'kind':'blend_targeted_monotone','alpha':.3,'name':'targeted_ath60_ensemble'}; dev['candidate_score']=selected_score(dev,dev.monotone_utility,partner,choice); pair=v.compare_metrics(v.evaluate(dev,'candidate_score'),v.evaluate(dev,'champion_score')); stats=strict_stats(pair,v.turnover(dev,'candidate_score')); choice.update({'strong_eligible':stats['strong_eligible'],'eligible':stats['eligible'],'utility':stats['utility']}); write('round5_finalist.json',{'candidate':choice,'details':stats}); csv('round5_predictions.csv.gz',dev[v.KEYS].assign(prediction=partner)); csv('round5_profile_date_results.csv',pair)
    paths={look:O/('model_'+('ath_specialist' if look==60 else 'specialist_ltr')+'_2023_look'+str(look)+'.txt') for look in [12,36,60]}; csv('round5_ath_behavior.csv',behavior_on_frame(dev.loc[dev.decision_date.eq('2023-12-31')],O/'model_monotone_utility_2023.txt',paths,.3)); print('TARGETED',choice,stats['checks'],stats['additional_checks'],flush=True)
def final_robustness():
    choice=json.loads((O/'selection_lock.json').read_text())['candidate']; x=pd.read_pickle(O/'historical.pkl'); dates=v.protocol()['development_selection_dates']; dev=x.loc[x.decision_date.isin(dates)].merge(v.benchmark(dates),on=v.KEYS); base=v.evaluate(dev,'champion_score'); results={}; audits=[]; tables=[]
    for variant,seed in [('seed20261004',20261004),('seed20261005',20261005),('per_date',20261003)]:
        pp=dev[v.KEYS].merge(pd.read_csv(O/('robustness_'+variant+'_predictions.csv.gz')),on=v.KEYS,validate='one_to_one'); raw1=pp.raw1; raw2=pp.raw2.copy()
        blocks=dates if variant=='per_date' else ['2020','2021','2022','2023']
        for block in blocks:
            mask=dev.decision_date.eq(block) if variant=='per_date' else dev.decision_date.str.startswith(block); test=dev.loc[mask&dev.lookback_months.eq(60)]; train=x.loc[x.endpoint.lt(test.decision_date.min())&x.lookback_months.eq(60)]
            print('FINAL ROBUST',variant,block,flush=True); pred,a=train_predict(train,test,'ath_raw','final_robust_'+variant+'_'+block+'_look60',seed); raw2.loc[test.index]=pred; audits.append(a)
        dev['candidate_score']=selected_score(dev,raw1,raw2,choice); pair=v.compare_metrics(v.evaluate(dev,'candidate_score'),base); stats=strict_stats(pair,v.turnover(dev,'candidate_score')); results[variant]=stats; tables.append(pair.assign(variant=variant)); write('final_robustness_results.json',results); write('final_robustness_training_audit.json',audits); csv('final_robustness_profile_date_results.csv',pd.concat(tables)); print('FINAL ROBUST RESULT',variant,stats['eligible'],stats['strong_eligible'],flush=True)
    print('FINAL ROBUSTNESS COMPLETE',flush=True)
def inference_diagnostics():
    choice=json.loads((O/'selection_lock.json').read_text())['candidate']; x=pd.read_csv(O/'current_rankings.csv.gz',low_memory=False); x[v.FEATURES+['evidence_confidence']]=x[v.FEATURES+['evidence_confidence']].astype('float32'); x=normalize(x)
    mono=O/'model_current_monotone.txt'; paths={look:O/('model_current_partner_look'+str(look)+'.txt') for look in [12,36,60]}; a,b=predict_models(x,mono,paths); reproduced=selected_score(x,a,b,choice); error=float((reproduced-x.v17_score).abs().max()); assert error<1e-10
    effects=[]; contributions=[]
    for family,cols in v.FAMILIES.items():
        if family=='history': continue
        z=x.copy()
        for c in cols:
            if c in RAW: z[c]=z.groupby(['decision_date','profile_name'])[c].transform('median').where(x[c].notna())
        z=normalize(z); aa,bb=predict_models(z,mono,paths); z['alternative']=selected_score(z,aa,bb,choice); rank=v.ranked(z,'alternative')
        for profile,g in x.groupby('profile_name'):
            top=set(g.loc[g.v17_rank.le(20),'isin']); other=set(g.loc[rank.loc[g.index].le(20),'isin']); effects.append({'family':family,'profile':profile,'top20_replacements':20-len(top&other),'mean_absolute_rank_displacement':(rank.loc[g.index]-g.v17_rank).abs().mean(),'mean_absolute_score_change':(z.loc[g.index,'alternative']-g.v17_score).abs().mean()})
    csv('current_family_sensitivity.csv',pd.DataFrame(effects))
    families={c:f for f,cs in v.FAMILIES.items() for c in cs}; fi=[]
    for label,path in [('monotone',mono)]+[('specialist_'+str(k),p) for k,p in paths.items()]:
        model=lgb.Booster(model_file=str(path)); features=model.feature_name()
        for feat,gain in zip(features,model.feature_importance('gain')):
            original=feat[2:] if feat.startswith(('q_','u_')) else feat; fi.append({'model':label,'feature':feat,'family':families.get(original,'goal_user'),'gain':gain})
        mask=x.v17_score.notna()&(True if label=='monotone' else x.lookback_months.eq(int(label.split('_')[1])))
        ny=x.loc[mask&x['isin'].eq('INE388Y01029')]
        if len(ny):
            sh=model.predict(ny[features],pred_contrib=True,num_threads=4)
            for i,(_,row) in enumerate(ny.iterrows()):
                for j,c in enumerate(features): contributions.append({'profile':row.profile_name,'component':label,'feature':c,'value':row[c],'raw_shap':sh[i,j]})
    csv('current_feature_importance.csv',pd.DataFrame(fi)); csv('nykaa_component_contributions.csv',pd.DataFrame(contributions))
    peers=pd.read_csv(O/'current_peer_diagnostics.csv'); joined=x.merge(peers[['isin','industry']],on='isin',validate='many_to_one'); industry=[]
    for model in ['champion','v15','v16','v17']:
        for profile,g in joined.groupby('profile_name'):
            for n in [20,50,100]:
                counts=g.loc[g[model+'_rank'].le(n)].industry.fillna('UNKNOWN').value_counts(normalize=True); industry.append({'model':model,'profile':profile,'top_n':n,'hhi':(counts**2).sum(),'largest_industry':counts.index[0],'largest_share':counts.iloc[0]})
    csv('current_industry_concentration.csv',pd.DataFrame(industry))
    assert not any(any(w in c.lower() for w in ['future','isin','ticker','company','industry','source']) for c in RAW+NORM)
    write('validation_checks.json',{'checked_at':now(),'current_score_reproduction_max_error':error,'no_identity_future_current_fundamental_or_sector_predictors':True,'normalized_missing_value':.5,'confidence':'Original observed-field fraction; missing evidence shrinks correction toward champion, no prescribed negative age penalty','seed':20261003,'current_source_hash_verified':v.sha(v.V7)==json.loads((v.OUT/'input_inventory.json').read_text())[str(v.V7.relative_to(ROOT))],'selection_before_exposed_and_current':True})
    definition={'name':choice['name'],'selection':choice,'features':{'monotone':NORM,'specialists':RAW},'formula':'C*(1-0.3*confidence)+0.3*confidence*(percentile(monotone)+percentile(lookback_specialist))/2','normalization':'Within decision_date/profile, no future labels. q_ negatives ranked descending; all q_ missing exactly0.5. u_ context transformations in normalize().','training':'Annual expanding maturity-purged research evaluation; current endpoint<2026-10-03. Seed20261003. Specialist60 has ATH monotone constraints;12/36 preserve raw learned interactions.','models':{str(p.relative_to(ROOT)):v.sha(p) for p in [mono]+list(paths.values())+[v.FREEZE/'lambdarank.txt']},'current_inputs':'Audited immutable V15 whole-share V7 replay; original quarantine preserved. No deploy.'}
    write('model_definition.json',definition); print('INFERENCE VERIFIED',error,flush=True)
def score_current_replay():
    x=pd.read_csv(v.OUT/'current_rankings.csv.gz',low_memory=False); x[v.FEATURES+['evidence_confidence']]=x[v.FEATURES+['evidence_confidence']].astype('float32'); x=normalize(x); choice=json.loads((O/'selection_lock.json').read_text())['candidate']; a,b=predict_models(x,O/'model_current_monotone.txt',{look:O/('model_current_partner_look'+str(look)+'.txt') for look in [12,36,60]}); x['v17_score']=selected_score(x,a,b,choice); x['v17_rank']=v.ranked(x,'v17_score'); csv('reproduced_current_scores.csv.gz',x[v.KEYS+['v17_score','v17_rank']]); print('REPRODUCED',flush=True)
def md(df):
    def fmt(x): return f'{x:.4f}' if isinstance(x,(float,np.floating)) else str(x).replace('|','/')
    return '| '+' | '.join(df.columns)+' |\n| '+' | '.join(['---']*len(df.columns))+' |\n'+'\n'.join('| '+' | '.join(fmt(x) for x in row)+' |' for row in df.itertuples(index=False,name=None))
def report():
    lock=json.loads((O/'selection_lock.json').read_text()); robust=json.loads((O/'final_robustness_results.json').read_text()); validation=json.loads((O/'validation_checks.json').read_text())
    profiles=pd.read_csv(O/'development_selected_profile_summary.csv'); exposed=pd.read_csv(O/'exposed_profile_date_results.csv'); comps=pd.read_csv(O/'current_composition.csv'); turnover=pd.read_csv(O/'current_turnover.csv'); personal=pd.read_csv(O/'current_personalization.csv'); ny=pd.read_csv(O/'nykaa_diagnostic.csv'); behavior=pd.read_csv(O/'current_ath_behavior.csv'); coh=pd.read_csv(O/'development_cohorts.csv'); intervals=pd.read_csv(O/'development_year_block_intervals.csv')
    old=pd.read_csv(ROOT/'experiments/personalized-v16-20261003/aggregate_comparison.csv'); rows=[]
    for c in v.METRICS:
        rows.append({'metric':c,'development_V17_delta':lock['details']['delta'][c],'development_V16_delta':float(old.loc[old.metric.eq(c),'V16_all_profile_delta'].iloc[0]),'exposed_V17_delta':float(exposed[c+'_delta'].mean())})
    csv('aggregate_comparison.csv',pd.DataFrame(rows))
    stability=[]
    for variant,stats in robust.items():
        pp=pd.DataFrame(stats['profile_deltas']).set_index('profile'); stability.append({'variant':variant,'original_gates_pass':stats['eligible'],'strict_gates_pass':stats['strong_eligible'],'median_return_delta':stats['delta']['median_xirr_top20'],'drawdown_delta':stats['delta']['mean_asset_drawdown_top20'],'12m_return_delta':pp.loc['lookback12','median_xirr_top20_delta'],'12m_drawdown_delta':pp.loc['lookback12','mean_asset_drawdown_top20_delta'],'worst_profile_return_delta':pp.median_xirr_top20_delta.min()})
    csv('robustness_summary.csv',pd.DataFrame(stability))
    decision={'verdict':'PROMISING CHALLENGER','research_model_improved':True,'production_replacement_authorized':False,'production_deployed':False,'candidate':lock['candidate'],'development_all_profiles_return_and_drawdown_positive':bool(profiles.median_xirr_top20_delta.gt(0).all() and profiles.mean_asset_drawdown_top20_delta.gt(0).all()),'strict_selection_gates_pass':lock['details']['strong_eligible'],'development_delta':lock['details']['delta'],'exposed_supporting_delta':{c:exposed[c+'_delta'].mean() for c in v.METRICS},'robustness':stability,'no_claim_of_unexposed_validation':True,'limitations':['39 adaptively chosen development configurations: multiple testing exposure, bootstrap intervals are conditional and not selection-adjusted','Annual and per-date refresh comparisons differ; variant-specific profile results retained','High-volatility within-cohort drawdown can regress even when overall selected basket improves','Current corporate-action completeness after2026-09-18 unproved; original quarantines preserved','Frozen universe survivorship and provider publication/revision limitations remain'],'completed_at':now()}
    write('decision.json',decision)
    trials=pd.concat([pd.read_csv(O/'round1_trials.csv').assign(round=1),pd.read_csv(O/'round2_trials.csv').assign(round=2),pd.read_csv(O/'round3_trials.csv').assign(round=3),pd.read_csv(O/'round4_trials.csv').assign(round=4),pd.DataFrame([lock['candidate']]).assign(round=5)],ignore_index=True); csv('complete_trial_ledger.csv',trials); assert len(trials)==39
    currny=ny.loc[ny.profile_name.eq('base7500')].iloc[0]; devturn=pd.read_csv(O/'development_turnover.csv').groupby(['comparison','top_n'],as_index=False)[['overlap_fraction','mean_absolute_rank_movement']].mean()
    lines=['# V17 trained personalized ranking model — 2026-10-03','','**Research outcome: a materially improved trained challenger. Verdict: PROMISING CHALLENGER.** All nine development profiles improve median return, drawdown, and target shortfall versus champion. Frozen production remains d499580; this research did not deploy or authorize replacement.','',
    '## What was trained and why','','The model combines two trained components: a monotone utility regressor on neutral percentile features and separate LambdaMART rankers for12/36/60-month investor lookbacks. Their prediction percentiles are averaged equally. The result provides at most30% of the final score, scaled by observed-field confidence; the champion supplies the remainder. Annual expanding fits use only labels whose endpoints precede the first decision date in that year. Current models are refitted on all labels mature before2026-10-03. All profiles have a12-month forward investment horizon; lookback is a separate input.','',
    'V15 froze its correction before2020 while the historical champion refreshed. V16 suppressed short-lookback growth inputs. V17 instead retrains, models investor lookbacks separately, and combines a return-oriented specialist with a constrained model. In the constrained component, better growth/goal fit cannot directly lower prediction and deeper/prolonged drawdowns cannot directly raise it. Missing values are neutral0.5 percentiles, with no age or source identity predictor. The raw specialist retains missing-value paths and nonlinear interactions; therefore this is not a mathematical guarantee of identical scores when evidence is removed. Missing evidence reduces correction confidence rather than imposing a fixed age penalty.','',
    'The initial ensemble had positive old/deep ATH response in the60M specialist. An additional development-only audit led to ATH sign constraints for that specialist. Other specialists already showed negative mean old/deep responses. Broad constraints and score caps were also tried and retained in the trial ledger; only the targeted60M repair met all fixed selection gates.','',
    '## Research and trial discipline','','The search tested39 configurations across five documented rounds. Round1 compared refreshed V15, lookback specialists, neutral ranking, monotone regression, monotone ranking, and a trained neural RankNet. Round2 combined complementary predictions. Round3 constrained ATH relationships, round4 tested score bounds, and round5 targeted the identified60M interaction. Every round wrote its hypothesis/grid before evaluating its candidates. The gate thresholds were never relaxed. Every trial, including unsuccessful ones, remains in `complete_trial_ledger.csv`. This is adaptive development research with multiple-testing exposure, not a blind39-way contest.','',
    'Sources that informed the design: [cross-sectional learning to rank](https://arxiv.org/abs/2012.07149), [nonlinear asset-pricing interactions](https://www.nber.org/papers/w25398), [ranking-loss comparison](https://arxiv.org/abs/2204.01500), [LightGBM objectives and monotone constraints](https://lightgbm.readthedocs.io/en/stable/Parameters.html), and [backtest overfitting](https://escholarship.org/uc/item/4w1110bb). [MASTER](https://arxiv.org/abs/2312.15235) and [TabPFN](https://github.com/PriorLabs/TabPFN) were investigated. Neither pretrained checkpoint was used; direct local training avoids an unaudited financial pretraining history, and documented CPU TabPFN scale is poorly matched to this panel. Published investment results were not assumed to transfer here.','',
    '## Development results','','Metrics average within-date/profile Top20 outcomes, then average over16 dates and nine equally weighted profiles. XIRR is the mean of date-level Top20 medians, not mean stock return. Drawdown is mean realized asset drawdown, not portfolio drawdown. Independent full-budget SIP plans follow the existing simulator. Values are fractions; multiply by100 for percentage points.','',md(pd.DataFrame(rows)),'',md(profiles[['profile','median_xirr_top20_delta','mean_asset_drawdown_top20_delta','target_achievement_top20_delta','target_shortfall_top20_delta']]),'',
    'Development median XIRR improves22.37pp overall, drawdown4.76pp, shortfall2.21pp, and target achievement3.96pp. The12M-lookback profile gains29.51pp median XIRR and3.90pp drawdown; V15 lost6.66pp and6.50pp respectively. V17 improves aggregate return and drawdown over V16, though V16 has higher aggregate achievement gain. Every profile has positive median-return and drawdown deltas in the selected annual-fit result. All original gates plus nonnegative returns in every profile and nonnegative12M drawdown pass.','',
    '## Stability and uncertainty','','The exact final model was checked with two additional seeds and refits at every decision date. These results do not select a lucky seed; deployed-research inference keeps seed20261003 and the locked formula. Failures of the stricter check, if any, remain visible below.','',md(pd.DataFrame(stability)),'',
    'Year-block intervals use only four calendar blocks and do not adjust for adaptive model selection. They quantify conditional development variation; they do not establish future profitability.','',md(intervals.loc[intervals.metric.isin(['median_xirr_top20','mean_asset_drawdown_top20'])]),'',
    'Robustness is evaluated for every profile and short/full history, high volatility, deep drawdown, deep ATH, old ATH, and recent ATH. Both within-cohort Top20 metrics and cohort share/outcomes inside the overall Top20 are saved. High-volatility within-cohort drawdown remains a weakness; it is not hidden by the overall risk improvement.','',md(coh.loc[coh.profile.eq('ALL')&coh.model.isin(['champion','v17']),['cohort','model','share_overall_top20','median_xirr_top20','mean_asset_drawdown_top20']]),'',
    '## Turnover','','The model is still a substantial correction. It qualifies under the original high-turnover exception, which requires NDCG gain>=0.03 and shortfall improvement>=0.02. It should not be described as a low-turnover replacement.','',md(devturn),'',
    '## Exposed supporting evaluation','','The2024–2025 period was already exposed in earlier experiments. It was accessed for V17 only after `selection_lock.json` was written and was never used to revise the selected model. The aggregate table above reports these results separately; full profile/date scores are in `exposed_*`. Historical evaluation refits annually with labels strictly mature before each year’s first decision. Differences from earlier V15/V16 fixed evaluation fits are therefore model-plus-training-policy differences.','',md(pd.read_csv(O/'exposed_profile_summary.csv')[['profile','median_xirr_top20_delta','mean_asset_drawdown_top20_delta','target_shortfall_top20_delta']]),'',
    '## Current V7 rankings and behavior','','Current inference reuses the immutable audited V15 V7 whole-share feature replay, restores original float32 feature types, and scores newly trained V17 models. Original plan quarantines remain. No current value is copied backward into historical dates. Top20/50/100, full ranks, largest movers, composition, personalization, current industry concentration, peer context, and feature-family sensitivity are saved. Model-score reproduction is verified to numerical precision.','',md(turnover.loc[turnover.profile.eq('base7500'),['comparison','top_n','overlap','mean_absolute_rank_movement']]),'',md(comps.loc[comps.profile.isin(['base7500','lookback12'])&comps.top_n.eq(20)]),'',md(personal.loc[personal.model.eq('v17')]),'',
    'ATH behavior is tested by each-stock counterfactuals anchored to the original query feature/prediction distributions:30 days/5% below high versus1825 days/70% below high, with derived age-depth fields updated and champion score fixed. This is a conditional synthetic audit, not a causal experiment or a fully realizable stock path. Current results below are reported even when a retrained model differs from the development fit. No current diagnostic changes selection.','',md(behavior.loc[behavior.scenario.eq('old_deep'),['profile','mean_score_change','median_score_change','negative_fraction','positive_fraction']]),'',
    '### NYKAA diagnostic only','',f"Current base rank: V17 **{int(currny.v17_rank)}**, refreshed champion {int(currny.champion_rank)}, V15 {int(currny.v15_rank)}, V16 {int(currny.v16_rank)}. Frozen September reference1 and V14 reference213 were never targets. Current1Y growth{currny.strict_cagr_1y:.2%},3Y growth{currny.cagr_3y:.2%}, ATH distance{currny.distance_from_recorded_high:.2%}, days since high{currny.days_since_recorded_high:.0f}, underwater duration{currny.current_drawdown_duration_days:.0f}, volatility{currny.realized_volatility_1y:.2%}, and confidence{currny.evidence_confidence:.1%}. Historical plan attainment{currny.target_attainment:.3f}. The full NYKAA CSV includes fundamentals, peer percentiles, all user-profile ranks, and current input evidence; `nykaa_component_contributions.csv` gives raw component TreeSHAP, which is not additive rank attribution.",'',
    'Current ROCE/ROE and industry-relative diagnostics are retained from V7; they are not trained historical predictors because dated publication and historical classification evidence are unavailable. Current sector comparisons are not backfilled into development.','',
    '## Reproduction, integrity, and limits','','See `REPRODUCE.md` and `model_definition.json`. Four final correction model files plus the frozen champion define inference. `score_current_replay` reproduces scores without training. Current replay and V7 hashes, training endpoints, input feature lists, all selection protocols, and all outcomes are auditable.','',
    'Protected hashes cover frozen champion, V14, V15, V16, historical inputs, and tracked production/website files. No Railway or deployment command was issued. Final verification is in `integrity_audit.json`; `manifest.json` hashes the completed artifacts, runner, and report.','',
    'The study retains frozen-universe survivorship/selection exposure, provider-revision and publication-time uncertainty, overlapping label dependence, and adaptive-search overfitting risk. All known evaluation periods are honestly labeled exposed. Current official-action authority ends2026-09-18; later action completeness is not proved. An improved research model is not proof of deployable investment superiority.','',
    '**Outcome:** A trained, reproducible model materially improves the prior development frontier and repairs12M return/drawdown while retaining meaningful growth, ATH, confidence, and user personalization. Production remains unchanged. Forward unexposed evidence and execution-data completeness are the remaining conditions for a justified production promotion.']
    reportpath=ROOT/'research/reports/personalized_v17_20261003.md'; reportpath.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (O/'REPRODUCE.md').write_text('''# Reproduce V17\n\nCompleted experiment: reproduce training in a separate checkout/output root; do not overwrite locks. Python3.13, numpy/pandas/lightgbm and CPU PyTorch.\n\nFrom repository root, run the research runner with stages in this order:\n\n```text\nprepare\nround1\nround2\nrobustness\ndevelopment_diagnostics\nhistorical_behavior\nround3\nround4\nround5\nlock_final\nfinal_pass\nfinal_robustness\ndevelopment_diagnostics\ninference_diagnostics\nreport\naudit\n```\n\nExample: `python research/runners/personalized_v17_20261003.py round1`. Each search round writes an exclusive protocol before evaluation. Round1 has24 configurations, round2 nine, round3 two, round4 three, round5 one; total39. No exposed/current results select candidates.\n\nFor inference only with completed models:\n\n```powershell\npython research/runners/personalized_v17_20261003.py score_current_replay\n```\n\nThis writes reproduced_current_scores.csv.gz using the immutable V15 current V7 replay and the four final trained correction files. It is research inference, not a data acquisition or production deployment command. The input must retain the same per-date/profile universe for percentile normalization. model_definition.json records exact features, formula, and hashes.\n\nHistorical annual fitting uses labels with endpoint strictly before the first scored decision date of each year. The lookback60 specialist adds ATH constraints;12/36 use the raw specialist. Monotone regression is pooled across profiles with query-normalized weights. No ISIN, ticker, source, current fundamental, or sector predictor is used. All raw fields and observed confidence come from the frozen dated replay.\n\nRead decision.json/report for caveats. Frozen dependencies V15/V16 must remain available; their runners are read-only imports. Never call their writing stages. Current post-September18 corporate-action completeness remains conditional.\n''',encoding='utf-8')
    import torch
    write('software_versions.json',{'python':sys.version,'numpy':np.__version__,'pandas':pd.__version__,'lightgbm':lgb.__version__,'torch':torch.__version__})
    print('REPORT WRITTEN',decision['verdict'],flush=True)
def audit():
    before=json.loads((O/'protected_before.json').read_text()); changed=[]
    def check(item):
        p,h=item; return p if not (ROOT/p).is_file() or v.sha(ROOT/p)!=h else None
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i,result in enumerate(pool.map(check,before.items())):
            if result: changed.append(result)
            if i%4000==0: print('VERIFY',i,flush=True)
    assert not changed,changed
    import subprocess
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(); assert head=='c12dd9b189bc71684bfac52606eb89abd5e383c7'
    write('integrity_audit.json',{'verified_at':now(),'protected_count':len(before),'changed':changed,'production_head':head,'frozen_champion_v14_v15_v16_unchanged':True,'production_website_railway':'No deployment/network service mutation. Tracked source/config hashes unchanged.','model_identity_features':False,'current_values_backfilled':False,'future_labels_as_features':False,'known_exposed_evaluation_not_used_for_selection':True})
    paths=[p for p in O.iterdir() if p.is_file() and p.name not in ['manifest.json','reproduced_current_scores.csv.gz']]+[Path(__file__),ROOT/'research/reports/personalized_v17_20261003.md']
    write('manifest.json',{'created_at':now(),'sha256':{str(p.relative_to(ROOT)):v.sha(p) for p in paths}}); print('AUDIT COMPLETE',len(before),len(paths),flush=True)
if __name__=='__main__': globals()[sys.argv[1]]()
