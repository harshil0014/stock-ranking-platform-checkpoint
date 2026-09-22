"""Verify artifacts and independently regenerate a deterministic panel sample."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
import numpy as np
import pandas as pd
from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_ranker.personalized import InvestorProfile, PersonalizedEngine
from stock_ranker.personalized_data import load_history_book
from stock_research.personalized_validation import verify_personalized_run


def run(root, output):
    if output.exists():
        raise ValueError('fresh verification output required')
    t = time.perf_counter()
    summary = verify_personalized_run(root)
    inputs = json.loads((root / 'inputs.json').read_text())
    def digest(path):
        return sha256(Path(path).read_bytes()).hexdigest()
    for name, expected in inputs['protected_state'].items():
        assert digest(ROOT / name) == expected, name
    for name, expected in inputs['source_sha256'].items():
        assert digest(ROOT / name) == expected, name
    for name, expected in inputs['history_sha256'].items():
        assert digest(ROOT / 'data/live_market/history_cache' / name) == expected, name
    protected = subprocess.check_output(['git', 'rev-parse', 'professor-railway-deploy-20260920'], cwd=ROOT, text=True).strip()
    assert protected == 'f4d178f84112babc2ef4d4eebafeaf77c6f55ea1'
    protocol = json.loads((root / 'protocol.json').read_text())
    panel = pd.read_csv(root / 'development_panel.csv.gz')
    identities = sorted(panel['isin'].unique())
    rng = np.random.default_rng(20260922)
    selected = rng.choice(identities, min(64, len(identities)), replace=False)
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / 'data/company_facts')).facts
    facts = facts.loc[facts['isin'].isin(selected)]
    book, _ = load_history_book(facts, ROOT / 'data/live_market/history_cache')
    engine = PersonalizedEngine(book)
    count = 0
    for (day, profile_name), group in panel.loc[panel['isin'].isin(selected)].groupby(['decision_date', 'profile_name']):
        profile = InvestorProfile(**protocol['profiles'][profile_name])
        actual = engine.rank(profile, day).set_index('isin')
        expected = group.set_index('isin').reindex(actual.index)
        columns = ['xirr_score', 'goal_score', 'target_shortfall', 'current_value', 'amount_contributed', 'unused_cash', 'price_drawdown']
        for col in columns:
            np.testing.assert_allclose(actual[col], expected[col], rtol=1e-10, atol=1e-9, equal_nan=True, err_msg=f'{day}/{profile_name}/{col}')
        endpoint = pd.Timestamp(day) + pd.DateOffset(months=profile.horizon_months)
        actual_future = engine.simulate(profile, endpoint, months=profile.horizon_months).set_index('isin').reindex(expected.index)
        np.testing.assert_allclose(actual_future.xirr, expected.future_xirr, rtol=1e-10, atol=1e-9, equal_nan=True)
        count += len(group)
    result = {'status': 'PASS', 'full_artifact_hash_verification': True, 'all_history_files_unchanged': len(inputs['history_sha256']),
              'production_branch_unchanged': protected, 'regenerated_panel_rows': count,
              'sample_identities': len(selected), 'sample_seed': 20260922,
              'universe': summary['universe'], 'seconds': time.perf_counter() - t,
              'manifest_sha256': digest(root / 'manifest.json'),
              'scope': 'Numerical/provenance verification, not investment-performance validation'}
    output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    run(args.run, args.output)
