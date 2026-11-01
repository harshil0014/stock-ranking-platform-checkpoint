"""Research cashflow replay using actual adjusted opens and cash while pending.

Paths contain (session dates, adjusted opens, adjusted closes). Provider-adjusted
prices and fractional shares are a proxy, not executable quotes or certified NAV.
"""
import numpy as np


def next_open_portfolio(paths, weights, start, end, amount, interval, cost_bps):
    from scipy.optimize import brentq

    start, end = np.datetime64(start, 'D'), np.datetime64(end, 'D')
    weights = np.asarray(weights, float)
    if (not paths or len(paths) != len(weights) or not np.isfinite(weights).all()
            or (weights < 0).any() or not np.isclose(weights.sum(), 1)
            or amount <= 0 or interval <= 0 or end <= start
            or not 0 <= cost_bps < 10000):
        raise ValueError('Invalid unlevered portfolio parameters')
    schedule = np.arange(start, end, np.timedelta64(interval, 'D'))
    cost = cost_bps / 10000
    calendar = np.unique(np.concatenate([schedule, [end]] + [
        ds[(ds >= start) & (ds <= end)] for ds, op, cl in paths]))
    deposits = np.zeros(len(calendar))
    np.add.at(deposits, np.searchsorted(calendar, schedule), amount)
    cash = np.cumsum(deposits)
    wealth = np.zeros(len(calendar))
    first_fills = []
    for (ds, op, cl), weight in zip(paths, weights):
        ds = np.asarray(ds, dtype='datetime64[D]')
        op, cl = np.asarray(op, float), np.asarray(cl, float)
        if (not len(ds) or len(ds) != len(op) or len(ds) != len(cl)
                or np.isnat(ds).any() or (np.diff(ds).astype(int) <= 0).any()
                or not (np.isfinite(op).all() and np.isfinite(cl).all())
                or (op <= 0).any() or (cl <= 0).any()):
            raise ValueError('Invalid actual open/close path')
        buy = np.searchsorted(ds, schedule, side='right')
        if (buy >= len(ds)).any():
            raise ValueError('Missing next open')
        if (ds[buy] > end).any() or ((ds[buy] - schedule).astype(int) > 7).any():
            raise ValueError('Selected stock execution gap')
        loc = np.searchsorted(calendar, ds[buy])
        increments = np.zeros(len(calendar))
        units = amount * weight / (1 + cost) / op[buy]
        np.add.at(increments, loc, units)
        spend = np.zeros(len(calendar))
        np.add.at(spend, loc, amount * weight)
        cash -= np.cumsum(spend)
        holdings = np.cumsum(increments)
        obs = np.searchsorted(ds, calendar, side='right') - 1
        held = holdings > 0
        if (obs[held] < 0).any() or ((calendar[held] - ds[obs[held]]).astype(int) > 7).any():
            raise ValueError('Selected stock stale daily mark')
        wealth[held] += holdings[held] * cl[obs[held]]
        first_fills.append(str(ds[buy[0]]))
    if cash.min() < -1e-6:
        raise ValueError('Negative cash')
    wealth[-1] *= 1 - cost
    wealth += cash
    returns = (wealth[1:] - deposits[1:]) / wealth[:-1] - 1
    nav = np.r_[1., np.cumprod(1 + returns)]
    drawdown = nav / np.maximum.accumulate(nav) - 1
    years = (np.r_[schedule, end] - start).astype(float) / 365.25
    flows = np.r_[np.full(len(schedule), -amount), wealth[-1]]
    def npv(rate):
        return np.sum(flows / (1 + rate) ** years)
    try:
        rate = brentq(npv, -.999999, 1e6)
    except ValueError:
        rate = float('nan')
    return dict(xirr=float(rate), terminal=float(wealth[-1]),
                contributed=float(deposits.sum()), terminal_cash=float(cash[-1]),
                tw_max_drawdown=float(drawdown.min()),
                first_fills=first_fills, _daily_dates=calendar[1:],
                _daily_returns=returns)
