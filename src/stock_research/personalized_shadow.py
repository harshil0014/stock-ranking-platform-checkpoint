"""Frozen, read-only rankings and deterministic cash/ownership shadow accounting.

No training, ranking refresh, production writes, or network access occurs here.
Each selected security is an independent SIP, as in the frozen tournament.
"""
from __future__ import annotations

from datetime import date
from fractions import Fraction
from hashlib import sha256
import json
import math
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
from stock_ranker.personalized import xirr

ACTION_TYPES = {'SPLIT', 'BONUS', 'CONSOLIDATION', 'DEMERGER', 'STOCK_EXCHANGE',
                'RIGHTS_LAPSE', 'CASH_DIVIDEND', 'CASH_EXIT', 'UNRESOLVED'}


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_bytes((json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode())


def seal(root):
    root = Path(root)
    files = [{'path': p.relative_to(root).as_posix(), 'size': p.stat().st_size, 'sha256': digest(p)}
             for p in sorted(root.rglob('*')) if p.is_file() and p != root / 'manifest.json']
    result = {'files': files, 'fingerprint': sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()}
    write_json(root / 'manifest.json', result)
    return result


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root / 'manifest.json').read_text())
    declared = set()
    for item in manifest['files']:
        path = (root / item['path']).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Missing or unsafe artifact: ' + item['path'])
        if path.stat().st_size != item['size'] or digest(path) != item['sha256']:
            raise ValueError('Artifact drift: ' + item['path'])
        declared.add(path)
    actual = {p.resolve() for p in root.rglob('*') if p.is_file() and p != root / 'manifest.json'}
    if actual != declared:
        raise ValueError('Undeclared freeze artifacts')
    expected = sha256(json.dumps(manifest['files'], sort_keys=True).encode()).hexdigest()
    if expected != manifest['fingerprint']:
        raise ValueError('Manifest fingerprint mismatch')
    return manifest


def load_freeze(root):
    root = Path(root)
    manifest = verify(root)
    config = json.loads((root / 'config.json').read_text())
    if config['challenger_commit'] != 'd4995807163bef1ec4b297179e6c54a59c71f390' or config['weights'] != [0.67, 0.33]:
        raise ValueError('Frozen challenger changed')
    if config['engine_sha256'] != digest(__file__):
        raise ValueError('Shadow engine differs from registered version; use the frozen code')
    ranks = pd.read_csv(root / 'rankings.csv.gz', low_memory=False)
    if set(ranks.decision_date) != {config['prediction_as_of']} or ranks.future_xirr.notna().any():
        raise ValueError('Original prediction date or future outcomes contaminated')
    if pd.Timestamp(config['latest_training_endpoint']) >= pd.Timestamp(config['prediction_as_of']):
        raise ValueError('Training outcome not mature before prediction date')
    selections = pd.read_csv(root / 'selections.csv')
    return config, selections, manifest


