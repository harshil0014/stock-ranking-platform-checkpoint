"""Locked, research-only pilots for the ten user-suggested experiments.

No serving code, incumbent artifacts, or prior evaluation outputs are mutated.
Run using the repository .venv, with PYTHONPATH=src.
"""
from pathlib import Path
import argparse, json, hashlib, gc
import numpy as np
import pandas as pd
from scipy.stats import rankdata, kendalltau
from scipy.special import logit
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.linear_model import LogisticRegression
import lightgbm as lgb
import sector_price_rebuild_20261010 as old

ROOT = old.ROOT
OUT = ROOT/'experiments/ten-hypotheses-20261031'
KEYS = ['isin','decision_date','profile_name']
GROUP = ['decision_date','profile_name','sector']
ANCHOR = 'active_champion'
SEED = 20261031
MONOTONE = False
VOL = ['abnormal_volume21','abnormal_volume5','high_volume_interaction','volume_trend','volume_zero_fraction','log_dollar_volume']
PEER = ['corr_peer_return21','corr_peer_return63','corr_peer_lag','corr_peer_correlation']
ANALOG = ['analog_xirr','analog_attainment','analog_dispersion','analog_distance']

def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/name).write_text(json.dumps(data, indent=2, default=lambda x: x.item() if hasattr(x,'item') else str(x)),encoding='utf-8')

def protocol():
    OUT.mkdir(parents=True,exist_ok=True)
    doc = dict(seed=SEED, baseline_commit='a216d6dd0af742b719cbe449ff2b2d2f4ef2ca5d',
        scope='Research-only. No deployment or automatic model promotion.',
        periods={'development':'2020-2023','exposed':'2024-2025; already repeatedly examined'},
        population='Saved current-survivor universe and retrospective sectors; finite existing guarded labels/features; same-row comparisons.',
        noise_floor='35 prespecified related score policies: original + 9 high + 6 complements + 15 SIP + 4 confirmation. Center each date-model difference against active incumbent. Circular moving-calendar-block bootstrap, 365 and 730 days, 4000 replicates, preserve simultaneous model/sector/profile dependence. Familywise 95th percentile maximum mean delta, not a universal future guarantee.',
        confidence='Dispersion of within-query percentile ranks across 35 policies; sampled pair agreement and selective pair accuracy. Development chooses retained fraction among .5,.75,1 maximizing accuracy with >=50% pairs retained; one exposed replay.',
        hysteresis='Adjacent prior-order swaps only if challenger score gap exceeds fixed margin. Margins 0,.0025,.005,.01,.02. Select max development stability subject IC loss <=.001. Quarterly/monthly historical snapshots, not live daily refresh validation.',
        goal='Binary future_xirr >= target_cagr (1e-7 tolerance), not the old composite utility. Annual folds. Base learner endpoint strictly before calibration-year January1; independent calibration outcomes mature strictly before test-year January1. Sigmoid calibration; equal query weights. Fixed 120 trees, 15 leaves, regularization30, seed fixed.',
        path='Explanatory association using REALIZED forward path, endpoint-return spline + sector/date fixed effects. Not tradable future features. Base7500 saved outcomes plus independent fractional monthly-SIP mechanism simulation.',
        meta='Predict success of incumbent Top3 using prior out-of-time predictions with fully mature outcomes. Liquidity, risk, market regime, agreement, and score gap. Annual folds; development selects .5,.75,1 coverage threshold; abstention compared with identical ungated picks.',
        volume='21/252 and5/252 mean-volume ratios, high proximity interaction, volume trend, zero-volume fraction, log median traded value. All inputs <= decision date, guarded by original price eligibility.',
        filing='Require actual filing broadcast timestamps, covered-period ends and historic observation coverage. Corporate-action ex-dates are not filing dates. No proxy fabrication.',
        peers='25 nearest same-date stocks by 252-observation daily return correlation, exclude self, >=200 jointly observed daily returns. Includes Unclassified/small sectors when evidence permits. Fixed peer-return/lag features; original sector evaluation preserved.',
        kronos='Frozen tokenizer and Kronos-mini hidden representation, last252 actual OHLCV observations. Outcome-independent hash sample512 stocks for bounded pilot; matched LightGBM base/augmented. Pretrained temporal contamination makes historical scores diagnostic only; no promotion.',
        analogs='Learned linear path embedding (PCA8 of64 normalized252-observation log-price samples), fit only on outcome-mature historical library at each calendar-year cutoff. Nearest50 cosine neighbors, exclude same issuer, require neighbor endpoint strictly before cutoff. Match profile outcomes. No future-path input.',
        model_variants=['goal_base','goal_volume','goal_peers','goal_analogs','goal_combined'],
        promotion='None in this run. Later research must exceed measured multiplicity threshold and preserve calibration/coverage/risk; exposed-period improvement is not fresh evidence.',
        sources=['https://scikit-learn.org/stable/modules/calibration.html','https://github.com/shiyu-coder/Kronos','https://doi.org/10.1111/0022-1082.00349','https://doi.org/10.1093/rfs/hhm003'],
        fresh_validation=False)
    p=OUT/'protocol.json'
    if p.exists(): assert json.loads(p.read_text())==doc
    else:save('protocol.json',doc)

