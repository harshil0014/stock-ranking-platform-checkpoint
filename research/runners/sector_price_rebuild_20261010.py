"""Price-basis rebuild and top-focused sector ranking experiment; no UI promotion."""
from pathlib import Path
import argparse,json,hashlib,gc,itertools
import numpy as np
import pandas as pd
import lightgbm as lgb
from sector_championship_20261005 import ROOT,KEYS,METRICS,metrics

OUT=ROOT/'experiments/sector-price-rebuild-20261010'
OLD=ROOT/'experiments/action-guarded-sector-20261008'
NEW=ROOT/'experiments/full-coverage-open-models-20261008'
ASOF='2026-10-03'
RAW=['return21','return63','return126','return252','momentum12_1',
     'high_gap63','high_gap126','high_gap252','high_age252','near_high_fraction',
     'high_hits','breakout_strength','slope126','trend_r2','efficiency126',
     'volatility252','downside252','drawdown252','positive_fraction',
     'zero_fraction','largest_jump_share','tail_loss','return_skew',
     'ma21_gap','ma63_gap','ma126_gap','ma252_gap','acceleration',
     'observations','stale_days','history_days']
PARAMS=['log_amount','lookback_months','log_interval','target_cagr']
COLS=RAW+['q_'+c for c in RAW]+['sector_return126','sector_breadth','relative_momentum','evidence_fraction']+PARAMS
CONFIGS=[dict(name=f'{loss}_{target}',loss=loss,target=target) for loss,target in itertools.product(['rank_xendcg','lambdarank','regression_l1'],['return','balanced'])]
WEIGHTS=[.1,.25,.5,1.0]

def snapshot(dates,prices,day,event_days=()):
    """Only observed prices at/before decision date; unresolved input windows abstain."""
    day=np.datetime64(day,'D');stop=np.searchsorted(dates,day,side='right')
    result={c:np.nan for c in RAW};result.update(input_status='NO_PRICE',last_price_date=None)
    if stop<22:return result
    d=dates[:stop];p=prices[:stop];begin=max(0,stop-253)
    result['last_price_date']=str(d[-1]);result['input_status']='USABLE_PROVIDER_BASIS'
    if any(d[begin] < np.datetime64(e,'D') <= day for e in event_days):
        result['input_status']='UNRESOLVED_ACTION_IN_FEATURE_WINDOW';return result
    if int((day-d[-1]).astype(int))>14:
        result['input_status']='STALE_PRICE';return result
    s=p[begin:];ret=np.diff(np.log(s));simple=np.expm1(ret)
    if not len(ret):return result
    result.update(observations=len(s)-1,stale_days=int((day-d[-1]).astype(int)),history_days=int((d[-1]-d[0]).astype(int)))
    for n in [21,63,126,252]:
        if len(p)>n:
            result[f'return{n}']=p[-1]/p[-n-1]-1
            result[f'ma{n}_gap']=p[-1]/p[-n:].mean()-1
            if n!=21:result[f'high_gap{n}']=p[-1]/p[-n:].max()-1
    if len(p)>252:result['momentum12_1']=p[-22]/p[-253]-1
    result['high_age252']=(len(s)-1-int(np.flatnonzero(s==s.max())[-1]))/252
    rolling_high=np.maximum.accumulate(s)
    result['near_high_fraction']=float(np.mean(s>=.95*rolling_high))
    result['high_hits']=float(np.mean(s>=rolling_high))
    result['breakout_strength']=s[-1]/s[:-1].max()-1
    result['volatility252']=float(np.std(simple)*np.sqrt(252))
    result['downside252']=float(np.sqrt(np.mean(np.minimum(simple,0)**2))*np.sqrt(252))
    result['drawdown252']=float(np.min(s/rolling_high-1))
    result['positive_fraction']=float(np.mean(simple>0));result['zero_fraction']=float(np.mean(simple==0))
    result['largest_jump_share']=float(np.max(np.abs(ret))/max(np.abs(ret).sum(),1e-12))
    result['tail_loss']=float(np.quantile(simple,.05))
    sd=np.std(simple);result['return_skew']=float(np.mean(((simple-simple.mean())/sd)**3)) if sd>1e-12 else 0.
    if len(p)>=126:
        logs=np.log(p[-126:]);time=np.arange(126);center=time-time.mean();yc=logs-logs.mean()
        slope=float(np.dot(center,yc)/np.dot(center,center));denom=float(np.dot(yc,yc))
        result['slope126']=slope*252;result['trend_r2']=float(slope*slope*np.dot(center,center)/denom) if denom>1e-12 else 0.
        result['efficiency126']=float((logs[-1]-logs[0])/max(np.abs(np.diff(logs)).sum(),1e-12))
    result['acceleration']=result['return21']-result['return126']/6 if np.isfinite(result['return126']) else np.nan
    return result