def load_evidence(root, endpoint):
    root = Path(root)
    frames = {name: pd.read_csv(root / (name + '.csv'), keep_default_na=False) for name in ['prices', 'actions', 'coverage']}
    required = {
        'prices': {'isin', 'date', 'close', 'source_url', 'source_sha256'},
        'actions': {'event_id', 'isin', 'ex_date', 'type', 'numerator', 'denominator', 'child_isin', 'cash_per_share', 'payment_date', 'fraction_cash_per_share', 'fraction_payment_date', 'source_url', 'source_sha256'},
        'coverage': {'isin', 'through_date', 'price_basis', 'action_status', 'source_url', 'source_sha256'},
    }
    source_hashes = {digest(p) for p in (root / 'sources').rglob('*') if p.is_file()}
    for name, frame in frames.items():
        if not required[name].issubset(frame.columns):
            raise ValueError('Missing evidence columns: ' + name)
        if not frame.empty and (not frame.source_sha256.isin(source_hashes).all() or frame.source_url.eq('').any()):
            raise ValueError('Evidence source is not preserved: ' + name)
    prices, actions, coverage = frames['prices'], frames['actions'], frames['coverage']
    if prices.duplicated(['isin', 'date']).any() or actions.event_id.duplicated().any() or coverage['isin'].duplicated().any():
        raise ValueError('Duplicate evidence identities/events')
    prices['date'] = pd.to_datetime(prices.date, errors='raise')
    prices['close'] = pd.to_numeric(prices.close, errors='raise')
    if not np.isfinite(prices.close).all() or prices.close.le(0).any() or prices.date.gt(endpoint).any():
        raise ValueError('Invalid or post-checkpoint prices')
    if not actions.type.isin(ACTION_TYPES).all():
        raise ValueError('Unknown corporate action type')
    actions['ex_date'] = pd.to_datetime(actions.ex_date, errors='raise')
    if actions.ex_date.gt(endpoint).any():
        raise ValueError('Post-checkpoint corporate action')
    coverage['through_date'] = pd.to_datetime(coverage.through_date, errors='raise')
    if not coverage.price_basis.eq('OBSERVED_NOMINAL_CLOSE').all() or not coverage.action_status.eq('COMPLETE').all():
        raise ValueError('Explicit nominal-price and complete action coverage required')
    for row in actions.itertuples(index=False):
        if row.type in {'SPLIT', 'BONUS', 'CONSOLIDATION', 'DEMERGER', 'STOCK_EXCHANGE'}:
            if int(row.numerator) != float(row.numerator) or int(row.denominator) != float(row.denominator) or int(row.numerator) <= 0 or int(row.denominator) <= 0:
                raise ValueError('Invalid exact action ratio')
        if row.type in {'DEMERGER', 'STOCK_EXCHANGE'} and (not row.child_isin or row.child_isin == row.isin):
            raise ValueError('Resulting security identity required')
        for amount, day in [(row.cash_per_share, row.payment_date), (row.fraction_cash_per_share, row.fraction_payment_date)]:
            if amount != '':
                if not math.isfinite(float(amount)) or float(amount) < 0 or day == '' or pd.Timestamp(day) < row.ex_date:
                    raise ValueError('Invalid cash settlement evidence')
    # Multiple non-dividend transformations on the same security/day require a
    # consolidated, evidenced event; ordering arbitrary rows would invent holdings.
    transforms = actions.loc[actions.type.ne('RIGHTS_LAPSE')]
    for _, group in transforms.groupby(['isin', 'ex_date']):
        if len(group) > 1 and not group.type.eq('DEMERGER').all():
            raise ValueError('Ambiguous same-day corporate-action ordering')
        if group.duplicated(['type', 'child_isin']).any():
            raise ValueError('Duplicate economic entitlement')
    for row in actions.loc[actions.type.isin({'DEMERGER', 'STOCK_EXCHANGE'})].itertuples(index=False):
        if ((actions['isin'] == row.child_isin) & actions.ex_date.eq(row.ex_date) & actions.type.ne('RIGHTS_LAPSE')).any():
            raise ValueError('Ambiguous child action on entitlement date')
    return prices.sort_values(['isin', 'date']), actions.sort_values(['ex_date', 'event_id']), coverage.set_index('isin')