def prepare():
    protocol()
    if (OUT/'panel.pkl.gz').exists():return
    x=pd.read_pickle(old.OUT/'prepared.pkl.gz',compression='gzip')
    scores=pd.concat([pd.read_csv(old.OUT/f'predictions_{y}.csv.gz',usecols=KEYS+['rank_xendcg_balanced']) for y in range(2020,2026)],ignore_index=True)
    other=pd.concat([pd.read_csv(old.OLD/f'predictions_{y}.csv.gz',usecols=KEYS+['profile_defensive_15']) for y in range(2020,2026)],ignore_index=True)
    scores=scores.merge(other,on=KEYS,validate='one_to_one')
    x=x.merge(scores,on=KEYS,how='left',validate='one_to_one');del scores,other
    x['original']=.75*(.8*x.open_model+.2*x.profile_defensive_15)+.25*x.rank_xendcg_balanced
    candidates=['original']
    for directory,file in [('champion-high-recency-20261017','historical_adjustments.csv.gz'),('champion-recency-complements-20261017','historical_adjustments.csv.gz'),('champion-sip-profit-20261017','historical_scores.csv.gz')]:
        s=pd.read_csv(ROOT/'experiments'/directory/file)
        cols=[c for c in s if c not in KEYS and c!='current_champion']
        candidates+=cols
        x=x.merge(s[KEYS+cols],on=KEYS,how='left',validate='one_to_one')
    x[ANCHOR]=x['sip_risk_confirmed_0.01']
    a=x['dual_w0.01']-x.original;b=x[ANCHOR]-x['dual_w0.01'];agree=(a*b>0).astype(float)
    for name,gate in [('double_both',1),('agree_only',agree),('agree_soft',agree*np.minimum(a.abs(),b.abs())/.005),('strong_both',agree*((a.abs()>=.0025)&(b.abs()>=.0025)))]:
        x[name]=x[ANCHOR]+gate*(a+b);candidates.append(name)
    assert len(candidates)==35,len(candidates)
    save('model_registry.json',dict(models=candidates,count=35,baseline=ANCHOR))
    x['goal_hit']=(x.future_xirr+1e-7>=x.target_cagr).where(x.future_xirr.notna())
    # Rank dispersion is computed independently for each date/profile/sector.
    ranked=x[candidates].groupby([x[g] for g in GROUP]).rank(pct=True)
    x['model_disagreement']=ranked.std(axis=1,ddof=0)
    x['anchor_rank']=x[ANCHOR].groupby([x[g] for g in GROUP]).rank(pct=True)
    for c in ['isin','profile_name','sector','period','input_status']:
        x[c]=x[c].astype('category')
    x.to_pickle(OUT/'panel.pkl.gz',compression='gzip')
    save('panel_audit.json',dict(rows=len(x),dates=x.decision_date.nunique(),profiles=x.profile_name.nunique(),models=35,goal_label_disagrees_with_old_shortfall=int(((x.goal_hit==1)!=x.future_shortfall.eq(0))[x.future_xirr.notna()].sum())))
    print('PREPARED',x.shape,flush=True)

