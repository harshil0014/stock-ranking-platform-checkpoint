"""Build a hash-sealed October3global selection with the approved fixed policy."""
import os
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
    os.environ[key]='1'
from pathlib import Path
import json,pickle,hashlib
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from stock_research.residual_history import weekly_prices,residual_features
from stock_research.constrained_selection import select_three
from champion_rank_correction_20261105 import FEATURES
from residual_challengers_20261105 import Q
ROOT=Path(__file__).resolve().parents[2]
DEST=ROOT/'research/runtime/global-rank-correction-20261106'


def main():
    DEST.mkdir(exist_ok=True)
    files=list((ROOT/'work/champion-rank-correction-20261105').glob('features_*.pkl.gz'))
    files+=[ROOT/'work/novel-champion-20261105/development_scored.pkl.gz',ROOT/'work/champion-open-search-20261105/transfer_scored.pkl.gz']
    allrows=pd.concat([pd.read_pickle(p,compression='gzip') for p in files],ignore_index=True)
    train=allrows[allrows.new_endpoint.lt('2026-01-01')&allrows.new_xirr.notna()].copy()
    train=train[train.groupby(['decision_date','sector'])['isin'].transform('size').ge(5)].copy()
    target=train.groupby(['decision_date','sector']).new_xirr.rank(pct=True)-train.champion
    weight=1/train.groupby(['decision_date','sector'])['isin'].transform('size').to_numpy(copy=True);weight/=weight.mean()
    model=LGBMRegressor(objective='regression',n_estimators=80,learning_rate=.03,num_leaves=7,max_depth=3,min_child_samples=100,reg_lambda=30,random_state=20261105,n_jobs=1,deterministic=True,force_col_wise=True,verbosity=-1)
    model.fit(train[FEATURES],target,sample_weight=weight)
    model.booster_.save_model(str(DEST/'model.txt'))
    source=ROOT/'experiments/professor-weight-curve-20261031/scored.pkl.gz'
    x=pd.read_pickle(source,compression='gzip');date=x.decision_date.max()
    x=x[x.decision_date.eq(date)&x.factor_eligible].copy().sort_values('isin')
    prices=pd.read_pickle(ROOT/'experiments/sector-price-rebuild-20261010/price_features.pkl.gz',compression='gzip')
    pricecols=['isin','decision_date','downside252','volatility252','return21']
    x=x.merge(prices[pricecols],on=['isin','decision_date'],validate='one_to_one')
    with (ROOT/'work/new-information-20261101/actual_adjusted_open_close.pkl').open('rb') as f:paths=pickle.load(f)
    quotes=np.column_stack([weekly_prices(paths[i],date) if i in paths else np.full(157,np.nan) for i in x['isin']])
    x[['residual_momentum','residual_high']]=residual_features(np.diff(np.log(quotes),axis=0),x.sector)
    x=x[np.isfinite(x[Q+['residual_momentum','residual_high','downside252','volatility252','return21']]).all(axis=1)].copy()
    x=x[x.groupby('sector')['isin'].transform('size').ge(5)].copy()
    x['champion']=x.champion_score
    for col in Q+['champion','residual_momentum','residual_high']:x[col]=x.groupby('sector')[col].rank(pct=True)
    x['correction']=model.predict(x[FEATURES]);x['raw_correction_score']=x.champion+.25*x.correction
    checks=[]
    for sector,g in x.groupby('sector'):
        g=g.sort_values('isin');champ=g.sort_values(['champion','isin'],ascending=[False,True]).head(3)
        score,r=select_three(g.raw_correction_score.to_numpy(),g[Q].to_numpy(),g.index.get_indexer(champ.index))
        x.loc[g.index,'global_champion_score']=score
        selected=g.iloc[np.argsort(-score)[:3]]
        assert (selected[Q].sum().to_numpy()-champ[Q].sum().to_numpy()>=-1e-7).all()
        checks.append(dict(sector=sector,optimal=r['optimal'],changed=set(selected['isin'])!=set(champ['isin'])))
    identities=pd.read_csv(ROOT/'experiments/champion-double-emphasis-20261017/current_all_4436_audit.csv')[['isin','ticker','company']]
    x=x.merge(identities,on='isin',validate='one_to_one',suffixes=('','_identity'))
    x=x.sort_values(['global_champion_score','isin'],ascending=[False,True]);x['global_champion_rank']=np.arange(1,len(x)+1)
    columns=['isin','ticker','company','sector','decision_date','global_champion_rank','global_champion_score','champion','correction']
    x[columns].to_csv(DEST/'ranking.csv',index=False)
    # Verify frozen input champion scores match the actual production scorer.
    from stock_ranker.sector_champion_product import ChampionScorer
    from stock_ranker.personalized_product import parse_profile
    scorer=ChampionScorer();profile=parse_profile(dict(amount=7500,lookback_months=36,interval_days=30,target_cagr_percent=20,horizon_months=12))
    actual=scorer.score(profile)
    actual=scorer.add_sip(actual,profile,scorer.sip_profiles[scorer.sip_profiles.profile_name.eq('base7500')])
    check=x[['isin','champion_score']].merge(actual[['isin','personalized_score']],on='isin',validate='one_to_one')
    error=float((check.champion_score-check.personalized_score).abs().max())
    assert error<1e-10,f'Current champion parity failed: {error}'
    manifest=dict(model_id='global_rank_correction_20261106',model_name='Global Top-20 Champion',candidate='error_corrected_professor',
        as_of_date=date,eligible_stocks=len(x),sectors=x.sector.nunique(),base_profile=dict(amount=7500,lookback_months=36,interval_days=30,target_cagr_percent=20,horizon_months=12),
        last_training_label_endpoint=train.new_endpoint.max(),training_rows=len(train),current_champion_parity_error=error,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        files={n:hashlib.sha256((DEST/n).read_bytes()).hexdigest() for n in ['ranking.csv','model.txt']},
        scope='Global selection across eligible sector-ranked stocks; sector ranks remain supplied by sector champion',
        evidence='Adaptive development and previously exposed later-period comparison; not fresh validation',
        missing_history_policy='Excluded from global selection, sector champion rank remains available',fresh_daily_inputs=False,
        user_authorized_promotion=True,solver_queries=len(checks),solver_fallbacks=sum(not r['optimal'] for r in checks))
    (DEST/'manifest.json').write_text(json.dumps(manifest,indent=2,default=lambda v:v.item() if hasattr(v,'item') else str(v)),encoding='utf-8')
    print(json.dumps(manifest,default=str),flush=True)


if __name__=='__main__':main()
