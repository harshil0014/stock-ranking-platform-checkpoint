"""Offline milestone runner. Fresh outputs only; no production write paths."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import platform
import os
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[name] = '1'

import numpy as np
import pandas as pd
from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_ranker.personalized import InvestorProfile, PersonalizedEngine
from stock_ranker.personalized_benchmark import professor_benchmark
from stock_ranker.personalized_data import load_history_book, current_evidence
from stock_research.current_price_ensemble import validate_current_price_ensemble
from stock_research.personalized_validation import fit_challengers, evaluate, block_uncertainty


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def historical_evidence(book, facts, day):
    # Current sectors are only exploratory grouping labels, explicitly disclosed.
    evidence = facts[['isin', 'product_sector']].rename(columns={'product_sector': 'sector'}).copy()
    rows = []
    for identity, (dates, prices) in book.arrays.items():
        terminal = np.datetime64(day, 'D')
        last = np.searchsorted(dates, terminal, side='right') - 1
        anchor_dates = [np.datetime64((pd.Timestamp(day) - pd.DateOffset(years=y)).date(), 'D') for y in (1, 3, 5)]
        anchors = [np.searchsorted(dates, d, side='right') - 1 for d in anchor_dates]
        if last < 0 or min(anchors) < 0 or (terminal - dates[last]).astype(int) > 7:
            continue
        if any((d - dates[i]).astype(int) > 7 for d, i in zip(anchor_dates, anchors)):
            continue
        values = [prices[last] / prices[i] - 1 for i in anchors]
        since_high = -int((dates[last] - dates[np.argmax(prices[:last + 1])]).astype(int))
        rows.append({'isin': identity, 'return1': values[0], 'return3': values[1], 'return5': values[2], 'recency': since_high})
    frame = evidence.merge(pd.DataFrame(rows), on='isin', how='left', validate='one_to_one')
    complete = frame[['return1', 'return3', 'return5', 'recency']].notna().all(axis=1)
    ranks = frame.loc[complete].groupby('sector')[['return1', 'return3', 'return5', 'recency']].rank(method='min', ascending=False)
    frame['production_score'] = -ranks.mean(axis=1)
    frame['production_score'] = frame.groupby('sector').production_score.rank(pct=True)
    return frame[['isin', 'sector', 'production_score']]


def run(output, workbook, research=True, panel_input=None):
    if output.exists():
        raise ValueError('fresh output directory required; historical artifacts cannot be overwritten')
    output.mkdir(parents=True)
    start_time = time.perf_counter()
    source_paths = [ROOT / 'src/stock_ranker' / name for name in ('personalized.py', 'personalized_benchmark.py', 'personalized_data.py')]
    source_paths += [ROOT / 'src/stock_research/personalized_validation.py', Path(__file__)]
    source_hashes = {str(p.relative_to(ROOT)): digest(p) for p in source_paths}
    protected = [ROOT / 'data/company_facts/accepted_state.json', ROOT / 'data/live_market/accepted_state.json']
    checkpoint = {str(p.relative_to(ROOT)): digest(p) for p in protected}
    snapshot = resolve_company_fact_snapshot(ROOT / 'data/company_facts')
    loaded = load_company_fact_snapshot(snapshot)
    facts = loaded.facts
    if facts['isin'].isna().any() or facts['isin'].duplicated().any():
        raise ValueError('universe identities must be complete and unique')
    as_of = str(facts.trade_date.max())
    profiles = {'base': InvestorProfile(), 'amount10000': InvestorProfile(amount=10000),
                'weekly': InvestorProfile(interval_days=7), 'quarterly': InvestorProfile(interval_days=90),
                'lookback12': InvestorProfile(lookback_months=12), 'lookback60': InvestorProfile(lookback_months=60),
                'target10': InvestorProfile(target_cagr=.1), 'target30': InvestorProfile(target_cagr=.3),
                'horizon24': InvestorProfile(horizon_months=24)}
    protocol = {'schema': 'personalized_v1', 'checkpoint_commit': 'f4d178f84112babc2ef4d4eebafeaf77c6f55ea1',
                'profiles': {k: asdict(v) for k, v in profiles.items()},
                'rolling_rule': 'Up to four evenly spaced horizon-length windows inside lookback; no horizon truncation',
                'training_dates': ['2016-12-31', '2017-12-31', '2018-12-31', '2019-12-31'],
                'validation_dates': ['2022-06-30', '2022-12-31', '2023-06-30', '2023-12-31'],
                'outcome_status': 'PREVIOUSLY_EXPOSED_HISTORY_DEVELOPMENT_ONLY',
                'locked_test_opened': False, 'selection_rule': 'No model promotion; descriptive validation diagnostics only',
                'model_parameters': {'ridge_alpha': 100, 'lambdarank_trees': 60, 'lambdarank_leaves': 7, 'seed': 20260922},
                'rank_cluster_correlation_threshold': .85,
                'replayed_panel_sha256': digest(panel_input) if panel_input else None,
                'limitations': ['Current-survivor universe', 'Current sector labels in retrospective diagnostics',
                               'Provider-adjusted histories, no verified delisting or total-return ledger',
                               'Historical quality and valuation unavailable in this new panel; no current fundamentals backfilled',
                               'Overlapping validation outcomes and rolling windows; no independent-probability claim',
                               'Asset drawdown and mean asset XIRR are not portfolio drawdown or portfolio XIRR'],
                'historical_production_comparator': 'Baseline V1 formula reconstructed on available current-survivor history; not archived historical production decisions',
                'professor_style_comparator': 'Fractional historical profit/loss proxy; verified whole-share workbook arithmetic is separate and cannot be populated from unusable purchase caches',
                'sources': ['https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.brentq.html',
                            'https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMRanker.html',
                            'https://www.nseindia.com/companies-listing/corporate-filings-actions',
                            'https://www.nseindia.com/static/products-services/equity-derivatives-corporate-actions-adjustments']}
    # Write the protocol before computing any new performance outcomes.
    write_json(output / 'protocol.json', protocol)
    book, history_hashes = load_history_book(facts, ROOT / 'data/live_market/history_cache')
    engine = PersonalizedEngine(book, cache_size=12)
    load_seconds = time.perf_counter() - start_time
    ensemble_root = ROOT / 'data/analysis/current_price_ensemble_v5_20260918_run_01'
    validate_current_price_ensemble(ensemble_root)
    ensemble = pd.read_csv(ensemble_root / 'rankings.csv')
    knowledge_date = json.loads((ROOT / 'data/company_facts/accepted_state.json').read_text())['accepted_at']
    evidence = current_evidence(facts, knowledge_date=knowledge_date, ensemble=ensemble)
    runtime, results = [], {}
    for name, profile in profiles.items():
        t = time.perf_counter()
        rank = engine.rank(profile, as_of, evidence)
        rank = facts[['isin', 'ticker', 'company', 'history_price_basis', 'corporate_action_history_status']].merge(rank, on='isin', how='left', validate='one_to_one')
        rank['profile_name'] = name
        rank.to_csv(output / f'current_{name}.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
        results[name] = rank
        runtime.append({'profile': name, 'seconds': time.perf_counter() - t, 'universe': len(rank),
                        'available': int(rank.status.eq('AVAILABLE').sum()), 'goal_ranked': int(rank.goal_score.notna().sum())})
        print(json.dumps(runtime[-1]), flush=True)
    comparisons = []
    base = results['base'].set_index('isin')
    for name, data in results.items():
        other = data.set_index('isin')
        for score in ('professor_style_score', 'xirr_score', 'goal_score', 'personalized_existing_score', 'family_aggregation_score'):
            pair = pd.concat([base[score].rename('base'), other[score].rename('other')], axis=1).dropna()
            comparisons.append({'profile': name, 'candidate': score, 'pairs': len(pair),
                                'spearman_with_base': pair['base'].corr(pair.other, method='spearman'),
                                'max_absolute_score_change': (pair['base'] - pair.other).abs().max()})
    pd.DataFrame(comparisons).to_csv(output / 'profile_sensitivity.csv', index=False)
    pd.DataFrame(runtime).to_csv(output / 'runtime.csv', index=False)
    bench, audit = professor_benchmark(workbook)
    bench.to_csv(output / 'professor_workbook_benchmark.csv', index=False)
    write_json(output / 'professor_workbook_audit.json', audit)
    print('Workbook cached benchmark complete', flush=True)
    panel_rows = []
    if research and panel_input is None:
        for day in protocol['training_dates'] + protocol['validation_dates']:
            old = historical_evidence(book, facts, day)
            for name in ('base', 'weekly', 'lookback12', 'target10', 'target30', 'horizon24'):
                profile = profiles[name]
                rank = engine.rank(profile, day, old)
                # Future contribution window starts at the decision. Calendar-month
                # offsets avoid imposing a lump-sum outcome on a recurring strategy.
                endpoint = pd.Timestamp(day) + pd.DateOffset(months=profile.horizon_months)
                future = engine.simulate(profile, endpoint, months=profile.horizon_months)
                future = future[['isin', 'xirr', 'target_shortfall', 'price_drawdown']].rename(columns={'xirr': 'future_xirr', 'target_shortfall': 'future_shortfall', 'price_drawdown': 'future_drawdown'})
                row = rank.merge(future, on='isin', validate='one_to_one')
                row['decision_date'], row['endpoint'], row['profile_name'] = day, str(endpoint.date()), name
                # A transparent aggregation challenger counts the entire price family
                # once. This overlapping two-price blend is explicitly a challenger.
                ranked = row.groupby('sector')[['goal_score', 'production_score']].rank(pct=True)
                row['personalized_existing_score'] = ranked.mean(axis=1).where(ranked.notna().all(axis=1))
                panel_rows.append(row)
            print(f'Completed chronological development date {day}', flush=True)
    if research:
        panel = pd.read_csv(panel_input) if panel_input else pd.concat(panel_rows, ignore_index=True)
        if panel_input:
            rebuilt = pd.concat([historical_evidence(book, facts, day).assign(decision_date=day) for day in sorted(panel.decision_date.unique())])
            panel = panel.drop(columns=['production_score']).merge(rebuilt[['isin', 'decision_date', 'production_score']], on=['isin', 'decision_date'], how='left', validate='many_to_one')
            ranks = panel.groupby(['decision_date', 'profile_name', 'sector'])[['goal_score', 'production_score']].rank(pct=True)
            panel['personalized_existing_score'] = ranks.mean(axis=1).where(ranks.notna().all(axis=1))
        panel.to_csv(output / 'development_panel.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
        validation, model_audit = fit_challengers(panel)
        validation.to_csv(output / 'validation_predictions.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
        write_json(output / 'experiments.json', model_audit)
        metrics, corr, turnover = evaluate(validation)
        metrics.to_csv(output / 'validation_metrics.csv', index=False)
        corr.to_csv(output / 'double_counting.csv', index=False)
        turnover.to_csv(output / 'turnover.csv', index=False)
        block_uncertainty(metrics).to_csv(output / 'uncertainty.csv', index=False)
        summary_metrics = metrics.groupby(['candidate', 'cohort']).mean(numeric_only=True).reset_index()
        summary_metrics.to_csv(output / 'candidate_summary.csv', index=False)
        # Sector stability is exploratory because historical sector identity is absent.
        sector_rows = []
        from stock_research.personalized_validation import ranking_metrics
        for (day, name, sector), group in validation.groupby(['decision_date', 'profile_name', 'sector']):
            for score in ('professor_style_score', 'goal_score', 'production_score', 'ridge_personalized_score', 'lambdarank_score'):
                if score in group:
                    sector_rows.append({'date': day, 'profile': name, 'sector': sector, 'candidate': score, **ranking_metrics(group, score)})
        pd.DataFrame(sector_rows).to_csv(output / 'sector_stability.csv', index=False)
    factor_columns = [c for c in results['base'] if c.endswith('_score') or c.startswith('cagr_')]
    normalized = results['base'].groupby('sector')[factor_columns].rank(pct=True)
    current_corr = normalized.corr(method='spearman')
    current_corr.to_csv(output / 'current_factor_correlation.csv')
    normalized.notna().astype(int).T.dot(normalized.notna().astype(int)).to_csv(output / 'current_factor_pair_counts.csv')
    current_comparison = []
    for (name, ranked) in results.items():
        for sector, group in ranked.groupby('sector'):
            for reference in ('production_score', 'ensemble_score', 'research_v2_score'):
                for candidate in ('professor_style_score', 'xirr_score', 'goal_score', 'personalized_existing_score', 'family_aggregation_score'):
                    if reference not in group or candidate not in group:
                        continue
                    pair = group[[reference, candidate, 'isin']].dropna()
                    if len(pair) < 3:
                        continue
                    reference_top = set(pair.sort_values([reference, 'isin'], ascending=[False, True]).head(5)['isin'])
                    candidate_top = set(pair.sort_values([candidate, 'isin'], ascending=[False, True]).head(5)['isin'])
                    current_comparison.append({'profile': name, 'sector': sector, 'reference': reference, 'candidate': candidate,
                                               'pair_count': len(pair), 'spearman': pair[reference].corr(pair[candidate], method='spearman') if pair[reference].nunique() > 1 and pair[candidate].nunique() > 1 else None,
                                               'top5_overlap': len(reference_top & candidate_top) / len(reference_top)})
    pd.DataFrame(current_comparison).to_csv(output / 'current_existing_comparison.csv', index=False)
    assert checkpoint == {str(p.relative_to(ROOT)): digest(p) for p in protected}, 'protected state changed during run'
    if source_hashes != {str(p.relative_to(ROOT)): digest(p) for p in source_paths}:
        raise ValueError('source changed during experiment; run is not a reproducible completed result')
    write_json(output / 'inputs.json', {'protected_state': checkpoint, 'history_sha256': history_hashes,
               'source_sha256': source_hashes, 'workbook_sha256': digest(workbook),
               'ensemble_manifest_sha256': digest(ensemble_root / 'manifest.json'),
               'company_manifest_sha256': digest(snapshot / 'manifest.json') if (snapshot / 'manifest.json').exists() else None})
    memory = None
    try:
        import psutil
        info = psutil.Process().memory_info()
        memory = getattr(info, 'peak_wset', info.rss) / 1024 ** 2
    except ImportError:
        pass
    summary = {'overall': 'PARTIAL', 'universe': len(facts), 'valid_history_files': len(book.arrays),
               'history_errors': len(book.errors), 'as_of_date': as_of,
               'production_changed': False, 'locked_test_opened': False,
               'load_seconds': load_seconds, 'total_seconds': time.perf_counter() - start_time,
               'peak_process_memory_mb': memory, 'python': platform.python_version(),
               'candidate_status': {'professor_workbook': 'INSUFFICIENT EVIDENCE', 'professor_style': 'RESEARCH ONLY', 'xirr': 'RESEARCH ONLY',
                                    'goal': 'RESEARCH ONLY', 'personalized_existing': 'RESEARCH ONLY',
                                    'family_aggregation': 'INSUFFICIENT EVIDENCE', 'ridge_personalized': 'RESEARCH ONLY',
                                    'lambdarank': 'RESEARCH ONLY', 'cluster_rank_aggregation': 'RESEARCH ONLY',
                                    'whole_share_full_universe': 'INSUFFICIENT EVIDENCE'},
               'limitations': protocol['limitations'],
               'next_milestone': 'Verified historical membership, identity/action ledger and delisting proceeds; preregister and freeze a prospective personalized comparison before new outcomes mature.'}
    import importlib.metadata
    summary['package_versions'] = {name: importlib.metadata.version(name) for name in ('numpy', 'pandas', 'scipy', 'scikit-learn', 'lightgbm') if importlib.util.find_spec(name.replace('-', '_')) is not None or name == 'scikit-learn'}
    write_json(output / 'summary.json', summary)
    artifacts = [{'path': p.name, 'sha256': digest(p), 'size': p.stat().st_size} for p in sorted(output.iterdir()) if p.is_file()]
    write_json(output / 'manifest.json', {'artifacts': artifacts, 'fingerprint': sha256(json.dumps(artifacts, sort_keys=True).encode()).hexdigest()})
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workbook', type=Path, required=True)
    parser.add_argument('--current-only', action='store_true')
    parser.add_argument('--panel-input', type=Path, help='Replay a fingerprinted development panel; no new locked-test claim')
    args = parser.parse_args()
    run(args.output.resolve(), args.workbook, research=not args.current_only, panel_input=args.panel_input)
