"""Hindsight feasibility diagnostic only; never used to train or choose a model."""
import json
import numpy as np
import pandas as pd
from sector_conservative_router_20261010 import p,BASE,ANCHOR
OUT=p.ROOT/'experiments/sector-targeted-round-20261010'

def run():
    OUT.mkdir(exist_ok=True)
    x=pd.concat([pd.read_csv(BASE/f'predictions_{year}.csv.gz',usecols=p.KEYS+['sector','period','future_xirr','future_drawdown','future_shortfall','sector_incumbent','open_model','frozen_challenger']) for year in range(2020,2026)],ignore_index=True)
    current=pd.read_csv(BASE/'selected_historical_scores.csv.gz').rename(columns={'replacement_score':ANCHOR})
    x=x.merge(current,on=p.KEYS,validate='one_to_one');rows=[]
    for scope in ['common','expanded']:
        z=x[x.sector_incumbent.notna()] if scope=='common' else x
        refs=['open_model','frozen_challenger',ANCHOR]+(['sector_incumbent'] if scope=='common' else [])
        z=z.dropna(subset=refs+['future_xirr','future_drawdown','future_shortfall']).sort_values('isin')
        for keys,g in z.groupby(['period','decision_date','profile_name','sector']):
            if keys[-1]=='Unclassified' or len(g)<5:continue
            choices=np.argmax(g[refs].to_numpy(),axis=0)
            outcomes=g[['future_xirr','future_drawdown','future_shortfall']].to_numpy();outcomes[:,2]*=-1
            # Componentwise best outcomes among stocks actually selected by references.
            requirement=outcomes[choices].max(axis=0)
            feasible=(outcomes>=requirement-1e-12).all(axis=1)
            rows.append(dict(scope=scope,period=keys[0],date=keys[1],profile=keys[2],sector=keys[3],stocks=len(g),feasible=bool(feasible.any())))
    q=pd.DataFrame(rows);q.to_csv(OUT/'oracle_top1_feasibility_queries.csv.gz',index=False)
    summary=q.groupby(['scope','period']).agg(queries=('feasible','size'),feasible_queries=('feasible','sum')).reset_index()
    summary['infeasible_queries']=summary.queries-summary.feasible_queries;summary['infeasible_fraction']=summary.infeasible_queries/summary.queries
    summary.to_csv(OUT/'oracle_top1_feasibility_summary.csv',index=False)
    (OUT/'oracle_scope.json').write_text(json.dumps({'role':'Hindsight feasibility only, never used for training or model selection','claim':'For an infeasible query no available stock can simultaneously match the best return, drawdown and shortfall among the stocks selected by reference models. This rules out per-query Top1 universal dominance on that cohort.','not_claimed':'Does not prove the aggregate promotion gate impossible. Does not address diversification, different horizons or trading execution. Outcome data limitations still apply.'},indent=2))
    print(summary.to_string(index=False),flush=True)

if __name__=='__main__':run()
