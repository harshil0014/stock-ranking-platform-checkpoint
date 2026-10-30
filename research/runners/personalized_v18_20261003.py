"""Bounded V18 research tournament against frozen V17 and production recipe."""
import sys,json,gc,hashlib,subprocess
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import lightgbm as lgb
import personalized_v17_20261003 as s
v=s.v; ROOT=v.ROOT; V17=s.O; O=ROOT/'experiments/personalized-v18-20261003'; O.mkdir(exist_ok=True)
FAMILIES=['xendcg','huber_return','median_return','multitask','recent_utility','regime_utility','specialist_utility','robust_shallow','neural_moe','return_ranker']
REGIME=['market_growth','market_volatility','market_ath_depth','market_momentum']
def now():return datetime.now(timezone.utc).isoformat()
def write(n,x,exclusive=False):
    with (O/n).open('x' if exclusive else 'w',encoding='utf-8') as f:json.dump(v.clean(x),f,indent=2,allow_nan=False)
def csv(n,x):x.to_csv(O/n,index=False,compression={'method':'gzip','mtime':0} if n.endswith('.gz') else None)
def features(x):
    x=s.normalize(x)
    for out,c in zip(REGIME,['strict_cagr_1y','realized_volatility_1y','distance_from_recorded_high','momentum_6m']):x[out]=x.groupby('decision_date')[c].transform('median').fillna(0).astype('float32')
    return x
def prepare():
    write('protocol_lock.json',{'locked_at':now(),'families':FAMILIES,'betas':[.05,.10],'seed':20261003,'annual_training':'All mature endpoints strictly before first target date in each year; expanding2015+ history. Development2020–2023; earlier trainable decisions get post-selection contextual evaluation. Earliest dates without mature labels explicitly unavailable.','selection':'Must pass original V17 strict champion gates AND V17-relative aggregate return>=0, drawdown>=-0.005, achievement>=-0.005, shortfall<=0.0025, NDCG>=0; every profile return>=-0.025 and drawdown>=-0.01; utility gain>=0.002; improvement utility in >=3 of4 calendar years. Utility uses .45NDCG+.20achievement-.25shortfall+.10drawdown+.10medianXIRR; meanXIRR zero. Rank eligible by utility then lower beta.','round2':'Exactly top3 round1 families by development utility, independent of eligibility; equal pairs and triple, beta0.05/0.10. Additional seed-averagedV17, component-agreement confidence, and short-history confidence controls. Stop after this registered space and robustness; no threshold chasing.','stopping':'10 trained families,20 single-model strengths,8 ensemble combinations,6 baseline/confidence controls; maximum34 selection configurations. Finalist robustness alternate seed and per-date refit; if no defensible eligible finalist survives, V17 remains best.','exposed_current_policy':'No2024–2025 outcome or current inference until final selection lock; previous exposure acknowledged. No identity, current fundamentals/industry, or source shortcuts.','point_in_time_limit':'Price-derived features and maturity-purged labels; fixed-universe survivorship and source-revision limits remain.','fundamentals_peers':'Only if dated source available. Existing panels have no valid dated fundamentals/industry history; current-only diagnostic layer retained.','training_parameters':{'trees':160,'learning_rate':.035,'leaves':15,'depth':4,'min_child':300,'l2':40},'neural':'Two-expert MLP32/16, soft gate over user/regime inputs; pairwise utility + pointwise utility;8 epochs,600 pairs/query; seed fixed.'},True)
    baseline=json.loads((V17/'protected_before.json').read_text()); paths=list(V17.rglob('*'))+[ROOT/'research/runners/personalized_v17_20261003.py',ROOT/'research/reports/personalized_v17_20261003.md']
    for p in paths:
        if p.is_file():baseline[str(p.relative_to(ROOT))]=v.sha(p)
    def check(item):
        p,h=item;return p if not (ROOT/p).is_file() or v.sha(ROOT/p)!=h else None
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i,result in enumerate(pool.map(check,baseline.items())):
            assert result is None,result
            if i%4000==0:print('PROTECT',i,flush=True)
    write('protected_before.json',baseline,True)
    write('sources.json',[{'url':'https://lightgbm.readthedocs.io/en/stable/Parameters.html','use':'Ranking, quantile, robust regression and constraints.'},{'url':'https://arxiv.org/abs/2312.15235','use':'Market-conditioned feature relevance; adapted as regime features and neural gating, not replication.'},{'url':'https://arxiv.org/abs/2012.07149','use':'Pairwise/listwise asset ranking alternatives.'},{'url':'https://www.nber.org/papers/w25398','use':'Nonlinear return predictors.'},{'url':'https://escholarship.org/uc/item/4w1110bb','use':'Bounded ledger and explicit adaptive development limitations.'}])
    print('PREPARED',flush=True)