def valid(x):
    x=x[x.evidence_fraction.gt(0)&x.future_xirr.notna()&x.sector.ne('Unclassified')].copy()
    return x[x.groupby(GROUP,observed=True)['isin'].transform('size').ge(5)].copy()

def metrics(x, columns):
    rows=[]
    for key,g in x.sort_values('isin').groupby(GROUP,observed=True,sort=True):
        if len(g)<5:continue
        y=g.future_xirr.to_numpy();ry=rankdata(y);ry-=ry.mean();norm=np.linalg.norm(ry)
        scores=g[columns].to_numpy(dtype=float);ok=np.isfinite(scores).all(axis=0)
        names=np.asarray(columns)[ok];scores=scores[:,ok]
        if not len(names):continue
        ranks=rankdata(scores,axis=0);ranks-=ranks.mean(axis=0)
        den=np.linalg.norm(ranks,axis=0)*norm
        ic=np.divide(ry@ranks,den,out=np.full(len(names),np.nan),where=den>0)
        order=np.argsort(-scores,axis=0,kind='stable')[:3]
        achievement=g.goal_hit.to_numpy(dtype=float)[order].mean(axis=0)
        legacy=g.future_shortfall.eq(0).to_numpy()[order].mean(axis=0)
        xr=np.median(y[order],axis=0);dd=g.future_drawdown.to_numpy()[order].mean(axis=0)
        for j,name in enumerate(names):
            rows.append(dict(zip(GROUP,key),model=name,rank_ic=ic[j],achievement=achievement[j],legacy_achievement=legacy[j],xirr=xr[j],drawdown=dd[j],n=len(g)))
    return pd.DataFrame(rows)

def block_floor(matrix, dates, span, replicates=4000):
    """Centered simultaneous circular calendar-block bootstrap maximum statistic."""
    a=np.asarray(matrix,float);assert np.isfinite(a).all()
    a=a-a.mean(axis=0,keepdims=True)
    d=pd.to_datetime(dates); offsets=(d-d[0]).days.to_numpy(); duration=(d[-1]-d[0]).days+90
    if span>=duration:
        return dict(calendar_block_days=span,replicates=0,familywise_95=np.nan,familywise_99=np.nan,median_lucky_win=np.nan,dates=len(a),models=a.shape[1],status='UNAVAILABLE: block spans the entire period')
    rng=np.random.default_rng(SEED+span);result=[]
    for _ in range(replicates):
        ids=[]
        while len(ids)<len(a):
            start=int(rng.integers(len(a)))
            distance=(offsets-offsets[start])%duration
            block=np.flatnonzero(distance<span)
            block=block[np.argsort(distance[block])]
            ids.extend(block.tolist())
        result.append(float(a[np.array(ids[:len(a)])].mean(axis=0).max()))
    return dict(calendar_block_days=span,replicates=replicates,familywise_95=float(np.quantile(result,.95)),familywise_99=float(np.quantile(result,.99)),median_lucky_win=float(np.median(result)),dates=len(a),models=a.shape[1])

