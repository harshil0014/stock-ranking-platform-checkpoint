"""Full-universe sector challenger: purged chronological ranking experiments.

No eligibility screen removes a score. Sparse evidence yields shrinkage and ties,
not fabricated precision. This isolated research runner never changes the live app.
"""
from pathlib import Path
import sys,json,hashlib,itertools
import numpy as np
import pandas as pd
import lightgbm as lgb
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'experiments/full-coverage-challenger-20261008'
PKG=ROOT/'research/runtime/personalized-v17'
KEYS=['isin','decision_date','profile_name']
RAW=['days_since_recorded_high','distance_from_recorded_high','high52_freshness',
     'downside_volatility_1y','momentum_12_1','distance_from_52w_high',
     'full_history_max_drawdown','history_months','cagr_3y','observed_cagr_5y',
     'high_support','strict_cagr_1y','momentum_6m','downside_frequency_1y']
METRICS=['xirr','drawdown','achievement','shortfall','ndcg']
CONFIGS=[dict(name=f'{objective}_{target}_{leaves}',objective=objective,target=target,leaves=leaves)
         for objective,target,leaves in itertools.product(['lambdarank','rank_xendcg'],['return','balanced'],[7,15])]


def write(name,data):
    OUT.mkdir(exist_ok=True)
    (OUT/name).write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf-8')


def prepare():
    protocol={'objective':'Within-sector full-coverage stock strength; trading suitability separate',
        'coverage':'Every current identity receives finite score; no usable price evidence gets neutral prior and LOW/NO_PRICE confidence; Unclassified is not a verified sector',
        'training':'Base7500 outcomes only; train endpoint strictly before Jan 1 of test year; annual forward folds 2020-2025',
        'selection':'2020-2023 only. 2024-2025 locked diagnostic after selection. All dates previously researched, not fresh holdout.',
        'families':CONFIGS,'trees':160,'features':RAW,
        'rule_families':['high_strength','balanced_strength','risk_strength'],
        'blend_weights':[0,.1,.25,.5,1],
        'primary':'Equal-sector/date Top3 SIP-XIRR, drawdown, achievement, shortfall, NDCG; evaluate common and expanded populations on same query dates',
        'gate':'Both common and expanded development: nonnegative utility; XIRR>=champion, drawdown loss <=1pp, shortfall increase <=0.5pp, achievement/NDCG loss <=1pp. Coverage 100%.',
        'utility':'delta xirr + .5 delta drawdown + .5 delta achievement - delta shortfall + .2 delta ndcg',
        'limits':'Current sector labels and surviving universe; pre-existing historical outcomes and adjustment conventions; no historical current-fundamental leakage.',
        'research_sources':['https://lightgbm.readthedocs.io/en/latest/Parameters.html',
          'https://lightgbm.readthedocs.io/en/latest/Advanced-Topics.html',
          'https://catboost.ai/docs/en/concepts/loss-functions-ranking',
          'https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html']}
    path=OUT/'protocol.json';OUT.mkdir(exist_ok=True)
    if path.exists() and json.loads(path.read_text())!=protocol:raise ValueError('Protocol mismatch')
    write('protocol.json',protocol)
    if (OUT/'historical.pkl.gz').exists():return
    x=pd.read_pickle(ROOT/'experiments/sector-championship-20261005/enhanced.pkl.gz',compression='gzip')
    x=x[x.profile_name.eq('base7500')].copy()
    original=pd.read_pickle(ROOT/'experiments/personalized-deep-championship-20261002/v3/prepared.pkl.gz',compression='gzip')
    x=x.merge(original[KEYS+['endpoint']],on=KEYS,validate='one_to_one')
    x=features(x)
    x.to_pickle(OUT/'historical.pkl.gz',compression='gzip')
    print('PREPARED',len(x),flush=True)


