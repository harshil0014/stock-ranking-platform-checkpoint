"""Sector-only professor/model benchmark and auditable successor experiments."""
from pathlib import Path
import sys,json,hashlib,itertools,gc
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'research/runners')]
from stock_ranker.sector_scoring import score
from stock_ranker.closing_high_review import review_stock
OUT=ROOT/'experiments/sector-championship-20261005'
PREV=ROOT/'experiments/sector-tuning-20261005'
KEYS=['isin','decision_date','profile_name']
METRICS=['xirr','drawdown','achievement','shortfall','ndcg','rank_ic']

def write(name,obj):
    OUT.mkdir(exist_ok=True)
    (OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False),encoding='utf-8')

def load():
    x=pd.read_pickle(PREV/'prepared.pkl.gz',compression='gzip')
    choice=json.loads((PREV/'selection_lock.json').read_text())['winner']
    x['sector_incumbent']=score(x,choice)
    return x

def workbook():
    from zipfile import ZipFile
    from xml.etree import ElementTree as ET
    from stock_ranker.professor_reference import _XlsxCells,NS
    source=Path(r'C:\Users\Harshil\Downloads\_Organized\Documents\Copy of OK Strategy - Master Sheet v4.3 (1).xlsx')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    prior=ROOT/'research/reports/top100-human-review-20261004'
    original=json.loads((prior/'professor_summary.json').read_text())
    assert digest==original['source_sha256'],'Workbook changed: re-audit required'
    with ZipFile(source) as z:
        shared=_XlsxCells._shared_strings(z);paths=_XlsxCells._sheet_paths(z);cells={}
        with z.open(paths['SIP Portfolio']) as stream:
            for _,node in ET.iterparse(stream,events=['end']):
                if node.tag!='{'+NS['m']+'}row':continue
                if int(node.attrib['r'])>22:break
                for c in node.findall('m:c',NS):
                    v,f=c.find('m:v',NS),c.find('m:f',NS);v=v.text if v is not None else None
                    if c.attrib.get('t')=='s' and v is not None:v=shared[int(v)]
                    cells[c.attrib['r']]={'value':v,'formula':f.text if f is not None else None}
                node.clear()
    current=pd.read_csv(PREV/'current_sector_rankings.csv.gz');current=current[current.profile_name.eq('base7500')]
    old=pd.read_csv(prior/'professor_stock_comparison.csv')
    fields=['isin','ticker','code','screenshot_rank','screenshot_cmp','workbook_cached_rank']
    compared=old[fields].merge(current.drop(columns=['ticker','profile_name']),on='isin',validate='one_to_one')
    runtime=pd.read_csv(ROOT/'research/runtime/personalized-v17/peak_current.csv.gz',usecols=['isin','profile_name','professor_whole_share_score'])
    runtime=runtime[runtime.profile_name.eq('base7500')].drop(columns='profile_name')
    peers=current.merge(runtime,on='isin',validate='one_to_one')
    peers['professor_sector_rank_common']=peers.professor_whole_share_score.where(peers.personalized_available).groupby(peers.sector).rank(ascending=False,method='min')
    compared=compared.merge(peers[['isin','professor_whole_share_score','professor_sector_rank_common']],on='isin',validate='one_to_one')
    compared.to_csv(OUT/'professor_workbook_sector_comparison.csv',index=False)
    pairrows=[]
    for sector,g in compared.groupby('sector'):
        for i,j in itertools.combinations(g.index,2):
            a,b=g.loc[i],g.loc[j]
            usable=pd.notna(a.screenshot_cmp) and pd.notna(b.screenshot_cmp)
            pairrows.append({'sector':sector,'a':a.ticker,'b':b.ticker,'screenshot_usable':usable,
                'current_order_agrees_with_screenshot':bool((a.personalized_sector_rank-b.personalized_sector_rank)*(a.screenshot_rank-b.screenshot_rank)>0) if usable else None})
    pd.DataFrame(pairrows).to_csv(OUT/'professor_screenshot_within_sector_pairs.csv',index=False)
    write('workbook_audit.json',{'sha256':digest,'source_unchanged':digest==hashlib.sha256(source.read_bytes()).hexdigest(),
        'matched_workbook_names':len(compared),'ranked':int(compared.personalized_available.sum()),
        'cached_ranks':[cells[f'N{r}']['value'] for r in range(7,21)],
        'same_sector_screenshot_pairs':len(pairrows),'usable_pairs':sum(r['screenshot_usable'] for r in pairrows),
        'interpretation':'Screenshot agreement is descriptive, not accuracy. Different snapshot; duplicate CEMPRO and missing quotes excluded. Current professor formula is evaluated separately on historical outcomes.',
        'cells':cells})
    print(compared[['ticker','sector','personalized_sector_rank','professor_sector_rank_common']].to_string(index=False),flush=True)

