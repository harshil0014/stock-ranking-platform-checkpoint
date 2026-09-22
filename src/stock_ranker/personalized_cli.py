"""Opt-in local personalized research export: python -m stock_ranker.personalized_cli."""
import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import time
import pandas as pd

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_ranker.personalized import InvestorProfile, PersonalizedEngine
from stock_ranker.personalized_data import current_evidence, load_history_book
from stock_research.current_price_ensemble import validate_current_price_ensemble


def main(argv=None):
    p = argparse.ArgumentParser(description='Research-only personalized ranking; no production promotion')
    p.add_argument('--amount', type=float, default=7500)
    p.add_argument('--interval-days', type=int, default=30)
    p.add_argument('--lookback-months', type=int, default=36)
    p.add_argument('--horizon-months', type=int, default=12)
    p.add_argument('--target-cagr', type=float, default=.2)
    p.add_argument('--fee-bps', type=float, default=0)
    p.add_argument('--fixed-fee', type=float, default=0)
    p.add_argument('--state-root', type=Path, default=Path('data/company_facts'))
    p.add_argument('--history-root', type=Path, default=Path('data/live_market/history_cache'))
    p.add_argument('--ensemble-root', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(argv)
    profile = InvestorProfile(amount=a.amount, interval_days=a.interval_days, lookback_months=a.lookback_months,
                              horizon_months=a.horizon_months, target_cagr=a.target_cagr, fee_bps=a.fee_bps, fixed_fee=a.fixed_fee)
    if a.output.exists():
        raise ValueError('output must be a fresh directory')
    state = json.loads((a.state_root / 'accepted_state.json').read_text())
    cutoff = state['accepted_at']
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(a.state_root)).facts
    ensemble = None
    if a.ensemble_root:
        validate_current_price_ensemble(a.ensemble_root)
        ensemble = pd.read_csv(a.ensemble_root / 'rankings.csv')
    evidence = current_evidence(facts, knowledge_date=cutoff, ensemble=ensemble)
    started = time.perf_counter()
    book, hashes = load_history_book(facts, a.history_root)
    engine = PersonalizedEngine(book)
    prepared = time.perf_counter()
    result = engine.rank(profile, str(facts.trade_date.max()), evidence)
    result = facts[['isin', 'ticker', 'company']].merge(result, on='isin', how='left', validate='one_to_one')
    a.output.mkdir(parents=True)
    result.to_csv(a.output / 'rankings.csv', index=False)
    summary = {'status': 'RESEARCH ONLY', 'profile': asdict(profile), 'profile_fingerprint': profile.fingerprint,
               'universe': len(result), 'ranked': int(result.goal_score.notna().sum()),
               'price_as_of': str(facts.trade_date.max()), 'knowledge_cutoff': cutoff,
               'load_seconds': prepared - started, 'ranking_seconds': time.perf_counter() - prepared,
               'history_sha256': hashes, 'accepted_state_sha256': sha256((a.state_root / 'accepted_state.json').read_bytes()).hexdigest(),
               'limitations': ['Provider-adjusted fractional units', 'Current survivors only', 'No calibrated future goal probability', 'No verified whole-share execution history']}
    (a.output / 'summary.json').write_text(json.dumps(summary, sort_keys=True, indent=2) + '\n')
    manifest = {f.name: sha256(f.read_bytes()).hexdigest() for f in a.output.iterdir()}
    (a.output / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'history_sha256'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