def features(x):
    x=x.copy();x['sector']=x.sector.fillna('Unclassified')
    groups=[x.decision_date,x.sector]
    for c in RAW:
        x[c]=pd.to_numeric(x[c],errors='coerce').replace([np.inf,-np.inf],np.nan)
        x['q_'+c]=x[c].groupby(groups).rank(pct=True,ascending=c not in ['days_since_recorded_high','downside_volatility_1y','downside_frequency_1y'])
    # Old highs are judged chiefly by proximity, not age alone.
    x['high_block']=pd.concat([x.q_distance_from_recorded_high,x.q_high52_freshness,x.q_distance_from_52w_high,x.q_high_support],axis=1).mean(axis=1)
    x['risk_block']=pd.concat([x.q_downside_volatility_1y,x.q_downside_frequency_1y,x.q_full_history_max_drawdown],axis=1).mean(axis=1)
    x['momentum_block']=pd.concat([x.q_momentum_12_1,x.q_momentum_6m,x.q_strict_cagr_1y],axis=1).mean(axis=1)
    x['growth_block']=pd.concat([x.q_cagr_3y,x.q_observed_cagr_5y],axis=1).mean(axis=1)
    x['evidence_fraction']=x[RAW].notna().mean(axis=1)
    for name,w in [('high_strength',[.55,.2,.15,.1]),('balanced_strength',[.35,.25,.25,.15]),('risk_strength',[.35,.4,.15,.1])]:
        b=x[['high_block','risk_block','momentum_block','growth_block']]
        score=(b.fillna(.5).to_numpy()*np.array(w)).sum(axis=1)
        x[name]=.5+(score-.5)*x.evidence_fraction
    return x


def predictors():return RAW+['q_'+c for c in RAW]+['evidence_fraction']


def fit(train,c):
    train=train.dropna(subset=['future_xirr','future_drawdown','future_shortfall']).copy()
    train=train[train.sector.ne('Unclassified')]
    counts=train.groupby(['decision_date','sector'])['isin'].transform('size')
    train=train[counts.ge(5)].sort_values(['decision_date','sector','isin'])
    groups=train.groupby(['decision_date','sector'],sort=False)
    yr=groups.future_xirr.rank(pct=True);dr=groups.future_drawdown.rank(pct=True);sr=groups.future_shortfall.rank(pct=True,ascending=False)
    relevance=yr if c['target']=='return' else .5*yr+.25*dr+.25*sr
    labels=np.floor(relevance*9).astype(int)
    model=lgb.LGBMRanker(objective=c['objective'],n_estimators=160,num_leaves=c['leaves'],
        learning_rate=.035,max_depth=5,min_child_samples=70,reg_lambda=20,verbosity=-1,
        n_jobs=3,random_state=20261008,deterministic=True,force_col_wise=True,label_gain=list(range(10)))
    model.fit(train[predictors()],labels,group=groups.size().to_numpy())
    return model,train


def learn():
    x=pd.read_pickle(OUT/'historical.pkl.gz',compression='gzip');pieces=[];audit=[]
    for year in range(2020,2026):
        cutoff=f'{year}-01-01';test=x[x.decision_date.str.startswith(str(year))].copy()
        train=x[x.endpoint.lt(cutoff)]
        assert len(train) and train.endpoint.max()<cutoff
        path=OUT/f'predictions_{year}.pkl.gz'
        if path.exists():pieces.append(pd.read_pickle(path,compression='gzip'));continue
        for c in CONFIGS:
            model,used=fit(train,c)
            pred=pd.Series(model.predict(test[predictors()]),index=test.index)
            test[c['name']]=pred.groupby([test.decision_date,test.sector]).rank(pct=True).where(test.evidence_fraction.gt(0),.5)
            model.booster_.save_model(str(OUT/f'{c["name"]}_{year}.txt'))
            audit.append({'year':year,'model':c['name'],'train_rows':len(used),'max_training_endpoint':used.endpoint.max(),'test_start':test.decision_date.min()})
            print('TRAINED',year,c['name'],flush=True)
            write('training_audit.json',audit)
        test.to_pickle(path,compression='gzip');pieces.append(test)
    pd.concat(pieces,ignore_index=True).to_pickle(OUT/'predictions.pkl.gz',compression='gzip')


