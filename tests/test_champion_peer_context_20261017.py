import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'research'/'runners'))
from champion_peer_context_20261017 import peer_features, FIELDS, STRENGTH, RISK

def example():
    x=pd.DataFrame(dict(isin=list('abcdef'),decision_date=['2020-01-01']*6,sector=['S']*6,evidence_fraction=[1]*6))
    for c in FIELDS:x[c]=np.arange(6,dtype=float)
    return x

def test_no_profile_duplication_or_future_contamination():
    x=example(); base=peer_features(x)
    profiles=pd.concat([x.assign(profile_name='a'),x.assign(profile_name='b')],ignore_index=True)
    future=x.assign(decision_date='2021-01-01'); future[FIELDS]=100
    actual=peer_features(pd.concat([profiles,future],ignore_index=True))
    np.testing.assert_allclose(actual.iloc[:6][STRENGTH+RISK],base[STRENGTH+RISK])
    expected=(0-np.mean([1,2,3,4,5]))/np.std([1,2,3,4,5])
    np.testing.assert_allclose(base.iloc[0][STRENGTH[0]],expected,rtol=1e-6)

def test_invalid_peers_and_small_sectors_do_not_create_evidence():
    x=example(); x.loc[5,'evidence_fraction']=0; x.loc[5,FIELDS]=10000
    actual=peer_features(x)
    assert actual.iloc[5][STRENGTH+RISK].isna().all()
    np.testing.assert_allclose(actual.iloc[0][STRENGTH[0]],-np.mean([1,2,3,4])/np.std([1,2,3,4]),rtol=1e-6)
    assert peer_features(x.iloc[:4])[STRENGTH+RISK].isna().all().all()

def test_constant_peer_group_has_no_infinite_features():
    x=example(); x[FIELDS]=1
    assert peer_features(x)[STRENGTH+RISK].isna().all().all()
