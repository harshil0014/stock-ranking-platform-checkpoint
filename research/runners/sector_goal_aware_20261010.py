"""Target the diagnosed achievement/large-contribution regression, with purged folds."""
import json
import numpy as np
import lightgbm as lgb
import sector_price_rebuild_20261010 as p
BASE=p.OUT

def fit(t,c):
    t=t.dropna(subset=['future_xirr','future_drawdown','future_shortfall'])
    t=t[t.evidence_fraction.gt(0)&t.sector.ne('Unclassified')]
    t=t[t.groupby(['decision_date','profile_name','sector'])['isin'].transform('size').ge(5)].sort_values(['decision_date','profile_name','sector','isin'])
    g=t.groupby(['decision_date','profile_name','sector'],sort=False)
    # All targets are matured training outcomes, never current-stock features.
    y=.5*t.future_shortfall.eq(0).astype(float)+.25*g.future_shortfall.rank(pct=True,ascending=False)+.125*g.future_xirr.rank(pct=True)+.125*g.future_drawdown.rank(pct=True)
    weights=1/g['isin'].transform('size');weights/=weights.mean()
    m=lgb.LGBMRegressor(objective='regression_l1',n_estimators=180,num_leaves=15,max_depth=5,min_child_samples=200,reg_lambda=30,learning_rate=.03,n_jobs=3,random_state=20261010,deterministic=True,force_col_wise=True,verbosity=-1)
    m.fit(t[p.COLS],y,sample_weight=weights);return m,t

def run():
    p.OUT=p.ROOT/'experiments/sector-goal-aware-20261010';p.OUT.mkdir(exist_ok=True)
    p.CONFIGS=[dict(name='goal_aware_l1',target='goal_aware',loss='regression_l1')];p.fit=fit
    (p.OUT/'protocol.json').write_text(json.dumps({'hypothesis':'Achievement and XIRR dominate remaining regressions, especially amount50000. Explicit goal-aware target; fixed one model and four blends.', 'target':'.5 achievement + .25 inverse-shortfall percentile + .125 return percentile + .125 drawdown percentile','selection':'Unchanged development-only regression-count criterion','features':'Same rebuilt70price/profilefeatures; no future information added','fresh_validation':False},indent=2))
    # Use the same immutable prepared input without duplicating it on disk.
    import os
    for name in ['prepared.pkl.gz','price_features.pkl.gz']:
        if not (p.OUT/name).exists():os.link(BASE/name,p.OUT/name)
    p.learn();p.evaluate()
    # Export reads the shared current feature receipt without rebuilding it.
    p.refresh_current=lambda:None
    p.export()
    print('GOAL COMPLETE',flush=True)

if __name__=='__main__':run()