def simulate(identity, profile_name, profile, origin, endpoint, prices, actions, coverage):
    origin, endpoint = pd.Timestamp(origin), pd.Timestamp(endpoint)
    schedule = pd.date_range(origin, endpoint - pd.Timedelta(days=1), freq=f"{profile['interval_days']}D")
    max_gap = 7
    cash = contributed = invested = dividend_cash = 0.0
    holdings, pending, journal, problems = {}, [], [], set()
    books = {isin: group.set_index('date').close for isin, group in prices.groupby('isin')}
    def require_coverage(isin):
        if isin not in coverage.index or coverage.loc[isin, 'through_date'] < endpoint:
            problems.add('INCOMPLETE_ACTION_COVERAGE:' + isin)
    require_coverage(identity)
    orders = {}
    for day in schedule:
        series = books.get(identity, pd.Series(dtype=float))
        options = series.loc[(series.index >= day) & (series.index <= min(day + pd.Timedelta(days=max_gap), endpoint))]
        if len(options):
            orders.setdefault(options.index[0], []).append(day)
        elif day + pd.Timedelta(days=max_gap) <= endpoint:
            problems.add('MISSING_EXECUTION_PRICE:' + day.date().isoformat())
    events = actions.loc[actions.ex_date.between(origin, endpoint)]
    # Daily timeline ensures distributions paid between contribution dates are
    # recorded at their observed payment date, never brought forward.
    exited = False
    for day in pd.date_range(origin, endpoint):
        # Ex-date actions precede any close purchase, so same-day buyers do not qualify.
        for event in events.loc[events.ex_date.eq(day)].itertuples(index=False):
            held = holdings.get(event.isin, 0)
            if not held:
                continue
            journal.append({'date': str(day.date()), 'kind': 'ACTION', 'isin': event.isin, 'event_id': event.event_id, 'action_type': event.type, 'shares_before': held, 'source_sha256': event.source_sha256})
            if event.type == 'UNRESOLVED':
                problems.add('UNRESOLVED_ACTION:' + event.event_id)
            elif event.type == 'RIGHTS_LAPSE':
                pass  # Explicit frozen no-subscription/no-sale policy; no invented RE value.
            elif event.type in {'CASH_DIVIDEND', 'CASH_EXIT'}:
                if event.cash_per_share == '':
                    problems.add('MISSING_CASH_TERMS:' + event.event_id)
                else:
                    pending.append((pd.Timestamp(event.payment_date), held * float(event.cash_per_share), event.type, event.event_id))
                if event.type == 'CASH_EXIT':
                    holdings[event.isin] = 0
                    if event.isin == identity:
                        exited = True
            else:
                target = event.child_isin if event.type in {'DEMERGER', 'STOCK_EXCHANGE'} else event.isin
                require_coverage(target)
                quantity = Fraction(held * int(event.numerator), int(event.denominator))
                whole = quantity.numerator // quantity.denominator
                fraction = quantity - whole
                if target == event.isin:
                    holdings[target] = whole
                else:
                    holdings[target] = holdings.get(target, 0) + whole
                if event.type == 'STOCK_EXCHANGE':
                    holdings[event.isin] = 0
                    if event.isin == identity:
                        exited = True  # Future contributions held in cash; no discretionary substitution.
                if fraction:
                    if event.fraction_cash_per_share == '':
                        problems.add('UNKNOWN_FRACTION_SETTLEMENT:' + event.event_id)
                    else:
                        pending.append((pd.Timestamp(event.fraction_payment_date), float(fraction) * float(event.fraction_cash_per_share), 'FRACTION', event.event_id))
        remaining = []
        for payment_day, amount, kind, event_id in pending:
            if payment_day == day:
                if kind == 'CASH_DIVIDEND':
                    dividend_cash += amount  # Separate non-reinvested total-return diagnostic.
                else:
                    cash += amount
                journal.append({'date': str(day.date()), 'kind': 'CASH_RECEIPT', 'event_id': event_id, 'cash_type': kind, 'cash_received': amount})
            else:
                remaining.append((payment_day, amount, kind, event_id))
        pending = remaining
        if day in schedule:
            cash += profile['amount']; contributed += profile['amount']
            journal.append({'date': str(day.date()), 'kind': 'CONTRIBUTION', 'cash_received': profile['amount'], 'cash_after': cash})
        for scheduled in orders.get(day, []):
            if exited:
                continue
            price = float(books[identity].loc[day])
            quantity = math.floor(cash / price)
            cost = quantity * price
            cash -= cost; invested += cost; holdings[identity] = holdings.get(identity, 0) + quantity
            journal.append({'date': str(day.date()), 'scheduled_date': str(scheduled.date()), 'kind': 'BUY', 'isin': identity, 'shares': quantity, 'price': price, 'spent': cost, 'cash_after': cash})
    value = 0.0
    positions = []
    for isin, quantity in sorted(holdings.items()):
        if not quantity:
            continue
        series = books.get(isin, pd.Series(dtype=float))
        quotes = series.loc[(series.index <= endpoint) & (series.index >= endpoint - pd.Timedelta(days=max_gap))]
        if quotes.empty:
            problems.add('MISSING_TERMINAL_PRICE:' + isin)
            price, quote_day = None, None
        else:
            price, quote_day = float(quotes.iloc[-1]), str(quotes.index[-1].date())
            value += quantity * price
        positions.append({'isin': isin, 'shares': quantity, 'terminal_price': price, 'terminal_price_date': quote_day})
    if any(kind != 'CASH_DIVIDEND' for _, _, kind, _ in pending):
        problems.add('UNPAID_MANDATORY_SETTLEMENT')
    target = float(sum(profile['amount'] * (1 + profile['target_cagr']) ** ((endpoint - d).days / 365) for d in schedule))
    wealth = value + cash
    result = {'profile': profile_name, 'isin': identity, 'status': 'BLOCKED' if problems else 'AVAILABLE',
              'reasons': '|'.join(sorted(problems)), 'contributed': contributed, 'purchase_spend': invested,
              'cash': cash, 'dividend_cash_excluded_from_primary': dividend_cash,
              'observed_holdings_value': value, 'primary_wealth': None if problems else wealth,
              'wealth_including_received_dividends': None if problems else wealth + dividend_cash,
              'target_wealth': target, 'target_shortfall': None if problems else max(0., 1 - wealth / target),
              'goal_achieved': None if problems else wealth >= target,
              'xirr': None if problems else xirr([*schedule, endpoint], [-profile['amount']] * len(schedule) + [wealth]),
              'positions': positions, 'pending_receivables': [{'date': str(d.date()), 'amount': a, 'type': k, 'event_id': e} for d, a, k, e in pending]}
    return result, journal


