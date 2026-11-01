import numpy as np
import pytest
from stock_research.professor_frontier import geometric_core,outranking_core


def test_balanced_factors_can_beat_compensated_weakness():
    x=np.array([[.6]*5,[1,1,1,1,.02]])
    assert x[1].mean()>x[0].mean()
    assert geometric_core(x)[0]>geometric_core(x)[1]


def test_geometry_preserves_common_scale():
    assert geometric_core([[.4]*5])[0]==pytest.approx(.4)


def test_dominant_stock_wins_peer_vote():
    assert outranking_core([[.8]*5,[.2]*5]).tolist()==[1,-1]


def test_severe_weakness_vetoes_majority_win():
    assert outranking_core([[.8,.8,.8,.8,.1],[.6,.6,.6,.6,.8]]).tolist()==[0,0]


def test_peer_ties_do_not_create_wins():
    assert outranking_core([[.5]*5,[.5]*5]).tolist()==[0,0]


def test_unknown_factors_are_not_imputed():
    with pytest.raises(ValueError):geometric_core([[.5,.5,.5,.5,np.nan]])
