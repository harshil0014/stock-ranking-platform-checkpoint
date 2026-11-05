"""Post-result cost sensitivity on frozen selections, without reselection."""
import os
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
    os.environ[key]='1'
from pathlib import Path
import json,pickle
import numpy as np
import pandas as pd
from stock_research.next_open_portfolio import next_open_portfolio
from residual_challengers_20261105 import evaluator
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/constrained-ranking-20261105'
WORK=ROOT/'work/constrained-ranking-20261105'


def main():
    (OUT/'cost_stress_registration.json').write_text(json.dumps(dict(timing='After primary results, before stress outcomes',cost_per_side_bps=200,selection='Frozen original scores; no retraining, reselection or adoption-rule change',scope='Descriptive sensitivity only'),indent=2),encoding='utf-8')
    ledger=ROOT/'research/research_variant_ledger.csv';registry=pd.read_csv(ledger)
    key='constrained_ranking_20261105::cost200_diagnostic'
    if key not in set(registry.id):
        registry=pd.concat([registry,pd.DataFrame([dict(id=key,family='constrained_ranking_20261105',name='cost200_diagnostic',source='experiments/constrained-ranking-20261105/cost_stress_registration.json',category='diagnostic_or_policy_attempt')])],ignore_index=True)
        registry.to_csv(ledger,index=False)
    x=pd.read_pickle(WORK/'development_scored.pkl.gz',compression='gzip')
    with (ROOT/'work/new-information-20261101/actual_adjusted_open_close.pkl').open('rb') as f:paths=pickle.load(f)
    actions=pd.read_csv(ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv');actions=actions[actions.status.ne('ALIGNED_MULTIPLIER')]
    helper=evaluator();rows=[];fail=[]
    for date,g in x.groupby('decision_date'):
        end=str((pd.Timestamp(date)+pd.DateOffset(months=12)).date())
        blocked=set(actions.loc[actions.event_date.gt(date)&actions.event_date.le(end),'isin'])
        for name in ['champion','constrained_residual','constrained_high']:
            selected=g.sort_values([name,'isin'],ascending=[False,True]).head(20)['isin'].tolist()
            try:
                if set(selected)&blocked:raise ValueError('Unresolved action')
                r=next_open_portfolio([helper.scope_path(paths[i],date,end) for i in selected],np.full(len(selected),1/len(selected)),date,end,7500,30,200)
                rows.append(dict(decision_date=date,model=name,xirr=r['xirr'],drawdown=r['tw_max_drawdown']))
            except (KeyError,ValueError) as e:fail.append(dict(decision_date=date,model=name,reason=str(e)))
    frame=pd.DataFrame(rows);frame.to_csv(OUT/'cost200_portfolios.csv',index=False)
    pd.DataFrame(fail).to_csv(OUT/'cost200_failures.csv',index=False)
    pairs=[]
    for name in ['constrained_residual','constrained_high']:
        a=frame[frame.model.eq(name)].merge(frame[frame.model.eq('champion')],on='decision_date',suffixes=('_new','_old'))
        pairs.append(dict(model=name,matched_dates=len(a),xirr_delta=(a.xirr_new-a.xirr_old).mean(),drawdown_delta=(a.drawdown_new-a.drawdown_old).mean()))
    pd.DataFrame(pairs).to_csv(OUT/'cost200_pairs.csv',index=False)
    print(pd.DataFrame(pairs).to_string(index=False),flush=True)


if __name__=='__main__':main()