def noise():
    models=json.loads((OUT/'model_registry.json').read_text())['models']
    cache=OUT/'35_model_queries.csv.gz'
    if cache.exists():q=pd.read_csv(cache)
    else:
        x=valid(pd.read_pickle(OUT/'panel.pkl.gz',compression='gzip'));x=x[x.decision_date.ge('2020-01-01')]
        q=metrics(x,models);q.to_csv(cache,index=False)
    # Pair each query with the active policy before equal date/sector/profile averaging.
    anchor=q[q.model.eq(ANCHOR if ANCHOR in models else 'sip_risk_confirmed_0.01')].set_index(GROUP)
    q=q.join(anchor[['rank_ic','achievement']],on=GROUP,rsuffix='_baseline')
    results=[]
    for period,mask in [('development',q.decision_date.lt('2024-01-01')),('exposed',q.decision_date.ge('2024-01-01'))]:
        for metric in ['rank_ic','achievement']:
            z=q[mask].copy();z['delta']=z[metric]-z[metric+'_baseline']
            # Every model must have precisely the same query support.
            wide=z.pivot(index=GROUP,columns='model',values='delta').dropna()
            daily=wide.groupby('decision_date').mean()
            for days in [365,730]:
                d=block_floor(daily.to_numpy(),daily.index,days);d.update(period=period,metric=metric,observed_best_delta=float(daily.mean().max()),best_model=daily.mean().idxmax(),matched_queries=len(wide));results.append(d)
    pd.DataFrame(results).to_csv(OUT/'noise_floor.csv',index=False)
    print('NOISE',results,flush=True)

def confidence():
    x=valid(pd.read_pickle(OUT/'panel.pkl.gz',compression='gzip'));x=x[x.decision_date.ge('2020-01-01')]
    models=json.loads((OUT/'model_registry.json').read_text())['models'];rng=np.random.default_rng(SEED);rows=[]
    for key,g in x.groupby(GROUP,observed=True,sort=True):
        if len(g)<5:continue
        s=g[models].to_numpy(); good=np.isfinite(s).all(axis=1);g=g.iloc[np.flatnonzero(good)];s=s[good]
        if len(g)<5:continue
        a=rng.integers(len(g),size=1000);b=rng.integers(len(g),size=1000)
        y=g.future_xirr.to_numpy();anchor=g[ANCHOR].to_numpy();keep=(a!=b)&(y[a]!=y[b]);a=a[keep];b=b[keep]
        votes=np.sign(s[a]-s[b]); agreement=np.abs(votes.mean(axis=1))
        correct=(np.sign(anchor[a]-anchor[b])*np.sign(y[a]-y[b])+1)/2
        dispersion=(g.model_disagreement.to_numpy()[a]+g.model_disagreement.to_numpy()[b])/2
        order=np.argsort(dispersion,kind='stable')
        for fraction in [.25,.5,.75,1.]:
            chosen=order[:max(1,int(len(a)*fraction))]
            rows.append(dict(zip(GROUP,key),retained=fraction,pair_accuracy=float(correct[chosen].mean()),pairs=len(chosen),agreement=float(agreement[chosen].mean())))
    q=pd.DataFrame(rows);q.to_csv(OUT/'confidence_queries.csv.gz',index=False)
    dev=q[q.decision_date.lt('2024-01-01')].groupby('retained').pair_accuracy.mean()
    chosen=float(dev.loc[[.5,.75,1.]].idxmax());save('confidence_lock.json',dict(retained=chosen,development_accuracy=dev.to_dict()))
    report=q.assign(period=np.where(q.decision_date.lt('2024-01-01'),'development','exposed')).groupby(['period','retained'])[['pair_accuracy','agreement']].mean().reset_index()
    report['selected']=report.retained.eq(chosen);report.to_csv(OUT/'confidence_summary.csv',index=False)
    print('CONFIDENCE',report.to_dict('records'),flush=True)

def hysteresis_order(previous, scores, margin):
    order=list(previous)
    for i in range(1,len(order)):
        j=i
        while j>0 and scores[order[j]]>scores[order[j-1]]+margin:
            order[j],order[j-1]=order[j-1],order[j];j-=1
    return order