def candidates(x):
    names=['high_strength','balanced_strength','risk_strength']+[c['name'] for c in CONFIGS]
    result={n:x[n] for n in names}
    # Preserve champion as an anchor when present; missing rows use price-only rules.
    base=x.sector_incumbent.groupby([x.decision_date,x.sector]).rank(pct=True).fillna(x.high_strength)
    result['coverage_extension']=base
    for n in names:
        for a in [.1,.25,.5]:result[f'{n}_blend{a}']=(1-a)*base+a*x[n]
    return result


def selection():
    path=OUT/'active_selection.json'
    return json.loads((path if path.exists() else OUT/'selection.json').read_text())


def selected_score(x,name):
    base=x.sector_incumbent.groupby([x.decision_date,x.sector]).rank(pct=True).fillna(x.high_strength)
    if name.startswith('dual_'):
        b,r,c=[float(v[1:]) for v in name.split('_')[1:]]
        rel=x.volume_active_fraction.clip(0,1).fillna(.5)*x.observations_1y.div(120).clip(0,1).fillna(.5)
        return (1-b-r)*base+b*x.rank_xendcg_balanced_15+r*x.rank_xendcg_return_15-c*(1-rel)
    if name=='coverage_extension':return base
    if '_blend' in name:
        source,weight=name.split('_blend')
        if '_continuity' in weight:
            alpha,c=map(float,weight.split('_continuity'))
            rel=x.volume_active_fraction.clip(0,1).fillna(.5)*x.observations_1y.div(120).clip(0,1).fillna(.5)
            return (1-alpha)*base+alpha*x[source]-c*(1-rel)
        if '_risk' in weight:
            alpha,risk=map(float,weight.split('_risk'))
            return (1-alpha-risk)*base+alpha*x[source]+risk*x.risk_block.fillna(.5)
        a=float(weight)
        return (1-a)*base+a*x[source]
    return x[name]


def activity(x,current=False):
    path=PKG/'peak_features_reviewed.csv.gz' if current else ROOT/'experiments/v17-peak-activity-20261004/dated_features.csv.gz'
    cols=['volume_active_fraction','observations_1y']
    d=pd.read_csv(path,usecols=['isin','decision_date']+cols)
    return x.drop(columns=[c for c in cols if c in x]).merge(d,on=['isin','decision_date'],how='left',validate='many_to_one')


def needed_models(name):
    if name.startswith('dual_'):return ['rank_xendcg_balanced_15','rank_xendcg_return_15']
    source=name.split('_blend')[0]
    return [source] if source in [c['name'] for c in CONFIGS] else []


def evaluate(x,columns,top_ns=(3,)):
    x=x.sort_values('isin');rows=[]
    for (day,sector),g in x.groupby(['decision_date','sector'],sort=False):
        if sector=='Unclassified':continue
        g=g.dropna(subset=['future_xirr','future_drawdown','future_shortfall'])
        common=g[g.sector_incumbent.notna()]
        if len(common)<5:continue
        for scope,cohort in [('common',common),('expanded',g)]:
            y=cohort.future_xirr.to_numpy();risk=cohort.future_drawdown.to_numpy();short=cohort.future_shortfall.to_numpy()
            rel=cohort.future_xirr.rank(pct=True).to_numpy()
            for n in top_ns:
                discount=1/np.log2(np.arange(n)+2);ideal=np.dot(np.sort(rel)[-n:][::-1],discount)
                for name in ['sector_incumbent']+columns:
                    valid=cohort[name].notna().to_numpy()
                    order=np.flatnonzero(valid)[np.argsort(-cohort[name].to_numpy()[valid],kind='stable')][:n]
                    assert len(order)==n
                    rows.append({'period':cohort.period.iloc[0],'date':day,'sector':sector,'scope':scope,'top_n':n,'model':name,
                        'xirr':float(np.median(y[order])),'drawdown':float(risk[order].mean()),
                        'achievement':float((short[order]==0).mean()),'shortfall':float(short[order].mean()),
                        'ndcg':float(np.dot(rel[order],discount)/ideal),'cohort_size':len(cohort)})
    return pd.DataFrame(rows)


