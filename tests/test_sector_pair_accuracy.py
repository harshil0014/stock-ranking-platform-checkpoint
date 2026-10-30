from pathlib import Path
import sys,itertools
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
from sector_accuracy_20261010 import pair_accuracy

def brute(x,y):
    values=[]
    for i,j in itertools.combinations(range(len(x)),2):
        p=np.sign(x[i]-x[j])*np.sign(y[i]-y[j]);values.append((p+1)/2)
    return np.mean(values)

def test_pair_accuracy_including_ties_matches_explicit_pairs():
    for x,y in [([1,2,3],[1,2,3]),([1,2,3],[3,2,1]),([1,1,3,4],[1,2,2,4]),([1,1,1],[1,2,3]),([3,1,2],[2,2,2])]:
        assert np.isclose(pair_accuracy(np.array(x),np.array(y)),brute(np.array(x),np.array(y)))

def test_random_tied_pair_accuracy_matches_direct_computation():
    rng=np.random.default_rng(42)
    for _ in range(20):
        x=rng.integers(0,6,25);y=rng.integers(0,8,25)
        assert np.isclose(pair_accuracy(x,y),brute(x,y))
