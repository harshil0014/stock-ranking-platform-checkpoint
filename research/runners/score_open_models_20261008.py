"""Reproduce the frozen open-model research candidate without retraining."""
import argparse,json,pickle
import pandas as pd
import numpy as np
from full_coverage_open_models_20261008 import OUT,COLS
from finalize_open_models_20261008 import score
from score_full_coverage_20261008 import score_frame

def run():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    from pathlib import Path
    if Path(args.input).resolve()==Path(args.output).resolve():raise ValueError('Use a separate output path')
    selected=json.loads((OUT/'selection.json').read_text())
    x=score_frame(pd.read_csv(args.input),OUT/'frozen_anchor')
    models=[]
    for c in selected['configs']:
        with (OUT/f'current_{c["name"]}.pkl').open('rb') as f:models.append(pickle.load(f))
    x['open_model_score']=score(x,models,selected['weight'],x.challenger_score)
    x['open_model_sector_rank']=x.open_model_score.groupby([x.decision_date,x.sector]).rank(ascending=False,method='min')
    assert np.isfinite(x.open_model_score).all()
    x.to_csv(args.output,index=False)
    print('Scored',len(x),'stocks; research model:',selected['name'])

if __name__=='__main__':run()