def evaluate(freeze, evidence, months, output, *, today=None):
    config, selections, manifest = load_freeze(freeze)
    if months not in (3, 6, 12):
        raise ValueError('Only registered 3/6/12-month checkpoints are allowed')
    endpoint = pd.Timestamp(config['checkpoints'][str(months)])
    if pd.Timestamp(today or date.today()) <= endpoint:
        raise ValueError('Checkpoint not closed; run on the following calendar day or later')
    evidence = Path(evidence)
    snapshot = [{'path': p.relative_to(evidence).as_posix(), 'sha256': digest(p)} for p in sorted(evidence.rglob('*')) if p.is_file()]
    request = {'freeze_fingerprint': manifest['fingerprint'], 'months': months, 'endpoint': str(endpoint.date()), 'evidence': snapshot, 'engine_sha256': digest(__file__)}
    output = Path(output)
    if output.exists():
        verify(output)
        if json.loads((output / 'request.json').read_text()) != request:
            raise ValueError('Checkpoint already sealed with different inputs; use a new revision directory')
        return json.loads((output / 'summary.json').read_text())
    prices, actions, coverage = load_evidence(evidence, endpoint)
    results, logs = [], []
    for row in selections[['profile', 'isin']].drop_duplicates().sort_values(['profile', 'isin']).itertuples(index=False):
        result, journal = simulate(row.isin, row.profile, config['profiles'][row.profile], config['prospective_origin'], endpoint, prices, actions, coverage)
        results.append(result)
        logs.extend(dict(profile=row.profile, parent_isin=row.isin, **j) for j in journal)
    keyed = {(r['profile'], r['isin']): r for r in results}
    metrics = []
    for (profile, strategy), group in selections.groupby(['profile', 'strategy'], sort=True):
        selected = [keyed[(profile, isin)] for isin in group['isin']]
        available = [r for r in selected if r['status'] == 'AVAILABLE']
        complete = len(available) == len(selected)
        metrics.append({'profile': profile, 'strategy': strategy, 'selected': len(selected), 'available': len(available),
                        'coverage': len(available) / len(selected), 'status': 'COMPLETE' if complete else 'INCOMPLETE_NO_AGGREGATE',
                        'mean_shortfall': float(np.mean([r['target_shortfall'] for r in available])) if complete else None,
                        'goal_achievement': float(np.mean([r['goal_achieved'] for r in available])) if complete else None,
                        'mean_wealth': float(np.mean([r['primary_wealth'] for r in available])) if complete else None})
    summary = {'checkpoint_months': months, 'endpoint': str(endpoint.date()), 'ranking_policy': 'FROZEN_NO_REFIT_NO_REBALANCING',
               'execution': 'Independent per-security SIPs; gross close fills, cash carry, rights lapse; dividends separately tracked without reinvestment.',
               'complete_security_profiles': sum(r['status'] == 'AVAILABLE' for r in results), 'security_profiles': len(results), 'metrics': metrics}
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'request.json', request)
    write_json(output / 'results.json', results)
    write_json(output / 'journal.json', logs)
    write_json(output / 'summary.json', summary)
    # A sealed checkpoint is self-contained. Source files are copied, never
    # moved, and rehashed to catch concurrent changes during the evaluation.
    shutil.copytree(evidence, output / 'evidence')
    copied = [{'path': p.relative_to(output / 'evidence').as_posix(), 'sha256': digest(p)}
              for p in sorted((output / 'evidence').rglob('*')) if p.is_file()]
    if copied != snapshot:
        raise ValueError('Evidence changed during checkpoint evaluation')
    metric_frame = pd.DataFrame(metrics)
    metric_frame.to_csv(output / 'metrics.csv', index=False, lineterminator='\n')
    comparisons = []
    for profile, group in metric_frame.groupby('profile'):
        candidate = group.loc[group.strategy.eq('challenger')].iloc[0]
        for baseline in group.loc[group.strategy.ne('challenger')].itertuples(index=False):
            complete = candidate.status == baseline.status == 'COMPLETE'
            comparisons.append({'profile': profile, 'baseline': baseline.strategy, 'status': 'COMPLETE' if complete else 'INCOMPLETE_NO_COMPARISON',
                                'shortfall_reduction': float(baseline.mean_shortfall - candidate.mean_shortfall) if complete else None,
                                'goal_achievement_difference': float(candidate.goal_achievement - baseline.goal_achievement) if complete else None,
                                'mean_wealth_difference': float(candidate.mean_wealth - baseline.mean_wealth) if complete else None})
    pd.DataFrame(comparisons).to_csv(output / 'comparisons.csv', index=False, lineterminator='\n')
    seal(output)
    return summary
