"""Research-only personalized cash-flow engine. No production defaults are changed.

Adjusted histories represent fractional investment units, never executable shares.
Raw execution requires an independently verified action ledger. All money is INR;
rates are decimal annual effective rates, using ACT/365 dated cash flows.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from dataclasses import replace
from collections import OrderedDict
from hashlib import sha256
import json
import math
from typing import Mapping

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class InvestorProfile:
    amount: float = 7500
    interval_days: int = 30
    lookback_months: int = 36
    horizon_months: int = 12
    target_cagr: float = .20
    whole_shares: bool = False
    fee_bps: float = 0
    fixed_fee: float = 0
    max_price_gap_days: int = 7

    def __post_init__(self):
        for key in ('amount', 'target_cagr', 'fee_bps', 'fixed_fee'):
            value = getattr(self, key)
            if isinstance(value, bool) or not math.isfinite(value):
                raise ValueError(f'{key} must be finite')
        if self.amount <= 0 or self.target_cagr <= -1 or self.fee_bps < 0 or self.fixed_fee < 0:
            raise ValueError('invalid money, target, or costs')
        for key in ('interval_days', 'lookback_months', 'horizon_months', 'max_price_gap_days'):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f'{key} must be a positive integer')
        if not isinstance(self.whole_shares, bool):
            raise ValueError('whole_shares must be boolean')

    @property
    def fingerprint(self):
        return sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


def xirr(dates, cashflows):
    """Unique conventional-flow XIRR; reject ambiguous multiple-sign-change flows."""
    dates = pd.to_datetime(dates)
    flows = np.asarray(cashflows, dtype=float)
    if len(flows) != len(dates) or not np.isfinite(flows).all() or dates.isna().any():
        raise ValueError('invalid cash flows')
    f = pd.Series(flows, index=dates).groupby(level=0).sum().sort_index()
    f = f[f != 0]
    if len(f) < 2 or not (f.iloc[:-1] < 0).all() or f.iloc[-1] <= 0:
        return None
    years = (f.index[-1] - f.index[:-1]).days.to_numpy() / 365
    lo, hi = -700 / max(years.max(), 1), 700 / max(years.max(), 1)
    for _ in range(100):
        mid = (lo + hi) / 2
        value = np.dot(-f.iloc[:-1].to_numpy(), np.exp(mid * years))
        if value > f.iloc[-1]:
            hi = mid
        else:
            lo = mid
    return float(np.expm1((lo + hi) / 2))


class HistoryBook:
    """Prevalidated immutable arrays, prepared once and reused across profiles."""
    def __init__(self, histories: Mapping[str, pd.DataFrame]):
        self.arrays = {}
        self.errors = {}
        for identity, frame in histories.items():
            try:
                dates = pd.to_datetime(frame['date'], errors='raise').to_numpy(dtype='datetime64[D]')
                prices = pd.to_numeric(frame['adjusted_close'], errors='raise').to_numpy(float)
                if len(dates) < 2 or np.isnat(dates).any() or (np.diff(dates).astype(int) <= 0).any():
                    raise ValueError('dates must be unique and strictly increasing')
                if not np.isfinite(prices).all() or (prices <= 0).any():
                    raise ValueError('prices must be finite and positive')
                dates.setflags(write=False)
                prices.setflags(write=False)
                self.arrays[identity] = (dates, prices)
            except (ValueError, KeyError, TypeError) as exc:
                self.errors[identity] = str(exc)

    def simulate(self, profile: InvestorProfile, end, *, months=None) -> pd.DataFrame:
        """Fixed calendar contributions; execute next observed close within tolerance.

        Contributions remain dated on the scheduled date, including weekend cash
        waiting. No interpolation, backfill before IPO, or terminal forward look.
        Missing any required execution invalidates that security's full scenario.
        """
        if profile.whole_shares:
            raise ValueError('whole shares require simulate_raw and a verified action ledger')
        end = pd.Timestamp(end).normalize()
        start = end - pd.DateOffset(months=months or profile.lookback_months)
        schedule = pd.date_range(start, end - pd.Timedelta(days=1), freq=f'{profile.interval_days}D')
        scheduled = schedule.to_numpy(dtype='datetime64[D]')
        terminal = np.datetime64(end.date(), 'D')
        years = (end - schedule).days.to_numpy() / 365
        target = float(profile.amount * np.power(1 + profile.target_cagr, years).sum())
        net = max(0., (profile.amount - profile.fixed_fee) / (1 + profile.fee_bps / 10000))
        records, valid = [], []
        for identity in sorted(set(self.arrays) | set(self.errors)):
            row = {'isin': identity, 'status': 'INVALID_HISTORY', 'profile': profile.fingerprint,
                   'as_of_date': end.date().isoformat(), 'target_wealth': target,
                   'evidence_grade': 'PROVIDER_ADJUSTED_RESEARCH_ONLY'}
            if identity not in self.arrays:
                row['reason'] = self.errors[identity]
                records.append(row)
                continue
            dates, prices = self.arrays[identity]
            buy = np.searchsorted(dates, scheduled)
            last = np.searchsorted(dates, terminal, side='right') - 1
            if last < 0 or dates[0] > scheduled[0]:
                row['status'] = 'INSUFFICIENT_HISTORY'
            elif int((terminal - dates[last]).astype(int)) > profile.max_price_gap_days:
                row['status'] = 'STALE_TERMINAL'
            elif ((dates[buy[buy <= last]] - scheduled[buy <= last]).astype(int) > profile.max_price_gap_days).any():
                row['status'] = 'MISSING_EXECUTION_PRICE'
            else:
                executed = buy[buy <= last]
                units = float((net / prices[executed]).sum())
                # With no affordable transaction the contribution remains cash, fees are not charged.
                cash = profile.amount * (len(schedule) if net == 0 else len(schedule) - len(executed))
                wealth = units * prices[last] + cash
                invested = profile.amount * len(schedule)
                window = prices[min(buy[0], last):last + 1]
                row.update(status='AVAILABLE', amount_contributed=invested, amount_invested=net * len(executed),
                           investment_units=units, shares_bought=np.nan, average_unit_price=(net * len(executed) / units if units else np.nan),
                           current_value=wealth, unused_cash=cash, fees=invested - net * len(executed) - cash,
                           profit_loss=wealth - invested, profit_loss_pct=wealth / invested - 1,
                           target_attainment=wealth / target, target_shortfall=max(0., 1 - wealth / target),
                           target_status='ACHIEVED_HISTORICALLY' if wealth >= target else 'SHORTFALL',
                           price_drawdown=float(np.min(window / np.maximum.accumulate(window) - 1)),
                           terminal_price_date=str(dates[last]), contribution_count=len(schedule))
                for y in (3, 5, 10):
                    anchor = np.datetime64((end - pd.DateOffset(years=y)).date(), 'D')
                    i = np.searchsorted(dates, anchor, side='right') - 1
                    row[f'cagr_{y}y'] = (prices[last] / prices[i]) ** (365 / int((dates[last] - dates[i]).astype(int))) - 1 if i >= 0 and 0 <= int((anchor - dates[i]).astype(int)) <= profile.max_price_gap_days and last > i else np.nan
                valid.append(len(records))
            records.append(row)
        result = pd.DataFrame(records)
        for column in ('xirr', 'target_shortfall', 'price_drawdown', 'profit_loss_pct', 'cagr_3y', 'cagr_5y', 'cagr_10y'):
            if column not in result:
                result[column] = np.nan
        if valid:
            # Solve all conventional cash-flow roots together in log-rate space.
            wealth = result.loc[valid, 'current_value'].to_numpy()
            lo = np.full(len(valid), -700 / years.max())
            hi = np.full(len(valid), 700 / years.max())
            for _ in range(64):
                mid = (lo + hi) / 2
                future = profile.amount * np.exp(years[:, None] * mid).sum(axis=0)
                higher = future > wealth
                hi = np.where(higher, mid, hi)
                lo = np.where(higher, lo, mid)
            result.loc[valid, 'xirr'] = np.expm1((lo + hi) / 2)
        return result


class PersonalizedEngine:
    """Bounded cache: amount and goal edits reuse price-dependent calculations."""
    def __init__(self, book: HistoryBook, cache_size=24):
        if cache_size < 1:
            raise ValueError('positive cache size required')
        self.book, self.cache_size, self.cache = book, cache_size, OrderedDict()

    def simulate(self, profile: InvestorProfile, end, *, months=None):
        # Fixed costs introduce a legitimate nonlinear amount dependence.
        unit = replace(profile, amount=1 if profile.fixed_fee == 0 else profile.amount, target_cagr=0)
        key = (unit.fingerprint, str(pd.Timestamp(end).date()), months)
        if key not in self.cache:
            self.cache[key] = self.book.simulate(unit, end, months=months)
            if len(self.cache) > self.cache_size:
                self.cache.popitem(last=False)
        self.cache.move_to_end(key)
        result = self.cache[key].copy(deep=True)
        scale = profile.amount / unit.amount
        for col in ('amount_contributed', 'amount_invested', 'investment_units', 'current_value', 'unused_cash', 'fees', 'profit_loss'):
            if col in result:
                result[col] *= scale
        end = pd.Timestamp(end)
        start = end - pd.DateOffset(months=months or profile.lookback_months)
        schedule = pd.date_range(start, end - pd.Timedelta(days=1), freq=f'{profile.interval_days}D')
        target = profile.amount * np.power(1 + profile.target_cagr, (end - schedule).days.to_numpy() / 365).sum()
        result['target_wealth'] = target
        result['profile'] = profile.fingerprint
        if 'current_value' in result:
            result['target_attainment'] = result.current_value / target
            result['target_shortfall'] = (1 - result.target_attainment).clip(lower=0)
            result['target_status'] = np.where(result.current_value.isna(), 'UNKNOWN', np.where(result.current_value >= target, 'ACHIEVED_HISTORICALLY', 'SHORTFALL'))
        return result

    def rank(self, profile, end, evidence=None):
        current = self.simulate(profile, end)
        if profile.horizon_months > profile.lookback_months:
            # A longer desired horizon has no complete scenario inside the stated
            # lookback. Do not silently substitute a shorter horizon.
            goals = [pd.DataFrame({'isin': current['isin'], 'target_shortfall': np.nan})]
        else:
            offsets = sorted(set(np.linspace(0, profile.lookback_months - profile.horizon_months, 4).astype(int)))
            goals = [self.simulate(profile, pd.Timestamp(end) - pd.DateOffset(months=int(m)), months=profile.horizon_months) for m in offsets]
        return rank_candidates(current, [], evidence, goal_scenarios=goals)


def simulate_raw(prices: pd.DataFrame, actions: pd.DataFrame, profile: InvestorProfile,
                 start, end, *, verified_ledger: bool = False, max_participation: float | None = None):
    """Executable whole/fractional shares, carry cash, splits and paid dividends.

    Action columns: date (ex-date), split_ratio (1 if none), dividend_per_old_share
    (0 if none), dividend_payment_date (required for dividends). Entitlement is
    captured before ex-date purchases; cash becomes available only on payment.
    Unpaid declared entitlements are marked separately at face value. Complex actions and
    unresolved delistings must be resolved upstream; unknown ledger is rejected.
    Raw prices MUST be unadjusted contemporaneous execution prices.
    """
    if not verified_ledger:
        raise ValueError('verified raw-price/action/identity ledger required')
    if max_participation is not None and not 0 < max_participation <= 1:
        raise ValueError('invalid participation cap')
    p = prices.copy()
    p['date'] = pd.to_datetime(p.date)
    if p.date.duplicated().any() or not p.date.is_monotonic_increasing or p.date.isna().any():
        raise ValueError('invalid execution dates')
    if not np.isfinite(p.raw_close).all() or (p.raw_close <= 0).any():
        raise ValueError('invalid raw execution prices')
    a = actions.copy()
    if not a.empty:
        a['date'] = pd.to_datetime(a.date)
        if a.date.duplicated().any() or a.date.isna().any() or not np.isfinite(a[['split_ratio', 'dividend_per_old_share']]).all().all() or (a.split_ratio <= 0).any() or (a.dividend_per_old_share < 0).any():
            raise ValueError('invalid action ledger')
        dividends = a.dividend_per_old_share.gt(0)
        if dividends.any():
            if 'dividend_payment_date' not in a:
                raise ValueError('dividend payment date required')
            a['dividend_payment_date'] = pd.to_datetime(a.dividend_payment_date, errors='coerce')
            if a.loc[dividends, 'dividend_payment_date'].isna().any() or (a.loc[dividends, 'dividend_payment_date'] < a.loc[dividends, 'date']).any():
                raise ValueError('invalid dividend payment date')
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    schedule = pd.date_range(start, end - pd.Timedelta(days=1), freq=f'{profile.interval_days}D')
    p = p[p.date.between(start, end)].set_index('date')
    if p.empty or (end - p.index[-1]).days > profile.max_price_gap_days:
        return {'status': 'UNKNOWN_TERMINAL', 'current_value': None, 'xirr': None}
    if max_participation is not None and ('volume' not in p or not np.isfinite(p.volume).all() or (p.volume < 0).any()):
        raise ValueError('participation cap requires valid historical volume')
    executions = {}
    for day in schedule:
        i = p.index.searchsorted(day)
        if i == len(p):
            continue  # Pending terminal contributions remain cash.
        if (p.index[i] - day).days > profile.max_price_gap_days:
            return {'status': 'MISSING_EXECUTION_PRICE', 'current_value': None, 'xirr': None}
        executions[p.index[i]] = executions.get(p.index[i], 0) + 1
    ledger = {} if a.empty else a.set_index('date').to_dict('index')
    payments = {v['dividend_payment_date'] for v in ledger.values() if v['dividend_per_old_share'] > 0 and start <= v['dividend_payment_date'] <= end}
    events = sorted(set(p.index) | set(schedule) | {d for d in ledger if start <= d <= end} | payments)
    shares = cash = fees = invested = 0.
    receivables = {}
    journal = []
    for day in events:
        if day in ledger:
            action = ledger[day]
            if action['dividend_per_old_share'] > 0:
                payment = action['dividend_payment_date']
                receivables[payment] = receivables.get(payment, 0.) + shares * action['dividend_per_old_share']
            shares *= action['split_ratio']
        cash += receivables.pop(day, 0.)
        if day in schedule:
            cash += profile.amount
        if day in executions:
            price = float(p.loc[day, 'raw_close'])
            quantity = max(0., (cash - profile.fixed_fee) / (price * (1 + profile.fee_bps / 10000)))
            if max_participation is not None:
                quantity = min(quantity, float(p.loc[day, 'volume']) * max_participation)
            if profile.whole_shares:
                quantity = math.floor(quantity)
            fee = profile.fixed_fee + quantity * price * profile.fee_bps / 10000 if quantity > 0 else 0.
            cash -= quantity * price + fee
            shares += quantity
            invested += quantity * price
            fees += fee
            journal.append({'date': day.isoformat(), 'shares_bought': quantity, 'cash': cash, 'fee': fee})
    dividend_receivable = sum(receivables.values())
    wealth = shares * p.raw_close.iloc[-1] + cash + dividend_receivable
    contributed = profile.amount * len(schedule)
    target = profile.amount * np.power(1 + profile.target_cagr, (end - schedule).days.to_numpy() / 365).sum()
    return {'status': 'AVAILABLE', 'shares_bought': shares, 'average_price': invested / shares if shares else None,
            'amount_invested': invested, 'amount_contributed': contributed, 'unused_cash': cash, 'fees': fees,
            'dividend_receivable_at_face_value': dividend_receivable,
            'current_value': wealth, 'profit_loss': wealth - contributed, 'profit_loss_pct': wealth / contributed - 1,
            'xirr': xirr([*schedule, end], [-profile.amount] * len(schedule) + [wealth]),
            'target_attainment': wealth / target, 'journal': journal}


def rank_candidates(current: pd.DataFrame, rolling: list[pd.DataFrame], evidence: pd.DataFrame | None = None, *, goal_scenarios=None):
    """One price family, one non-price family; missing components never become zero.

    Goal score is negative mean squared downside of capped goal attainment across
    historical windows. It is an empirical scenario utility, not a probability.
    Families are separate challengers, with no automatic winning model.
    """
    result = current.copy().set_index('isin')
    for column in ('profit_loss_pct', 'xirr', 'target_shortfall'):
        if column not in result:
            result[column] = np.nan
    result['professor_style_score'] = result.profit_loss_pct
    result['xirr_score'] = result.xirr
    scenarios = [x.set_index('isin').get('target_shortfall', pd.Series(dtype=float)).rename(i) for i, x in enumerate(goal_scenarios if goal_scenarios is not None else [current, *rolling])]
    shortfalls = pd.concat(scenarios, axis=1).reindex(result.index)
    result['goal_windows'] = shortfalls.notna().sum(axis=1)
    result['goal_score'] = -shortfalls.pow(2).mean(axis=1).where(shortfalls.notna().all(axis=1))
    result['historical_target_frequency'] = shortfalls.eq(0).sum(axis=1).div(shortfalls.notna().sum(axis=1)).where(shortfalls.notna().sum(axis=1) > 0)
    if evidence is not None:
        if evidence['isin'].duplicated().any():
            raise ValueError('duplicate evidence identity')
        allowed = ['isin', 'sector', 'production_score', 'ensemble_score', 'quality_score', 'valuation_score', 'research_v2_score']
        result = result.join(evidence[[c for c in allowed if c in evidence]].set_index('isin'), validate='one_to_one')
        # Sector percentiles preserve the existing engine's scope; the combination
        # uses one price representation, not SIP + CAGR + momentum as extra votes.
        if 'ensemble_score' in result:
            group = result.groupby('sector', dropna=True)
            goal = group.goal_score.rank(pct=True)
            ensemble = group.ensemble_score.rank(pct=True)
            result['personalized_existing_score'] = (goal + ensemble) / 2
        families = [c for c in ('quality_score', 'valuation_score') if c in result and result[c].notna().any()]
        if families:
            ranks = result.groupby('sector', dropna=True)[['goal_score', *families]].rank(pct=True)
            result['family_aggregation_score'] = ranks.mean(axis=1).where(ranks.notna().all(axis=1))
            for removed in ['goal_score', *families]:
                subset = ranks.drop(columns=removed)
                result[f'family_without_{removed.removesuffix("_score")}_score'] = subset.mean(axis=1).where(subset.notna().all(axis=1))
    for col in list(result):
        if col.endswith('_score'):
            if 'sector' in result:
                result[col.removesuffix('_score') + '_sector_rank'] = result.groupby('sector')[col].rank(ascending=False, method='min')
            if col not in ('production_score', 'ensemble_score', 'research_v2_score'):
                result[col.removesuffix('_score') + '_rank'] = result[col].rank(ascending=False, method='min')
    return result.reset_index()
