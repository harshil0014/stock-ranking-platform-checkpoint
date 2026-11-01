"""Concentration audit and five fixed professor-framework extensions."""
import os
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[key]='1'
from pathlib import Path
import argparse,csv,datetime,gc,hashlib,json,pickle,shutil
import numpy as np
import pandas as pd
from scipy.optimize import brentq
from sklearn.linear_model import Ridge
from stock_research.sir_ladder import high_features,funded_stock
from stock_research.next_open_portfolio import next_open_portfolio
from filing_probe_20261101 import start_watchdog
from professor_frontier_20261101 import Q,scope_path
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'work/sir-extensions-20261101';OUT=ROOT/'experiments/sir-extensions-20261101'
PARENT=ROOT/'work/professor-frontier-20261101';SOURCE=ROOT/'experiments/professor-frontier-20261101'


def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,default=lambda x:x.item() if hasattr(x,'item') else str(x)),encoding='utf-8')


def irate(terminal,start,end):
    ds=np.arange(np.datetime64(start),np.datetime64(end),np.timedelta64(30,'D'));years=(np.datetime64(end)-ds).astype(float)/365.25
    return float(brentq(lambda r:7500*np.sum((1+r)**years)-terminal,-.999999,1e6))


def terminal(rate,start,end):
    ds=np.arange(np.datetime64(start),np.datetime64(end),np.timedelta64(30,'D'));years=(np.datetime64(end)-ds).astype(float)/365.25
    return float(7500*np.sum((1+rate)**years))


def winmean(values):
    v=np.sort(np.asarray(values,float));n=int(len(v)*.1)
    return float(np.clip(v,v[n],v[-n-1]).mean()) if n else float(v.mean())


def boot(values,dates):
    from champion_market_review_20261031 import block_indices
    v=np.asarray(values,float);rng=np.random.default_rng(20261101);center=v-v.mean()
    draws=np.array([center[block_indices(np.asarray(dates),365,rng)].mean() for _ in range(2000)])
    p=float((1+np.sum(draws>=v.mean()))/(len(draws)+1))
    return dict(mean=float(v.mean()),median=float(np.median(v)),winsorized_mean=winmean(v),
        lodo_min=float(min(np.delete(v,i).mean() for i in range(len(v)))),lodo_max=float(max(np.delete(v,i).mean() for i in range(len(v)))),
        low95=float(v.mean()-np.quantile(draws,.975)),high95=float(v.mean()-np.quantile(draws,.025)),nominal_p=p)


