from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
from sector_price_rebuild_20261010 import snapshot,RAW,engineer

def history():
    dates=pd.bdate_range('2020-01-01',periods=300).to_numpy(dtype='datetime64[D]')
    return dates,np.exp(np.arange(300)*.002)*100

def test_future_prices_cannot_change_earlier_features():
    dates,prices=history();day=dates[260]
    before=snapshot(dates,prices,day)
    prices[261:]*=1000
    after=snapshot(dates,prices,day)
    for c in RAW:np.testing.assert_allclose(before[c],after[c],equal_nan=True,atol=0,rtol=0)
    assert after['last_price_date']==str(day)

def test_scale_invariant_features_do_not_require_nominal_split_unadjustment():
    dates,prices=history();a=snapshot(dates,prices,dates[-1]);b=snapshot(dates,prices/335.5,dates[-1])
    for c in RAW:np.testing.assert_allclose(a[c],b[c],equal_nan=True,atol=1e-9,rtol=1e-9)

def test_unresolved_feature_window_abstains_but_future_event_does_not():
    dates,prices=history();a=snapshot(dates,prices,dates[260],[str(dates[150])])
    assert a['input_status']=='UNRESOLVED_ACTION_IN_FEATURE_WINDOW'
    assert all(np.isnan(a[c]) for c in RAW)
    b=snapshot(dates,prices,dates[260],[str(dates[270])])
    assert b['input_status']=='USABLE_PROVIDER_BASIS'

def test_old_action_outside_window_does_not_block_and_stale_data_does():
    dates,prices=history()
    assert snapshot(dates,prices,dates[-1],[str(dates[0])])['input_status']=='USABLE_PROVIDER_BASIS'
    assert snapshot(dates,prices,dates[-1]+np.timedelta64(15,'D'))['input_status']=='STALE_PRICE'

def test_sector_percentiles_do_not_depend_on_other_sector_stocks():
    dates,prices=history();r=snapshot(dates,prices,dates[-1]);rows=[]
    for i in range(6):rows.append(dict(**r,isin=str(i),sector='A' if i<3 else 'B',decision_date=str(dates[-1])))
    x=pd.DataFrame(rows);a=engineer(x)
    x.loc[x.sector.eq('B'),'return126']=1e6
    b=engineer(x)
    pd.testing.assert_frame_equal(a[a.sector.eq('A')],b[b.sector.eq('A')])
