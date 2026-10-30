import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
from sector_tabpfn_hybrid_20261011 import ANCHOR,enrich,corrected,train_rows

def test_percentiles_use_only_same_date_profile_sector():
    x=pd.DataFrame({'decision_date':['2020-01-01']*4+['2021-01-01']*2,'profile_name':['a']*6,'sector':['s','s','t','t','s','s'],ANCHOR:[.2,.4,.8,.9,20,40],'guarded_previous':[.1,.4,.8,.9,20,40]})
    y=enrich(x.copy());np.testing.assert_array_equal(y.champion_percentile,[.5,1,.5,1,.5,1])
    changed=x.copy();changed.loc[changed.decision_date.eq('2021-01-01'),ANCHOR]*=-100
    np.testing.assert_array_equal(enrich(changed).champion_percentile.iloc[:4],y.champion_percentile.iloc[:4])

def test_missing_evidence_keeps_champion_order_and_zero_correction():
    z=pd.DataFrame({'champion_percentile':[.2,.8,.6],'evidence_fraction':[0.,1.,0.]})
    np.testing.assert_array_equal(corrected(z,np.array([999.,.2,-999.]),.5),[.2,.9,.6])

def test_training_cutoff_and_small_usable_query():
    rows=[]
    for sector in ['valid','too_small']:
        for date,end in [('2020-03-31','2021-03-31'),('2021-01-01','2022-01-01')]:
            for i in range(6):rows.append(dict(isin=str(i),decision_date=date,endpoint=end,profile_name='p',sector=sector,open_model=i/6,profile_defensive_15=i/6,rank_xendcg_balanced=i/6,future_xirr=i/6,future_drawdown=-i/6,future_shortfall=i/6,champion_percentile=(i+1)/6,evidence_fraction=float(sector=='valid' or i<4)))
    t=train_rows(pd.DataFrame(rows),'2022-01-01')
    assert len(t)==6 and set(t.sector)=={'valid'} and t.endpoint.max()=='2021-03-31'
    assert abs(t.weight.sum()-1)<1e-12
