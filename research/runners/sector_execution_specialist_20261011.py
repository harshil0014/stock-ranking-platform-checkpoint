"""Matched activity-feature and conservative-return specialist experiment."""
import sys,json,time,hashlib
import numpy as np
import pandas as pd
import lightgbm as lgb
import sector_tabpfn_hybrid_20261011 as h
p=h.p;OUT=p.ROOT/'experiments/sector-execution-specialist-20261011'
SOURCE=p.ROOT/'experiments/v17-peak-activity-20261004/dated_features.csv.gz'
EXTRA=['volume_active_fraction','traded_value','last_positive_volume_lag_days','execution_quote_lag','activity_available','log_contribution_to_traded_value']
CONFIGS=[(loss,features) for loss in ['balanced_l1','return_q25'] for features in ['base','activity']]
WEIGHTS=[.1,.3,1.]
NAMES=[f'{a}_{b}_w{w}' for a,b in CONFIGS for w in WEIGHTS]
def write(name,data):(OUT/name).write_text(json.dumps(data,indent=2),encoding='utf-8')
def enrich(x,activity):
    cols=['isin','decision_date','volume_active_fraction','traded_value','last_positive_volume_lag_days','last_observed_date']
    # The current export already carries an older activity field. Use one explicitly dated source.
    x=x.drop(columns=[col for col in cols[2:] if col in x])
    z=x.merge(activity[cols],on=['isin','decision_date'],how='left',validate='many_to_one')
    lag=(pd.to_datetime(z.decision_date)-pd.to_datetime(z.last_observed_date)).dt.days
    assert lag.dropna().ge(0).all()
    z['execution_quote_lag']=lag;z['activity_available']=z.traded_value.notna().astype(float)
    z['log_contribution_to_traded_value']=z.log_amount-z.traded_value
    # Inactive evidence stays visible; unresolved primary price windows do not become valid through this join.
    for col in EXTRA:z.loc[z.evidence_fraction.le(0),col]=np.nan
    return z
