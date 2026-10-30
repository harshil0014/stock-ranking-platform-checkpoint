"""Descriptive date-block sensitivity; no adjustment for adaptive selection."""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
METRICS=['xirr','drawdown','achievement','shortfall','ndcg','rank_ic']


def block_indices(n, length, replicates, rng):
    starts=rng.integers(0,n,size=(replicates,(n+length-1)//length))
    return ((starts[:,:,None]+np.arange(length))%n).reshape(replicates,-1)[:,:n]


def main(kind):
    folder={'execution':'sector-execution-specialist-20261011','specialist':'sector-specialist-ensemble-20261011','neural':'sector-tabm-continuation-20261011'}[kind]
    out=ROOT/'experiments'/folder
    q=pd.read_csv(out/'finalist_queries.csv.gz')
    q=q[q.top_n.eq(3)]
    keys=['period','date','profile','sector','scope','return_treatment']
    base=q[q.model.eq('current_champion')].set_index(keys)[METRICS]
    assert base.index.is_unique
    rng=np.random.default_rng(20261011)
    rows=[];annual=[]
    for name,g in q[q.model.ne('current_champion')].groupby('model'):
        cand=g.set_index(keys)[METRICS]
        assert cand.index.is_unique and cand.index.difference(base.index).empty
        diff=cand-base.reindex(cand.index)
        diff.shortfall=-diff.shortfall
        diff=diff.reset_index()
        # Equal sector within profile/date, then equal profiles, then equal dates.
        dated=diff.groupby(['period','scope','return_treatment','date','profile'])[METRICS].mean().groupby(['period','scope','return_treatment','date']).mean().reset_index()
        for (period,scope,treatment),d in dated.groupby(['period','scope','return_treatment']):
            d=d.sort_values('date');values=d[METRICS].to_numpy();n=len(d)
            gaps=pd.to_datetime(d.date).diff().dt.days.dropna()
            for length in [2,4,8]:
                samples=values[block_indices(n,length,2000,rng)].mean(axis=1)
                for j,metric in enumerate(METRICS):
                    rows.append(dict(model=name,period=period,scope=scope,return_treatment=treatment,metric=metric,dates=n,block_dates=length,median_date_gap_days=float(gaps.median()),date_balanced_delta=float(values[:,j].mean()),lower95=float(np.quantile(samples[:,j],.025)),upper95=float(np.quantile(samples[:,j],.975)),bootstrap_fraction_positive=float(np.mean(samples[:,j]>0))))
            d['year']=d.date.str[:4]
            for year in sorted(d.year.unique()):
                remaining=d[d.year.ne(year)]
                if remaining.empty:
                    continue
                for metric in METRICS:
                    annual.append(dict(model=name,period=period,scope=scope,return_treatment=treatment,omitted_year=year,metric=metric,remaining_date_balanced_delta=float(remaining[metric].mean())))
    pd.DataFrame(rows).to_csv(out/'descriptive_date_block_bootstrap.csv',index=False)
    pd.DataFrame(annual).to_csv(out/'leave_one_year_out_differences.csv',index=False)
    protocol=dict(top_n=3,blocks_in_ordered_decision_dates=[2,4,8],replicates=2000,seed=20261011,
        aggregation='Pair candidate and champion on identical queries; equal sectors within profile/date, equal profiles within date, equal dates. This date-balanced diagnostic can differ from the primary sector-balanced summary.',
        interpretation='Circular moving-block resampling keeps every sector/profile on the same sampled date and groups adjacent dates. Report all block lengths, actual date gaps and leave-one-year-out estimates. Few periods and overlapping outcome windows limit inference. Intervals are descriptive, not post-selection-valid significance tests; no PBO or fresh-validation claim.',
        selection_changed=False,source='https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf')
    (out/'date_block_protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    print('DATE BLOCK AUDIT',kind,len(rows),'intervals',len(annual),'omitted-year comparisons',flush=True)


if __name__=='__main__':
    main(sys.argv[1])