def hysteresis():
    x=valid(pd.read_pickle(OUT/'panel.pkl.gz',compression='gzip'));x=x[x.decision_date.ge('2020-01-01')];rows=[]
    for (profile,sector),series in x.groupby(['profile_name','sector'],observed=True):
        snapshots=[]
        for day,g in series.groupby('decision_date',sort=True,observed=True):
            g=g.dropna(subset=[ANCHOR]).sort_values('isin')
            if len(g)<5:continue
            scores=g.set_index('isin')[ANCHOR].to_dict();raw=sorted(scores,key=lambda i:(-scores[i],i))
            outcomes=g.set_index('isin').future_xirr.to_dict()
            rawic=g[ANCHOR].corr(g.future_xirr,method='spearman')
            snapshots.append((day,scores,raw,outcomes,rawic))
        for margin in [0,.0025,.005,.01,.02]:
            previous=[];previous_raw=[]
            for day,scores,raw,outcomes,rawic in snapshots:
                old=[i for i in previous if i in scores];oldset=set(old);new=[i for i in raw if i not in oldset]
                ordered=hysteresis_order(old+new,scores,margin)
                if len(old)>=2:
                    ranks={s:i for i,s in enumerate(ordered)};rawranks={s:i for i,s in enumerate(raw)}
                    stable=kendalltau(np.arange(len(old)),[ranks[i] for i in old]).statistic
                    raw_old=[i for i in previous_raw if i in scores]
                    raw_stable=kendalltau(np.arange(len(raw_old)),[rawranks[i] for i in raw_old]).statistic
                    yr=rankdata([outcomes[s] for s in ordered]);yr-=yr.mean()
                    pr=-np.arange(len(ordered),dtype=float);pr-=pr.mean()
                    den=np.linalg.norm(yr)*np.linalg.norm(pr);ic=np.dot(yr,pr)/den if den else np.nan
                    rows.append(dict(decision_date=day,profile_name=profile,sector=sector,margin=margin,kendall_tau=stable,raw_tau=raw_stable,ic_delta=ic-rawic,n_common=len(old)))
                previous=ordered;previous_raw=raw
    q=pd.DataFrame(rows);q.to_csv(OUT/'hysteresis_queries.csv.gz',index=False)
    dev=q[q.decision_date.lt('2024-01-01')].groupby('margin')[['kendall_tau','ic_delta']].mean()
    chosen=float(dev[dev.ic_delta.ge(-.001-1e-12)].kendall_tau.idxmax());save('hysteresis_lock.json',dict(margin=chosen,ic_loss_budget=.001,snapshot_frequency='quarterly until2024,monthly2025'))
    report=q.assign(period=np.where(q.decision_date.lt('2024-01-01'),'development','exposed')).groupby(['period','margin'])[['kendall_tau','raw_tau','ic_delta']].mean().reset_index();report['selected']=report.margin.eq(chosen);report.to_csv(OUT/'hysteresis_summary.csv',index=False)
    print('HYSTERESIS',report.to_dict('records'),flush=True)

def constrain_calibrator(calibrator,labels,weights):
    """Convex sigmoid optimum under nonnegative slope: boundary if sign flips."""
    if calibrator.coef_[0,0]<0:
        calibrator.coef_[0,0]=0.
        calibrator.intercept_[0]=logit(np.clip(np.average(labels,weights=weights),1e-6,1-1e-6))
    return calibrator