def human():
    """Evidence checklist, never a fabricated ground-truth return label."""
    current=pd.read_csv(PREV/'current_sector_rankings.csv.gz');current=current[current.profile_name.eq('base7500')]
    facts=pd.read_csv(ROOT/'research/runtime/personalized-v17/facts.csv.gz',low_memory=False)
    ev=pd.read_csv(ROOT/'research/runtime/personalized-v17/peak_current.csv.gz',low_memory=False);ev=ev[ev.profile_name.eq('base7500')]
    dated=pd.read_csv(ROOT/'research/runtime/personalized-v17/peak_features_reviewed.csv.gz')
    receipts=pd.read_csv(ROOT/'research/runtime/personalized-v17/peak_review.csv').set_index('ticker')
    sir=set(pd.read_csv(OUT/'professor_workbook_sector_comparison.csv')['isin'])
    chosen=current[current.personalized_sector_rank.le(3)|current['isin'].isin(sir)]
    rows=[]
    for r in chosen.itertuples():
        f=facts[facts['isin'].eq(r.isin)].iloc[0];e=ev[ev['isin'].eq(r.isin)].iloc[0]
        d=dated[dated['isin'].eq(r.isin)].iloc[0]
        review=review_stock(f,e,receipts.loc[r.ticker] if r.ticker in receipts.index else None)
        flags=review['review_flags'].copy()
        if r.personalized_sector_peer_count<5:flags.append('Small peer group: sector tuning falls back to prior score')
        if e.days_since_recorded_high>1095 and e.distance_from_recorded_high>=-.05:flags.append('Old high but within 5%: age alone must not demote')
        if e.downside_volatility_1y<.08 and d.volume_active_fraction<.95:flags.append('Low volatility with intermittent activity: potential stale-price effect')
        rows.append({'isin':r.isin,'ticker':r.ticker,'sector':r.sector,'sector_rank':r.personalized_sector_rank,
            'peer_count':r.personalized_sector_peer_count,'professor_name':r.isin in sir,
            'history_months':e.history_months,'ath_age':e.days_since_recorded_high,'high_distance':e.distance_from_recorded_high,
            'downside_volatility':e.downside_volatility_1y,'high_support':d.high_support,
            'reported_daily_value':float(np.expm1(d.traded_value)),'review_flags':' | '.join(flags),
            'review_source':review.get('review_source_url'),'financial_observed_at':f.get('screener_source_observed_at'),
            'assessment':'Evidence needs review' if flags else 'No trigger in this limited evidence checklist',
            'benchmark_type':'Dated factual checks; not investment-return ground truth'})
    out=pd.DataFrame(rows);out.to_csv(OUT/'human_reasoning_benchmark.csv',index=False)
    write('human_review_summary.json',{'stocks':len(out),'flagged':int(out.review_flags.ne('').sum()),
        'unique_sectors':out.sector.nunique(),'rubric':'Execution, price continuity, business continuity, available history, financial concerns, old-high recovery, peer count',
        'limitations':'Rule-based evidence review informed by prior due diligence. Not independent alpha labels or a guarantee that unflagged stocks are good investments.'})
    print('HUMAN REVIEW',len(out),flush=True)

