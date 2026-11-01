"""Fixed nonlinear factor cores; preference scores, not probabilities."""
import numpy as np


def geometric_core(values):
    x=np.asarray(values,float)
    if x.ndim!=2 or x.shape[1]!=5 or not np.isfinite(x).all() or (x<=0).any() or (x>1).any():
        raise ValueError('Five finite positive percentile blocks required')
    return np.exp(np.log(x).mean(axis=1))


def outranking_core(values):
    x=np.asarray(values,float)
    if x.ndim!=2 or x.shape[1]!=5 or not np.isfinite(x).all() or (x<0).any() or (x>1).any():
        raise ValueError('Five finite percentile blocks required')
    # Bound memory: one stock against its sector, rather than a population cube.
    wins=np.zeros(len(x),int);losses=np.zeros(len(x),int)
    for i,row in enumerate(x):
        diff=row-x
        won=(np.sum(diff>0,axis=1)>=3)&np.all(diff>=-.40,axis=1)
        wins[i]=int(won.sum());losses+=won
    return wins-losses