def engineer(x):
    x=x.copy();groups=[x.decision_date,x.sector]
    for c in RAW:x['q_'+c]=x[c].groupby(groups).rank(pct=True)
    x['sector_return126']=x.return126.groupby(groups).transform('median')
    x['sector_breadth']=x.return126.gt(0).where(x.return126.notna()).groupby(groups).transform('mean')
    x['relative_momentum']=x.return126-x.sector_return126
    x['evidence_fraction']=x[RAW].notna().mean(axis=1)
    return x

def prepare():
    OUT.mkdir(exist_ok=True)
    protocol={'as_of':ASOF,'configs':CONFIGS,'blend_weights':WEIGHTS,'features':COLS,
      'price_basis':'Provider raw_close is already split-adjusted. Do not undo provider splits and combine with a different holdings ledger. Use scale-invariant price features only; not nominal execution prices.',
      'feature_guard':'Use at most last 253 observations at/before decision. Mask all price features when this window spans an unresolved provider/official event; abstain on >14 calendar day stale prices.',
      'outcomes':'Retained SIP outcomes with prior unresolved-action windows masked; not a complete independent rebuild of all outcomes.',
      'gate':'All six metrics nonworse across Top1/3/5, both periods, raw/capped, nine profiles and common/expanded scopes versus production where scored, old full-coverage models and guarded challenger. Strict improvement required. No change to prior gate.',
      'training':'Six annual folds; actual outcome endpoint strictly before test-year Jan1. Train all nine profiles; equal date/profile/sector weights; no feature-empty training rows.',
      'selection':'Choose fewest development Top3 regressions, then total development regressions before examining recent outcomes. Prior studies exposed all dates; no fresh holdout.',
      'targets':'Sector percentile future return or .5 return + .25 drawdown + .25 inverse shortfall. Ranker uses integer levels; L1 regressor continuous relevance.',
      'rank_loss':'lambdarank truncation 5 and linear gains for top-focused alternative; rank_xendcg comparator; robust absolute-error regression alternative.',
      'sources':['https://proceedings.mlr.press/v202/lyzhin23a.html','https://arxiv.org/abs/2012.07149','https://lightgbm.readthedocs.io/en/latest/Parameters.html'],
      'limits':'Current-survivor identities and retrospective sector mapping. Provider basis not official price certification. Saved anchors can inherit old label defects. All dates previously exposed.'}
    path=OUT/'protocol.json'
    if path.exists():assert json.loads(path.read_text())==protocol
    path.write_text(json.dumps(protocol,indent=2))
    if (OUT/'prepared.pkl.gz').exists():return
    original=pd.read_pickle(OLD/'prepared.pkl.gz',compression='gzip')
    keep=KEYS+['sector','period','endpoint','future_xirr','future_drawdown','future_shortfall','sector_incumbent','open_model','frozen_challenger']+PARAMS
    x=original[keep].copy();del original;gc.collect()
    identities=pd.read_csv(NEW/'current_all_stock_rankings.csv',usecols=['isin','ticker','sector'])
    dates=sorted(set(x.decision_date)|{ASOF})
    events=pd.read_csv(ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv')
    unresolved={i:g.event_date.tolist() for i,g in events[events.status.ne('ALIGNED_MULTIPLIER')].groupby('isin')}
    rows=[];audit=[]
    for n,row in enumerate(identities.itertuples(index=False)):
        p=ROOT/'data/live_market/history_cache'/f'{row.ticker}.csv'
        try:
            h=pd.read_csv(p,usecols=['date','raw_close']);h.date=pd.to_datetime(h.date)
            assert h.date.is_monotonic_increasing and h.date.is_unique
            ds=h.date.to_numpy(dtype='datetime64[D]');prices=h.raw_close.to_numpy(float)
            assert np.isfinite(prices).all() and (prices>0).all()
            for day in dates:rows.append(dict(isin=row.isin,sector=row.sector,decision_date=day,**snapshot(ds,prices,day,unresolved.get(row.isin,()))))
            audit.append(dict(isin=row.isin,ticker=row.ticker,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),status='READ'))
        except (OSError,ValueError,AssertionError) as exc:
            audit.append(dict(isin=row.isin,ticker=row.ticker,status='UNAVAILABLE',reason=str(exc)))
            for day in dates:rows.append(dict(isin=row.isin,sector=row.sector,decision_date=day,**{c:np.nan for c in RAW},input_status='NO_VALID_HISTORY',last_price_date=None))
        if (n+1)%500==0:print('FEATURES',n+1,flush=True)
    f=engineer(pd.DataFrame(rows));f.to_pickle(OUT/'price_features.pkl.gz',compression='gzip')
    pd.DataFrame(audit).to_csv(OUT/'history_source_audit.csv',index=False)
    assert not f.duplicated(['isin','decision_date']).any()
    assert (f.last_price_date.dropna()<=f.loc[f.last_price_date.notna(),'decision_date']).all()
    # Each profile receives precisely the same price features and sector peers.
    x=x.merge(f.drop(columns='sector'),on=['isin','decision_date'],how='left',validate='many_to_one')
    for c in COLS:x[c]=x[c].astype('float32')
    x.to_pickle(OUT/'prepared.pkl.gz',compression='gzip')
    f.groupby(['decision_date','input_status']).size().rename('stocks').reset_index().to_csv(OUT/'feature_coverage.csv',index=False)
    print('PREPARED',len(x),len(f),flush=True)

