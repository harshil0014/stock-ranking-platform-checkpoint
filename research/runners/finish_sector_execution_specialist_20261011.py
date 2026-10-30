"""Evaluate activity/quantile ablations with the same full sector diagnostics."""
import sector_execution_specialist_20261011 as e
import audit_sector_specialist_ensemble_20261011 as a
import pandas as pd
import numpy as np
import json,sys
OUT=e.OUT;p=e.p;h=e.h;ANCHOR=h.ANCHOR

def evaluate(stage):
    dev=stage=='development';names=e.NAMES if dev else json.loads((OUT/'locked_finalists.json').read_text())['finalists'];years=list(range(2020,2024)) if dev else [2024,2025]
    x=h.load();x=x[x.decision_date.str[:4].astype(int).isin(years)]
    scores=pd.concat([pd.read_csv(OUT/f'predictions_{y}.csv.gz',usecols=p.KEYS+names) for y in years]);x=x.merge(scores,on=p.KEYS,validate='one_to_one');summary=[]
    for scope in ['common','expanded']:
        z=x[x.sector_incumbent.notna()].copy() if scope=='common' else x.copy()
        for cap in [False,True]:
            path=OUT/f'queries_{stage}_{scope}_{cap}_0.csv.gz'
            if path.exists():q=pd.read_csv(path)
            else:
                zz=z.copy()
                if cap:zz.future_xirr=zz.future_xirr.clip(-1,1)
                q=p.metrics(zz,[ANCHOR]+names,top_ns=(1,3,5));q.to_csv(path,index=False)
            assert set(q.model)==set([ANCHOR]+names)
            agg=q.groupby(['model','period','profile','top_n','sector'])[p.METRICS].mean().groupby(['model','period','profile','top_n']).mean().reset_index();agg['scope']=scope;agg['return_treatment']='capped' if cap else 'raw';summary.append(agg)
            print('EVALUATED',stage,scope,cap,flush=True)
    ss=pd.concat(summary);ss.to_csv(OUT/f'summary_{stage}.csv',index=False);ix=ss.set_index(['model','period','profile','top_n','scope','return_treatment'])[p.METRICS];trials=[]
    for name in names:
        d=(ix.loc[name]-ix.loc[ANCHOR]).reset_index();d.shortfall=-d.shortfall;v=d[p.METRICS].to_numpy();nonreturn=[m for m in p.METRICS if m!='xirr'];nv=d[nonreturn].to_numpy();top=d[d.top_n.eq(3)][nonreturn].to_numpy()
        ic=ss[ss.model.eq(name)&ss.scope.eq('expanded')&ss.return_treatment.eq('raw')&ss.top_n.eq(3)].rank_ic.mean()
        trials.append(dict(model=name,rank_ic=ic,regressed=int((v< -1e-12).sum()),improved=int((v>1e-12).sum()),nonreturn_regressions=int((nv< -1e-12).sum()),top3_nonreturn_regressions=int((top< -1e-12).sum())))
    trials=pd.DataFrame(trials);trials.to_csv(OUT/f'trials_{stage}.csv',index=False)
    if dev:
        order=trials.sort_values(['rank_ic','nonreturn_regressions','model'],ascending=[False,True,True]);chosen=[]
        for loss,features in e.CONFIGS:chosen.append(order[order.model.str.startswith(loss+'_'+features+'_')].iloc[0].model)
        chosen.append(trials.sort_values(['top3_nonreturn_regressions','nonreturn_regressions','model']).iloc[0].model)
        for name in list(chosen):chosen.append(name.replace('_activity_','_base_') if '_activity_' in name else name.replace('_base_','_activity_'))
        e.write('locked_finalists.json',dict(finalists=list(dict.fromkeys(chosen)),development_sha256=a.s.digest(OUT/'trials_development.csv'),selection_mean_xirr_weight=0))
    print(trials.to_string(index=False),flush=True)