def train_predict(train,test,family,tag,seed=20261003):
    t=train.dropna(subset=v.OUTCOME+['enhanced_carry_xirr_score']).sort_values(v.KEYS[1:]+v.KEYS[:1]).reset_index(drop=True); valid=test.champion_score.notna(); pred=pd.Series(np.nan,index=test.index)
    if family=='specialist_utility':
        audits=[]
        for look in [12,36,60]:
            a=t.loc[t.lookback_months.eq(look)]; b=test.loc[test.lookback_months.eq(look)]; p,au=train_predict(a,b,'utility',tag+'_look'+str(look),seed);pred.loc[b.index]=p;audits.append(au)
        return pred,{'specialists':audits}
    cols=s.NORM+(REGIME if family in ['regime_utility','neural_moe'] else []);g=t.groupby(['decision_date','profile_name'],sort=False); groups=g.size().to_numpy(); utility=s.target(t); y=utility.copy();params=dict(n_estimators=160,learning_rate=.035,num_leaves=15,max_depth=4,min_child_samples=300,reg_lambda=40,n_jobs=4,verbosity=-1,random_state=seed,deterministic=True,force_col_wise=True)
    weights=np.repeat(1/groups,groups);weights/=weights.mean()
    if family=='recent_utility':
        age=(pd.Timestamp(test.decision_date.min())-pd.to_datetime(t.endpoint)).dt.days/365.25;weights*=np.exp(-np.log(2)*age/3)
    if family=='robust_shallow':params.update(num_leaves=7,max_depth=3,reg_lambda=100,n_estimators=120)
    if family in ['recent_utility','regime_utility','specialist_utility','utility','robust_shallow']:
        params.update(monotone_constraints=[1]*len(s.POS+s.NEG)+[0]*(len(cols)-len(s.POS+s.NEG)),monotone_constraints_method='advanced')
    if family=='neural_moe':
        import torch
        torch.set_num_threads(4);torch.manual_seed(seed)
        class Net(torch.nn.Module):
            def __init__(self):
                super().__init__();self.experts=torch.nn.ModuleList([torch.nn.Sequential(torch.nn.Linear(len(cols),32),torch.nn.SiLU(),torch.nn.Linear(32,16),torch.nn.SiLU(),torch.nn.Linear(16,1)) for _ in range(2)]);self.gate=torch.nn.Sequential(torch.nn.Linear(len(s.CONTEXT)+len(REGIME),8),torch.nn.SiLU(),torch.nn.Linear(8,2))
            def forward(self,x):return (torch.cat([e(x) for e in self.experts],1)*torch.softmax(self.gate(x[:,-(len(s.CONTEXT)+len(REGIME)):]),1)).sum(1)
        net=Net();optimizer=torch.optim.AdamW(net.parameters(),lr=.001,weight_decay=.02); xx=torch.from_numpy(t[cols].to_numpy(dtype=np.float32));yy=torch.from_numpy(y.to_numpy(dtype=np.float32));rng=np.random.default_rng(seed);offsets=np.r_[0,np.cumsum(groups)]
        for epoch in range(8):
            aa=np.concatenate([rng.integers(offsets[i],offsets[i+1],600) for i in range(len(groups))]);bb=np.concatenate([rng.integers(offsets[i],offsets[i+1],600) for i in range(len(groups))]); order=rng.permutation(len(aa))
            for ids in np.array_split(order,max(1,len(order)//4096)):
                a=aa[ids];b=bb[ids];pa=net(xx[a]);pb=net(xx[b]);delta=yy[a]-yy[b];loss=(torch.nn.functional.softplus(-delta.sign()*(pa-pb))*delta.abs()).mean()+.2*((pa-yy[a])**2).mean();optimizer.zero_grad();loss.backward();optimizer.step()
        net.eval()
        with torch.no_grad():pred.loc[valid]=net(torch.from_numpy(test.loc[valid,cols].to_numpy(dtype=np.float32))).numpy()
        torch.save({'state_dict':net.state_dict(),'features':cols},O/('model_'+tag+'.pt'))
    else:
        if family in ['xendcg','return_ranker']:
            if family=='return_ranker':y=.85*g.future_xirr.rank(pct=True)+.10*g.future_shortfall.rank(pct=True,ascending=False)+.05*g.future_drawdown.rank(pct=True)
            model=lgb.LGBMRanker(objective='rank_xendcg' if family=='xendcg' else 'lambdarank',lambdarank_truncation_level=30,**params);labels=np.minimum(np.floor(y*16),15).astype('int8');model.fit(t[cols],labels,group=groups.tolist())
        elif family=='multitask':
            heads=[('return',g.future_xirr.rank(pct=True),.7),('shortfall',g.future_shortfall.rank(pct=True,ascending=False),.2),('drawdown',g.future_drawdown.rank(pct=True),.1)]; pred.loc[valid]=0
            for name,target,w in heads:
                model=lgb.LGBMRegressor(objective='regression',**params);model.fit(t[cols],target,sample_weight=weights);model.booster_.save_model(str(O/('model_'+tag+'_'+name+'.txt')));pred.loc[valid]+=w*model.predict(test.loc[valid,cols],num_threads=4)
        else:
            objective='regression'
            if family in ['huber_return','median_return']:
                y=np.arcsinh(t.future_xirr.clip(-1,10));objective='huber' if family=='huber_return' else 'quantile';params['alpha']=.9 if family=='huber_return' else .5
            model=lgb.LGBMRegressor(objective=objective,**params);model.fit(t[cols],y,sample_weight=weights)
        if family!='multitask':model.booster_.save_model(str(O/('model_'+tag+'.txt')));pred.loc[valid]=model.predict(test.loc[valid,cols],num_threads=4)
    return pred,{'family':family,'seed':seed,'rows':len(t),'groups':len(groups),'max_endpoint':t.endpoint.max(),'min_decision':test.decision_date.min(),'features':cols}
def data():
    x=features(pd.read_pickle(V17/'historical.pkl'));dates=v.protocol()['development_selection_dates'];dev=x.loc[x.decision_date.isin(dates)].merge(pd.read_csv(V17/'development_scores.csv.gz',usecols=v.KEYS+['champion_score','v17_score']),on=v.KEYS,validate='one_to_one');return x,dev
def pct(dev,raw):return raw.where(dev.champion_score.notna()).groupby([dev.decision_date,dev.profile_name]).rank(pct=True)
def score(dev,signals,choice):
    if choice['family']=='v17':return dev.v17_score.copy()
    if choice['family'].startswith('seed_average'):return (dev.v17_score+signals[choice['family']])/2
    if choice['family']=='confidence_agreement':
        factor=1-choice['beta']*(signals['v17_mono']-signals['v17_partner']).abs();return dev.champion_score+(dev.v17_score-dev.champion_score)*factor
    if choice['family']=='confidence_squared':return dev.champion_score+(dev.v17_score-dev.champion_score)*(1-choice['beta']*(1-dev.evidence_confidence))
    corr=sum(signals[f] for f in choice['family'].split('+'))/len(choice['family'].split('+'));effective=choice['beta']*dev.evidence_confidence
    return dev.v17_score*(1-effective)+corr*effective
def assess(dev,pred,base=None,ref=None):
    z=dev.assign(candidate_score=pred);base=v.evaluate(dev,'champion_score') if base is None else base;ref=v.evaluate(dev,'v17_score') if ref is None else ref;metrics=v.evaluate(z,'candidate_score');champ=v.compare_metrics(metrics,base);against=v.compare_metrics(metrics,ref);stats=s.strict_stats(champ,v.turnover(z,'candidate_score'));p=against.groupby('profile')[[c+'_delta' for c in v.METRICS]].mean();d={c:against[c+'_delta'].mean() for c in v.METRICS};utility=.45*d['ndcg20']+.2*d['target_achievement_top20']-.25*d['target_shortfall_top20']+.1*d['mean_asset_drawdown_top20']+.1*d['median_xirr_top20'];yr=against.assign(year=against.decision_date.str[:4]).groupby('year')[[c+'_delta' for c in v.METRICS]].mean();yu=.45*yr.ndcg20_delta+.2*yr.target_achievement_top20_delta-.25*yr.target_shortfall_top20_delta+.1*yr.mean_asset_drawdown_top20_delta+.1*yr.median_xirr_top20_delta
    checks={'champion_strict':stats['strong_eligible'],'v17_return':d['median_xirr_top20']>=0,'v17_drawdown':d['mean_asset_drawdown_top20']>=-.005,'v17_achievement':d['target_achievement_top20']>=-.005,'v17_shortfall':d['target_shortfall_top20']<=.0025,'v17_ndcg':d['ndcg20']>=0,'profile_return':p.median_xirr_top20_delta.min()>=-.025,'profile_drawdown':p.mean_asset_drawdown_top20_delta.min()>=-.01,'utility_gain':utility>=.002,'three_years':int(yu.gt(0).sum())>=3}
    return {'eligible':all(checks.values()),'checks':checks,'utility_gain':utility,'v17_delta':d,'champion':stats,'year_utility':yu.to_dict(),'v17_profile_deltas':p.reset_index().to_dict('records')},champ,against
def round1():
    x,dev=data();base=v.evaluate(dev,'champion_score');ref=v.evaluate(dev,'v17_score');rows=[];details={};audits=json.loads((O/'training_audit.json').read_text()) if (O/'training_audit.json').exists() else [];allmetrics=[]
    for family in FAMILIES:
        cache=O/('predictions_'+family+'.csv.gz')
        if cache.exists():raw=dev[v.KEYS].merge(pd.read_csv(cache),on=v.KEYS,validate='one_to_one').prediction
        else:
            raw=pd.Series(np.nan,index=dev.index)
            for year in ['2020','2021','2022','2023']:
                test=dev.loc[dev.decision_date.str.startswith(year)];train=x.loc[x.endpoint.lt(test.decision_date.min())];print('TRAIN',family,year,flush=True);p,a=train_predict(train,test,family,family+'_'+year);raw.loc[test.index]=p;audits.append(a);write('training_audit.json',audits)
            csv(cache.name,dev[v.KEYS].assign(prediction=raw))
        for beta in [.05,.10]:
            choice={'family':family,'beta':beta};st,ch,ag=assess(dev,score(dev,{family:pct(dev,raw)},choice),base,ref);name=family+'__'+str(beta);details[name]=st;rows.append({'candidate':name,**choice,'eligible':st['eligible'],'utility_gain':st['utility_gain'],**st['v17_delta']});allmetrics.append(ag.assign(candidate=name));print('RESULT',name,st['eligible'],round(st['utility_gain'],5),[k for k,b in st['checks'].items() if not b],flush=True)
        csv('round1_trials.csv',pd.DataFrame(rows).sort_values(['eligible','utility_gain'],ascending=False));write('round1_details.json',details);csv('round1_vs_v17_profile_date.csv',pd.concat(allmetrics,ignore_index=True))
    print('ROUND1 COMPLETE',flush=True)
def fit_v17(train,test,tag,seed=20261003):
    t=train.dropna(subset=v.OUTCOME+['enhanced_carry_xirr_score']).sort_values(v.KEYS[1:]+v.KEYS[:1]);groups=t.groupby(['decision_date','profile_name'],sort=False).size().to_numpy();valid=test.champion_score.notna();a=pd.Series(np.nan,index=test.index);b=a.copy();params=dict(n_estimators=140,learning_rate=.035,num_leaves=15,max_depth=4,min_child_samples=300,reg_lambda=40,n_jobs=4,verbosity=-1,random_state=seed,deterministic=True,force_col_wise=True)
    m=lgb.LGBMRegressor(objective='regression',monotone_constraints=[1]*len(s.POS+s.NEG)+[0]*len(s.CONTEXT),monotone_constraints_method='advanced',**params);w=np.repeat(1/groups,groups);w/=w.mean();m.fit(t[s.NORM],s.target(t),sample_weight=w);m.booster_.save_model(str(O/('model_'+tag+'_mono.txt')));a.loc[valid]=m.predict(test.loc[valid,s.NORM],num_threads=4)
    for look in [12,36,60]:
        tt=t.loc[t.lookback_months.eq(look)];mask=valid&test.lookback_months.eq(look);pp={**params,**v.PARAMS};signs={'days_since_recorded_high':-1,'current_drawdown_duration_days':-1,'distance_from_recorded_high':1,'old_high_depth':-1,'underwater_depth':-1,'recovery_vs_old_high':-1}
        if look==60:pp.update(monotone_constraints=[signs.get(c,0) for c in s.RAW],monotone_constraints_method='advanced')
        m=lgb.LGBMRanker(objective='lambdarank',**pp);labels=np.minimum(np.floor(s.target(tt,True)*8),7).astype('int8');m.fit(tt[s.RAW],labels,group=tt.groupby(['decision_date','profile_name'],sort=False).size().tolist());m.booster_.save_model(str(O/('model_'+tag+'_look'+str(look)+'.txt')));b.loc[mask]=m.predict(test.loc[mask,s.RAW],num_threads=4)
    return s.selected_score(test,a,b,{'kind':'blend_targeted_monotone','alpha':.3}),{'tag':tag,'max_endpoint':t.endpoint.max(),'min_decision':test.decision_date.min(),'rows':len(t)}

def early_predictions():
    from research.runners import personalized_deeper_championship_v2 as old
    x=features(pd.read_pickle(V17/'historical.pkl'));dates=sorted(d for d in x.decision_date.unique() if d<'2020');outputs=[];audit=json.loads((O/'early_training_audit.json').read_text()) if (O/'early_training_audit.json').exists() else [];unavailable=[]
    for day in dates:
        train=x.loc[x.endpoint.lt(day)].copy();test=x.loc[x.decision_date.eq(day)].copy()
        if train.dropna(subset=v.OUTCOME+['enhanced_carry_xirr_score']).empty:unavailable.append({'date':day,'reason':'No strictly matured prior labels; cannot fit an honest supervised model.'});continue
        cache=O/('early_'+day+'.csv.gz')
        if cache.exists():outputs.append(pd.read_csv(cache));continue
        print('EARLY',day,len(train),flush=True);train['cagr_5y']=train.original_cagr_5y;test['cagr_5y']=test.original_cagr_5y;raw,m=old.old.fit_predict(train,test,old.old.CORE,'lgbm','xirr4',old.old.BASE_PARAMS,old.SEED);m.booster_.save_model(str(O/('model_early_'+day+'_champion.txt')));test['ranker_score']=raw;test['champion_score']=old.hist.blend(test,'ranker_score',.67)
        # Restore V17's safe input representation after the exact champion recipe.
        train['cagr_5y']=x.loc[train.index,'cagr_5y'];test['cagr_5y']=x.loc[test.index,'cagr_5y'];test['v17_score'],au=fit_v17(train,test,'early_'+day);audit.append(au);write('early_training_audit.json',audit);out=test[v.KEYS+['champion_score','v17_score']];csv(cache.name,out);outputs.append(out)
    csv('early_scores.csv.gz',pd.concat(outputs,ignore_index=True));write('early_unavailable.json',unavailable);print('EARLY PREDICTIONS COMPLETE',flush=True)

def v17_variant(dev,variant):
    pp=dev[v.KEYS].merge(pd.read_csv(V17/('robustness_'+variant+'_predictions.csv.gz')),on=v.KEYS,validate='one_to_one'); a=pp.raw1;b=pp.raw2.copy()
    blocks=sorted(dev.decision_date.unique()) if variant=='per_date' else ['2020','2021','2022','2023']
    for block in blocks:
        mask=(dev.decision_date.eq(block) if variant=='per_date' else dev.decision_date.str.startswith(block))&dev.lookback_months.eq(60)&dev.champion_score.notna();m=lgb.Booster(model_file=str(V17/('model_final_robust_'+variant+'_'+block+'_look60.txt')));b.loc[mask]=m.predict(dev.loc[mask,m.feature_name()],num_threads=4)
    return s.selected_score(dev,a,b,{'kind':'blend_targeted_monotone','alpha':.3}),a,b

def signals_for(dev):
    signals={f:pct(dev,dev[v.KEYS].merge(pd.read_csv(O/('predictions_'+f+'.csv.gz')),on=v.KEYS,validate='one_to_one').prediction) for f in FAMILIES}
    for name,file in [('v17_mono','round1_predictions_monotone_utility.csv.gz'),('v17_partner','round5_predictions.csv.gz')]:signals[name]=pct(dev,dev[v.KEYS].merge(pd.read_csv(V17/file),on=v.KEYS,validate='one_to_one').prediction)
    for seed in [20261004,20261005]:signals['seed_average'+str(seed)]=v17_variant(dev,'seed'+str(seed))[0]
    return signals

def round2():
    import itertools
    x,dev=data();del x;gc.collect();base=v.evaluate(dev,'champion_score');ref=v.evaluate(dev,'v17_score');r=pd.read_csv(O/'round1_trials.csv');best=r.sort_values('utility_gain',ascending=False).drop_duplicates('family').family.head(3).tolist()
    choices=[{'family':'+'.join(parts),'beta':beta} for n in [2,3] for parts in itertools.combinations(best,n) for beta in [.05,.10]]
    choices += [{'family':'seed_average'+str(seed),'beta':.5} for seed in [20261004,20261005]]+[{'family':family,'beta':beta} for family in ['confidence_agreement','confidence_squared'] for beta in [.5,1.]]
    if not (O/'round2_lock.json').exists():write('round2_lock.json',{'locked_at':now(),'top3':best,'choices':choices},True)
    signals=signals_for(dev);rows=[];details={};metrics=[]
    for choice in choices:
        st,ch,ag=assess(dev,score(dev,signals,choice),base,ref);name=choice['family']+'__'+str(choice['beta']);details[name]=st;rows.append({'candidate':name,**choice,'eligible':st['eligible'],'utility_gain':st['utility_gain'],**st['v17_delta']});metrics.append(ag.assign(candidate=name));print('ROUND2',name,st['eligible'],round(st['utility_gain'],5),[k for k,b in st['checks'].items() if not b],flush=True)
    csv('round2_trials.csv',pd.DataFrame(rows));write('round2_details.json',details);csv('round2_vs_v17_profile_date.csv',pd.concat(metrics,ignore_index=True));trials=pd.concat([r,pd.DataFrame(rows)],ignore_index=True).sort_values(['eligible','utility_gain'],ascending=False);csv('all_trials.csv',trials)
    write('development_finalists.json',{'candidates':trials.loc[trials.eligible].to_dict('records'),'best_rejected':trials.iloc[0].to_dict(),'count':len(trials)},True);print('ROUND2 COMPLETE',len(trials),'ELIGIBLE',int(trials.eligible.sum()),flush=True)

def robustness():
    finalists=json.loads((O/'development_finalists.json').read_text()); results={};chosen=None
    if finalists['candidates']:
        x,dev=data();base=v.evaluate(dev,'champion_score');audit=[];tables=[]
        for choice in finalists['candidates']:
            passed=True;name=choice['candidate'];results[name]={}
            for variant,seed in [('seed20261004',20261004),('per_date',20261003)]:
                z=dev.copy();z['v17_score'],a,b=v17_variant(z,variant);signals={'v17_mono':pct(z,a),'v17_partner':pct(z,b)}
                if choice['family'].startswith('seed_average'):
                    if variant=='seed20261004':signals[choice['family']]=v17_variant(z,'seed20261005')[0]
                    else:
                        partner_seed=int(choice['family'].replace('seed_average',''));raw=pd.Series(np.nan,index=z.index)
                        for day,g in z.groupby('decision_date'):
                            train=x.loc[x.endpoint.lt(day)];raw.loc[g.index],au=fit_v17(train,g,'robust_seed_average_'+str(partner_seed)+'_'+day,partner_seed);audit.append(au);write('robustness_training_audit.json',audit)
                        signals[choice['family']]=raw
                elif choice['family'] not in ['confidence_agreement','confidence_squared']:
                    for family in choice['family'].split('+'):
                        cache=O/('robust_'+variant+'_'+family+'.csv.gz')
                        if cache.exists():raw=z[v.KEYS].merge(pd.read_csv(cache),on=v.KEYS).prediction
                        else:
                            raw=pd.Series(np.nan,index=z.index);blocks=sorted(z.decision_date.unique()) if variant=='per_date' else ['2020','2021','2022','2023']
                            for block in blocks:
                                test=z.loc[z.decision_date.eq(block) if variant=='per_date' else z.decision_date.str.startswith(block)];train=x.loc[x.endpoint.lt(test.decision_date.min())];print('ROBUST',name,variant,family,block,flush=True);p,au=train_predict(train,test,family,'robust_'+variant+'_'+family+'_'+block,seed);raw.loc[test.index]=p;audit.append(au);write('robustness_training_audit.json',audit)
                            csv(cache.name,z[v.KEYS].assign(prediction=raw))
                        signals[family]=pct(z,raw)
                st,ch,ag=assess(z,score(z,signals,choice),base,v.evaluate(z,'v17_score'));p=ch.groupby('profile')[[c+'_delta' for c in v.METRICS]].mean();st['robust_pass']=bool(st['champion']['eligible'] and p.median_xirr_top20_delta.min()>=-.025 and p.mean_asset_drawdown_top20_delta.min()>=-.01 and p.loc['lookback12','median_xirr_top20_delta']>=0 and p.loc['lookback12','mean_asset_drawdown_top20_delta']>=0 and all(st['checks'][k] for k in ['v17_return','v17_drawdown','v17_achievement','v17_shortfall','v17_ndcg']) and st['utility_gain']>0);results[name][variant]=st;tables.append(ag.assign(candidate=name,variant=variant));write('robustness_results.json',results);csv('robustness_vs_v17_profile_date.csv',pd.concat(tables));print('ROBUST RESULT',name,variant,st['robust_pass'],flush=True)
                if not st['robust_pass']:passed=False;break
            if passed:chosen=choice;break
    else:write('robustness_results.json',{'status':'No eligible new finalist; frozen V17 robustness retained without new selection.'})
    write('selection_lock.json',{'locked_at':now(),'choice':chosen or {'family':'v17','beta':0.,'candidate':'frozen_v17'},'new_model_survived':chosen is not None,'trial_count':finalists['count'],'best_rejected':finalists['best_rejected'],'exposed_outcomes_used_for_selection':False,'research_only':True},True);print('SELECTION LOCKED',chosen or 'V17',flush=True)

def domain_signals(train,test,choice,tag,mono,partners):
    family=choice['family'];signals={};audit=[]
    if family in ['confidence_agreement','confidence_squared']:
        a,b=s.predict_models(test,mono,partners);signals.update(v17_mono=pct(test,a),v17_partner=pct(test,b))
    elif family.startswith('seed_average'):
        signals[family],au=fit_v17(train,test,tag+'_seed',int(family.replace('seed_average','')));audit.append(au)
    elif family!='v17':
        for f in family.split('+'):
            print('FINAL FIT',tag,f,flush=True);raw,au=train_predict(train,test,f,tag+'_'+f);signals[f]=pct(test,raw);audit.append(au)
    return score(test,signals,choice),audit

def final_scores():
    lock=json.loads((O/'selection_lock.json').read_text());choice=lock['choice'] if lock['new_model_survived'] else lock['best_rejected']
    if (O/'reported_new_candidate.json').exists():assert json.loads((O/'reported_new_candidate.json').read_text())==choice
    else:write('reported_new_candidate.json',choice,True)
    x,dev=data();signals=signals_for(dev);dev['new_score']=score(dev,signals,choice);csv('development_scores.csv.gz',dev[v.KEYS+v.OUTCOME+['champion_score','v17_score','new_score']]);del signals;gc.collect();audit=[]
    early=x.merge(pd.read_csv(O/'early_scores.csv.gz'),on=v.KEYS,validate='one_to_one');outputs=[]
    for day,g in early.groupby('decision_date'):
        train=x.loc[x.endpoint.lt(day)];g=g.copy();g['new_score'],au=domain_signals(train,g,choice,'earlynew_'+day,O/('model_early_'+day+'_mono.txt'),{look:O/('model_early_'+day+'_look'+str(look)+'.txt') for look in [12,36,60]});audit.extend(au);outputs.append(g[v.KEYS+v.OUTCOME+['champion_score','v17_score','new_score']]);write('final_training_audit.json',audit)
    csv('early_all_scores.csv.gz',pd.concat(outputs,ignore_index=True));del early,x;gc.collect()
    x=features(v.load_historical(True));outputs=[]
    for year in ['2024','2025']:
        g=x.loc[x.decision_date.str.startswith(year)].merge(pd.read_csv(V17/('exposed_'+year+'_scores.csv.gz'),usecols=v.KEYS+['champion_score','v17_score']),on=v.KEYS,validate='one_to_one');train=x.loc[x.endpoint.lt(g.decision_date.min())];g['new_score'],au=domain_signals(train,g,choice,'exposed_'+year,V17/('model_exposed_'+year+'_monotone.txt'),{look:V17/('model_exposed_'+year+'_partner_look'+str(look)+'.txt') for look in [12,36,60]});audit.extend(au);outputs.append(g[v.KEYS+v.OUTCOME+['champion_score','v17_score','new_score']]);write('final_training_audit.json',audit)
    csv('exposed_scores.csv.gz',pd.concat(outputs,ignore_index=True))
    current=pd.read_csv(V17/'current_rankings.csv.gz',low_memory=False);current[v.FEATURES+['evidence_confidence']]=current[v.FEATURES+['evidence_confidence']].astype('float32');current=features(current);mono=V17/'model_current_monotone.txt';partners={look:V17/('model_current_partner_look'+str(look)+'.txt') for look in [12,36,60]};a,b=s.predict_models(current,mono,partners);reproduced=s.selected_score(current,a,b,{'kind':'blend_targeted_monotone','alpha':.3});error=float((reproduced-current.v17_score).abs().max());assert error<1e-10
    train=x.loc[x.endpoint.lt(current.decision_date.min())];current['new_score'],au=domain_signals(train,current,choice,'current',mono,partners);audit.extend(au);write('final_training_audit.json',audit);current['new_rank']=v.ranked(current,'new_score');current['winner_score']=current['new_score'] if lock['new_model_survived'] else current.v17_score;current['winner_rank']=v.ranked(current,'winner_score');csv('current_rankings.csv.gz',current)
    assert current['isin'].nunique()==4436 and len(current)==4436*9 and not current.duplicated(v.KEYS).any()
    for n in [20,50,100]:
        csv('current_top'+str(n)+'.csv',current.loc[current.winner_rank.le(n)].sort_values(['profile_name','winner_rank']));csv('current_new_candidate_top'+str(n)+'.csv',current.loc[current.new_rank.le(n)].sort_values(['profile_name','new_rank']))
    csv('nykaa_diagnostic.csv',current.loc[current['isin'].eq('INE388Y01029')]);write('current_validation.json',{'v17_reproduction_max_error':error,'universe':current['isin'].nunique(),'profile_rows':len(current),'winner_scored_rows':int(current.winner_score.notna().sum()),'new_scored_rows':int(current.new_score.notna().sum()),'identical_coverage':bool(current.new_score.notna().equals(current.v17_score.notna())),'choice':choice,'winner':lock['choice'],'inference_after_selection':True,'current_date':current.decision_date.unique().tolist()});print('FINAL SCORES COMPLETE',flush=True)

def evaluation():
    assert (O/'selection_lock.json').exists();x=features(v.load_historical(True));allmetrics=[];cohorts=[];turns=[];profile_tables=[]
    for period,file in [('early_2016_2019','early_all_scores.csv.gz'),('development_2020_2023','development_scores.csv.gz'),('exposed_2024_2025','exposed_scores.csv.gz')]:
        scores=pd.read_csv(O/file,usecols=v.KEYS+['champion_score','v17_score','new_score']);frame=x.merge(scores,on=v.KEYS,validate='one_to_one');metrics=pd.concat([v.evaluate(frame,m+'_score').assign(model=m,period=period) for m in ['champion','v17','new']],ignore_index=True);allmetrics.append(metrics)
        for reference in ['champion','v17']:
            for model in ['v17','new']:
                if model==reference:continue
                pair=v.compare_metrics(metrics.loc[metrics.model.eq(model)].drop(columns=['model','period']),metrics.loc[metrics.model.eq(reference)].drop(columns=['model','period']));profile_tables.append(pair.assign(model=model,reference=reference,period=period));z=frame.copy();z['champion_score']=frame[reference+'_score'];turns.append(v.turnover(z,model+'_score').assign(model=model,reference=reference,period=period))
        for profile,g in [('ALL',frame)]+list(frame.groupby('profile_name')):
            masks={'short_history':g.history_months.lt(60),'full_history':g.has_true_5y.eq(1),'high_volatility':g.realized_volatility_1y.ge(g.groupby(['decision_date','profile_name']).realized_volatility_1y.transform('quantile',.75)),'deep_drawdown':g.full_history_max_drawdown.le(-.5),'deep_ath':g.distance_from_recorded_high.le(-.4),'old_ath':g.days_since_recorded_high.ge(1095),'recent_ath':g.days_since_recorded_high.le(90)}
            for name,mask in masks.items():
                for model in ['champion','v17','new']:
                    mm=v.evaluate(g.loc[mask],model+'_score').reindex(columns=v.METRICS);selected=g.dropna(subset=[model+'_score']+v.OUTCOME).sort_values(['decision_date','profile_name',model+'_score','isin'],ascending=[True,True,False,True]).groupby(['decision_date','profile_name']).head(20);selected=selected.loc[mask.reindex(selected.index)];cohorts.append({'period':period,'profile':profile,'cohort':name,'model':model,'share_overall_top20':len(selected)/(20*g.groupby(['decision_date','profile_name']).ngroups),'selected_xirr':selected.future_xirr.median(),'selected_drawdown':selected.future_drawdown.mean(),**mm[v.METRICS].mean().to_dict()})
            print('COHORTS',period,profile,flush=True)
        csv('all_profile_date_metrics.csv',pd.concat(allmetrics));csv('all_cohorts.csv',pd.DataFrame(cohorts));csv('all_comparison_deltas.csv',pd.concat(profile_tables));csv('all_turnover.csv',pd.concat(turns))
    mm=pd.concat(allmetrics);csv('aggregate_metrics.csv',mm.groupby(['period','model'])[v.METRICS].mean().reset_index());csv('profile_metrics.csv',mm.groupby(['period','profile','model'])[v.METRICS].mean().reset_index());write('date_coverage.json',{'scored_dates':sorted(mm.decision_date.unique()),'scored_date_count':mm.decision_date.nunique(),'profiles':sorted(mm.profile.unique()),'no_prior_labels':json.loads((O/'early_unavailable.json').read_text()),'all_valid_dates':True,'early_results_contextual_not_selection':True,'exposed_results_not_selection':True});print('EVALUATION COMPLETE',flush=True)

def loaded_raw(x,family,tag):
    valid=x.champion_score.notna();pred=pd.Series(np.nan,index=x.index)
    if family=='specialist_utility':
        for look in [12,36,60]:
            mask=x.lookback_months.eq(look);pred.loc[mask]=loaded_raw(x.loc[mask],'utility',tag+'_look'+str(look))
    elif family=='multitask':
        pred.loc[valid]=0
        for head,w in [('return',.7),('shortfall',.2),('drawdown',.1)]:pred.loc[valid]+=w*loaded_raw(x,'utility',tag+'_'+head).loc[valid]
    elif family=='neural_moe':
        import torch
        torch.set_num_threads(4);checkpoint=torch.load(O/('model_'+tag+'.pt'),weights_only=True);cols=checkpoint['features']
        class Net(torch.nn.Module):
            def __init__(self):
                super().__init__();self.experts=torch.nn.ModuleList([torch.nn.Sequential(torch.nn.Linear(len(cols),32),torch.nn.SiLU(),torch.nn.Linear(32,16),torch.nn.SiLU(),torch.nn.Linear(16,1)) for _ in range(2)]);self.gate=torch.nn.Sequential(torch.nn.Linear(len(s.CONTEXT)+len(REGIME),8),torch.nn.SiLU(),torch.nn.Linear(8,2))
            def forward(self,a):return (torch.cat([e(a) for e in self.experts],1)*torch.softmax(self.gate(a[:,-(len(s.CONTEXT)+len(REGIME)):]),1)).sum(1)
        net=Net();net.load_state_dict(checkpoint['state_dict']);net.eval()
        with torch.no_grad():pred.loc[valid]=net(torch.from_numpy(x.loc[valid,cols].to_numpy(dtype=np.float32))).numpy()
    else:
        m=lgb.Booster(model_file=str(O/('model_'+tag+'.txt')));pred.loc[valid]=m.predict(x.loc[valid,m.feature_name()],num_threads=4)
    return pred

def current_predict(x,choice):
    a,b=s.predict_models(x,V17/'model_current_monotone.txt',{look:V17/('model_current_partner_look'+str(look)+'.txt') for look in [12,36,60]});z=x.copy();z['v17_score']=s.selected_score(x,a,b,{'kind':'blend_targeted_monotone','alpha':.3});signals={'v17_mono':pct(x,a),'v17_partner':pct(x,b)};f=choice['family']
    if f.startswith('seed_average'):
        aa,bb=s.predict_models(x,O/'model_current_seed_mono.txt',{look:O/('model_current_seed_look'+str(look)+'.txt') for look in [12,36,60]});signals[f]=s.selected_score(x,aa,bb,{'kind':'blend_targeted_monotone','alpha':.3})
    elif f not in ['v17','confidence_agreement','confidence_squared']:
        for family in f.split('+'):signals[family]=pct(x,loaded_raw(x,family,'current_'+family))
    return score(z,signals,choice)

def anchored_ath(x,choice):
    mono=V17/'model_current_monotone.txt';paths={look:V17/('model_current_partner_look'+str(look)+'.txt') for look in [12,36,60]};basea,baseb=s.predict_models(x,mono,paths);f=choice['family'];extra={}
    if f.startswith('seed_average'):extra['sa'],extra['sb']=s.predict_models(x,O/'model_current_seed_mono.txt',{look:O/('model_current_seed_look'+str(look)+'.txt') for look in [12,36,60]})
    elif f not in ['v17','confidence_agreement','confidence_squared']:
        extra={family:loaded_raw(x,family,'current_'+family) for family in f.split('+')}
    def ecdf(ref,values):
        ref=np.sort(ref.dropna().to_numpy());return np.clip((np.searchsorted(ref,values,side='left')+np.searchsorted(ref,values,side='right')+1)/(2*len(ref)),0,1)
    def anchored(ref,values):
        result=pd.Series(np.nan,index=x.index)
        for _,g in x.groupby(['decision_date','profile_name']):
            ids=g.index[g.champion_score.notna()];result.loc[ids]=ecdf(ref.loc[g.index],values.loc[ids])
        return result
    scenarios={}
    for name,days,depth in [('recent_near',30,-.05),('old_near',1825,-.05),('old_deep',1825,-.7)]:
        z=x.copy();z['days_since_recorded_high']=days;z['current_drawdown_duration_days']=days;z['distance_from_recorded_high']=depth;z['old_high_depth']=np.log1p(days/365)*(-depth);z['underwater_depth']=z.old_high_depth;z['recovery_vs_old_high']=z.recovery_from_worst_trough.clip(-1,10)*(-depth)
        for _,g in x.groupby(['decision_date','profile_name']):
            for c in ['distance_from_recorded_high','old_high_depth','underwater_depth']:
                values=ecdf(g[c],z.loc[g.index,c]);z.loc[g.index,'q_'+c]=(values if c in s.POS else 1-values).astype('float32')
        aa,bb=s.predict_models(z,mono,paths);pa=anchored(basea,aa);pb=anchored(baseb,bb);z['v17_score']=v.guided(z,(pa+pb)/2,.3);signals={'v17_mono':pa,'v17_partner':pb}
        if f.startswith('seed_average'):
            sa,sb=s.predict_models(z,O/'model_current_seed_mono.txt',{look:O/('model_current_seed_look'+str(look)+'.txt') for look in [12,36,60]});signals[f]=v.guided(z,(anchored(extra['sa'],sa)+anchored(extra['sb'],sb))/2,.3)
        elif f not in ['v17','confidence_agreement','confidence_squared']:
            for family in f.split('+'):signals[family]=anchored(extra[family],loaded_raw(z,family,'current_'+family))
        scenarios[name]=score(z,signals,choice)
    rows=[]
    for profile,g in x.groupby('profile_name'):
        for name in ['old_near','old_deep']:
            delta=(scenarios[name]-scenarios['recent_near']).loc[g.index].dropna();rows.append({'profile':profile,'scenario':name,'mean_score_change':delta.mean(),'median_score_change':delta.median(),'negative_fraction':delta.lt(-1e-8).mean(),'positive_fraction':delta.gt(1e-8).mean(),'method':'Original feature and prediction empirical CDF anchors; champion/confidence/regime held fixed. Conditional diagnostic, not causal.'})
    return pd.DataFrame(rows)

def diagnostics():
    import shutil
    lock=json.loads((O/'selection_lock.json').read_text());choice=json.loads((O/'reported_new_candidate.json').read_text());x=pd.read_csv(O/'current_rankings.csv.gz',low_memory=False);x[v.FEATURES+['evidence_confidence']]=x[v.FEATURES+['evidence_confidence']].astype('float32');x=features(x);pred=current_predict(x,choice);error=float((pred-x.new_score).abs().max());assert error<1e-10,error;validation=json.loads((O/'current_validation.json').read_text());validation['new_reproduction_max_error']=error;write('current_validation.json',validation)
    composition=[];personal=[];turn=[]
    fields=['strict_cagr_1y','cagr_3y','observed_cagr_5y','days_since_recorded_high','distance_from_recorded_high','current_drawdown_duration_days','recovery_from_worst_trough','full_history_max_drawdown','realized_volatility_1y','evidence_confidence','target_attainment','historical_target_frequency_score']
    for model in ['champion','v17','new']:
        rank=v.ranked(x,model+'_score');x[model+'_rank']=rank;base=x.loc[x.profile_name.eq('base7500')].set_index('isin');top=set(base.loc[base[model+'_rank'].le(20)].index)
        for profile,g in x.groupby('profile_name'):
            for n in [20,50,100]:
                z=g.loc[rank.loc[g.index].le(n)];composition.append({'model':model,'profile':profile,'top':n,'count':len(z),'missing_true_5y_share':z.has_true_5y.eq(False).mean(),**{c+'_median':z[c].median() for c in fields}})
            gg=g.set_index('isin');joined=base[[model+'_rank']].join(gg[[model+'_rank']],lsuffix='_base',rsuffix='_profile').dropna();personal.append({'model':model,'profile':profile,'top20_overlap_with_base':len(top&set(gg.loc[gg[model+'_rank'].le(20)].index))/20,'mean_absolute_rank_change':(joined.iloc[:,0]-joined.iloc[:,1]).abs().mean(),'rank_correlation':joined.iloc[:,0].corr(joined.iloc[:,1],method='spearman')})
        for ref in ['champion','v17']:
            if ref==model:continue
            z=x.copy();z['champion_score']=x[ref+'_score'];turn.append(v.turnover(z,model+'_score').assign(model=model,reference=ref))
    csv('current_composition.csv',pd.DataFrame(composition));csv('current_personalization.csv',pd.DataFrame(personal));csv('current_turnover.csv',pd.concat(turn))
    # Frozen V17 diagnostics remain directly applicable to a V17 winner.
    for filename in ['current_ath_behavior.csv','current_family_sensitivity.csv','current_history_behavior.csv','current_peer_diagnostics.csv','nykaa_peer_context.csv','final_robustness_profile_date_results.csv','final_robustness_results.json']:
        if (V17/filename).exists():shutil.copyfile(V17/filename,O/('v17_'+filename))
    effects=[]
    for family,cols in v.FAMILIES.items():
        if family=='history':continue
        z=x.copy()
        for c in cols:
            if c in z:z[c]=z.groupby(['decision_date','profile_name'])[c].transform('median')
        z=features(z);alternative=current_predict(z,choice);rr=v.ranked(z.assign(alternative=alternative),'alternative')
        for profile,g in x.groupby('profile_name'):
            top=set(g.loc[g.new_rank.le(20),'isin']);other=set(g.loc[rr.loc[g.index].le(20),'isin']);effects.append({'profile':profile,'feature_family':family,'top20_replacements':20-len(top&other),'mean_absolute_rank_change':(rr.loc[g.index]-g.new_rank).abs().mean(),'mean_absolute_score_change':(alternative.loc[g.index]-g.new_score).abs().mean(),'interpretation':'Conditional sensitivity with champion held fixed; not causal attribution.'})
        print('SENSITIVITY',family,flush=True)
    csv('new_current_family_sensitivity.csv',pd.DataFrame(effects));csv('new_current_ath_behavior.csv',anchored_ath(x,choice))
    # No identity or historical-age direct feature: changing only these labels cannot alter predictions.
    z=x.copy();z['isin']='ANONYMOUS';z['history_months']=0;z['has_true_5y']=False;z['cagr_5y_observed']=0;unchanged=current_predict(z,choice);validation['identity_and_age_label_only_max_error']=float((unchanged-pred).abs().max());assert validation['identity_and_age_label_only_max_error']<1e-10;write('current_validation.json',validation)
    print('DIAGNOSTICS COMPLETE',flush=True)

def report():
    lock=json.loads((O/'selection_lock.json').read_text());choice=json.loads((O/'reported_new_candidate.json').read_text());trials=pd.read_csv(O/'all_trials.csv');metrics=pd.read_csv(O/'aggregate_metrics.csv');deltas=pd.read_csv(O/'all_comparison_deltas.csv');profiles=deltas.groupby(['period','model','reference','profile'])[[c+'_delta' for c in v.METRICS]].mean().reset_index();csv('profile_comparison_deltas.csv',profiles);coh=pd.read_csv(O/'all_cohorts.csv');ny=pd.read_csv(O/'nykaa_diagnostic.csv');dates=json.loads((O/'date_coverage.json').read_text());validation=json.loads((O/'current_validation.json').read_text());current=pd.read_csv(O/'current_top20.csv');details={**json.loads((O/'round1_details.json').read_text()),**json.loads((O/'round2_details.json').read_text())};detail=details[choice['candidate']]
    verdict='PROMISING CHALLENGER' if lock['new_model_survived'] else 'V17 REMAINS BEST CHALLENGER';winner=choice['candidate'] if lock['new_model_survived'] else 'V17 targeted ATH60 ensemble';bad=profiles.loc[profiles.period.eq('development_2020_2023')&profiles.model.eq('new')&profiles.reference.eq('v17')].sort_values('median_xirr_top20_delta');summary={'verdict':verdict,'winner':winner,'new_candidate':choice,'selection_checks':detail['checks'],'development_new_vs_v17':detail['v17_delta'],'worst_new_vs_v17_profile':bad.iloc[0].to_dict(),'trial_count':len(trials),'eligible_count':int(trials.eligible.sum()),'date_coverage':dates,'current_validation':validation,'production_champion':'d4995807163bef1ec4b297179e6c54a59c71f390','deployed':False,'mean_xirr_selection_weight':0,'fundamentals_peer_scope':'Current-only explanatory context; historical dated inputs unavailable. Not a historically validated fundamental/industry model.','limitations':['Development adaptivity:39 prior V17 and34 additional V18 configurations. No untouched validation.','Fixed-universe survivorship and provider revision risks remain.','Current corporate-action completeness after2026-09-18 remains unproved; existing quarantine retained.','Small number of calendar regimes; block intervals do not adjust for adaptive selection.'],'completed_at':now()};write('decision_summary.json',summary)
    intervals=[];rng=np.random.default_rng(20261003)
    for keys,g in deltas.groupby(['period','model','reference','profile']):
        annual=g.assign(year=g.decision_date.str[:4]).groupby('year')[[c+'_delta' for c in v.METRICS]].mean();arr=annual.to_numpy();boot=arr[rng.integers(0,len(arr),(2000,len(arr)))].mean(axis=1)
        for j,c in enumerate(v.METRICS):intervals.append(dict(zip(['period','model','reference','profile'],keys),metric=c,delta=g[c+'_delta'].mean(),p025=np.quantile(boot[:,j],.025),p975=np.quantile(boot[:,j],.975),calendar_blocks=len(arr)))
    csv('year_block_intervals.csv',pd.DataFrame(intervals));display=['period','model','median_xirr_top20','target_achievement_top20','target_shortfall_top20','mean_asset_drawdown_top20','ndcg20'];cols=[c for c in ['winner_rank','company_name','name','ticker','isin','strict_cagr_1y','days_since_recorded_high','distance_from_recorded_high'] if c in current];base=current.loc[current.profile_name.eq('base7500'),cols]
    lines=['# V18: bounded research beyond V17','',f'## Verdict: {verdict}','',f'Best defensible research model: **{winner}**. Frozen production champion remains **d499580**. Nothing deployed.','',f'Compared {len(trials)} new configurations across10 trained families,8 registered pair/triple mixtures and6 seed/confidence controls. The reported new candidate is **{choice["candidate"]}**; it is '+('accepted as a research challenger.' if lock['new_model_survived'] else '**rejected**, not a replacement for V17.'),'','## Selection and complete comparison','','All selection used2020–2023. Earlier trainable dates and already-exposed2024–2025 are contextual evaluation only. Mean XIRR had zero selection weight. Median-XIRR entries below are equal-weight averages of each date/profile Top20 median, not portfolio CAGR. Drawdown is mean selected-asset drawdown, not a simulated portfolio drawdown; less negative is better. All returns and rates are decimals.','',s.md(metrics[display]),'','### New candidate acceptance checks','',s.md(pd.DataFrame([{'check':k,'passed':value} for k,value in detail['checks'].items()])),'','### Every development profile: new candidate minus V17','',s.md(bad[['profile','median_xirr_top20_delta','target_achievement_top20_delta','target_shortfall_top20_delta','mean_asset_drawdown_top20_delta','ndcg20_delta']]),'','## Historical coverage and robustness','',f'{dates["scored_date_count"]} trainable decision dates, all9 profiles;6 earlier2015 dates have no matured prior training labels and are explicitly unavailable. Training labels always mature strictly before each fitted decision block. V17/experimental candidates use annual development/exposed refits; frozen champion uses its original per-date recipe refits. Earlier contextual evaluation refits each date. See early_training_audit.json, training_audit.json and final_training_audit.json.','', 'All7 robustness cohorts are evaluated for every profile and period: short history, full history, high volatility, deep drawdown, deep ATH, old ATH, recent ATH. Both within-cohort rankings and representation/outcomes inside overall Top20 are saved in all_cohorts.csv. Variant robustness, including the inherited V17 alternate seeds and per-date refits, is retained without concealing profile regressions. Year-block intervals are conditional diagnostics, not selection-adjusted significance claims.','','### Development cohort comparison (all profiles)','',s.md(coh.loc[coh.period.eq('development_2020_2023')&coh.profile.eq('ALL'),['cohort','model','share_overall_top20','median_xirr_top20','mean_asset_drawdown_top20']]),'','## Current inference','',f'All4,436 V7 stocks ×9 profiles =39,924 rows retained; {validation["winner_scored_rows"]:,} winner scores. Unscored/quarantined rows remain in current_rankings.csv.gz with their existing reasons. Top20/50/100 files are for the winning model across all9 profiles; separate new-candidate lists retain the rejected alternative for review. Scores reproduced from saved models to numerical precision.','', 'Base profile Top20:','',s.md(base),'','## NYKAA diagnostic','',s.md(ny[[c for c in ['profile_name','champion_rank','v17_rank','new_rank','winner_rank','strict_cagr_1y','cagr_3y','days_since_recorded_high','distance_from_recorded_high','evidence_confidence'] if c in ny]]),'','No NYKAA or company-identity predictor or ranking override exists. The diagnostic is after selection. Five-year missingness reduces evidence confidence; it does not impose a bad-company penalty. ATH age, depth and underwater duration enter learned interactions; reported conditional sensitivities retain both favorable and unfavorable exceptions.','', 'Current peer/fundamental context is preserved in v17_current_peer_diagnostics.csv. It explains the current universe only. No current Screener, professor, Yahoo fundamentals or industry classifications were copied backward. The lack of dated historical fundamentals means this requirement cannot honestly be claimed as a validated historical ranking contribution.','','## Weaknesses and stopping','', 'V17 has conditional profile instability under alternate seeds/refit schedules and can worsen drawdown inside the high-volatility cohort. Current and early-period weaknesses are visible in the full tables. No model earns production promotion from this evidence.','', 'The sensible registered search was completed, rather than extending thresholds or optimizing exposed dates. This is a bounded research conclusion within the available data and compute, not proof that no better model exists. A larger unbounded adaptive search on the same exposed dates would not create independent evidence.','', *['- '+z for z in summary['limitations']],'','## Reproduction','','Runner: research/runners/personalized_v18_20261003.py. Stages: prepare, round1, early_predictions, round2, robustness, final_scores, evaluation, diagnostics, report, audit. Lock-writing stages intentionally refuse to overwrite locks. Existing frozen V17 inputs and d499580 are hashed and read-only. No deployment or production code changes.','','## Research sources','']
    for source in json.loads((O/'sources.json').read_text()):lines.append(f'- [{source["use"]}]({source["url"]})')
    reportpath=ROOT/'research/reports/personalized_v18_20261003.md';reportpath.write_text('\n'.join(lines),encoding='utf-8');print('REPORT',reportpath,flush=True)

def audit():
    before=json.loads((O/'protected_before.json').read_text());changed=[]
    def check(item):
        p,h=item;return p if not (ROOT/p).is_file() or v.sha(ROOT/p)!=h else None
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i,result in enumerate(pool.map(check,before.items())):
            if result:changed.append(result)
            if i%4000==0:print('AUDIT',i,flush=True)
    assert not changed,changed
    maturity=[]
    def visit(obj):
        if isinstance(obj,list):
            for z in obj:visit(z)
        elif isinstance(obj,dict):
            if 'max_endpoint' in obj:
                cutoff=obj.get('min_decision',obj.get('min_scored_date'));assert obj['max_endpoint']<cutoff,obj;maturity.append({'endpoint':obj['max_endpoint'],'cutoff':cutoff})
            for z in obj.values():
                if isinstance(z,(dict,list)):visit(z)
    for file in O.glob('*training_audit.json'):visit(json.loads(file.read_text()))
    for file in [O/'training_audit.json']:
        if file.exists():visit(json.loads(file.read_text()))
    forbidden={'isin','ticker','company_name','future_xirr','future_shortfall','future_drawdown','endpoint','history_months','has_true_5y','cagr_5y_observed'};modelcount=0
    for file in O.glob('model_*.txt'):
        m=lgb.Booster(model_file=str(file));assert not forbidden.intersection(m.feature_name()),file;modelcount+=1
    for file in O.glob('model_*.pt'):
        import torch
        checkpoint=torch.load(file,weights_only=True);assert not forbidden.intersection(checkpoint['features']),file;modelcount+=1
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();assert head=='c12dd9b189bc71684bfac52606eb89abd5e383c7';summary=json.loads((O/'decision_summary.json').read_text());assert summary['trial_count']==34;assert summary['date_coverage']['scored_date_count']==44;assert summary['current_validation']['identical_coverage'];assert summary['current_validation']['new_reproduction_max_error']<1e-10
    write('audit.json',{'checked_at':now(),'protected_count':len(before),'changed_protected':changed,'maturity_records_checked':len(maturity),'models_checked_for_forbidden_features':modelcount,'HEAD':head,'production_deployed':False,'all_checks_passed':True})
    paths=sorted(p for p in O.rglob('*') if p.is_file() and p.name!='manifest.json')+[ROOT/'research/runners/personalized_v18_20261003.py',ROOT/'research/reports/personalized_v18_20261003.md'];write('manifest.json',{str(p.relative_to(ROOT)):v.sha(p) for p in paths});print('AUDIT PASSED',len(paths),'files',len(before),'protected',flush=True)

def finish():
    assert len(pd.read_csv(O/'round1_trials.csv'))==20
    stages=[round2,robustness,final_scores,evaluation,diagnostics,report,audit]
    for stage in stages:
        print('STAGE',stage.__name__,now(),flush=True);stage();gc.collect()

if __name__=='__main__':globals()[sys.argv[1]]()
