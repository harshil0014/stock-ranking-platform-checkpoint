from pathlib import Path
import sys,itertools,numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
from champion_market_evaluate_20261031 import pair_accuracy,metrics
from champion_market_common_20261031 import sample_queries,stable_random

def test_exact_pair_concordance_with_ties():
 y=np.array([1.,1.,2.,3.]);s=np.array([0.,1.,1.,2.]);pairs=[.5 if s[i]==s[j] else float((s[i]-s[j])*(y[i]-y[j])>0) for i,j in itertools.combinations(range(4),2) if y[i]!=y[j]]
 assert abs(pair_accuracy(y,s)-np.mean(pairs))<1e-12
 assert pair_accuracy(y,np.ones(4))==.5
 assert abs(pair_accuracy(np.arange(4),np.arange(4))-1)<1e-12
 assert abs(pair_accuracy(np.arange(4),-np.arange(4)))<1e-12

def test_top20_not_reported_for_tiny_sector():
 x=pd.DataFrame(dict(future_xirr=[1,2,3,4,5],goal_hit=[0,0,1,1,1],future_drawdown=[-.1]*5,future_shortfall=[.1]*5,champ=[1,2,3,4,5]))
 r=metrics(x,['champ'])[0]
 assert abs(r['rank_ic']-1)<1e-12 and abs(r['ndcg3']-1)<1e-12
 assert r['attainment3']==1 and np.isnan(r['attainment20'])

def test_cap_retains_complete_queries_and_is_reproducible():
 x=pd.DataFrame(dict(isin=list('abcdef'),decision_date=['2016']*6,profile_name=['base']*6,sector=['a']*3+['b']*3))
 a=sample_queries(x,cap=4);b=sample_queries(x,cap=4)
 assert len(a)==3 and a.equals(b) and a.sector.nunique()==1
 assert np.array_equal(stable_random(x),stable_random(x))

def test_actual_cashflow_cost_and_portfolio_cash_conservation():
 from champion_market_indices_20261031 import sip_path
 from champion_market_portfolio_20261031 import portfolio_path
 d=pd.date_range('2020-01-01','2021-01-01',freq='D').to_numpy(dtype='datetime64[D]');p=np.ones(len(d))*100
 a=sip_path(d,p,'2020-01-01','2021-01-01',1000,30,0);b=sip_path(d,p,'2020-01-01','2021-01-01',1000,30,50)
 assert abs(a['xirr'])<1e-10 and b['xirr']<0
 assert abs(b['terminal']/b['contributed']-(.995/1.005))<1e-12
 z=portfolio_path([(d,p),(d,p*2)],np.array([.3,.7]),'2020-01-01','2021-01-01',1000,30,50)
 assert abs(z['terminal']-b['terminal'])<1e-8 and abs(z['xirr']-b['xirr'])<1e-10
 assert b['tw_max_drawdown']<-.005 and abs(z['tw_max_drawdown']-b['tw_max_drawdown'])<1e-10

def test_missing_selected_execution_is_blocked():
 import pytest
 from champion_market_portfolio_20261031 import portfolio_path
 d=pd.date_range('2020-01-01','2020-06-01',freq='D').to_numpy(dtype='datetime64[D]')
 with pytest.raises(ValueError,match='missing contribution'):
  portfolio_path([(d,np.ones(len(d)))],np.ones(1),'2020-01-01','2021-01-01',1000,30,0)

def test_temporal_blocks_are_reproducible_and_preserve_length():
 from champion_market_review_20261031 import block_indices
 dates=pd.date_range('2020-01-01',periods=16,freq='3MS').to_numpy(dtype='datetime64[D]')
 a=block_indices(dates,365,np.random.default_rng(1));b=block_indices(dates,365,np.random.default_rng(1))
 assert len(a)==16 and np.array_equal(a,b) and a.min()>=0 and a.max()<16

def test_undefined_neutral_ic_cannot_erase_familywise_evidence(tmp_path,monkeypatch):
 import json
 import champion_market_review_20261031 as review
 monkeypatch.setattr(review.c,'OUT',tmp_path);folder=tmp_path/'audit';folder.mkdir();(folder/'development_lock.json').write_text(json.dumps(dict(selected=review.c.ANCHOR)));rows=[]
 for period,start in [('development','2020-01-01'),('exposed','2024-01-01')]:
  for day in pd.date_range(start,periods=12,freq='3MS').strftime('%Y-%m-%d'):
   for name,ic in [(review.c.ANCHOR,.1),('better',.2),('neutral',np.nan)]:rows.append(dict(period=period,decision_date=day,model=name,rank_ic=ic,attainment3=.3,drawdown3=-.2))
 review.familywise(pd.DataFrame(rows),folder);z=pd.read_csv(folder/'familywise_bounds.csv');e=z[z.model.eq('better')&z.metric.eq('rank_ic')]
 assert len(e)==4 and e.familywise_noise_floor.notna().all() and e.simultaneous_lower95.gt(.09).all()

def test_short_history_is_unavailable_not_zero_uncertainty(tmp_path,monkeypatch):
 import json
 import champion_market_review_20261031 as review
 monkeypatch.setattr(review.c,'OUT',tmp_path);folder=tmp_path/'audit';folder.mkdir();(folder/'development_lock.json').write_text(json.dumps(dict(selected=review.c.ANCHOR)));rows=[]
 for period,start in [('development','2020-01-01'),('exposed','2024-01-01')]:
  for day in pd.date_range(start,periods=4,freq='3MS').strftime('%Y-%m-%d'):
   for name in [review.c.ANCHOR,'other']:rows.append(dict(period=period,decision_date=day,model=name,rank_ic=.1,attainment3=.3,drawdown3=-.2))
 review.familywise(pd.DataFrame(rows),folder);z=pd.read_csv(folder/'familywise_bounds.csv');assert z.status.eq('INSUFFICIENT_TEMPORAL_SPAN').all() and z.familywise_noise_floor.isna().all()

def test_equal_weight_ensemble_uses_ranks_without_outcome_weights():
 import pytest
 from champion_market_evaluate_20261031 import add_ensembles
 x=pd.DataFrame(dict(decision_date=['2020']*3,profile_name=['base']*3,sector=['a']*3,future_xirr=[1,2,3],ml__a__return=[1,3,2],ml__b__return=[5,1,2],ml__a__balanced=[2,1,3]))
 a=x.copy();add_ensembles(a,'full');b=x.copy();b['future_xirr']=[100,-50,0];b['ml__a__return']=b.ml__a__return*100+90;add_ensembles(b,'full');np.testing.assert_allclose(a.ensemble__return,b.ensemble__return);np.testing.assert_allclose(a.ensemble__return,[2/3,2/3,2/3])
 b.loc[0,'ml__a__return']=np.nan
 with pytest.raises(ValueError,match='Missing component'):add_ensembles(b,'full')
