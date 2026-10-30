"""Check the optimized statistic against its independent SciPy reference."""
import sys
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
from audit_sector_specialist_ensemble_20261011 import paired_rank_stability


def test_vectorized_stability_preserves_ties_constants_and_rank_correlations():
    rng=np.random.default_rng(71)
    previous=rng.integers(0,6,size=(83,7)).astype(float)
    current=rng.integers(0,6,size=(83,7)).astype(float)
    previous[:,0]=1
    current[:,1]=1
    current[:,2]=previous[:,2]
    current[:,3]=-previous[:,3]
    retained,corr=paired_rank_stability(previous,current)
    for j in range(7):
        reference=spearmanr(previous[:,j],current[:,j]).statistic
        np.testing.assert_allclose(corr[j],reference,atol=1e-14,rtol=0,equal_nan=True)
        a=set(np.argsort(-previous[:,j],kind='stable')[:3])
        b=set(np.argsort(-current[:,j],kind='stable')[:3])
        assert retained[j]==len(a&b)/3
