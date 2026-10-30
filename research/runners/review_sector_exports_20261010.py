"""Transparent all-stock review flags; no unvalidated ranking overrides."""
import argparse,json
import numpy as np
import pandas as pd
from sector_price_rebuild_20261010 import ROOT

def run(family):
    folder=ROOT/'experiments'/({'rebuilt':'sector-price-rebuild','yeti':'sector-yetirank','accuracy':'sector-accuracy'}[family]+'-20261010')
    x=pd.read_csv(folder/'current_all_stock_rankings.csv');rank={'rebuilt':'rebuilt_sector_rank','yeti':'yeti_sector_rank','accuracy':'accuracy_sector_rank'}[family]
    sizes=x.groupby('sector')['isin'].transform('size')
    flags={
      'NO_USABLE_REBUILT_INPUT':x.evidence_fraction.eq(0),
      'SHORT_PRICE_HISTORY':x.evidence_fraction.gt(0)&x.observations.lt(252),
      'SMALL_SECTOR_NOT_BENCHMARKED':sizes.lt(5),
      'UNCLASSIFIED_NOT_BENCHMARKED':x.sector.eq('Unclassified'),
      'MORE_THAN_HALF_ZERO_PRICE_CHANGES':x.zero_fraction.gt(.5),
      'ONE_DAY_DOMINATES_PRICE_PATH':x.largest_jump_share.gt(.2),
      'DRAWDOWN_BELOW_MINUS_50_PERCENT':x.drawdown252.lt(-.5),
      'NEAR_RECENT_ROLLING_HIGH':x.high_gap252.ge(-.05)&x.high_age252.le(21/252),
      'OLD_RECORDED_HIGH_ANCHOR_ONLY':x.days_since_recorded_high.gt(1095),
    }
    x['review_flags']=[';'.join(k for k,v in flags.items() if bool(v.iloc[i])) for i in range(len(x))]
    x['sector_size']=sizes;x['current_rank']=x[rank]
    columns=['isin','ticker','company','sector','sector_size','current_rank','input_status','rebuilt_input_confidence','observations','last_price_date','high_gap252','high_age252','days_since_recorded_high','drawdown252','zero_fraction','largest_jump_share','review_flags']
    x[columns].to_csv(folder/'all_stock_structural_review.csv',index=False)
    leaders=x[x.current_rank.le(3)].copy();leaders[columns].to_csv(folder/'sector_leader_structural_review.csv',index=False)
    counts={k:{'all_stocks':int(v.sum()),'sector_top3':int(v[x.current_rank.le(3)].sum())} for k,v in flags.items()}
    doc={'stocks':len(x),'sectors_including_unclassified':x.sector.nunique(),'top3_rows_including_ties':len(leaders),'flags':counts,
      'interpretation':'Diagnostic thresholds, not trained penalties or proof of a bad stock. Recent rolling highs are positive context. Recorded ATH age is inherited anchor evidence and is not certified by this price rebuild. No automatic rank changes applied.',
      'human_review_scope':'All stocks receive structural checks. Existing company rubric is separate; this is not 4436 new company due-diligence investigations.'}
    (folder/'structural_review.json').write_text(json.dumps(doc,indent=2));print(json.dumps(doc,indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--family',choices=['rebuilt','yeti','accuracy'],default='rebuilt');run(a.parse_args().family)
