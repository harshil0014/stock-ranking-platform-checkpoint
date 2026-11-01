import numpy as np
import pytest
from stock_research.next_open_portfolio import next_open_portfolio


def replay(op, cl, cost=0, days=None, interval=30):
    ds = np.arange('2020-01-01', '2020-01-07', dtype='datetime64[D]') if days is None else days
    return next_open_portfolio([(ds, np.asarray(op), np.asarray(cl))], [1],
                               '2020-01-01', '2020-01-06', 100, interval, cost)


def test_actual_next_open_gap_not_same_close():
    r = replay([10, 20, 20, 20, 20, 20], [10, 20, 20, 20, 20, 20])
    assert r['terminal'] == 100
    assert r['first_fills'] == ['2020-01-02']


def test_open_to_close_loss_is_included():
    r = replay([10, 20, 10, 10, 10, 10], [10] * 6)
    assert r['terminal'] == 50
    assert r['tw_max_drawdown'] == -.5


def test_delay_can_improve_return_too():
    assert replay([20, 10, 20, 20, 20, 20], [20] * 6)['terminal'] == 200


def test_idle_cash_and_multiple_contributions_conserved():
    r = replay([10] * 6, [10] * 6, interval=2)
    assert r['terminal'] == r['contributed'] == 300
    assert r['tw_max_drawdown'] == 0
    assert r['xirr'] == pytest.approx(0, abs=1e-10)


def test_both_sides_cost():
    assert replay([10] * 6, [10] * 6, 25)['terminal'] == pytest.approx(100 * .9975 / 1.0025)


def test_missing_open_fails():
    with pytest.raises(ValueError, match='actual open'):
        replay([10, np.nan, 10, 10, 10, 10], [10] * 6)


def test_no_leverage():
    with pytest.raises(ValueError, match='unlevered'):
        next_open_portfolio([([], [], [])], [2], '2020-01-01', '2020-02-01', 100, 30, 25)


def test_missing_next_session_fails():
    ds = np.array(['2020-01-01', '2020-01-10'], dtype='datetime64[D]')
    with pytest.raises(ValueError, match='execution gap'):
        replay([10, 10], [10, 10], days=ds)
