"""Prefix-only weekly residual features with leave-one-out reference baskets."""
import numpy as np


def weekly_prices(path, asof):
    dates, _, prices = path
    date = np.datetime64(asof, 'D')
    stop = np.searchsorted(dates, date, side='right')
    dates, prices = dates[:stop], prices[:stop]
    anchors = date - np.arange(156, -1, -1) * np.timedelta64(7, 'D')
    indices = np.searchsorted(dates, anchors, side='right') - 1
    result = np.full(157, np.nan)
    if not len(dates):
        return result
    valid = indices >= 0
    safe = np.maximum(indices, 0)
    valid &= (anchors - dates[safe]).astype(int) <= 7
    valid &= np.isfinite(prices[safe]) & (prices[safe] > 0)
    result[valid] = prices[safe[valid]]
    return result


def leave_one_out(returns, minimum):
    count = np.isfinite(returns).sum(axis=1, keepdims=True)
    total = np.nansum(returns, axis=1, keepdims=True)
    denominator = count - np.isfinite(returns)
    result = np.divide(total - np.nan_to_num(returns), denominator,
                       out=np.full_like(returns, np.nan), where=denominator >= minimum)
    return result


def residual_features(returns, sectors):
    market = leave_one_out(returns, 20)
    peers = np.full_like(returns, np.nan)
    sectors = np.asarray(sectors)
    for sector in np.unique(sectors):
        mask = sectors == sector
        peers[:, mask] = leave_one_out(returns[:, mask], 5)
    output = []
    for column in range(returns.shape[1]):
        observed = np.isfinite(returns[:, column]) & np.isfinite(market[:, column]) & np.isfinite(peers[:, column])
        if observed.sum() < 130 or not observed[-48:].all():
            output.append((np.nan, np.nan))
            continue
        design = np.column_stack([np.ones(observed.sum()), market[observed, column], peers[observed, column]])
        coefficients = np.linalg.lstsq(design, returns[observed, column], rcond=None)[0]
        residual = returns[:, column] - (coefficients[0] + coefficients[1]*market[:, column] + coefficients[2]*peers[:, column])
        formation = residual[-52:-4]
        if not np.isfinite(formation).all() or formation.std() <= 1e-10:
            output.append((np.nan, np.nan))
            continue
        momentum = formation.sum() / (formation.std()*np.sqrt(len(formation)))
        path = np.r_[0., np.cumsum(residual[-48:])]
        last_high = np.flatnonzero(np.isclose(path, path.max(), rtol=1e-10, atol=1e-12))[-1]
        output.append((float(momentum), -float(len(path)-1-last_high)))
    return np.asarray(output)