def aggregate(q):return q.groupby(['model','period','scope','top_n','sector'])[METRICS].mean().groupby(['model','period','scope','top_n']).mean()
def utility(d):return d.xirr+.5*d.drawdown+.5*d.achievement-d.shortfall+.2*d.ndcg


def search():
    x=pd.concat([pd.read_pickle(OUT/f'predictions_{year}.pkl.gz',compression='gzip') for year in range(2020,2024)],ignore_index=True)
    x=x[x.period.eq('development')].copy()
    scores=candidates(x);trials=[]
    for start in range(0,len(scores),6):
        names=list(scores)[start:start+6]
        for n in names:x[n]=scores[n]
        q=evaluate(x,names);a=aggregate(q).droplevel(['period','top_n']);ref=a.loc['sector_incumbent']
        for n in names:
            delta=a.loc[n]-ref
            gate=bool((delta.xirr>=-1e-12).all() and (delta.drawdown>=-.01).all() and (delta.shortfall<=.005).all()
                      and (delta.achievement>=-.01).all() and (delta.ndcg>=-.01).all() and (utility(delta)>=0).all())
            trials.append({'name':n,'gate':gate,'utility':float(utility(delta).mean()),
                **{f'{scope}_{metric}_delta':float(delta.loc[scope,metric]) for scope in delta.index for metric in METRICS}})
        pd.DataFrame(trials).to_csv(OUT/'trials.csv',index=False)
        print('EVALUATED',len(trials),len(scores),'passing',sum(t['gate'] for t in trials),flush=True)
    passing=sorted([t for t in trials if t['gate']],key=lambda t:(-t['utility'],t['name']))
    best=passing[0] if passing else max(trials,key=lambda t:t['utility'])
    write('selection.json',{'selected':best,'passing_count':len(passing),'promotion_eligible_on_development':bool(passing),
        'trial_count':len(trials),'protocol_sha256':hashlib.sha256((OUT/'protocol.json').read_bytes()).hexdigest()})


