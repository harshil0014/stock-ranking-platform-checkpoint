"""ICML2023-style NDCG mode on rebuilt sector features; separate research arm."""
import sys,json,shutil
from pathlib import Path
import numpy as np
import pandas as pd
import sector_price_rebuild_20261010 as p
sys.path.insert(0,str(p.ROOT/'experiments/model_dependencies_20261008'))
from catboost import CatBoostRanker,Pool
BASE=p.OUT
OUT=p.ROOT/'experiments/sector-yetirank-20261010'
CONFIGS=[dict(name=f'yeti_ndcg3_{target}',target=target) for target in ['return','balanced']]

def fit(train,c):
    t=train.dropna(subset=['future_xirr','future_drawdown','future_shortfall'])
    t=t[t.evidence_fraction.gt(0)&t.sector.ne('Unclassified')]
    t=t[t.groupby(['decision_date','profile_name','sector'])['isin'].transform('size').ge(5)].sort_values(['decision_date','profile_name','sector','isin'])
    g=t.groupby(['decision_date','profile_name','sector'],sort=False)
    r=g.future_xirr.rank(pct=True);d=g.future_drawdown.rank(pct=True);s=g.future_shortfall.rank(pct=True,ascending=False)
    y=r if c['target']=='return' else .5*r+.25*d+.25*s
    weights=1/g['isin'].transform('size');weights=weights/weights.mean()
    pool=Pool(t[p.COLS],label=y,group_id=g.ngroup().to_numpy(),group_weight=weights.to_numpy())
    m=CatBoostRanker(loss_function='YetiRank:mode=NDCG;top=3',iterations=120,depth=5,learning_rate=.04,l2_leaf_reg=30,thread_count=2,random_seed=20261010,allow_writing_files=False,verbose=False)
    m.fit(pool);return m,t

def run():
    OUT.mkdir(exist_ok=True)
    protocol={'configs':CONFIGS,'source_features':str(BASE.relative_to(p.ROOT)),'loss':'YetiRank:mode=NDCG;top=3','iterations':120,'depth':5,'weights':'1/query size, constant within each query','selection':'Same development-only regression-count criterion; all dates previously exposed.','sources':['https://proceedings.mlr.press/v202/lyzhin23a.html','https://catboost.ai/docs/en/concepts/loss-functions-ranking?lang=en'],'guard':'Same rebuilt inputs, feature masks, outcome masks, endpoint purging and four reference models as the main experiment.'}
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2))
    x=pd.read_pickle(BASE/'prepared.pkl.gz',compression='gzip');audit=[]
    for year in range(2020,2026):
        path=OUT/f'predictions_{year}.csv.gz'
        if path.exists():continue
        test=x[x.decision_date.str.startswith(str(year))].copy()
        for c in CONFIGS:
            m,t=fit(x[x.endpoint.lt(f'{year}-01-01')],c);test[c['name']]=p.rank_prediction(m,test)
            m.save_model(str(OUT/f'{c["name"]}_{year}.cbm'))
            audit.append(dict(year=year,model=c['name'],training_rows=len(t),max_training_endpoint=t.endpoint.max(),profiles=t.profile_name.nunique()))
            print('YETI FIT',year,c['name'],flush=True)
        test[p.KEYS+['sector','period','endpoint','future_xirr','future_drawdown','future_shortfall','sector_incumbent','open_model','frozen_challenger','evidence_fraction']+[c['name'] for c in CONFIGS]].to_csv(path,index=False)
        old=pd.read_csv(OUT/'training_audit.csv') if (OUT/'training_audit.csv').exists() else pd.DataFrame()
        pd.concat([old,pd.DataFrame(audit)]).drop_duplicates(['year','model'],keep='last').to_csv(OUT/'training_audit.csv',index=False)
    p.OUT=OUT;p.CONFIGS=CONFIGS;p.evaluate()
    selected=json.loads((OUT/'selection.json').read_text());name,w=selected['model'].split('_blend');w=float(w)
    c=next(c for c in CONFIGS if c['name']==name);m,t=fit(x[x.endpoint.lt(p.ASOF)],c);m.save_model(str(OUT/'current_model.cbm'))
    current=pd.read_csv(p.OLD/'current_all_stock_rankings.csv');f=pd.read_pickle(BASE/'price_features.pkl.gz',compression='gzip');f=f[f.decision_date.eq(p.ASOF)]
    z=current.drop(columns=[c for c in p.COLS if c in current and c not in p.PARAMS]+['input_status','last_price_date'],errors='ignore').merge(f.drop(columns='sector'),on=['isin','decision_date'],validate='one_to_one')
    z[p.COLS]=z[p.COLS].astype('float32');pure=p.rank_prediction(m,z);replay=CatBoostRanker();replay.load_model(str(OUT/'current_model.cbm'))
    np.testing.assert_allclose(pure,p.rank_prediction(replay,z),atol=0,rtol=0)
    z['yeti_score']=(1-w)*z.guarded_model_score+w*pure;z['yeti_pure_score']=pure
    z['yeti_sector_rank']=z.yeti_score.groupby(z.sector).rank(method='min',ascending=False)
    z=z.rename(columns={'evidence_confidence':'anchor_evidence_confidence'});z['rebuilt_input_confidence']=np.where(z.evidence_fraction.gt(0),'USABLE_PRICE_FEATURES',z.input_status)
    assert len(z)==4436 and np.isfinite(z.yeti_score).all()
    z.to_csv(OUT/'current_all_stock_rankings.csv',index=False)
    selected.update(current_rows=len(z),max_training_endpoint=t.endpoint.max(),current_replay_exact=True,input_usable=int(z.evidence_fraction.gt(0).sum()))
    (OUT/'selection.json').write_text(json.dumps(selected,indent=2));print('YETI COMPLETE',json.dumps(selected),flush=True)

if __name__=='__main__':run()
