"""Freeze the closest guarded challenger; export base7500, without promotion."""
import json,hashlib
import numpy as np
import pandas as pd
import lightgbm as lgb
import profile_aware_sector_20261008 as p

OUT=p.ROOT/'experiments/action-guarded-sector-20261008'
AS_OF='2026-10-03'

def run():
    trials=pd.read_csv(OUT/'trials.csv').sort_values(['strict_gate','top3_regressing_cells','regressing_cells'],ascending=[False,True,True])
    chosen=trials.iloc[0];name,weight=chosen.model.split('_blend');weight=float(weight)
    config=next(c for c in p.CONFIGS if c['name']==name)
    t=pd.read_pickle(OUT/'prepared.pkl.gz',compression='gzip')
    t=t[t.endpoint.lt(AS_OF)].dropna(subset=['future_xirr','future_drawdown','future_shortfall'])
    t=t[t.sector.ne('Unclassified')];t=t[t.groupby(['decision_date','profile_name','sector'])['isin'].transform('size').ge(5)]
    t=t.sort_values(['decision_date','profile_name','sector','isin']);g=t.groupby(['decision_date','profile_name','sector'],sort=False)
    r=g.future_xirr.rank(pct=True);d=g.future_drawdown.rank(pct=True);s=g.future_shortfall.rank(pct=True,ascending=False)
    y=.5*r+.25*d+.25*s if config['target']=='balanced' else .25*r+.5*d+.25*s
    w=1/g['isin'].transform('size');w=w/w.mean()
    model=lgb.LGBMRanker(objective='rank_xendcg',n_estimators=120,num_leaves=config['leaves'],max_depth=5,min_child_samples=200,reg_lambda=30,learning_rate=.035,label_gain=list(range(10)),n_jobs=3,random_state=20261008,deterministic=True,force_col_wise=True,verbosity=-1)
    model.fit(t[p.COLS],np.floor(y*9).astype(int),group=g.size().to_numpy(),sample_weight=w)
    path=OUT/'current_guarded_ranker.txt';model.booster_.save_model(str(path))
    importance=pd.DataFrame({'feature':model.booster_.feature_name(),'split_gain':model.booster_.feature_importance(importance_type='gain'),'split_count':model.booster_.feature_importance(importance_type='split')}).sort_values('split_gain',ascending=False)
    importance['gain_fraction']=importance.split_gain/importance.split_gain.sum()
    importance.to_csv(OUT/'current_feature_importance.csv',index=False)
    current=pd.read_csv(p.NEW/'current_all_stock_rankings.csv')
    profile=json.loads((p.ROOT/'research/protocols/personalized_official_action_tournament_v1.json').read_text())['profiles']['base7500']
    current[p.PARAMS]=[np.log(profile['amount']),profile['lookback_months'],np.log(profile['interval_days']),profile['target_cagr']]
    matrix=current[p.COLS].astype('float32')
    def score(m):
        pred=pd.Series(m.predict(matrix),index=current.index)
        pure=pred.groupby([current.decision_date,current.sector]).rank(pct=True).where(current.evidence_fraction.gt(0),.5)
        blend=((1-weight)*current.open_model_score+weight*pure).where(current.evidence_fraction.gt(0),.5)
        return pure,blend
    pure,blend=score(model)
    pure_replay,blend_replay=score(lgb.Booster(model_file=str(path)))
    np.testing.assert_allclose(pure,pure_replay,atol=0,rtol=0)
    np.testing.assert_allclose(blend,blend_replay,atol=0,rtol=0)
    assert len(current)==4436 and current['isin'].is_unique and np.isfinite(blend).all()
    current['guarded_model_score']=blend;current['guarded_pure_score']=pure
    current['guarded_sector_rank']=blend.groupby(current.sector).rank(method='min',ascending=False)
    current['validation_status']='RESEARCH_ONLY_NOT_APPROVED'
    current['profile_name']='base7500';current['guarded_model']=chosen.model
    current.sort_values(['sector','guarded_sector_rank','isin']).to_csv(OUT/'current_all_stock_rankings.csv',index=False)
    decision={'name':chosen.model,'status':'RESEARCH_ONLY_NOT_APPROVED','selection_rule':'Fewest Top3 regressions, then fewest full-panel regressions; adaptive selection.',
      'weight':weight,'as_of':AS_OF,'current_profile':'base7500','stocks':4436,'training_profiles':int(t.profile_name.nunique()),
      'training_rows':len(t),'max_training_endpoint':t.endpoint.max(),'training_outcome_guard':True,
      'top3_regressing_cells':int(chosen.top3_regressing_cells),'top3_comparisons':int(chosen.top3_cells),
      'all_regressing_cells':int(chosen.regressing_cells),'all_comparisons':int(chosen.total_cells),
      'saved_model_inference_reproduced_exactly':True,'production_replaced':False,'fresh_validation':False,
      'limits':'Input history not fully repaired; anchor trained on original labels; current export is base7500 only. Missing price evidence receives a neutral prior.',
      'neutral_no_price_stocks':int(current.evidence_fraction.eq(0).sum())}
    decision['sha256']={str(f.relative_to(p.ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [path,OUT/'current_all_stock_rankings.csv',p.NEW/'current_all_stock_rankings.csv',OUT/'trials.csv']}
    (OUT/'current_selection.json').write_text(json.dumps(decision,indent=2))
    print(json.dumps({k:v for k,v in decision.items() if k!='sha256'},indent=2),flush=True)

if __name__=='__main__':run()
