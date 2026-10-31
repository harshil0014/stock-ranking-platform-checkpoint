"""Transparent majority-factor scores. These are preference weights, not probabilities."""
import numpy as np
import pandas as pd

FACTOR_COLUMNS = ['annual_consistency', 'cagr3', 'cagr5', 'high_recency', 'sip_profit']


def price_features(dates, prices, asof):
    """Use only prefix prices; strict calendar coverage and <=7-day boundary lag."""
    dates = np.asarray(dates, dtype='datetime64[D]')
    prices = np.asarray(prices, dtype=float)
    asof = np.datetime64(asof, 'D')
    stop = np.searchsorted(dates, asof, side='right')
    d, p = dates[:stop], prices[:stop]
    out = {k: np.nan for k in ['cagr3', 'cagr5', 'high_recency'] + [f'annual{i}' for i in range(1, 6)]}
    if not len(d) or np.any(d[1:] <= d[:-1]):
        return out
    def close(boundary):
        b = np.datetime64(boundary, 'D'); i = np.searchsorted(d, b, side='right') - 1
        if i < 0 or (b-d[i]).astype(int) > 7 or not np.isfinite(p[i]) or p[i] <= 0:
            return None
        return i
    end = close(asof)
    if end is None:
        return out
    for years in [3, 5]:
        start = close((pd.Timestamp(asof) - pd.DateOffset(years=years)).date())
        if start is not None and end > start:
            span = (d[end]-d[start]).astype(int)
            out[f'cagr{years}'] = float((p[end]/p[start])**(365.25/span)-1)
    valid = np.isfinite(p[:end+1]) & (p[:end+1] > 0)
    if valid.any():
        highest = np.max(p[:end+1][valid])
        last = np.flatnonzero(valid & np.isclose(p[:end+1], highest, rtol=1e-10, atol=0))[-1]
        out['high_recency'] = -float((asof-d[last]).astype(int))
    day = pd.Timestamp(asof)
    last_year = day.year if (day.month, day.day) == (12, 31) else day.year - 1
    for offset in range(5):
        year = last_year-offset
        a, b = close(f'{year-1}-12-31'), close(f'{year}-12-31')
        if a is not None and b is not None:
            out[f'annual{offset+1}'] = float(p[b]/p[a]-1)
    return out


def normalize_factors(frame):
    """Complete evidence only; never fill a missing preferred factor with neutral."""
    raw = ['cagr3', 'cagr5', 'high_recency', 'sip_profit'] + [f'annual{i}' for i in range(1, 6)]
    x = frame.copy()
    eligible = x[raw].replace([np.inf, -np.inf], np.nan).notna().all(axis=1)
    eligible &= x.evidence_fraction.gt(0) & x.sector.ne('Unclassified')
    eligible &= x.volume_active_fraction.ge(.8) & x.last_positive_volume_lag_days.between(0, 14)
    eligible &= ~x.sip_action_blocked & x.sip_invested_fraction.ge(.5)
    eligible &= x.sip_profit.ge(-1)
    groups = ['decision_date', 'sector']
    count = eligible.groupby([x[k] for k in groups]).transform('sum')
    x['factor_eligible'] = eligible & count.ge(5)
    keys = [x[k] for k in groups]
    for col in raw:
        x['q_'+col] = x[col].where(x.factor_eligible).groupby(keys).rank(pct=True)
    x['q_annual_consistency'] = x[[f'q_annual{i}' for i in range(1, 6)]].mean(axis=1, skipna=False)
    # Re-percentile the block so its scale matches the other four blocks.
    x['q_annual_consistency'] = x.q_annual_consistency.groupby(keys).rank(pct=True)
    x['champion_percentile'] = x.champion_score.where(x.factor_eligible).groupby(keys).rank(pct=True)
    return x


def constrained_weights(coefficients):
    """Each factor >=10% of core; remaining50% can be learned, total core sum1."""
    c = np.asarray(coefficients, dtype=float)
    if c.shape != (5,) or not np.isfinite(c).all():
        raise ValueError('Expected five finite coefficients')
    c = np.maximum(c, 0)
    learned = c/c.sum() if c.sum() > 0 else np.ones(5)/5
    return .1 + .5*learned


def score(frame, weights, core_share=.9):
    weights = np.asarray(weights, dtype=float)
    if weights.shape != (5,) or np.any(weights < 0) or not np.isclose(weights.sum(), 1):
        raise ValueError('Factor weights must be nonnegative and sum to one')
    if core_share not in [.8, .9]:
        raise ValueError('Unregistered core share')
    cols = ['q_'+c for c in FACTOR_COLUMNS]
    result = core_share * (frame[cols].to_numpy(float) @ weights) + (1-core_share)*frame.champion_percentile
    return result.where(frame.factor_eligible)