def learn():
    OUT.mkdir(exist_ok=True)
    doc=dict(configs=CONFIGS,weights=WEIGHTS,extra_features=EXTRA,source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
      design='Matched base70features versus plus6execution features, same training rows. LightGBM balanced percentile L1 and capped future SIP-XIRR lower25th-quantile specialists. 240trees,depth4,leaves15,minchild120,L2=40,lr.03,threads3,seed20261011.',
      training='Entire guarded historical prepared panel, endpoint<annualJan1/currentOct3, known sectors with5peers, usable primary inputs, equal query weight. No future trade observations. Missing activity remains missing; no zero volume fabrication.',
      scoring='Rank model outputs within sector/date/profile; missing primary evidence retains champion percentile; test standalone1 and .1/.3 champion blends. Quantile is a fitted conditional quantile, not a calibrated guarantee.',
      limitations='Provider raw-close times volume median is an approximate historical activity signal, not executable orderbook capacity. The contribution ratio is log(amount+1)-log(median reported traded value+1); it is not slippage. Current-universe mapping and corporate-action revision limits remain.',
      selection='Development2020-23 whole-sector rankIC and non-return Top3 regressions; meanXIRR weight0. Recent2024-25 exposed. Exact feature-matched controls retained for any finalists.',fresh_validation=False,
      sources=['https://lightgbm.readthedocs.io/en/latest/Parameters.html','https://academic.oup.com/rfs/article-abstract/12/5/1113/1565408'])
    path=OUT/'protocol.json'
    if path.exists():assert json.loads(path.read_text())==json.loads(json.dumps(doc))
    else:write('protocol.json',doc)
    activity=pd.read_csv(SOURCE);assert not activity.duplicated(['isin','decision_date']).any() and (activity.last_observed_date<=activity.decision_date).all()
    x=enrich(pd.read_pickle(p.OUT/'prepared.pkl.gz',compression='gzip'),activity);anchor=h.load();audit=[]
    for year in [2020,2021,2022,2023,2024,2025,'current']:
        receipt=OUT/f'audit_{year}.json'
        if receipt.exists():audit+=json.loads(receipt.read_text());continue
        cutoff=p.ASOF if year=='current' else f'{year}-01-01'
        t=x[x.endpoint.lt(cutoff)&x.sector.ne('Unclassified')].dropna(subset=['future_xirr','future_drawdown','future_shortfall']).copy()
        keys=['decision_date','profile_name','sector'];t=t[t.groupby(keys)['isin'].transform('size').ge(5)].copy();g=t.groupby(keys)
        t['balanced_target']=.5*g.future_xirr.rank(pct=True)+.25*g.future_drawdown.rank(pct=True)+.25*g.future_shortfall.rank(pct=True,ascending=False)
        t=t[t.evidence_fraction.gt(0)].copy();t=t[t.groupby(keys)['isin'].transform('size').ge(5)];weight=1/t.groupby(keys)['isin'].transform('size');weight/=weight.mean()
        assert t.endpoint.max()<cutoff
        if year=='current':z=enrich(h.current(),activity)
        else:
            z=x[x.decision_date.str.startswith(str(year))].copy();z=z.merge(anchor[p.KEYS+[h.ANCHOR,'champion_percentile']] if 'champion_percentile' in anchor else anchor[p.KEYS+[h.ANCHOR]],on=p.KEYS,validate='one_to_one')
            z['champion_percentile']=z.groupby(keys)[h.ANCHOR].rank(pct=True)
        pred=z[p.KEYS+['sector',h.ANCHOR,'evidence_fraction']].copy();rows=[]
        for loss,feature_set in CONFIGS:
            cols=p.COLS+(EXTRA if feature_set=='activity' else []);target=t.balanced_target if loss=='balanced_l1' else t.future_xirr.clip(-1,1)
            m=lgb.LGBMRegressor(objective='regression_l1' if loss=='balanced_l1' else 'quantile',alpha=.25,n_estimators=240,num_leaves=15,max_depth=4,min_child_samples=120,reg_lambda=40,learning_rate=.03,n_jobs=3,random_state=20261011,deterministic=True,force_col_wise=True,verbosity=-1)
            started=time.time();m.fit(t[cols],target,sample_weight=weight);modelpath=OUT/f'{loss}_{feature_set}_{year}.txt';m.booster_.save_model(str(modelpath))
            raw=m.predict(z[cols]);replay=lgb.Booster(model_file=str(modelpath)).predict(z[cols],num_threads=3);np.testing.assert_allclose(raw,replay,rtol=0,atol=0)
            rank=pd.Series(raw,index=z.index).groupby([z[k] for k in keys]).rank(pct=True).where(z.evidence_fraction.gt(0),z.champion_percentile)
            for w in WEIGHTS:pred[f'{loss}_{feature_set}_w{w}']=(1-w)*z.champion_percentile+w*rank
            rows.append(dict(year=year,loss=loss,feature_set=feature_set,training_rows=len(t),max_endpoint=t.endpoint.max(),cutoff=cutoff,seconds=time.time()-started,replay_exact=True,activity_training_rows=int(t.activity_available.eq(1).sum()),model_sha256=hashlib.sha256(modelpath.read_bytes()).hexdigest()))
            print('FIT',year,loss,feature_set,len(t),flush=True)
        assert np.isfinite(pred[NAMES]).all().all();pred.to_csv(OUT/f'predictions_{year}.csv.gz',index=False)
        if year=='current':
            cur=pred.merge(z[['isin','ticker','company','input_status','rebuilt_input_confidence','rebuilt_sector_rank']+EXTRA],on='isin',validate='one_to_one')
            for name in NAMES:cur[name+'_rank']=cur[name].groupby(cur.sector).rank(method='min',ascending=False)
            assert len(cur)==4436 and cur['isin'].is_unique;cur.to_csv(OUT/'all_4436_all_candidates.csv',index=False)
        write(receipt.name,rows);audit+=rows;pd.DataFrame(audit).to_csv(OUT/'training_audit.csv',index=False)
if __name__=='__main__':learn()