def final():
    chosen=selection();name=chosen['selected']['name']
    x=activity(pd.read_pickle(OUT/'predictions.pkl.gz',compression='gzip'));x['challenger']=selected_score(x,name)
    q=evaluate(x,['challenger'],top_ns=(1,3,5));q.to_csv(OUT/'historical_query_metrics.csv.gz',index=False)
    a=aggregate(q);a.to_csv(OUT/'historical_summary.csv');print(a.to_string(),flush=True)
    current=pd.read_csv(PKG/'peak_current.csv.gz',low_memory=False);current=current[current.profile_name.eq('base7500')].copy()
    facts=pd.read_csv(PKG/'facts.csv.gz',low_memory=False)
    current=current.merge(facts[['isin','product_sector']].rename(columns={'product_sector':'sector'}),on='isin',validate='one_to_one')
    dated=pd.read_csv(PKG/'peak_features_reviewed.csv.gz',usecols=['isin','decision_date','high52_freshness','momentum_12_1','high_support'])
    current=current.drop(columns=[c for c in ['high52_freshness','momentum_12_1','high_support'] if c in current])
    current=current.merge(dated,on=['isin','decision_date'],how='left',validate='one_to_one')
    old=pd.read_csv(ROOT/'experiments/sector-championship-20261005/corrected_current_rankings.csv.gz');old=old[old.profile_name.eq('base7500')]
    current=current.merge(old[['isin','personalized_score','activity_filter_reason']].rename(columns={'personalized_score':'sector_incumbent','activity_filter_reason':'purchase_eligibility_reason'}),on='isin',validate='one_to_one')
    for r in json.loads((PKG/'sector_review.json').read_text())['entries']:current.loc[current['isin'].eq(r['isin']),'sector']=r['sector']
    current=activity(features(current),current=True)
    training=[]
    for needed in needed_models(name):
        c=next(c for c in CONFIGS if c['name']==needed)
        hist=pd.read_pickle(OUT/'historical.pkl.gz',compression='gzip');train=hist[hist.endpoint.lt('2026-10-03')]
        model,used=fit(train,c);model.booster_.save_model(str(OUT/f'selected_{needed}.txt'))
        pred=pd.Series(model.predict(current[predictors()]),index=current.index)
        current[needed]=pred.groupby([current.decision_date,current.sector]).rank(pct=True).where(current.evidence_fraction.gt(0),.5)
        training.append({'rows':len(used),'max_endpoint':used.endpoint.max(),'features':predictors(),'config':c})
    write('current_training.json',{'models':training,'as_of':'2026-10-03'})
    value=selected_score(current,name)
    current['challenger_score']=value.where(current.evidence_fraction.gt(0),.5)
    # Fully absent price evidence is an explicit tied prior.
    current['evidence_confidence']=np.select([current.evidence_fraction.eq(0),current.evidence_fraction.lt(.5),current.evidence_fraction.lt(.85)],['NO_PRICE_EVIDENCE','LOW','PARTIAL'],default='HIGH')
    current['challenger_sector_rank']=current.challenger_score.groupby(current.sector).rank(ascending=False,method='min')
    current['rank_scope']=np.where(current.sector.eq('Unclassified'),'UNCLASSIFIED_POOL_NOT_A_SECTOR','WITHIN_SECTOR')
    current['champion_available']=current.sector_incumbent.notna()
    assert len(current)==4436 and current['isin'].nunique()==4436 and np.isfinite(current.challenger_score).all()
    columns=['isin','ticker','company','decision_date','sector','challenger_sector_rank','challenger_score','evidence_fraction','evidence_confidence','rank_scope','champion_available','sector_incumbent','purchase_eligibility_reason','volume_active_fraction','observations_1y']+RAW
    current.sort_values(['sector','challenger_sector_rank','isin'])[columns].to_csv(OUT/'current_all_stock_rankings.csv',index=False)
    write('coverage.json',{'stocks':len(current),'finite_scores':int(current.challenger_score.notna().sum()),'champion_scores':int(current.champion_available.sum()),
        'confidence':current.evidence_confidence.value_counts().to_dict(),'sector_groups':current.sector.nunique(),'selected':name,
        'model_status':'RESEARCH_CHALLENGER_NOT_DEPLOYED','snapshot':'2026-10-03'})


def profiles():
    """Locked chosen model across nine profiles; no refitting to these diagnostics."""
    name=selection()['selected']['name']
    raw=pd.read_pickle(ROOT/'experiments/sector-championship-20261005/enhanced.pkl.gz',compression='gzip')
    summaries=[];predictions=[]
    for profile,g in raw.groupby('profile_name'):
        g=g[g.decision_date.ge('2020-01-01')].copy();g=activity(features(g))
        for needed in needed_models(name):
            g[needed]=np.nan
            for year in range(2020,2026):
                mask=g.decision_date.str.startswith(str(year));test=g.loc[mask]
                model=lgb.Booster(model_file=str(OUT/f'{needed}_{year}.txt'))
                pred=pd.Series(model.predict(test[predictors()],num_threads=3),index=test.index)
                g.loc[mask,needed]=pred.groupby([test.decision_date,test.sector]).rank(pct=True).where(test.evidence_fraction.gt(0),.5)
        g['challenger']=selected_score(g,name)
        q=evaluate(g,['challenger'],top_ns=(1,3,5));q['profile']=profile
        q.to_csv(OUT/f'profile_{profile}_query_metrics.csv.gz',index=False)
        a=aggregate(q).reset_index();a['profile']=profile;summaries.append(a)
        predictions.append(g[KEYS+['sector','period','sector_incumbent','challenger','future_xirr','future_drawdown','future_shortfall']])
        print('PROFILE VERIFIED',profile,flush=True)
    pd.concat(summaries).to_csv(OUT/'all_profile_summary.csv',index=False)
    pd.concat(predictions).to_csv(OUT/'locked_all_profile_predictions.csv.gz',index=False)


if __name__=='__main__':globals()[sys.argv[1]]()