def fit(t,c):
    t=t.dropna(subset=['future_xirr','future_drawdown','future_shortfall'])
    t=t[t.evidence_fraction.gt(0)&t.sector.ne('Unclassified')]
    t=t[t.groupby(['decision_date','profile_name','sector'])['isin'].transform('size').ge(5)].sort_values(['decision_date','profile_name','sector','isin'])
    g=t.groupby(['decision_date','profile_name','sector'],sort=False)
    r=g.future_xirr.rank(pct=True);d=g.future_drawdown.rank(pct=True);s=g.future_shortfall.rank(pct=True,ascending=False)
    y=r if c['target']=='return' else .5*r+.25*d+.25*s
    w=1/g['isin'].transform('size');w=w/w.mean()
    kwargs=dict(objective=c['loss'],n_estimators=180,num_leaves=15,max_depth=5,min_child_samples=200,reg_lambda=30,learning_rate=.03,n_jobs=3,random_state=20261010,deterministic=True,force_col_wise=True,verbosity=-1)
    if c['loss']=='regression_l1':
        model=lgb.LGBMRegressor(**kwargs);model.fit(t[COLS],y,sample_weight=w)
    else:
        model=lgb.LGBMRanker(**kwargs,label_gain=list(range(20)),lambdarank_truncation_level=5)
        model.fit(t[COLS],np.floor(y*19).astype(int),group=g.size().to_numpy(),sample_weight=w)
    return model,t

def rank_prediction(model,x):
    raw=pd.Series(model.predict(x[COLS]),index=x.index)
    return raw.groupby([x.decision_date,x.profile_name,x.sector]).rank(pct=True).where(x.evidence_fraction.gt(0),.5)

def learn():
    x=pd.read_pickle(OUT/'prepared.pkl.gz',compression='gzip');audit=[]
    for year in range(2020,2026):
        path=OUT/f'predictions_{year}.csv.gz'
        if path.exists():continue
        test=x[x.decision_date.str.startswith(str(year))].copy();train=x[x.endpoint.lt(f'{year}-01-01')]
        for c in CONFIGS:
            m,t=fit(train,c);test[c['name']]=rank_prediction(m,test)
            m.booster_.save_model(str(OUT/f'{c["name"]}_{year}.txt'))
            audit.append(dict(year=year,model=c['name'],training_rows=len(t),max_training_endpoint=t.endpoint.max(),test_start=test.decision_date.min(),profiles=t.profile_name.nunique()))
            print('FIT',year,c['name'],len(t),flush=True)
        test[KEYS+['sector','period','endpoint','future_xirr','future_drawdown','future_shortfall','sector_incumbent','open_model','frozen_challenger','evidence_fraction']+[c['name'] for c in CONFIGS]].to_csv(path,index=False)
        previous=pd.read_csv(OUT/'training_audit.csv') if (OUT/'training_audit.csv').exists() else pd.DataFrame()
        pd.concat([previous,pd.DataFrame(audit)]).drop_duplicates(['year','model'],keep='last').to_csv(OUT/'training_audit.csv',index=False)