def registry():
    path=ROOT/'research/research_variant_ledger.csv';rows=[]
    def add(family,name,source,category='configuration'):
        rows.append(dict(id=family+'::'+str(name),family=family,name=str(name),source=str(source),category=category))
    file=ROOT/'experiments/v17-ath-refinement-20261004/trials.csv'
    for name in sorted({r['name'] for r in csv.DictReader(file.open())}):add('ath_refinement_20261004',name,file.relative_to(ROOT))
    file=ROOT/'experiments/champion-vs-market-20261031/portfolio_paired_comparisons.csv'
    for name in sorted({r['model'] for r in csv.DictReader(file.open())}):add('champion_market_20261031',name,file.relative_to(ROOT))
    for file in list((ROOT/'research/protocols').glob('personalized*.json'))+[ROOT/'research/protocols/professor_majority_20261031.json',ROOT/'research/protocols/professor_weight_curve_20261031.json',ROOT/'experiments/ten-hypotheses-20261031/protocol.json']:
        def visit(d,key=''):
            if not isinstance(d,dict):return
            for k,v in d.items():
                if k in ['fixed_candidates','model_variants','candidate_core_shares'] and isinstance(v,list):
                    for name in v:add(file.stem+'.'+key+k,name,file.relative_to(ROOT))
                elif k=='families' and isinstance(v,dict):
                    for name in v:add(file.stem+'.'+key+k,name,file.relative_to(ROOT))
                elif isinstance(v,dict):visit(v,key+k+'.')
        if file.exists():visit(json.loads(file.read_text()))
    for family,names in [('frontier_20261101',['linear75','balanced75','outrank75','tail75']),('delivery_20261101',['control','delivery']),('timing_20261101',['dip_rule','dip_plus_overlay'])]:
        for name in names:add(family,name,'research/reports/'+('professor_frontier_20261101.md' if family.startswith('frontier') else 'new_information_20261101.md' if family.startswith('delivery') else 'momentum_timing_20261101.md'))
    new=['tail_concentration','target10','target20','target30']+['legacy_'+p for p in ['amount1000','amount50000','base7500','lookback12','lookback60','weekly','quarterly','target10','target30']]+['dose_middle_vs_top','dose_middle_vs_low','cagr_high_gate','static_ladder_cash0','static_ladder_cash4','ath_count_baseline','ath_count_increment']
    for name in new:add('sir_extensions_20261101',name,'research/protocols/sir_extensions_20261101.md','diagnostic_or_policy_attempt')
    old=pd.read_csv(path).to_dict('records') if path.exists() else []
    known={r['id']:r for r in old}
    for row in rows:
        if row['id'] not in known:known[row['id']]=row
    pd.DataFrame(list(known.values())).sort_values('id').to_csv(path,index=False)
    save('variant_count.json',dict(documented_attempts=len(known),configuration_records=sum(r['category']=='configuration' for r in known.values()),
        new_round_records=len(new),scope='Scoped evaluated configurations and diagnostic attempts; cross-round aliases/retests retained; fits/seeds not independent strategies',
        omissions='Older uncatalogued manual searches, adaptive band interpretation and absent artifacts are not exhaustively counted. Adjustment does not certify global significance.',
        ledger_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return len(known)


def prepare():
    x=pd.read_pickle(PARENT/'corrected_panel.pkl.gz',compression='gzip');x=x[x.decision_date.lt('2024-01-01')].copy()
    root=ROOT/'experiments/current-data-recovery-20261003/yahoo-full-recovery-v1';mapping=pd.read_csv(root/'yahoo_symbol_map.csv').dropna(subset=['isin','yahoo_symbol']);lookup=dict(zip(mapping.yahoo_symbol,mapping['isin']))
    wanted=set(x['isin']);dest=WORK/'split_paths_observed.pkl';receipts=[]
    if dest.exists():
        with dest.open('rb') as f:paths=pickle.load(f)
    else:
        prior=WORK/'split_paths.pkl'
        if prior.exists():
            with prior.open('rb') as f:paths=pickle.load(f)
        else:paths={}
        for file in ([] if prior.exists() else sorted((root/'history-cache').glob('batch_*.pkl'))):
            receipts.append(dict(path=file.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
            with file.open('rb') as f:batch=pickle.load(f)
            for symbol,frame in batch['frames'].items():
                isin=lookup.get(symbol)
                if isin not in wanted or not isinstance(frame,pd.DataFrame) or not {'Open','Close','Volume'}.issubset(frame):continue
                z=frame[['Open','Close','Volume']];z=z[~z.index.duplicated(keep='last')].sort_index()
                if isin in paths and len(paths[isin][0])>=len(z):continue
                paths[isin]=(z.index.tz_localize(None).to_numpy(dtype='datetime64[D]'),z.Open.to_numpy(float),z.Close.to_numpy(float),z.Volume.to_numpy(float))
            del batch;gc.collect()
        removed=0
        for isin,(ds,op,cl,v) in list(paths.items()):
            observed=np.isfinite(cl)&(cl>0);removed+=int((~observed).sum())
            paths[isin]=(ds[observed],op[observed],cl[observed],v[observed])
        with dest.open('wb') as f:pickle.dump(paths,f,protocol=5)
        if receipts:save('provider_source_receipts.json',receipts)
        save('quote_validation_receipt.json',dict(nonpriced_padding_rows_removed=removed,open_and_volume_missingness_preserved=True,
            original_cache_preserved=prior.exists(),reason='A padded row with no close is not an observed market quote. No prices imputed; execution gaps and zero volume remain blocking.'))
    features=[]
    for isin,g in x.groupby('isin'):
        if isin not in paths:continue
        ds,op,cl,v=paths[isin]
        for date in g.decision_date:
            row=dict(isin=isin,decision_date=date,adv20=np.nan)
            try:row.update(high_features(ds,cl,date))
            except ValueError:continue
            end=np.searchsorted(ds,np.datetime64(date),'left');start=end-20
            if start>=0 and int((np.datetime64(date)-ds[end-1]).astype(int))<=7 and not (np.diff(ds[start:end]).astype(int)>7).any():
                values=cl[start:end]*v[start:end]
                if np.isfinite(values).all() and (values>=0).all():row['adv20']=float(values.mean())
            features.append(row)
    f=pd.DataFrame(features);x=x.merge(f,on=['isin','decision_date'],how='left',validate='one_to_one')
    prior=pd.read_pickle(ROOT/'experiments/sector-price-rebuild-20261010/price_features.pkl.gz',compression='gzip')[['isin','decision_date','high_hits']]
    x=x.merge(prior,on=['isin','decision_date'],validate='one_to_one',how='left');x['core']=x[Q].mean(axis=1)
    x['liquidity_quintile']=np.ceil(x.groupby('decision_date').adv20.rank(pct=True)*5)
    x['sir_gate']=x.cagr3.ge(.10)&x.cagr5.ge(.10)&x.high_recency.ge(-365)
    x.to_pickle(WORK/'panel.pkl.gz',compression='gzip')
    registry();save('prepared_receipt.json',dict(rows=len(x),paths=len(paths),panel_sha256=hashlib.sha256((WORK/'panel.pkl.gz').read_bytes()).hexdigest(),price_basis='Cached provider Open/Close, split-adjusted price-only proxy; no independent vintage certification'))
    print('PREPARED',len(x),'rows',len(paths),'paths',flush=True)


def concentration(x,count):
    z=pd.read_pickle(PARENT/'development_scored.pkl.gz',compression='gzip')
    old=pd.read_csv(SOURCE/'development_portfolios.csv');common=sorted(set(old.loc[old.model.eq('tail75')&old.policy.eq('global_top20'),'decision_date'])&set(old.loc[old.model.eq('champion')&old.policy.eq('global_top20'),'decision_date']))
    details=[];stock={};membership=[]
    for date in common:
        g=z[z.decision_date.eq(date)];end=str((pd.Timestamp(date)+pd.DateOffset(months=12)).date());values={};ids={}
        for name in ['champion','tail75']:
            h=g.sort_values([name,'isin'],ascending=[False,True]).head(20)
            ids[name]=set(h['isin']);terms={r.isin:terminal(r.new_xirr,date,end)/20 for r in h.itertuples()};values[name]=sum(terms.values())
            actual=float(old.loc[old.model.eq(name)&old.policy.eq('global_top20')&old.decision_date.eq(date),'xirr'].iloc[0])
            assert abs(irate(values[name],date,end)-actual)<1e-9
            for isin,value in terms.items():stock[isin]=stock.get(isin,0)+(1 if name=='tail75' else -1)*value
            membership.extend(dict(decision_date=date,model=name,stock_xirr=r.new_xirr) for r in h.itertuples())
        details.append(dict(decision_date=date,end=end,tail_terminal=values['tail75'],champ_terminal=values['champion'],delta=irate(values['tail75'],date,end)-irate(values['champion'],date,end),tail_ids=ids['tail75'],champ_ids=ids['champion'],frame=g))
    dates=[r['decision_date'] for r in details];diff=np.array([r['delta'] for r in details]);result=boot(diff,dates)
    result.update(best_date=dates[int(np.argmax(diff))],best_date_share_of_net=float(diff.max()/diff.sum()),best_stock_terminal_share=float(max(stock.values())/(sum(stock.values()))),dates=len(diff))
    exclusions=[]
    for isin in sorted(stock):
        changes=[]
        for r in details:
            unused=7500*len(np.arange(np.datetime64(r['decision_date']),np.datetime64(r['end']),np.timedelta64(30,'D')))/20
            a=r['tail_terminal'];b=r['champ_terminal']
            if isin in r['tail_ids']:a+=unused-terminal(float(r['frame'].loc[r['frame']['isin'].eq(isin),'new_xirr'].iloc[0]),r['decision_date'],r['end'])/20
            if isin in r['champ_ids']:b+=unused-terminal(float(r['frame'].loc[r['frame']['isin'].eq(isin),'new_xirr'].iloc[0]),r['decision_date'],r['end'])/20
            changes.append(irate(a,r['decision_date'],r['end'])-irate(b,r['decision_date'],r['end']))
        exclusions.append(float(np.mean(changes)))
    result.update(leave_one_security_out_min=float(min(exclusions)),leave_one_security_out_max=float(max(exclusions)),security_count=len(stock),
        documented_adjusted_p=min(1,result['nominal_p']*count))
    result['concentration_screen_pass']=bool(min(result['median'],result['winsorized_mean'],result['lodo_min'],result['leave_one_security_out_min'])>0)
    pd.DataFrame([dict(decision_date=r['decision_date'],portfolio_xirr_delta=r['delta']) for r in details]).to_csv(OUT/'tail_date_concentration.csv',index=False)
    pd.DataFrame(membership).groupby('model').stock_xirr.agg(['mean','median']).to_csv(OUT/'tail_selected_stock_distribution.csv')
    save('tail_concentration.json',result);print('TAIL CONCENTRATION',result,flush=True)


def dose(x):
    x=x[x.decision_date.ge('2020-01-01')].copy();rows=[]
    for date,g in x.groupby('decision_date'):
        g=g.sort_values(['core','isin']).copy();g['decile']=np.minimum(9,np.arange(len(g))*10//len(g))+1
        for d,h in g.groupby('decile'):
            good=h[h.new_xirr.notna()];rows.append(dict(decision_date=date,year=int(date[:4]),decile=int(d),feature_count=len(h),valid_count=len(good),xirr=good.new_xirr.mean(),drawdown=good.new_dd.mean()))
    r=pd.DataFrame(rows);r.to_csv(OUT/'dose_date_deciles.csv',index=False)
    annual=r.groupby(['year','decile'])[['xirr','drawdown']].mean().reset_index();annual.to_csv(OUT/'dose_year_deciles.csv',index=False)
    contrast=[]
    for year,g in annual.groupby('year'):
        middle=g[g.decile.between(6,9)];top=g[g.decile.eq(10)];low=g[g.decile.le(5)]
        contrast.append(dict(year=int(year),middle_minus_top=float(middle.xirr.mean()-top.xirr.mean()),middle_minus_low=float(middle.xirr.mean()-low.xirr.mean()),middle_dd_minus_top=float(middle.drawdown.mean()-top.drawdown.mean())))
    c=pd.DataFrame(contrast);c.to_csv(OUT/'dose_fixed_contrasts.csv',index=False);dev=c[c.year.between(2021,2023)]
    n=int((dev.middle_minus_top.gt(0)&dev.middle_minus_low.gt(0)&dev.middle_dd_minus_top.ge(0)).sum())
    save('dose_gate.json',dict(status='NOT_CONFIRMED' if n<2 or dev.middle_minus_top.mean()<=0 or dev.middle_minus_low.mean()<=0 else 'EXPLORATORY_SHAPE_PASS',qualifying_years=n,band='Fixed deciles6–9; no new band selected'))


def profiles(x):
    scores=[];path=ROOT/'experiments/champion-sip-profit-20261017/historical_scores.csv.gz'
    for chunk in pd.read_csv(path,usecols=['isin','decision_date','profile_name','sip_risk_confirmed_0.01'],chunksize=20000):
        h=chunk[chunk.decision_date.ge('2020-01-01')&chunk.decision_date.lt('2024-01-01')]
        if len(h):scores.append(h)
    scores=pd.concat(scores,ignore_index=True).rename(columns={'sip_risk_confirmed_0.01':'profile_champion'})
    z=pd.read_pickle(PARENT/'development_scored.pkl.gz',compression='gzip')[['isin','decision_date','tail75']]
    base=x[x.decision_date.ge('2020-01-01')].drop(columns=['profile_name']).merge(z,on=['isin','decision_date'],validate='one_to_one')
    rows=[];selected=[];score_coverage=[]
    for (profile,date),g in scores.merge(base,on=['isin','decision_date'],validate='many_to_one').groupby(['profile_name','decision_date']):
        score_coverage.append(dict(profile_name=profile,decision_date=date,feature_rows=len(g),missing_scores=int(g.profile_champion.isna().sum())))
        if not g.profile_champion.notna().all():continue
        for name,col in [('champion','profile_champion'),('tail75','tail75')]:
            h=g.sort_values([col,'isin'],ascending=[False,True]).head(20)
            selected.extend(dict(profile_name=profile,decision_date=date,model=name,isin=r.isin) for r in h.itertuples())
        if profile not in ['target10','base7500','target30']:continue
        threshold=.10 if profile=='target10' else .30 if profile=='target30' else .20
        picks={name:g.sort_values([col,'isin'],ascending=[False,True]).head(20) for name,col in [('champion','profile_champion'),('tail75','tail75')]}
        if any(not h.new_xirr.notna().all() for h in picks.values()):continue
        for name,h in picks.items():rows.append(dict(profile_name=profile,decision_date=date,year=int(date[:4]),model=name,target=threshold,attainment=float(h.new_xirr.ge(threshold).mean())))
    r=pd.DataFrame(rows);r.to_csv(OUT/'corrected_profile_goal_dates.csv',index=False)
    if r.empty:raise RuntimeError('No corrected profile rows; preserve source evidence and inspect missing-score coverage')
    pivot=r.pivot(index=['profile_name','decision_date','year'],columns='model',values='attainment').dropna().reset_index();pivot['delta']=pivot.tail75-pivot.champion
    annual=pivot.groupby(['profile_name','year']).agg(delta=('delta','mean'),dates=('decision_date','nunique')).reset_index();annual.to_csv(OUT/'corrected_profile_goal_years.csv',index=False)
    high=annual[annual.profile_name.eq('target30')&annual.year.between(2021,2023)];n=int(high.delta.gt(0).sum())
    pooled=float(pivot.loc[pivot.profile_name.eq('target30')&pivot.year.between(2021,2023),'delta'].mean())
    save('goal_profile_gate.json',dict(status='EXPLORATORY_THRESHOLD_PASS' if len(high)==3 and high.dates.ge(2).all() and n>=2 and pooled>0 else 'NOT_CONFIRMED',positive_high_target_years=n,pooled_high_target_delta=pooled,personalized_rank_learned=False,interpretation='Frozen base7500tail order; threshold utility is not proof of target-conditional ordering'))
    pd.DataFrame(score_coverage).to_csv(OUT/'profile_score_coverage.csv',index=False)
    picks=pd.DataFrame(selected);labels=[];panel=ROOT/'experiments/personalized-deep-history-20261002/real-panel-v12/deep_panel.csv.gz'
    wanted=set(picks.decision_date)
    for chunk in pd.read_csv(panel,usecols=['isin','decision_date','profile_name','future_xirr'],chunksize=20000):
        h=chunk[chunk.decision_date.isin(wanted)]
        if len(h):labels.append(h)
    labels=pd.concat(labels,ignore_index=True);legacy=picks.merge(labels,on=['isin','decision_date','profile_name'],validate='many_to_one')
    config=json.loads((ROOT/'research/protocols/personalized_official_action_tournament_v1.json').read_text())['profiles'];out=[];coverage=[]
    for (profile,date),g in legacy.groupby(['profile_name','decision_date']):
        coverage.append(dict(profile_name=profile,decision_date=date,selected_rows=len(g),unknown_outcomes=int(g.future_xirr.isna().sum())))
        if len(g)!=40 or g.future_xirr.isna().any():continue
        target=config[profile]['target_cagr']
        for name,h in g.groupby('model'):out.append(dict(profile_name=profile,decision_date=date,year=int(date[:4]),model=name,attainment=float(h.future_xirr.ge(target).mean())))
    legacy=pd.DataFrame(out);legacy.to_csv(OUT/'legacy_nine_profile_dates.csv',index=False)
    pd.DataFrame(coverage).to_csv(OUT/'legacy_profile_coverage.csv',index=False)
    legacy.groupby(['profile_name','year','model']).attainment.mean().to_csv(OUT/'legacy_nine_profile_transfer.csv')


def gate_and_ladder(x):
    dev=x[x.decision_date.ge('2020-01-01')&x.champion_percentile.notna()].copy();sector=[]
    for (date,s),g in dev.groupby(['decision_date','sector']):
        if len(g)<5:continue
        g=g.copy();g['gate_score']=np.where(g.sir_gate,.5+.5*g.champion_percentile,.5*g.champion_percentile)
        good=g[g.new_xirr.notna()]
        if len(good)<5:continue
        base=g.sort_values(['champion_percentile','isin'],ascending=[False,True]).head(3)
        passed=g[g.sir_gate].sort_values(['champion_percentile','isin'],ascending=[False,True]).head(3)
        ok=len(passed)==3 and base.new_dd.notna().all() and passed.new_dd.notna().all()
        sector.append(dict(decision_date=date,sector=s,champion_ic=good.champion_percentile.corr(good.new_xirr,method='spearman'),gate_ic=good.gate_score.corr(good.new_xirr,method='spearman'),
            selected_stock_dd_delta=float(passed.new_dd.mean()-base.new_dd.mean()) if ok else np.nan))
    q=pd.DataFrame(sector);q.to_csv(OUT/'gate_sector_metrics.csv',index=False)
    d=q.groupby('decision_date')[['champion_ic','gate_ic','selected_stock_dd_delta']].mean().reset_index();d['ic_delta']=d.gate_ic-d.champion_ic;d.to_csv(OUT/'gate_date_metrics.csv',index=False)
    with (ROOT/'work/new-information-20261101/actual_adjusted_open_close.pkl').open('rb') as f:adjusted=pickle.load(f)
    with (WORK/'split_paths_observed.pkl').open('rb') as f:raw=pickle.load(f)
    actions=pd.read_csv(ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv');actions=actions[actions.status.ne('ALIGNED_MULTIPLIER')]
    portfolios=[];ladder=[];failures=[];saved_picks=[]
    for date,g in dev.groupby('decision_date',sort=True):
        end=str((pd.Timestamp(date)+pd.DateOffset(months=12)).date());startd=np.datetime64(date);endd=np.datetime64(end)
        passed=g[g.sir_gate].sort_values(['champion_percentile','isin'],ascending=[False,True]).head(20)
        base=g.sort_values(['champion_percentile','isin'],ascending=[False,True]).head(20)
        bad=set(actions.loc[actions.event_date.gt(date)&actions.event_date.le(end),'isin'])
        for name,h in [('champion',base),('gated',passed)]:
            try:
                if len(h)!=20:raise ValueError('Fewer than20eligible gate names')
                ids=h['isin'].tolist()
                if set(ids)&bad:raise ValueError('Unresolved corporate action')
                if set(ids)-set(adjusted):raise ValueError('Missing adjusted execution path')
                r=next_open_portfolio([scope_path(adjusted[i],date,end) for i in ids],np.full(20,.05),date,end,7500,30,100)
                portfolios.append(dict(decision_date=date,model=name,xirr=r['xirr'],drawdown=r['tw_max_drawdown']))
            except ValueError as e:failures.append(dict(test='gate',decision_date=date,scope=name,reason=str(e)))
        # Membership and cash weights are frozen before liquidity/outcome guards.
        if len(passed)!=20:
            failures.append(dict(test='ladder',decision_date=date,scope='all',reason='Fewer than20gate selections'));continue
        saved_picks.extend(dict(decision_date=date,isin=r.isin,liquidity_quintile=r.liquidity_quintile) for r in passed.itertuples())
        if set(passed['isin'])&bad:
            failures.append(dict(test='ladder',decision_date=date,scope='both_liquidity_scopes',reason='Original portfolio has unresolved corporate action; remains blocked'));continue
        for liquidity_scope in ['all','exclude_bottom_quintile']:
            if passed.liquidity_quintile.isna().any():
                failures.append(dict(test='ladder',decision_date=date,scope=liquidity_scope,reason='Unknown ADV20quintile'));continue
            included=passed if liquidity_scope=='all' else passed[passed.liquidity_quintile.gt(1)]
            ids=included['isin'].tolist();excluded=20-len(ids)
            try:
                if not ids or set(ids)-set(raw):raise ValueError('Missing source path or empty liquidity cohort')
                if set(ids)&bad:raise ValueError('Unresolved corporate action')
                calendar=np.unique(np.concatenate([[startd,endd]]+[raw[i][0][(raw[i][0]>=startd)&(raw[i][0]<=endd)] for i in ids]))
                per_scope=[]
                for rate in [0.,.04]:
                    rows={}
                    for policy in ['ladder','sip']:
                        r=[funded_stock(raw[i],date,end,policy,cash_rate=rate,calendar=calendar) for i in ids]
                        cash=90000*(1+rate)**((calendar-startd).astype(float)/365.25)
                        wealth=(np.sum([v['_wealth'] for v in r],axis=0)+excluded*cash)/20
                        nav=wealth/90000;dd=float((nav/np.maximum.accumulate(nav)-1).min())
                        annual=float((wealth[-1]/90000)**(365.25/int((endd-startd).astype(int)))-1)
                        rows[policy]=dict(xirr=annual,dd=dd,deployment=float(sum(v['deployment'] for v in r)/20),
                            no_fill=float(np.mean([v['no_fill'] for v in r])),trap=float(np.mean([v['trap'] for v in r])))
                    a,b=rows['ladder'],rows['sip']
                    per_scope.append(dict(decision_date=date,year=int(date[:4]),liquidity_scope=liquidity_scope,cash_rate=rate,included_stocks=len(ids),
                        ladder_xirr=a['xirr'],sip_xirr=b['xirr'],delta=a['xirr']-b['xirr'],dd_delta=a['dd']-b['dd'],
                        budget_deployed=a['deployment'],never_fill_share=a['no_fill'],five_plus_below_cost_share=a['trap']))
                ladder.extend(per_scope)
            except ValueError as e:failures.append(dict(test='ladder',decision_date=date,scope=liquidity_scope,reason=str(e)))
        print('GATE/LADDER',date,'comparisons',len(ladder),'blocked',len(failures),flush=True)
    pd.DataFrame(saved_picks).to_pickle(WORK/'ladder_selected_ids.pkl.gz',compression='gzip')
    p=pd.DataFrame(portfolios);p.to_csv(OUT/'gate_portfolios.csv',index=False)
    pairs=p[p.model.eq('gated')].merge(p[p.model.eq('champion')],on='decision_date',suffixes=('_gate','_champion'),validate='one_to_one')
    pairs['dd_delta']=pairs.drawdown_gate-pairs.drawdown_champion;pairs.to_csv(OUT/'gate_portfolio_pairs.csv',index=False)
    delta=float(d.ic_delta.mean());dd=float(pairs.dd_delta.mean())
    save('gate_rule_result.json',dict(status='EXPLORATORY_GATE_PASS' if len(pairs)>=8 and delta>=-.01 and dd>0 else 'NOT_CONFIRMED',ic_delta=delta,portfolio_dd_delta=dd,matched_dates=len(pairs),selected_stock_dd_delta=float(d.selected_stock_dd_delta.mean())))
    r=pd.DataFrame(ladder);r.to_csv(OUT/'ladder_date_results.csv',index=False);pd.DataFrame(failures).to_csv(OUT/'execution_failure_counts.csv',index=False)
    tests=[];annual=[]
    for (scope,rate),h in r.groupby(['liquidity_scope','cash_rate']):
        h=h.sort_values('decision_date');stats=boot(h.delta,h.decision_date);years=h.groupby('year').delta.agg(['mean','size'])
        for year,v in years.iterrows():annual.append(dict(liquidity_scope=scope,cash_rate=rate,year=int(year),delta=float(v['mean']),dates=int(v['size'])))
        complete=set(years.index)=={2020,2021,2022,2023} and years['size'].ge(2).all()
        passed=bool(complete and years['mean'].gt(0).all() and stats['mean']>0 and stats['winsorized_mean']>0 and stats['lodo_min']>0 and h.dd_delta.mean()>=0)
        tests.append(dict(liquidity_scope=scope,cash_rate=rate,pass_fixed_rule=passed,mean_dd_delta=float(h.dd_delta.mean()),dates=len(h),**stats))
    pd.DataFrame(annual).to_csv(OUT/'ladder_year_results.csv',index=False);pd.DataFrame(tests).to_csv(OUT/'ladder_robustness.csv',index=False)
    save('ladder_gate.json',dict(status='EXPLORATORY_PROXY_PASS' if len(tests)==4 and all(t['pass_fixed_rule'] for t in tests) else 'NOT_CONFIRMED',
        label='static fixed-anchor ladder, not the daily-reset ladder',cash_rate4='Fixed scenario, not observed liquid-fund history',exposed_evaluated=False))


def ath_increment(x,count):
    x=x.copy();raw=['downside252','volatility252','return21','ath_gap','ath_recency','high_hits']
    x=x[np.isfinite(x[raw+['ath_count']]).all(axis=1)].copy()
    for c in raw+['ath_count']:x['f_'+c]=x.groupby(['decision_date','sector'])[c].rank(pct=True)
    base=Q+['f_'+c for c in raw];extra=base+['f_ath_count'];rows=[];folds=[]
    for year in range(2020,2024):
        train=x[x.new_endpoint.lt(f'{year}-01-01')&x.new_xirr.notna()];test=x[x.decision_date.str.startswith(str(year))].copy()
        if len(train)<100 or train.decision_date.nunique()<2:continue
        for name,cols in [('baseline',base),('ath_count',extra)]:
            model=Ridge(alpha=10);model.fit(train[cols],np.log1p(train.new_xirr.clip(-.95,3)));test[name]=model.predict(test[cols])
        folds.append(dict(year=year,latest_training_label=train.new_endpoint.max(),train_rows=len(train)))
        for (date,sector),g in test.groupby(['decision_date','sector']):
            g=g[g.new_xirr.notna()]
            if len(g)<5:continue
            rows.append(dict(decision_date=date,year=year,sector=sector,baseline_ic=g.baseline.corr(g.new_xirr,method='spearman'),count_ic=g.ath_count.corr(g.new_xirr,method='spearman')))
    z=pd.DataFrame(rows);z.to_csv(OUT/'ath_count_sector_ic.csv',index=False)
    d=z.groupby(['decision_date','year'])[['baseline_ic','count_ic']].mean().reset_index();d['delta']=d.count_ic-d.baseline_ic;d.to_csv(OUT/'ath_count_date_ic.csv',index=False)
    pd.DataFrame(folds).to_csv(OUT/'ath_count_folds.csv',index=False);stats=boot(d.delta,d.decision_date)
    # Centered95% one-sided paired hurdle = point estimate minus lower one-sided95% bound.
    from champion_market_review_20261031 import block_indices
    rng=np.random.default_rng(20261101);values=d.delta.to_numpy();center=values-values.mean()
    null=np.array([center[block_indices(d.decision_date.to_numpy(),365,rng)].mean() for _ in range(2000)])
    floor=max(.01013492400721767,float(np.quantile(null,.95)));annual=d.groupby('year').delta.mean();n=int(annual.loc[[2021,2022,2023]].gt(0).sum())
    save('ath_count_gate.json',dict(status='EXPLORATORY_INCREMENT_PASS' if stats['mean']>floor and n>=2 else 'NOT_CONFIRMED',
        required_increment=floor,positive_2021_23_years=n,documented_adjusted_p=min(1,stats['nominal_p']*count),baseline_ic=float(d.baseline_ic.mean()),augmented_ic=float(d.count_ic.mean()),**stats))


def analyze():
    count=registry();x=pd.read_pickle(WORK/'panel.pkl.gz',compression='gzip')
    x.assign(has_ath=x.ath_count.notna(),has_adv=x.adv20.notna()).groupby('decision_date').agg(rows=('isin','size'),available_ath=('has_ath','sum'),available_adv20=('has_adv','sum')).to_csv(OUT/'feature_coverage.csv')
    concentration(x,count);profiles(x);dose(x);gate_and_ladder(x);ath_increment(x,count)


if __name__=='__main__':
    OUT.mkdir(exist_ok=True);WORK.mkdir(exist_ok=True)
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','analyze','profiles']);a=p.parse_args()
    proto=ROOT/'research/protocols/sir_extensions_20261101.md'
    receipt=OUT/'protocol_receipt.json'
    if not receipt.exists():save(receipt.name,dict(sha256=hashlib.sha256(proto.read_bytes()).hexdigest(),frozen_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    assert json.loads(receipt.read_text())['sha256']==hashlib.sha256(proto.read_bytes()).hexdigest()
    timer=start_watchdog(1200,OUT/f'{a.stage}_timeout.json')
    try:
        if a.stage=='profiles':profiles(pd.read_pickle(WORK/'panel.pkl.gz',compression='gzip'))
        else:globals()[a.stage]()
    finally:timer.cancel()
