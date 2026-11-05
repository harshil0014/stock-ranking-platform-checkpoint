import itertools
import numpy as np
import pytest
from stock_research.constrained_selection import select_three


def test_solution_matches_exhaustive_small_case():
    rng=np.random.default_rng(8)
    objective=rng.random(8)
    factors=rng.random((8,5))
    champion=np.array([0,1,2])
    score,receipt=select_three(objective,factors,champion)
    feasible=[s for s in itertools.combinations(range(8),3)
              if (factors[list(s)].sum(axis=0)>=factors[champion].sum(axis=0)-1e-7).all()]
    best=max(sum(objective[list(s)]) for s in feasible)
    chosen=np.argsort(-score)[:3]
    assert objective[chosen].sum()==pytest.approx(best)
    assert receipt['optimal']
    np.testing.assert_equal(np.sort(score),np.sort(objective))


def test_professor_constraints_override_high_objective():
    factors=np.array([[1]*5,[1]*5,[1]*5,[0]*5],float)
    score,receipt=select_three([.2,.3,.4,.99],factors,[0,1,2])
    assert set(np.argsort(-score)[:3])=={0,1,2}
    assert min(receipt['factor_sum_differences'])>=-1e-7


def test_unknown_factor_is_rejected():
    with pytest.raises(ValueError,match='Unknown'):
        select_three([.2,.3,.4],np.full((3,5),np.nan),[0,1,2])


def test_tied_scores_preserve_the_selected_set():
    factors=np.array([[1]*5,[1]*5,[1]*5,[0]*5],float)
    score,receipt=select_three([.5]*4,factors,[0,1,2])
    assert set(np.argsort(-score)[:3])==set(receipt['selected'])