def metrics(frame,columns,top_ns=(3,)):
    """Paired finite rows; all columns must share the given query population."""
    from scipy.stats import rankdata
    frame=frame.sort_values('isin').reset_index(drop=True)
    predictions=frame[columns].to_numpy()
    outcomes=frame[['future_xirr','future_drawdown','future_shortfall']].to_numpy()
    finite=np.isfinite(predictions).all(axis=1)&np.isfinite(outcomes).all(axis=1)
    records=[]
    for (period,day,profile,sector),idx in frame.groupby(['period','decision_date','profile_name','sector'],sort=False).indices.items():
        if sector=='Unclassified':continue
        idx=idx[finite[idx]]
        if len(idx)<5:continue
        values=predictions[idx];order=np.argsort(-values,axis=0,kind='stable')
        y,risk,short=outcomes[idx].T
        yr=rankdata(y)/len(y);ranks=rankdata(values,axis=0)
        center=ranks-ranks.mean(axis=0);yc=yr-yr.mean()
        denom=np.sqrt(np.square(center).sum(axis=0)*np.square(yc).sum())
        ic=np.divide((center*yc[:,None]).sum(axis=0),denom,out=np.zeros(len(columns)),where=denom>0)
        for n in top_ns:
            top=order[:n];discount=np.log2(np.arange(2,n+2))[:,None]
            ndcg=(yr[top]/discount).sum(axis=0)/(np.sort(yr)[-n:][::-1]/discount[:,0]).sum()
            arr=np.column_stack([np.median(y[top],axis=0),risk[top].mean(axis=0),(short[top]==0).mean(axis=0),short[top].mean(axis=0),ndcg,ic])
            for i,col in enumerate(columns):records.append({'period':period,'date':day,'profile':profile,'sector':sector,'n':len(idx),'top_n':n,'model':col,**dict(zip(METRICS,arr[i]))})
    return pd.DataFrame(records)

def aggregate(q):
    return q.groupby(['model','period','top_n','sector','profile'])[METRICS].mean().groupby(['model','period','top_n']).mean()

def benchmark():
    x=load().dropna(subset=['sector_incumbent']).copy()
    specs=json.loads((ROOT/'research/reports/all-models-audit-20261004/comparison_sources.json').read_text())
    # The preceding reviewed model is also a distinct comparator.
    results=[];sources=[];panel=None
    if (OUT/'benchmark_sources.json').exists():
        sources=json.loads((OUT/'benchmark_sources.json').read_text())
        results=[pd.read_csv(OUT/'all_previous_sector_summary.csv')]
    for idx,entry in enumerate(specs):
        if any(s['opponent']==entry['opponent'] for s in sources):continue
        col=entry['score_column'];paths=[ROOT/p for p in entry['artifacts']]
        if len(paths)==1 and paths[0].name=='deep_panel.csv.gz':
            if panel is None:
                cols=pd.read_csv(paths[0],nrows=0).columns
                panel=pd.read_csv(paths[0],usecols=KEYS+[c for c in cols if c.endswith('_score')])
            other=panel[KEYS+[col]]
        else:other=pd.concat([pd.read_csv(p,usecols=KEYS+[col]) for p in paths],ignore_index=True)
        paired=x.merge(other.rename(columns={col:'opponent_score'}),on=KEYS,validate='one_to_one')
        q=metrics(paired,['sector_incumbent','opponent_score'])
        a=aggregate(q).reset_index();a['opponent']=entry['opponent'];results.append(a)
        # Native query detail remains auditable rather than hiding bad sectors.
        q.to_csv(OUT/f'benchmark_{idx:02d}.csv.gz',index=False)
        sources.append({'file':f'benchmark_{idx:02d}.csv.gz',**entry})
        pd.concat(results).to_csv(OUT/'all_previous_sector_summary.csv',index=False)
        write('benchmark_sources.json',sources)
        print('BENCHMARK',idx+1,len(specs),entry['opponent'],flush=True)