def fit_calibrated(train,cal,test,cols,monotone=False):
    params=dict(n_estimators=120,num_leaves=15,max_depth=5,min_child_samples=150,reg_lambda=30,learning_rate=.04,n_jobs=3,random_state=SEED,verbosity=-1,deterministic=True,force_col_wise=True)
    if monotone:
        params['monotone_constraints']=[-1 if c=='target_cagr' else 1 if c=='analog_attainment' else 0 for c in cols]
    m=lgb.LGBMClassifier(**params)
    w=1/train.groupby(GROUP,observed=True).isin.transform('size');w/=w.mean()
    m.fit(train[cols],train.goal_hit.astype(int),sample_weight=w)
    cp=np.clip(m.predict_proba(cal[cols])[:,1],1e-6,1-1e-6)
    cw=1/cal.groupby(GROUP,observed=True).isin.transform('size');cw/=cw.mean()
    calibrator=LogisticRegression(C=1e3,max_iter=500,random_state=SEED).fit(logit(cp).reshape(-1,1),cal.goal_hit.astype(int),sample_weight=cw)
    if monotone:calibrator=constrain_calibrator(calibrator,cal.goal_hit.astype(int),cw)
    raw=np.clip(m.predict_proba(test[cols])[:,1],1e-6,1-1e-6)
    return calibrator.predict_proba(logit(raw).reshape(-1,1))[:,1],m,calibrator

def goal():
    x=valid(pd.read_pickle(OUT/'panel.pkl.gz',compression='gzip'))
    if (OUT/'extra_features.pkl.gz').exists():x=x.merge(pd.read_pickle(OUT/'extra_features.pkl.gz',compression='gzip'),on=['isin','decision_date'],how='left',validate='many_to_one')
    if (OUT/'analog_features.pkl.gz').exists():x=x.merge(pd.read_pickle(OUT/'analog_features.pkl.gz',compression='gzip'),on=KEYS,how='left',validate='one_to_one')
    families={'goal_base':old.COLS,'goal_volume':old.COLS+VOL,'goal_peers':old.COLS+PEER,'goal_analogs':old.COLS+ANALOG,'goal_combined':old.COLS+VOL+PEER+ANALOG}
    families={n:c for n,c in families.items() if all(v in x for v in c)}
    audits=[];pred=[]
    for year in range(2020,2026):
        # A 12-month outcome requires the calibration decisions to start two
        # calendar years before the test, not one year before it.
        cutoff=f'{year}-01-01';split=f'{year-2}-01-01'
        t=x[x.endpoint.lt(split)];cal=x[x.decision_date.ge(split)&x.endpoint.lt(cutoff)];z=x[x.decision_date.str.startswith(str(year))].copy()
        z['climatology']=float(cal.goal_hit.mean())
        assert len(t) and len(cal) and len(z)
        assert t.endpoint.max()<split and cal.endpoint.max()<cutoff
        for name,cols in families.items():
            audits.append(dict(model=name,year=year,train_rows=len(t),calibration_rows=len(cal),max_training_endpoint=t.endpoint.max(),max_calibration_endpoint=cal.endpoint.max(),feature_count=len(cols)))
            dest=OUT/f'{name}_{year}.csv.gz'
            if dest.exists():
                z[name]=pd.read_csv(dest)[name].to_numpy();continue
            probability,m,c=fit_calibrated(t,cal,z,cols,monotone=MONOTONE);z[name]=probability
            m.booster_.save_model(str(OUT/f'{name}_{year}.txt'))
            save(f'{name}_{year}_calibrator.json',dict(intercept=c.intercept_.tolist(),coefficient=c.coef_.tolist()))
            z[KEYS+[name]].to_csv(dest,index=False)
            print('GOAL FIT',name,year,len(t),len(cal),flush=True)
        pred.append(z[KEYS+['sector','future_xirr','future_drawdown','future_shortfall','goal_hit',ANCHOR,'target_cagr','climatology']+list(families)])
    z=pd.concat(pred,ignore_index=True);z.to_pickle(OUT/'goal_predictions.pkl.gz',compression='gzip')
    if audits:pd.DataFrame(audits).to_csv(OUT/'goal_training_audit.csv',index=False)
    devq=metrics(z[z.decision_date.lt('2024-01-01')],[ANCHOR]+list(families))
    development=devq.groupby(['model','decision_date']).achievement.mean().groupby('model').mean()
    chosen=development.loc[sorted(families)].idxmax()
    save('goal_development_lock.json',dict(selected=chosen,selection='equal-date/equal-query Top3 goal attainment; deterministic model-name tie break',development=development.to_dict()))
    recentq=metrics(z[z.decision_date.ge('2024-01-01')],[ANCHOR]+list(families))
    q=pd.concat([devq,recentq],ignore_index=True);q.to_csv(OUT/'goal_queries.csv.gz',index=False)
    summary=q.assign(period=np.where(q.decision_date.lt('2024-01-01'),'development','exposed')).groupby(['period','model','decision_date'])[['rank_ic','achievement','legacy_achievement','xirr','drawdown']].mean().groupby(['period','model']).mean().reset_index();summary['selected']=summary.model.eq(chosen);summary.to_csv(OUT/'goal_summary.csv',index=False)
    calibration=[]
    for period,g in z.groupby(np.where(z.decision_date.lt('2024-01-01'),'development','exposed')):
        for name in [*families,'climatology']:
            y=g.goal_hit.astype(int);prob=g[name]
            calibration.append(dict(period=period,model=name,brier=brier_score_loss(y,prob),log_loss=log_loss(y,prob,labels=[0,1]),auc=roc_auc_score(y,prob),mean_probability=prob.mean(),actual_frequency=y.mean()))
    pd.DataFrame(calibration).to_csv(OUT/'goal_calibration.csv',index=False)
    # Target changes use exactly the same investor schedule and same identities.
    matched=z[z.profile_name.isin(['base7500','target10','target30'])].pivot(index=['isin','decision_date'],columns='profile_name',values='goal_base').dropna()
    save('goal_personalization.json',dict(matched_stock_dates=len(matched),probabilities_changed=int((matched.max(axis=1)-matched.min(axis=1)>1e-9).sum()),target10_ge_target30_fraction=float((matched.target10>=matched.target30).mean())))
    print('GOAL SUMMARY',summary.to_dict('records'),flush=True)

