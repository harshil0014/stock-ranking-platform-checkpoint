"""Matched-family uncertainty, calibration and artifact audit after fixed pilots."""
import json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import ten_hypotheses_20261031 as r
OUT=r.OUT

def run():
    q=pd.read_csv(OUT/'goal_queries.csv.gz');models=sorted(set(q.model)-{r.ANCHOR});floors=[]
    for metric in ['rank_ic','achievement']:
        d=q[q.decision_date.lt('2024-01-01')].pivot(index=r.GROUP,columns='model',values=metric)
        # A constant probability has undefined Spearman IC. Use a separately
        # disclosed zero-association convention rather than deleting its dates.
        d=d.fillna(0) if metric=='rank_ic' else d.dropna()
        d=d[models].subtract(d[r.ANCHOR],axis=0).groupby('decision_date').mean()
        for span in [365,730]:
            row=r.block_floor(d.to_numpy(),d.index,span);row.update(metric=metric,observed_best_delta=float(d.mean().max()),best_model=d.mean().idxmax());floors.append(row)
    pd.DataFrame(floors).to_csv(OUT/'goal_family_noise_floor.csv',index=False)
    diagnostics=[]
    for (period,model),g in q.assign(period=np.where(q.decision_date.lt('2024-01-01'),'development','exposed')).groupby(['period','model']):
        diagnostics.append(dict(period=period,model=model,defined_ic_fraction=float(g.rank_ic.notna().mean()),zero_association_ic=float(g.assign(rank_ic=g.rank_ic.fillna(0)).groupby('decision_date').rank_ic.mean().mean())))
    pd.DataFrame(diagnostics).to_csv(OUT/'constant_probability_ic_audit.csv',index=False)
    z=pd.read_pickle(OUT/'goal_predictions.pkl.gz',compression='gzip');reliability=[]
    for period,g in z.groupby(np.where(z.decision_date.lt('2024-01-01'),'development','exposed')):
        for model in models:
            b=pd.cut(g[model],np.linspace(0,1,11),include_lowest=True)
            a=g.groupby(b,observed=True).agg(mean_probability=(model,'mean'),hit_frequency=('goal_hit','mean'),rows=('goal_hit','size')).reset_index(drop=True)
            a['period']=period;a['model']=model;reliability.append(a)
    pd.concat(reliability).to_csv(OUT/'probability_reliability.csv',index=False)
    identity=['isin','decision_date','sector'];p=z[z.profile_name.isin(['base7500','target10','target30'])].copy()
    for model in models:p[model+'_rank']=p[model].groupby([p[k] for k in r.GROUP]).rank(pct=True)
    changes=[]
    for model in models:
        wide=p.pivot(index=identity,columns='profile_name',values=[model,model+'_rank']).dropna()
        changes.append(dict(model=model,matched_stock_dates=len(wide),probability_changes=int((wide[model].max(axis=1)-wide[model].min(axis=1)>1e-9).sum()),rank_changes=int((wide[model+'_rank'].max(axis=1)-wide[model+'_rank'].min(axis=1)>1e-9).sum()),monotone_target_probability_fraction=float((wide[model].target10+1e-9>=wide[model].base7500).mul(wide[model].base7500+1e-9>=wide[model].target30).mean())))
    pd.DataFrame(changes).to_csv(OUT/'goal_target_rank_changes.csv',index=False)
    if OUT.name=='monotone_round':
        assert all(c['monotone_target_probability_fraction']>=1-1e-12 for c in changes)
    calibrators=[]
    for f in sorted(OUT.glob('goal_*_calibrator.json')):
        c=json.loads(f.read_text());calibrators.append(dict(file=f.name,slope=c['coefficient'][0][0],intercept=c['intercept'][0]))
    pd.DataFrame(calibrators).to_csv(OUT/'calibrator_slope_audit.csv',index=False)
    if OUT.name=='monotone_round':assert min(c['slope'] for c in calibrators)>=0
    train=pd.read_csv(OUT/'goal_training_audit.csv');assert len(train)==30
    for row in train.itertuples():
        assert row.max_training_endpoint<f'{row.year-2}-01-01'
        assert row.max_calibration_endpoint<f'{row.year}-01-01'
    donor=pd.read_csv(OUT/'analog_maturity_audit.csv')
    for row in donor.itertuples():assert row.max_library_endpoint<f'{row.year}-01-01'
    examples=pd.read_csv(OUT/'current_analog_examples.csv');assert examples.outcome_endpoint.lt('2026-10-03').all();assert examples.query_isin.ne(examples.neighbor_isin).all()
    # Independently replay serialized annual classifier and calibrator on stored input.
    import lightgbm as lgb
    from scipy.special import logit,expit
    panel=r.valid(pd.read_pickle(OUT/'panel.pkl.gz',compression='gzip'))
    test=panel[panel.decision_date.str.startswith('2025')].head(500).copy()
    model=lgb.Booster(model_file=str(OUT/'goal_base_2025.txt'));cal=json.loads((OUT/'goal_base_2025_calibrator.json').read_text())
    raw=np.clip(model.predict(test[r.old.COLS],num_threads=3),1e-6,1-1e-6)
    replay=expit(logit(raw)*cal['coefficient'][0][0]+cal['intercept'][0])
    saved=pd.read_csv(OUT/'goal_base_2025.csv.gz').set_index(r.KEYS)['goal_base'];actual=saved.reindex(pd.MultiIndex.from_frame(test[r.KEYS])).to_numpy()
    error=float(np.max(np.abs(actual-replay)));assert error<1e-12,error
    r.save('verification.json',dict(annual_models=30,strict_training_and_calibration_maturity=True,analog_maturity=True,example_self_matches=0,classifier_replay_rows=len(test),classifier_replay_max_abs_error=error,application_changed=False,fresh_holdout=False))
    inputs=[r.old.OUT/'prepared.pkl.gz',r.old.OUT/'price_features.pkl.gz',r.ROOT/'experiments/champion-high-recency-20261017/historical_adjustments.csv.gz',r.ROOT/'experiments/champion-recency-complements-20261017/historical_adjustments.csv.gz',r.ROOT/'experiments/champion-sip-profit-20261017/historical_scores.csv.gz']
    inputs += [folder/f'predictions_{year}.csv.gz' for folder in [r.old.OUT,r.old.OLD] for year in range(2020,2026)]
    def digest(p):
        h=hashlib.sha256()
        with p.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
        return h.hexdigest()
    r.save('input_manifest.json',{p.relative_to(r.ROOT).as_posix():digest(p) for p in inputs})
    sources=[*Path(r.ROOT/'research/runners').glob('*ten_hypotheses*20261031.py'),r.ROOT/'tests/test_ten_hypotheses_20261031.py']
    receipts=[p for p in OUT.iterdir() if p.suffix in ['.json','.csv'] and p.stat().st_size<5_000_000]
    r.save('compact_manifest.json',{p.relative_to(r.ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources+receipts if p.name!='compact_manifest.json'})
    print('REVIEW VERIFIED',error,flush=True)

if __name__=='__main__':run()
