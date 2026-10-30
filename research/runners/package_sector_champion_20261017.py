"""Package user-approved dual_w0.01, without modifying research decisions."""
import hashlib,json,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
import lightgbm as lgb
import numpy as np
import pandas as pd
from stock_ranker.sector_champion_product import ChampionScorer
from stock_ranker.personalized_product import parse_profile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'research/runtime/sector-champion-recency'
def main():
    OUT.mkdir(exist_ok=True)
    original=ROOT/'experiments/champion-high-recency-20261017/current_all_4436_audit.csv'
    x=pd.read_csv(original).sort_values('isin').reset_index(drop=True)
    old=ROOT/'experiments/action-guarded-sector-20261008/current_all_stock_rankings.csv'
    legacy=pd.read_csv(old).set_index('isin').loc[x['isin']].reset_index()
    sources={'profile':ROOT/'experiments/action-guarded-sector-20261008/current_guarded_ranker.txt',
             'price':ROOT/'experiments/sector-price-rebuild-20261010/current_model.txt'}
    extra=['sector','evidence_fraction']
    for name,source in sources.items():
        shutil.copy2(source,OUT/f'{name}.txt')
        fields=lgb.Booster(model_file=str(source)).feature_name()
        frame=legacy if name=='profile' else x
        if name=='price':extra+=['open_model_score','observations','history_days','volume_active_fraction',
             'last_positive_volume_lag_days','days_since_52w_closing_high','days_since_recorded_high',
             'distance_from_52w_high','distance_from_recorded_high','momentum12_1']
        frame[list(dict.fromkeys(['isin']+extra+fields))].to_csv(OUT/f'{name}_inputs.csv.gz',index=False)
    manifest={'model_id':'sector_champion_recency_20261017','as_of_date':'2026-10-03',
      'chosen_by':'Explicit user direction: retain extra days-since-high weighting despite slight degradation',
      'formula':'0.75*(0.8*open_model+0.2*profile_defensive_15)+0.25*rank_xendcg_balanced+0.01*(0.60*dual_recency+0.25*dual_proximity+0.15*momentum-0.5)',
      'fresh_validation':False,'automated_research_gate_passed':False,
      'profile_affects_ranking':False,
      'profile_behavior':'Parameters are passed through; frozen rankers learned zero parameter splits. User fields change execution/goal calculations, not stock order.',
      'rollback':'Original champion score is included per row; previous website modes and research artifacts retained.',
      'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [original,old,*sources.values()]},
      'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.name in ['profile.txt','price.txt','profile_inputs.csv.gz','price_inputs.csv.gz']}}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    p=parse_profile(dict(amount=7500,lookback_months=36,interval_days=30,target_cagr_percent=20,horizon_months=12))
    scored=ChampionScorer().score(p)
    np.testing.assert_allclose(scored.original_champion_score,x.current_champion,atol=1e-12,rtol=0)
    np.testing.assert_allclose(scored.personalized_score,x['dual_w0.01'],atol=1e-12,rtol=0)
    np.testing.assert_array_equal(scored.personalized_sector_rank,x.patch_sector_rank)
    (OUT/'verification.json').write_text(json.dumps({'stocks':len(x),'base_profile_score_max_error':float((scored.personalized_score-x['dual_w0.01']).abs().max()),'sector_ranks_exact':True},indent=2))
    print((OUT/'verification.json').read_text())

if __name__=='__main__':main()