def evaluate():
    x=pd.concat([pd.read_csv(OUT/f'predictions_{y}.csv.gz') for y in range(2020,2026)],ignore_index=True)
    old=pd.concat([pd.read_csv(OLD/f'predictions_{y}.csv.gz',usecols=KEYS+['profile_defensive_15']) for y in range(2020,2026)],ignore_index=True)
    x=x.merge(old,on=KEYS,validate='one_to_one');x['guarded_previous']=.8*x.open_model+.2*x.profile_defensive_15
    names=[]
    for c in CONFIGS:
        for w in WEIGHTS:
            n=f'{c["name"]}_blend{w}';x[n]=(1-w)*x.guarded_previous+w*x[c['name']];names.append(n)
    summaries=[]
    for scope in ['common','expanded']:
        z=x[x.sector_incumbent.notna()].copy() if scope=='common' else x.copy()
        refs=['open_model','frozen_challenger','guarded_previous']+(['sector_incumbent'] if scope=='common' else [])
        for bounded in [False,True]:
            zz=z.copy()
            if bounded:zz.future_xirr=zz.future_xirr.clip(-1,1)
            for i in range(0,len(names),6):
                q=metrics(zz,refs+names[i:i+6],top_ns=(1,3,5))
                q.to_csv(OUT/f'queries_{scope}_{bounded}_{i}.csv.gz',index=False)
                a=q.groupby(['model','period','profile','top_n','sector'])[METRICS].mean().groupby(['model','period','profile','top_n']).mean().reset_index()
                a['scope']=scope;a['return_treatment']='capped' if bounded else 'raw';summaries.append(a)
                print('EVALUATE',scope,bounded,i,flush=True)
    summary=pd.concat(summaries).drop_duplicates(['model','period','profile','top_n','scope','return_treatment'])
    summary.to_csv(OUT/'summary.csv',index=False)
    a=summary.set_index(['model','period','profile','top_n','scope','return_treatment'])[METRICS];trials=[];all_deltas=[]
    for n in names:
        differences=[]
        for ref in ['open_model','frozen_challenger','guarded_previous','sector_incumbent']:
            d=(a.loc[n]-a.loc[ref]).dropna();d.shortfall=-d.shortfall;d['reference']=ref;differences.append(d.reset_index())
        d=pd.concat(differences);d['model']=n
        all_deltas.append(d)
        values=d[METRICS].to_numpy().ravel();top=d[d.top_n.eq(3)][METRICS].to_numpy().ravel();dev=d[d.period.eq('development')];devtop=dev[dev.top_n.eq(3)]
        trials.append(dict(model=n,strict_gate=bool((values>=-1e-12).all() and (values>1e-12).any()),regressing_cells=int((values < -1e-12).sum()),total_cells=len(values),top3_regressing_cells=int((top < -1e-12).sum()),top3_cells=len(top),development_top3_regressions=int(devtop[METRICS].lt(-1e-12).sum().sum()),development_regressions=int(dev[METRICS].lt(-1e-12).sum().sum())))
    trials=pd.DataFrame(trials).sort_values(['development_top3_regressions','development_regressions','model']);trials.to_csv(OUT/'trials.csv',index=False)
    pd.concat(all_deltas).to_csv(OUT/'directional_deltas.csv',index=False)
    selected=trials.iloc[0].to_dict();selected.update(status='RESEARCH_ONLY',fresh_validation=False,production_replaced=False)
    (OUT/'selection.json').write_text(json.dumps(selected,indent=2))
    x[KEYS+[selected['model']]].rename(columns={selected['model']:'replacement_score'}).to_csv(OUT/'selected_historical_scores.csv.gz',index=False)
    print(trials.head(10).to_string(index=False),flush=True)

