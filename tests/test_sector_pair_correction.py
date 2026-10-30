"""Guard the pairwise experiment's group boundaries and fallback behavior."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
import sector_pair_correction_20261011 as r

def fixture():
    return pd.DataFrame(dict(isin=list('abcdefghij'),decision_date=['2020-01-01']*10,profile_name=['p']*10,sector=['A']*5+['B']*5,return_target=[0,.25,.5,.75,1]*2,champion_percentile=[0,.5,.25,1,.75]*2))

def test_pairs_have_correct_orientation_and_query_normalization():
    t=fixture();a,u,g=r.pairs_for(t,'return','uniform');b,w,_=r.pairs_for(t,'return','mistakes')
    np.testing.assert_array_equal(a,b)
    assert np.all(g[a[:,0]]==g[a[:,1]])
    assert np.all(t.return_target.to_numpy()[a[:,0]]>t.return_target.to_numpy()[a[:,1]])
    assert len(a)==20
    totals=pd.Series(w).groupby(g[a[:,0]]).sum()
    np.testing.assert_allclose(totals,totals.iloc[0])
    base=t.champion_percentile.to_numpy();bad=base[a[:,0]]<=base[a[:,1]]
    assert np.isclose(w[bad].mean()/w[~bad].mean(),2)

def test_tied_targets_do_not_create_false_preferences():
    t=fixture();t.loc[1,'return_target']=t.loc[0,'return_target']
    pairs,_,_=r.pairs_for(t,'return','uniform')
    assert len(pairs)==19

def test_missing_evidence_has_no_learned_correction():
    z=pd.DataFrame(dict(champion_percentile=[.2,.8],evidence_fraction=[0,1]))
    np.testing.assert_allclose(r.h.corrected(z,np.array([100.,.1]),.3),[.2,.83])