def meta():
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    x=valid(pd.read_pickle(OUT/'panel.pkl.gz',compression='gzip'));x=x[x.decision_date.ge('2020-01-01')].dropna(subset=[ANCHOR])
    x['score_gap']=x[ANCHOR]-x[ANCHOR].groupby([x[g] for g in GROUP]).transform('median')
    x['regime']=x.return63.groupby(x.decision_date).transform('median')
    picks=x.sort_values([*GROUP,ANCHOR,'isin'],ascending=[True,True,True,False,True]).groupby(GROUP,observed=True).head(3).copy()
    features=['model_disagreement','score_gap','regime','evidence_fraction','zero_fraction','stale_days','volatility252','downside252','drawdown252','return21','return63','target_cagr']
    z=[];audit=[]
    for year in range(2022,2026):
        cutoff=f'{year}-01-01';train=picks[picks.endpoint.lt(cutoff)];test=picks[picks.decision_date.str.startswith(str(year))].copy()
        model=make_pipeline(SimpleImputer(add_indicator=True),StandardScaler(),LogisticRegression(C=.1,max_iter=500,random_state=SEED))
        model.fit(train[features],train.goal_hit.astype(int));test['meta_probability']=model.predict_proba(test[features])[:,1];z.append(test)
        audit.append(dict(year=year,training_rows=len(train),max_training_endpoint=train.endpoint.max(),test_start=test.decision_date.min()))
    z=pd.concat(z);dev=z[z.decision_date.lt('2024-01-01')];choices=[]
    for retain in [.5,.75,1.]:
        threshold=float(dev.meta_probability.quantile(1-retain)) if retain<1 else 0.
        selected=dev[dev.meta_probability.ge(threshold)]
        choices.append(dict(retained=retain,threshold=threshold,accuracy=float(selected.goal_hit.mean())))
    chosen=sorted(choices,key=lambda c:(-c['accuracy'],-c['retained']))[0];save('meta_lock.json',chosen)
    rows=[]
    for period,g in z.groupby(np.where(z.decision_date.lt('2024-01-01'),'development','exposed')):
        selected=g[g.meta_probability.ge(chosen['threshold'])]
        rows.append(dict(period=period,ungated_hit_rate=float(g.goal_hit.mean()),selected_hit_rate=float(selected.goal_hit.mean()),retained_fraction=len(selected)/len(g),total_picks=len(g),selected_picks=len(selected),selected_mean_drawdown=float(selected.future_drawdown.mean()),ungated_mean_drawdown=float(g.future_drawdown.mean()),queries_with_any_pick=selected.groupby(GROUP,observed=True).ngroups,total_queries=g.groupby(GROUP,observed=True).ngroups))
    pd.DataFrame(rows).to_csv(OUT/'meta_summary.csv',index=False);pd.DataFrame(audit).to_csv(OUT/'meta_maturity_audit.csv',index=False)
    z[KEYS+['sector','goal_hit','meta_probability']].to_csv(OUT/'meta_predictions.csv.gz',index=False)
    print('META',rows,flush=True)