def enrich():
    x=load()
    raw=pd.read_pickle(ROOT/'experiments/personalized-deep-championship-20261002/v3/prepared.pkl.gz',compression='gzip')
    cols=['distance_from_52w_high','full_history_max_drawdown','current_drawdown_duration_days','history_months','cagr_3y','observed_cagr_5y']
    x=x.merge(raw[KEYS+cols],on=KEYS,validate='one_to_one');del raw
    dated=pd.read_csv(ROOT/'experiments/v17-peak-activity-20261004/dated_features.csv.gz',usecols=['isin','decision_date','high_support','nonzero_fraction'])
    x=x.merge(dated,on=['isin','decision_date'],validate='many_to_one')
    growth=pd.read_csv(ROOT/'experiments/personalized-v14-ml-20261003/historical_growth.csv.gz',usecols=['isin','decision_date','strict_cagr_1y','momentum_6m','downside_frequency_1y'])
    x=x.merge(growth,on=['isin','decision_date'],validate='many_to_one')
    panel=pd.read_csv(ROOT/'experiments/personalized-deep-history-20261002/real-panel-v12/deep_panel.csv.gz',usecols=KEYS+['professor_whole_share_score'])
    x=x.merge(panel,on=KEYS,validate='one_to_one')
    groups=[x[c] for c in ['decision_date','profile_name','sector']]
    def q(v):return v.where(x.sector_incumbent.notna()).groupby(groups).rank(pct=True).fillna(.5)
    x['support']=q(x.high_support)
    x['annual_high']=q(x.distance_from_52w_high)
    x['risk_adjusted_momentum']=q(np.log1p(x.momentum_12_1.clip(lower=-.99))/x.downside_volatility_1y.clip(lower=.1))
    x['professor']=q(x.professor_whole_share_score)
    x['momentum6']=q(x.momentum_6m)
    x['tail_risk']=q(x.full_history_max_drawdown)
    x['trend_confirmation']=(x.support+x.momentum6)/2
    x['balanced_strength']=(x.annual_high+x.support+x.momentum6+x.sector_goal)/4
    # Strict observed four-factor Baseline formula on the eligible peer cohort.
    complete=x[['strict_cagr_1y','cagr_3y','observed_cagr_5y','days_since_recorded_high']].notna().all(axis=1)&x.sector_incumbent.notna()&x.history_months.ge(60)
    ranks=[x[c].where(complete).groupby(groups).rank(method='min',ascending=(c=='days_since_recorded_high'))
           for c in ['strict_cagr_1y','cagr_3y','observed_cagr_5y','days_since_recorded_high']]
    x['baseline_formula_replay']=-sum(ranks)/4
    x.to_pickle(OUT/'enhanced.pkl.gz',compression='gzip')
    print('ENRICHED',len(x),flush=True)

def baseline():
    x=pd.read_pickle(OUT/'enhanced.pkl.gz',compression='gzip')
    q=metrics(x,['sector_incumbent','baseline_formula_replay'],top_ns=(1,3,5))
    q.to_csv(OUT/'baseline_formula_sector_metrics.csv.gz',index=False)
    aggregate(q).to_csv(OUT/'baseline_formula_summary.csv')
    print('BASELINE REPLAY',len(q),flush=True)

def candidate_score(x,c):
    if c['family']=='local':
        h,d=c['high'],c['downside']
        value=(1-h-d-.05)*x.sector_base+h*(x.closing_high_component+x.sector_high)/2+d*x.sector_downside+.05*x.sector_momentum
    else:value=(1-c['weight'])*x.sector_incumbent+c['weight']*x[c['family']]
    fallback=x.sector_peer_count.lt(5)|x.sector.eq('Unclassified')
    return value.where(~fallback,x.sector_incumbent).where(x.sector_incumbent.notna())

def utility(delta):
    return delta.xirr+.5*delta.drawdown+.5*delta.achievement-delta.shortfall+.2*delta.ndcg+.1*delta.rank_ic

