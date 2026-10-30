"""Score a sector universe with the frozen full-coverage challenger, without training.

Required input columns: isin, sector, decision_date. Price fields from RAW are
optional but missing evidence is disclosed. A frozen champion score may be supplied
as sector_incumbent. Scores depend on the supplied peer universe. No order execution.
"""
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
from full_coverage_challenger_20261008 import OUT,RAW,features,predictors,selected_score,needed_models


def score_frame(frame,package=OUT):
    x=frame.copy()
    if not {'isin','sector','decision_date'}.issubset(x):raise ValueError('isin, sector and decision_date required')
    if x['isin'].isna().any() or x.decision_date.isna().any() or x.duplicated(['isin','decision_date']).any():raise ValueError('Missing/duplicate identity or date')
    pd.to_datetime(x.decision_date,errors='raise')
    training=json.loads((package/'current_training.json').read_text())
    if x.decision_date.min()<training['as_of']:raise ValueError('Frozen current model cannot score dates before its training snapshot')
    for col in RAW+['sector_incumbent','volume_active_fraction','observations_1y']:
        if col not in x:x[col]=np.nan
    x=features(x)
    name=json.loads((package/'active_selection.json').read_text())['selected']['name']
    for source in needed_models(name):
        model=lgb.Booster(model_file=str(package/f'selected_{source}.txt'))
        pred=pd.Series(model.predict(x[predictors()],num_threads=3),index=x.index)
        x[source]=pred.groupby([x.decision_date,x.sector]).rank(pct=True).where(x.evidence_fraction.gt(0),.5)
    x['challenger_score']=selected_score(x,name).where(x.evidence_fraction.gt(0),.5)
    x['challenger_sector_rank']=x.challenger_score.groupby([x.decision_date,x.sector]).rank(ascending=False,method='min')
    x['evidence_confidence']=np.select([x.evidence_fraction.eq(0),x.evidence_fraction.lt(.5),x.evidence_fraction.lt(.85)],['NO_PRICE_EVIDENCE','LOW','PARTIAL'],default='HIGH')
    x['rank_scope']=np.where(x.sector.eq('Unclassified'),'UNCLASSIFIED_POOL_NOT_A_SECTOR','WITHIN_SECTOR')
    assert np.isfinite(x.challenger_score).all()
    return x


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--package',type=Path,default=OUT);args=p.parse_args()
    if args.input.resolve()==args.output.resolve():raise ValueError('Use a separate output path')
    x=score_frame(pd.read_csv(args.input),args.package)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    x.to_csv(args.output,index=False)
    print(json.dumps({'stocks':len(x),'finite_scores':int(x.challenger_score.notna().sum()),'output':str(args.output)}))


if __name__=='__main__':main()