def kronos_compare():
    from sklearn.decomposition import PCA
    x=valid(pd.read_pickle(OUT/'panel.pkl.gz',compression='gzip'))
    keys=pd.read_csv(OUT/'kronos_input_keys.csv');embedding=np.load(OUT/'kronos_embeddings.npy');keys['embedding_row']=np.arange(len(keys))
    x=x.merge(keys,on=['isin','decision_date'],validate='many_to_one');records=[];calibrations=[];audit=[]
    for year in range(2020,2026):
        cutoff=f'{year}-01-01';split=f'{year-2}-01-01'
        train=x[x.endpoint.lt(split)].copy();cal=x[x.decision_date.ge(split)&x.endpoint.lt(cutoff)].copy();test=x[x.decision_date.str.startswith(str(year))].copy()
        if min(len(train),len(cal),len(test))<100:continue
        rows=np.unique(train.embedding_row);pca=PCA(n_components=16,random_state=SEED).fit(embedding[rows])
        cols=[f'kronos_pca{j}' for j in range(16)]
        for g in [train,cal,test]:g[cols]=pca.transform(embedding[g.embedding_row])
        for name,features in [('matched_base',old.COLS),('kronos_features',old.COLS+cols)]:
            prob,model,c=fit_calibrated(train,cal,test,features);test[name]=prob
            calibrations.append(dict(year=year,model=name,brier=brier_score_loss(test.goal_hit.astype(int),prob),auc=roc_auc_score(test.goal_hit.astype(int),prob)))
        records.append(test[KEYS+['sector','goal_hit','future_xirr','future_drawdown','future_shortfall',ANCHOR,'matched_base','kronos_features']])
        audit.append(dict(year=year,max_training_endpoint=train.endpoint.max(),max_calibration_endpoint=cal.endpoint.max(),rows=len(test),pca_fit_unique_training_windows=len(rows),pretrained_temporal_contamination=True))
        print('KRONOS COMPARE',year,len(test),flush=True)
    q=metrics(pd.concat(records),['matched_base','kronos_features']);q.to_csv(OUT/'kronos_queries.csv.gz',index=False)
    summary=q.assign(period=np.where(q.decision_date.lt('2024-01-01'),'development','exposed')).groupby(['period','model'])[['rank_ic','achievement','xirr','drawdown']].mean().reset_index();summary.to_csv(OUT/'kronos_summary.csv',index=False)
    pd.DataFrame(audit).to_csv(OUT/'kronos_training_audit.csv',index=False);pd.DataFrame(calibrations).to_csv(OUT/'kronos_calibration.csv',index=False)
    print('KRONOS SUMMARY',summary.to_dict('records'),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('stage',choices=['prepare','noise','confidence','hysteresis','goal','meta','kronos_compare']);args=a.parse_args();globals()[args.stage]()