def search2():
    choices=[]
    for family,w in itertools.product(['support','annual_high','risk_adjusted_momentum','professor','momentum6','tail_risk','trend_confirmation','balanced_strength'],[.025,.05,.1,.15,.2,.3]):
        choices.append({'name':f'{family}_{w}','family':family,'weight':w})
    for h,d in itertools.product([.4,.45,.5,.55],[.1,.15,.2]):
        choices.append({'name':f'local_h{h}_d{d}','family':'local','high':h,'downside':d})
    write('round2_protocol.json',{'candidates':choices,'selection':'2020-2023 only; lock before evaluating early/recent',
        'gate':'Top1/3/5: all six aggregate metrics nonworse; each profile Top3 return loss <=1pp and shortfall increase <=0.5pp; sector utility positive in >=55% of sectors',
        'objective':'Mean utility across Top1/3/5; within-sector only',
        'interpretation':'Historical price/professor proxies, not financial quality or true regression residual momentum. All dates previously exposed.'})
    x=pd.read_pickle(OUT/'enhanced.pkl.gz',compression='gzip');x=x[x.period.eq('development')].copy()
    trials=[]
    for start in range(0,len(choices),6):
        batch=choices[start:start+6]
        for c in batch:x[c['name']]=candidate_score(x,c)
        q=metrics(x,['sector_incumbent']+[c['name'] for c in batch],top_ns=(1,3,5))
        a=aggregate(q).droplevel('period');ref=a.loc['sector_incumbent']
        prof=q[q.top_n.eq(3)].groupby(['model','sector','profile'])[METRICS].mean().groupby(['model','profile']).mean()
        sectors=q[q.top_n.eq(3)].groupby(['model','sector','profile'])[METRICS].mean().groupby(['model','sector']).mean()
        for c in batch:
            delta=a.loc[c['name']]-ref;pdiff=prof.loc[c['name']]-prof.loc['sector_incumbent'];sdiff=sectors.loc[c['name']]-sectors.loc['sector_incumbent']
            win=float((utility(sdiff)>=-1e-12).mean())
            gate=bool((delta[['xirr','drawdown','achievement','ndcg','rank_ic']]>=-1e-12).all().all() and delta.shortfall.le(1e-12).all()
                and pdiff.xirr.min()>=-.01 and pdiff.shortfall.max()<=.005 and win>=.55)
            trials.append({**c,'gate':gate,'utility':float(utility(delta).mean()),'sector_win_fraction':win,
                **{f'top{n}_{m}_delta':float(delta.loc[n,m]) for n in [1,3,5] for m in METRICS}})
        pd.DataFrame(trials).to_csv(OUT/'round2_trials.csv',index=False)
        print('ROUND2',len(trials),'passing',sum(t['gate'] for t in trials),flush=True)
        x=x.drop(columns=[c['name'] for c in batch])
    passing=sorted([c for c in trials if c['gate'] and c['utility']>1e-12],key=lambda c:(-c['utility'],c['name']))
    write('round2_selection.json',{'winner':passing[0] if passing else None,'trials':len(trials),
          'protocol_sha256':hashlib.sha256((OUT/'round2_protocol.json').read_bytes()).hexdigest()})
    print('ROUND2 LOCKED',passing[:1],flush=True)

def final2():
    c=json.loads((OUT/'round2_selection.json').read_text())['winner']
    if c is None:print('No strict all-shortlist dominance candidate');return
    x=pd.read_pickle(OUT/'enhanced.pkl.gz',compression='gzip');x['successor']=candidate_score(x,c)
    q=metrics(x,['sector_incumbent','successor'],top_ns=(1,3,5))
    q.to_csv(OUT/'round2_final_metrics.csv.gz',index=False);aggregate(q).to_csv(OUT/'round2_final_summary.csv')
    print(aggregate(q).to_string(),flush=True)

