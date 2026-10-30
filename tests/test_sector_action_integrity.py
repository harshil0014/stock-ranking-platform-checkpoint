from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
from sector_action_integrity_20261008 import align,flagged_windows

def test_missing_official_action_is_not_treated_as_no_action():
    provider=pd.DataFrame([dict(isin='A',ticker='A',event_date='2021-05-07',split_ratio=1/335.5,source_url='receipt')])
    official=pd.DataFrame(columns=['isin','event_date','mechanics_status','total_share_multiplier'])
    result=align(provider,official)
    assert result.status.iloc[0]=='UNRESOLVED_PROVIDER_OFFICIAL_MISMATCH'
    x=pd.DataFrame([dict(isin='A',decision_date='2021-03-31',endpoint='2022-03-31'),dict(isin='A',decision_date='2021-06-30',endpoint='2022-06-30'),dict(isin='B',decision_date='2021-03-31',endpoint='2022-03-31')])
    assert flagged_windows(x,result).tolist()==[True,False,False]

def test_coincident_official_multipliers_compound_and_date_tolerance_is_explicit():
    provider=pd.DataFrame([dict(isin='A',ticker='A',event_date='2021-05-07',split_ratio=4.,source_url='receipt')])
    official=pd.DataFrame([dict(isin='A',event_date='2021-05-10',mechanics_status='AUTO_MULTIPLIER',total_share_multiplier=2.)]*2)
    assert align(provider,official).status.iloc[0]=='ALIGNED_MULTIPLIER'
    official.event_date='2021-05-20'
    assert align(provider,official).status.iloc[0]=='UNRESOLVED_PROVIDER_OFFICIAL_MISMATCH'
