"""Batched NumPy evaluator; same cohorts, ties and metrics as the reference."""
import numpy as np
import pandas as pd

def evaluate(x,columns,top_ns=(3,)):
    rows=[];names=['sector_incumbent']+columns
    for (day,sector),g in x.sort_values('isin').groupby(['decision_date','sector'],sort=False):
        if sector=='Unclassified':continue
        g=g.dropna(subset=['future_xirr','future_drawdown','future_shortfall'])
        common=g[g.sector_incumbent.notna()]
        if len(common)<5:continue
        for scope,cohort in [('common',common),('expanded',g)]:
            scores=cohort[names].to_numpy().T
            assert (np.isfinite(scores).sum(axis=1)>=max(top_ns)).all()
            order=np.argsort(-np.nan_to_num(scores,nan=-np.inf),axis=1,kind='stable')[:,:max(top_ns)]
            y=cohort.future_xirr.to_numpy();risk=cohort.future_drawdown.to_numpy();short=cohort.future_shortfall.to_numpy();rel=cohort.future_xirr.rank(pct=True).to_numpy()
            for n in top_ns:
                chosen=order[:,:n];discount=1/np.log2(np.arange(n)+2);ideal=np.dot(np.sort(rel)[-n:][::-1],discount)
                xr=np.median(y[chosen],axis=1);dd=risk[chosen].mean(axis=1);ach=(short[chosen]==0).mean(axis=1);sf=short[chosen].mean(axis=1);nd=(rel[chosen]*discount).sum(axis=1)/ideal
                for i,name in enumerate(names):
                    rows.append(dict(period=cohort.period.iloc[0],date=day,sector=sector,scope=scope,top_n=n,model=name,xirr=xr[i],drawdown=dd[i],achievement=ach[i],shortfall=sf[i],ndcg=nd[i],cohort_size=len(cohort)))
    return pd.DataFrame(rows)