def learn():
    """Walk-forward sector-normalized residual challenger; mature outcomes only."""
    import lightgbm as lgb
    x=pd.read_pickle(OUT/'enhanced.pkl.gz',compression='gzip')
    raw=pd.read_pickle(ROOT/'experiments/personalized-deep-championship-20261002/v3/prepared.pkl.gz',compression='gzip')
    x=x.merge(raw[KEYS+['endpoint']],on=KEYS,validate='one_to_one');del raw
    x=x[x.sector_incumbent.notna()&x.sector_peer_count.ge(5)&x.sector.ne('Unclassified')].copy()
    features=['sector_base','sector_high','closing_high_component','sector_downside','sector_momentum','sector_goal',
              'support','annual_high','risk_adjusted_momentum','professor','momentum6','tail_risk']
    configs=[{'name':f'{target}_leaves{leaves}','target':target,'leaves':leaves} for target,leaves in itertools.product(['return','balanced'],[7,15])]
    write('round3_protocol.json',{'families':configs,'alphas':[.05,.1,.2,.3],'features':features,
        'training':'For each 2020-2023 year, outcomes must mature strictly before the first decision of that year. No current company financials.',
        'selection':'Same Top1/3/5 strict nonworseness gate as round2, positive utility required; no feature/parameter changes after testing',
        'params':{'trees':120,'learning_rate':.035,'min_child_samples':150,'reg_lambda':40,'seed':20261005},
        'exposure':'All dates previously researched; not independent validation'})
    prediction=[];audits=[]
    for year in [2020,2021,2022,2023]:
        test=x[x.period.eq('development')&x.decision_date.str.startswith(str(year))].copy()
        cutoff=test.decision_date.min()
        train=x[x.endpoint.lt(cutoff)].dropna(subset=['future_xirr','future_drawdown','future_shortfall']).copy()
        assert train.endpoint.max()<cutoff
        groups=train.groupby(['decision_date','profile_name','sector'])
        weights=1/groups['isin'].transform('size');weights/=weights.mean()
        yr=groups.future_xirr.rank(pct=True);dr=groups.future_drawdown.rank(pct=True);sr=groups.future_shortfall.rank(pct=True,ascending=False)
        for c in configs:
            target=.7*yr+.15*dr+.15*sr if c['target']=='return' else .4*yr+.3*dr+.3*sr
            model=lgb.LGBMRegressor(n_estimators=120,learning_rate=.035,num_leaves=c['leaves'],max_depth=4,
                min_child_samples=150,reg_lambda=40,n_jobs=3,verbosity=-1,random_state=20261005,deterministic=True,force_col_wise=True)
            model.fit(train[features],target,sample_weight=weights)
            test[c['name']]=model.predict(test[features])
            test[c['name']]=test.groupby(['decision_date','profile_name','sector'])[c['name']].rank(pct=True)
            model.booster_.save_model(str(OUT/f'round3_{c["name"]}_{year}.txt'))
            audits.append({'year':year,'model':c['name'],'train_n':len(train),'max_endpoint':train.endpoint.max(),'test_start':cutoff})
        prediction.append(test)
        write('round3_training_audit.json',audits)
        print('LEARNED',year,flush=True)
    z=pd.concat(prediction,ignore_index=True);trials=[]
    for c in configs:
        columns=['sector_incumbent']
        for alpha in [.05,.1,.2,.3]:
            name=f'{c["name"]}_a{alpha}';z[name]=(1-alpha)*z.sector_incumbent+alpha*z[c['name']];columns.append(name)
        q=metrics(z,columns,top_ns=(1,3,5));a=aggregate(q).droplevel('period');ref=a.loc['sector_incumbent']
        for alpha,name in zip([.05,.1,.2,.3],columns[1:]):
            delta=a.loc[name]-ref
            gate=bool((delta[['xirr','drawdown','achievement','ndcg','rank_ic']]>=-1e-12).all().all() and delta.shortfall.le(1e-12).all() and utility(delta).mean()>1e-12)
            trials.append({**c,'name':name,'alpha':alpha,'gate':gate,'utility':float(utility(delta).mean()),
                **{f'top{n}_{m}_delta':float(delta.loc[n,m]) for n in [1,3,5] for m in METRICS}})
        pd.DataFrame(trials).to_csv(OUT/'round3_trials.csv',index=False)
        print('LEARNED EVALUATED',c['name'],flush=True)
    z[KEYS+['sector_incumbent']+[c['name'] for c in configs]].to_csv(OUT/'round3_development_predictions.csv.gz',index=False)
    passing=sorted([c for c in trials if c['gate']],key=lambda c:(-c['utility'],c['name']))
    write('round3_selection.json',{'winner':passing[0] if passing else None,'trials':len(trials)})
    print('ROUND3 LOCKED',passing[:1],flush=True)

