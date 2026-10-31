from pathlib import Path
import sys,numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
import round2_sector_placebo_20261031 as p
from round2_universe_renames_20261031 import reconstruct_with_renames

def test_sector_permutations_preserve_counts_and_dates():
 sectors=pd.Series(['a','a','b','b','b','c']);dates=pd.Series(['2020']*3+['2021']*3)
 result=p.assignment(sectors,dates,42)
 assert sectors.groupby(dates).value_counts().equals(result.groupby(dates).value_counts())
 assert result.equals(p.assignment(sectors,dates,42))

def test_frozen_ridge_arithmetic_matches_pipeline_with_missing_indicators():
 from sklearn.pipeline import make_pipeline
 from sklearn.impute import SimpleImputer
 from sklearn.preprocessing import StandardScaler
 from sklearn.linear_model import Ridge
 x=pd.DataFrame([[1.,np.nan],[2.,3.],[np.nan,4.],[4.,5.],[5.,2.]])
 fitted=make_pipeline(SimpleImputer(strategy='median',add_indicator=True),StandardScaler(),Ridge(alpha=100)).fit(x,[1.,3.,2.,5.,4.])
 np.testing.assert_allclose(p.frozen_ridge_predict(fitted,x),fitted.predict(x),atol=1e-14,rtol=0)

def test_official_rename_only_moves_active_name_on_effective_day():
 e=pd.DataFrame([dict(company='Old Ltd',company_key='OLD',action='INCLUDE',effective_date='2012-01-01'),dict(company='New Ltd',company_key='NEW',action='EXCLUDE',effective_date='2012-04-01')])
 r=pd.DataFrame([dict(old_key='OLD',new_key='NEW',new_name='New Ltd',symbol='NEW',effective_date='2012-03-01')])
 intervals,errors,counts,bridges=reconstruct_with_renames(e,r)
 assert errors.empty and len(bridges)==1
 assert intervals.iloc[0].end_exclusive=='2012-03-01'
 assert intervals.iloc[1].issuer_key=='OLD' and intervals.iloc[1].end_exclusive=='2012-04-01'

def test_new_name_does_not_union_unrelated_preexisting_issuer():
 e=pd.DataFrame([dict(company='Old Ltd',company_key='OLD',action='INCLUDE',effective_date='2012-01-01'),dict(company='New Ltd',company_key='NEW',action='INCLUDE',effective_date='2012-01-01')])
 r=pd.DataFrame([dict(old_key='OLD',new_key='NEW',new_name='New Ltd',symbol='NEW',effective_date='2012-03-01')])
 intervals,errors,counts,bridges=reconstruct_with_renames(e,r)
 assert set(intervals.company_key)=={'OLD','NEW'} and len(errors)==1 and bridges.empty