def refresh_current():
    identities=pd.read_csv(NEW/'current_all_stock_rankings.csv',usecols=['isin','ticker','sector'])
    events=pd.read_csv(ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv')
    unresolved={i:g.event_date.tolist() for i,g in events[events.status.ne('ALIGNED_MULTIPLIER')].groupby('isin')}
    histories={};sources=[]
    for name in ['history.npz','peak_history.npz']:
        path=ROOT/'research/runtime/personalized-v17'/name
        with np.load(path,allow_pickle=False) as data:
            offsets=data['offsets'];dates=data['dates'].astype('datetime64[D]');raw=data['raw']
            for i,isin in enumerate(data['identities'].astype(str)):
                a,b=int(offsets[i]),int(offsets[i+1]);histories[isin]=(dates[a:b],raw[a:b])
        sources.append(dict(path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),basis='raw provider split-adjusted Close, not reconstructed nominal or economic series'))
    rows=[]
    for r in identities.itertuples(index=False):
        dates,prices=histories.get(r.isin,(np.array([],dtype='datetime64[D]'),np.array([],dtype=float)))
        rows.append(dict(isin=r.isin,sector=r.sector,decision_date=ASOF,**snapshot(dates,prices,ASOF,unresolved.get(r.isin,()))))
    current=pd.DataFrame(rows)
    rescue=OUT/'current_input_rescue/accepted_features.csv'
    if rescue.exists():
        recovered=pd.read_csv(rescue).set_index('isin')
        current=current.set_index('isin')
        for isin,row in recovered.iterrows():
            assert row.decision_date==ASOF and row.input_status=='USABLE_PROVIDER_BASIS'
            if isin in current.index and current.at[isin,'input_status']=='NO_PRICE':
                for col in RAW+['input_status','last_price_date']:current.at[isin,col]=row[col]
        current=current.reset_index();sources.append(dict(path=str(rescue.relative_to(ROOT)),sha256=hashlib.sha256(rescue.read_bytes()).hexdigest(),basis='Current-only provider receipts from verified identity mappings; unresolved splits excluded.'))
    current=engineer(current)
    f=pd.read_pickle(OUT/'price_features.pkl.gz',compression='gzip');f=pd.concat([f[f.decision_date.ne(ASOF)],current],ignore_index=True)
    f.to_pickle(OUT/'price_features.pkl.gz',compression='gzip')
    f.groupby(['decision_date','input_status']).size().rename('stocks').reset_index().to_csv(OUT/'feature_coverage.csv',index=False)
    (OUT/'current_history_source_audit.json').write_text(json.dumps({'sources':sources,'reason':'Historical CSV cache ends September18. Current-only features use later runtime source receipts, without using later observations in training.','input_status':current.input_status.value_counts().to_dict()},indent=2))
    print('CURRENT FEATURES',current.input_status.value_counts().to_dict(),flush=True)

def export():
    refresh_current()
    chosen=json.loads((OUT/'selection.json').read_text());name,w=chosen['model'].split('_blend');w=float(w);config=next(c for c in CONFIGS if c['name']==name)
    x=pd.read_pickle(OUT/'prepared.pkl.gz',compression='gzip');m,t=fit(x[x.endpoint.lt(ASOF)],config)
    m.booster_.save_model(str(OUT/'current_model.txt'))
    current=pd.read_csv(OLD/'current_all_stock_rankings.csv')
    f=pd.read_pickle(OUT/'price_features.pkl.gz',compression='gzip');f=f[f.decision_date.eq(ASOF)]
    z=current.drop(columns=[c for c in COLS if c in current and c not in PARAMS]+['input_status','last_price_date'],errors='ignore').merge(f.drop(columns='sector'),on=['isin','decision_date'],validate='one_to_one')
    z[COLS]=z[COLS].astype('float32');z['rebuilt_pure_score']=rank_prediction(m,z)
    replay=rank_prediction(lgb.Booster(model_file=str(OUT/'current_model.txt')),z)
    np.testing.assert_allclose(z.rebuilt_pure_score,replay,atol=0,rtol=0)
    z['rebuilt_score']=(1-w)*z.guarded_model_score+w*z.rebuilt_pure_score
    z['rebuilt_sector_rank']=z.rebuilt_score.groupby(z.sector).rank(method='min',ascending=False)
    z=z.rename(columns={'evidence_confidence':'anchor_evidence_confidence'})
    z['rebuilt_input_confidence']=np.where(z.input_status.ne('USABLE_PROVIDER_BASIS'),z.input_status,np.where(z.observations.ge(252),'FULL_YEAR_OBSERVATIONS','SHORT_HISTORY'))
    assert len(z)==4436 and z['isin'].is_unique and np.isfinite(z.rebuilt_score).all()
    z.sort_values(['sector','rebuilt_sector_rank','isin']).to_csv(OUT/'current_all_stock_rankings.csv',index=False)
    chosen.update(current_rows=len(z),input_usable=int(z.evidence_fraction.gt(0).sum()),current_snapshot=ASOF,current_training_rows=len(t),max_training_endpoint=t.endpoint.max(),current_replay_exact=True)
    (OUT/'selection.json').write_text(json.dumps(chosen,indent=2));print('CURRENT',json.dumps(chosen),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','learn','evaluate','export','all']);args=parser.parse_args()
    for name,fn in [('prepare',prepare),('learn',learn),('evaluate',evaluate),('export',export)]:
        if args.stage in [name,'all']:fn()