def interactions():
    """A final targeted round: offset the return challengers' downside regression."""
    choices=[{'name':f'{f}_w{w}_risk{r}','family':f,'weight':w,'risk_weight':r}
             for f,w,r in itertools.product(['momentum6','annual_high','risk_adjusted_momentum'],[.05,.1,.15,.2],[.025,.05,.1,.15])]
    write('round4_protocol.json',{'candidates':choices,'reason':'Round2 momentum/annual-high proxies can raise returns while worsening drawdown or shortfall; test explicit within-sector risk offsets.',
        'formula':'(1-weight-risk_weight)*incumbent + weight*signal + risk_weight*sector_downside',
        'gate':'Strict aggregate nonworseness for six metrics at Top1/3/5; positive utility; Top3 profile and sector safeguards from round2',
        'selection':'2020-2023 only; early/recent evaluation after lock; all historical outcomes previously exposed',
        'stopping_rule':'No promotion without gate; stop this sequence after these prespecified interactions, retain frontier and require new dated evidence rather than infinite tuning on exposed data.'})
    x=pd.read_pickle(OUT/'enhanced.pkl.gz',compression='gzip');x=x[x.period.eq('development')].copy();trials=[]
    for start in range(0,len(choices),6):
        batch=choices[start:start+6]
        for c in batch:
            x[c['name']]=(1-c['weight']-c['risk_weight'])*x.sector_incumbent+c['weight']*x[c['family']]+c['risk_weight']*x.sector_downside
        q=metrics(x,['sector_incumbent']+[c['name'] for c in batch],top_ns=(1,3,5));a=aggregate(q).droplevel('period');ref=a.loc['sector_incumbent']
        prof=q[q.top_n.eq(3)].groupby(['model','sector','profile'])[METRICS].mean().groupby(['model','profile']).mean()
        sectors=q[q.top_n.eq(3)].groupby(['model','sector','profile'])[METRICS].mean().groupby(['model','sector']).mean()
        for c in batch:
            delta=a.loc[c['name']]-ref;pdiff=prof.loc[c['name']]-prof.loc['sector_incumbent'];sdiff=sectors.loc[c['name']]-sectors.loc['sector_incumbent']
            win=float((utility(sdiff)>=-1e-12).mean());u=float(utility(delta).mean())
            gate=bool((delta[['xirr','drawdown','achievement','ndcg','rank_ic']]>=-1e-12).all().all() and delta.shortfall.le(1e-12).all()
                and u>1e-12 and pdiff.xirr.min()>=-.01 and pdiff.shortfall.max()<=.005 and win>=.55)
            trials.append({**c,'gate':gate,'utility':u,'sector_win_fraction':win,
                **{f'top{n}_{m}_delta':float(delta.loc[n,m]) for n in [1,3,5] for m in METRICS}})
        pd.DataFrame(trials).to_csv(OUT/'round4_trials.csv',index=False)
        x=x.drop(columns=[c['name'] for c in batch]);print('ROUND4',len(trials),'passing',sum(c['gate'] for c in trials),flush=True)
    passing=sorted([c for c in trials if c['gate']],key=lambda c:(-c['utility'],c['name']))
    write('round4_selection.json',{'winner':passing[0] if passing else None,'trials':len(trials)})
    print('ROUND4 LOCKED',passing[:1],flush=True)

def frontier():
    parts=[]
    for rnd in [2,3,4]:
        f=pd.read_csv(OUT/f'round{rnd}_trials.csv');f['round']=rnd;parts.append(f)
    f=pd.concat(parts,ignore_index=True)
    columns=[f'top{n}_{m}_delta' for n in [1,3,5] for m in METRICS]
    values=f[columns].to_numpy()
    signs=np.array([-1 if 'shortfall' in c else 1 for c in columns])
    values*=signs
    f['regressing_metrics']=(values<-1e-12).sum(axis=1)
    f['improving_metrics']=(values>1e-12).sum(axis=1)
    f['pareto_frontier']=[not any(np.all(b>=a-1e-12) and np.any(b>a+1e-12) for b in values) for a in values]
    f.to_csv(OUT/'complete_trial_ledger.csv',index=False)
    f[f.pareto_frontier].to_csv(OUT/'candidate_frontier.csv',index=False)
    write('search_summary.json',{'trials':len(f),'strict_improvements':int(((f.regressing_metrics==0)&(f.improving_metrics>0)).sum()),
        'frontier_candidates':int(f.pareto_frontier.sum()),'note':'Finite tested search; not proof of an absolute optimum. Identical control is not an improvement.'})

if __name__=='__main__':
    OUT.mkdir(exist_ok=True)
    globals()[sys.argv[1]]()
