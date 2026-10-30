"""Persist frozen annual predictions for the all-legacy sector audit."""
import pickle,json,gc
import numpy as np
import pandas as pd
from full_coverage_open_models_20261008 import ROOT,OUT,PRIOR,activity
from full_coverage_challenger_20261008 import features,KEYS,RAW
from finalize_open_models_20261008 import score

def run():
    selected=json.loads((OUT/'selection.json').read_text())
    raw=pd.read_pickle(ROOT/'experiments/sector-championship-20261005/enhanced.pkl.gz',compression='gzip')
    retained=KEYS+['sector','period','sector_incumbent','future_xirr','future_drawdown','future_shortfall','baseline_formula_replay','current_score','professor_whole_share_score']
    raw=raw.loc[raw.decision_date.ge('2020-01-01'),retained+RAW].copy();gc.collect()
    frozen=pd.read_csv(PRIOR/'locked_all_profile_predictions.csv.gz',usecols=KEYS+['challenger']).rename(columns={'challenger':'frozen_challenger'})
    for profile,g in raw.groupby('profile_name'):
        path=OUT/f'locked_scores_{profile}.csv.gz'
        if path.exists():continue
        g=activity(features(g));g=g.merge(frozen,on=KEYS,validate='one_to_one');g['open_model']=np.nan
        for year in range(2020,2026):
            mask=g.decision_date.str.startswith(str(year));part=g.loc[mask];models=[]
            for c in selected['configs']:
                with (OUT/f'{c["name"]}_{year}.pkl').open('rb') as f:models.append(pickle.load(f))
            g.loc[mask,'open_model']=score(part,models,selected['weight'],part.frozen_challenger)
        assert np.isfinite(g.open_model).all()
        g[retained+['frozen_challenger','open_model']].to_csv(path,index=False)
        print('SAVED',profile,len(g),flush=True)

if __name__=='__main__':run()