def audit():
    # Identical generic outcome/stock-review audit; its independent-model replay is not used here.
    a.OUT=OUT;a.s.OUT=OUT;a.c.NAMES=e.NAMES
    for year in range(2020,2026):
        dest=OUT/f'combined_{year}.csv.gz';source=OUT/f'predictions_{year}.csv.gz'
        if not dest.exists():dest.hardlink_to(source)
    a.evaluate();a.company_audit()
    ss=pd.read_csv(OUT/'finalist_summary.csv').set_index(['model','period','profile','top_n','scope','return_treatment'])[p.METRICS];names=ss.index.get_level_values('model').unique();comparisons=[]
    for name in names:
        if '_activity_' not in name:continue
        control=name.replace('_activity_','_base_')
        assert control in names
        d=(ss.loc[name]-ss.loc[control]).reset_index();d.shortfall=-d.shortfall;d['activity_model']=name;d['matched_base']=control;comparisons.append(d)
    pd.concat(comparisons).to_csv(OUT/'activity_feature_contribution.csv',index=False)

def replay():
    activity=pd.read_csv(e.SOURCE);x=e.enrich(pd.read_pickle(p.OUT/'prepared.pkl.gz',compression='gzip'),activity);anchor=h.load();errors=[];calibration=[]
    for year in [2020,2021,2022,2023,2024,2025,'current']:
        z=e.enrich(h.current(),activity) if year=='current' else x[x.decision_date.str.startswith(str(year))].merge(anchor[p.KEYS+[ANCHOR,'champion_percentile']],on=p.KEYS,validate='one_to_one')
        saved=pd.read_csv(OUT/f'predictions_{year}.csv.gz').set_index(p.KEYS).reindex(pd.MultiIndex.from_frame(z[p.KEYS]));assert saved[e.NAMES].notna().all().all()
        receipts=json.loads((OUT/f'audit_{year}.json').read_text());keys=['decision_date','profile_name','sector']
        for loss,features in e.CONFIGS:
            cols=p.COLS+(e.EXTRA if features=='activity' else []);path=OUT/f'{loss}_{features}_{year}.txt'
            receipt=next(r for r in receipts if r['loss']==loss and r['feature_set']==features)
            assert receipt['max_endpoint']<receipt['cutoff'] and receipt['model_sha256']==a.s.digest(path)
            model=e.lgb.Booster(model_file=str(path));raw=model.predict(z[cols],num_threads=3)
            if loss=='return_q25' and year!='current':
                valid=z.future_xirr.notna()&z.evidence_fraction.gt(0)&z.sector.ne('Unclassified')
                rr=z.loc[valid,['decision_date','profile_name','sector']].copy();yy=z.loc[valid,'future_xirr'].clip(-1,1).to_numpy();pp=raw[valid.to_numpy()]
                rr['below_predicted_q25']=(yy<=pp).astype(float);rr['pinball_loss']=np.maximum(.25*(yy-pp),-.75*(yy-pp));rr['model']=loss+'_'+features;rr['year']=year
                calibration.append(rr.groupby(['model','year','decision_date','profile_name','sector'])[['below_predicted_q25','pinball_loss']].mean().reset_index())
            rank=pd.Series(raw,index=z.index).groupby([z[k] for k in keys]).rank(pct=True).where(z.evidence_fraction.gt(0),z.champion_percentile)
            for w in e.WEIGHTS:
                expected=(1-w)*z.champion_percentile+w*rank;error=float(np.max(abs(expected.to_numpy()-saved[f'{loss}_{features}_w{w}'].to_numpy())))
                assert error<1e-12, (year,loss,features,w,error)
                errors.append(error)
        print('REPLAY',year,flush=True)
    e.write('replay_verification.json',dict(models=28,maximum_csv_replay_error=max(errors),cutoffs_verified=True,source_sha256=a.s.digest(e.SOURCE)))
    q=pd.concat(calibration);q.to_csv(OUT/'quantile_calibration_queries.csv',index=False)
    q.groupby(['model','year','profile_name','sector'])[['below_predicted_q25','pinball_loss']].mean().groupby(['model','year','profile_name']).mean().groupby(['model','year']).mean().reset_index().to_csv(OUT/'quantile_calibration_summary.csv',index=False)

if __name__=='__main__':
    if sys.argv[1] in ['development','recent']:evaluate(sys.argv[1])
    elif sys.argv[1]=='audit':audit()
    elif sys.argv[1]=='replay':replay()
