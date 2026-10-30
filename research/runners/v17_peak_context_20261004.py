"""Exploratory closing-high-aware reranking of V17 refined.

Selection uses 2020-2023 only. Earlier and later dates are contextual checks,
not blind validation. This runner never changes the production website.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'research/runners')]
import v17_ath_refinement_20261004 as a

v = a.v
OUT = ROOT / 'experiments/v17-peak-context-20261004'
BASE = ROOT / 'experiments/v17-refinement-20261004'
OLD = ROOT / 'experiments/v17-ath-refinement-20261004'
KEYS = v.KEYS


def write(name, value):
    OUT.mkdir(exist_ok=True)
    (OUT / name).write_text(json.dumps(v.clean(value), indent=2, allow_nan=False), encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protocol():
    OUT.mkdir(exist_ok=True)
    path = OUT / 'protocol.json'
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    candidates = [{'name': f'{kind}_{beta}', 'kind': kind, 'beta': beta}
                  for kind in ['age_only', 'age_52w', 'age_momentum', 'age_risk']
                  for beta in [0.005, 0.01, 0.02]]
    doc = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'status': 'exploratory; older and later dates are exposed context',
        'hypothesis': 'Blend the age-aware learned expert at 10% and add an explicit adjusted-closing-high-age penalty. Test whether 52-week-high distance, momentum, or downside volatility helps condition the penalty.',
        'candidate_count': len(candidates), 'candidates': candidates,
        'age_weight': '10% age-aware learned expert plus 0.5%, 1%, or 2% maximum direct closing-high-age penalty',
        'selection_dates': list(v.protocol()['development_selection_dates']),
        'selection': 'Among candidates with positive aggregate median XIRR, NDCG, drawdown and achievement deltas and nonpositive shortfall against V17 refined, select highest original utility. No all-profile or current-overlap veto because user explicitly permits ranking changes. If none passes, keep the existing learned expert as exploratory comparison.',
        'source_limits': 'Published 52-week-high and historical-high momentum evidence motivates variables; it does not prove this Indian SIP strategy. 2020-2023 has prior research exposure; 2016-2019 and 2024-2025 are contextual, not blind.',
        'sources': [
            'https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4587697',
            'https://www.sciencedirect.com/science/article/abs/pii/S0378426613002446',
            'https://www.sciencedirect.com/science/article/pii/S1544612324012455',
        ],
    }
    write('protocol.json', doc)
    write('baseline_hashes.json', {str(p.relative_to(ROOT)): sha(p) for p in [
        BASE / 'final_current_rankings.csv.gz', BASE / 'refinement_final_lock.json',
        ROOT / 'research/runtime/personalized-v17/manifest.json']})
    return doc


def components(z):
    age = (z.days_since_recorded_high.clip(lower=0) /
           (z.days_since_recorded_high.clip(lower=0) + 365)).fillna(0)
    gap52 = (-z.distance_from_52w_high).clip(0, 1).fillna(0)
    momentum = z.momentum_6m.clip(-1, 1).fillna(0)
    downside = z.downside_volatility_1y.clip(0, 1).fillna(0)
    return {
        'age_only': age,
        'age_52w': age * (0.5 + 0.5 * np.sqrt(gap52)),
        'age_momentum': age * (0.5 + 0.5 * ((1 - momentum) / 2)),
        'age_risk': age * (0.5 + 0.5 * downside),
    }


def learned(z, period):
    if period == 'development':
        raw = a.signal(z, 'age_monotone')
    else:
        raw = pd.Series(np.nan, index=z.index)
        source = a.features(v.load_historical(True)) if period == 'exposed' else a.features(pd.read_pickle(a.s.O / 'historical.pkl'))
        for year in sorted(z.decision_date.str[:4].unique()):
            test = z[z.decision_date.str.startswith(year)]
            pred, audit = a.fit(source[source.endpoint.lt(test.decision_date.min())], test,
                                'age_monotone', f'peak_context_{period}_{year}')
            raw.loc[test.index] = pred
            write('training_audit.json', (json.loads((OUT / 'training_audit.json').read_text())
                                          if (OUT / 'training_audit.json').exists() else []) + [audit])
    return raw.where(z.repair_score.notna()).groupby([z.decision_date, z.profile_name]).rank(pct=True)


def score(z, expert, kind, beta):
    base = z.repair_score
    return (0.9 * base + 0.1 * expert - beta * z.evidence_confidence * components(z)[kind]).where(base.notna())


def summary(z, score_col, reference):
    metrics = v.evaluate(z, score_col)
    pair = v.compare_metrics(metrics, reference)
    d = {c: float(pair[c + '_delta'].mean()) for c in v.METRICS}
    utility = (0.45 * d['ndcg20'] + 0.20 * d['target_achievement_top20']
               - 0.25 * d['target_shortfall_top20'] + 0.10 * d['mean_asset_drawdown_top20']
               + 0.10 * d['median_xirr_top20'])
    return {'utility': utility, 'delta': d,
            'profile_return': pair.groupby('profile').median_xirr_top20_delta.mean().to_dict(),
            'metrics': metrics[v.METRICS].mean().to_dict()}


def search():
    config = protocol()
    _, z = a.data()
    expert = learned(z, 'development')
    ref = v.evaluate(z, 'repair_score')
    records = []
    for c in config['candidates']:
        z['candidate_score'] = score(z, expert, c['kind'], c['beta'])
        stats = summary(z, 'candidate_score', ref)
        d = stats['delta']
        eligible = (d['median_xirr_top20'] >= 0 and d['ndcg20'] >= 0
                    and d['mean_asset_drawdown_top20'] >= 0
                    and d['target_achievement_top20'] >= 0
                    and d['target_shortfall_top20'] <= 0)
        records.append({**c, **stats, 'eligible': eligible})
        write('search_results.json', records)
        print('TRIAL', c['name'], eligible, round(stats['utility'], 6), flush=True)
    passing = [r for r in records if r['eligible']]
    winner = max(passing, key=lambda r: r['utility']) if passing else None
    write('selection_lock.json', {'winner': winner, 'trial_count': len(records),
                                   'selected_at': datetime.now(timezone.utc).isoformat(),
                                   'protocol_sha256': sha(OUT / 'protocol.json')})
    print('SELECTED', winner['name'] if winner else 'none', flush=True)


def evaluate():
    lock = json.loads((OUT / 'selection_lock.json').read_text())
    winner = lock['winner']
    if winner is None:
        raise RuntimeError('No candidate met the exploratory aggregate selection rules')
    results = {}
    for period, file in [('development', 'development_refined_scores.csv.gz'),
                         ('early', 'early_refined_scores.csv.gz'),
                         ('exposed', 'exposed_refined_scores.csv.gz')]:
        source = a.features(v.load_historical(True)) if period == 'exposed' else a.features(pd.read_pickle(a.s.O / 'historical.pkl'))
        scores = pd.read_csv(BASE / file, usecols=KEYS + ['champion_score', 'v17_score', 'repair_score'])
        z = source.merge(scores, on=KEYS, validate='one_to_one')
        assert len(z) == len(scores), (period, len(z), len(scores))
        expert = learned(z, period)
        z['candidate_score'] = score(z, expert, winner['kind'], winner['beta'])
        reference = v.evaluate(z, 'repair_score')
        results[period] = summary(z, 'candidate_score', reference)
        z[KEYS + ['candidate_score']].to_csv(OUT / f'{period}_scores.csv.gz', index=False)
        print('PERIOD', period, len(z), results[period]['utility'], flush=True)
    current = a.features(pd.read_csv(BASE / 'final_current_rankings.csv.gz', low_memory=False))
    current['repair_score'] = current.winner_score
    full = a.features(v.load_historical(True))
    pred, audit = a.fit(full[full.endpoint.lt('2026-10-03')], current,
                        'age_monotone', 'peak_context_current')
    write('current_training_audit.json', audit)
    expert = pred.where(current.repair_score.notna()).groupby([current.decision_date, current.profile_name]).rank(pct=True)
    current['peak_score'] = score(current, expert, winner['kind'], winner['beta'])
    current['peak_rank'] = v.ranked(current, 'peak_score')
    current.to_csv(OUT / 'current_rankings.csv.gz', index=False)
    for top in [20, 50, 100]:
        current[current.peak_rank.le(top)].sort_values(['profile_name', 'peak_rank']).to_csv(OUT / f'current_top{top}.csv', index=False)
    current[current.ticker.eq('NYKAA')][['profile_name', 'days_since_recorded_high',
        'distance_from_recorded_high', 'winner_rank', 'peak_rank']].to_csv(OUT / 'nykaa.csv', index=False)
    hashes = json.loads((OUT / 'baseline_hashes.json').read_text())
    assert all(sha(ROOT / p) == h for p, h in hashes.items())
    write('decision.json', {'model': winner['name'], 'results': results,
        'decision_dates': sum({'development': 16, 'early': 16, 'exposed': 12}.values()),
        'current_universe': int(current['isin'].nunique()),
        'baseline_files_unchanged': True, 'website_changed': False,
        'status': 'experimental ranking; all historical windows previously researched'})


def persistent_penalty(z, kind):
    years = z.days_since_recorded_high.clip(lower=0).fillna(0) / 365.25
    depth = (-z.distance_from_recorded_high).clip(0, 1).fillna(0)
    # Unlike days/(days+365), these distinguish a five-year peak from a
    # twenty-year peak. Cap at ten units only as a numerical safeguard.
    if kind == 'log_age':
        return np.log1p(years).clip(0, 10)
    return np.log1p(years) * np.sqrt(depth)


def persistent_search():
    path = OUT / 'persistent_protocol.json'
    if not path.exists():
        write('persistent_protocol.json', {
            'created_at': datetime.now(timezone.utc).isoformat(),
            'motivation': 'Current-universe review exposed old/deep peaks near the top. This is an exploratory response to that general diagnostic, not a company-specific rule. Previous current rankings have been viewed.',
            'candidates': [{'name': f'{kind}_{weight}', 'kind': kind, 'weight': weight}
                           for kind in ['log_age', 'log_age_depth']
                           for weight in [.005, .01, .02, .04]],
            'selection': 'Same aggregate five-metric directions versus V17 refined; greatest utility. Show all profile tradeoffs. Exposed-period performance is not used to select weight.',
            'no_guarantee': 'Research exposure prevents a fresh validation claim.'})
    config = json.loads(path.read_text())
    _, z = a.data()
    frozen = pd.read_csv(OUT / 'development_scores.csv.gz')
    z = z.merge(frozen, on=KEYS, validate='one_to_one')
    reference = v.evaluate(z, 'repair_score')
    records = []
    for c in config['candidates']:
        z['persistent_score'] = z.candidate_score - c['weight'] * persistent_penalty(z, c['kind'])
        st = summary(z, 'persistent_score', reference)
        d = st['delta']
        eligible = (min(d[k] for k in ['median_xirr_top20', 'ndcg20',
                    'mean_asset_drawdown_top20', 'target_achievement_top20']) >= 0
                    and d['target_shortfall_top20'] <= 0)
        records.append({**c, **st, 'eligible': eligible})
        write('persistent_results.json', records)
        print('PERSISTENT', c['name'], eligible, st['utility'], flush=True)
    passing = [r for r in records if r['eligible']]
    write('persistent_lock.json', {'winner': max(passing, key=lambda r: r['utility']) if passing else None,
                                   'locked_at': datetime.now(timezone.utc).isoformat()})


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['search', 'evaluate', 'persistent_search'])
    args = parser.parse_args()
    globals()[args.stage]()
