"""Check audit coverage, common populations, attribution and unchanged sources."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'research/reports/top100-human-review-20261004'

def run():
    summary = json.loads((OUT / 'top100_summary.json').read_text())
    professor = json.loads((OUT / 'professor_summary.json').read_text())
    for relative, expected in summary['source_sha256'].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected
    workbook = Path(r'C:\Users\Harshil\Downloads\_Organized\Documents\Copy of OK Strategy - Master Sheet v4.3 (1).xlsx')
    assert hashlib.sha256(workbook.read_bytes()).hexdigest() == professor['source_sha256']
    review = pd.read_csv(OUT / 'top100_stock_by_stock_review.csv')
    assert len(review) == 100 and review['isin'].is_unique
    assert set(review.new_rank) == set(range(1, 101))
    assert review.analyst_note.fillna('').str.len().gt(40).all()
    age = pd.read_csv(OUT / 'age_sensitivity.csv')
    assert len(age) == 4436 and age['isin'].is_unique
    eligible = age.new_rank.notna()
    assert eligible.sum() == 1773
    np.testing.assert_allclose(age.loc[eligible, 'remove_explicit_age_score'],
                               age.loc[eligible, 'new_score'] - age.loc[eligible, 'explicit_age_points'], atol=1e-12)
    expected_ranks = age.loc[eligible, 'remove_explicit_age_score'].rank(ascending=False, method='min')
    np.testing.assert_allclose(expected_ranks, age.loc[eligible, 'remove_explicit_age_rank'])
    common = pd.read_csv(OUT / 'professor_same_universe_comparison.csv')
    missing = pd.read_csv(OUT / 'professor_missing_score_eligible.csv')
    assert len(common) == 1755 and len(missing) == 18
    assert common['isin'].is_unique and missing['isin'].is_unique
    assert not set(common['isin']) & set(missing['isin'])
    assert set(common['isin']) | set(missing['isin']) == set(age.loc[eligible, 'isin'])
    for n in [20, 50, 100]:
        overlap = len(set(common.loc[common.closing_high_rank_common_population.le(n), 'isin']) &
                      set(common.loc[common.professor_rank_same_eligible_universe.le(n), 'isin']))
        assert overlap == professor[f'same_universe_top{n}_overlap']
    assert len(pd.read_csv(OUT / 'professor_stock_comparison.csv')) == 14
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.iterdir())
              if p.is_file() and p.name != 'verification.json'}
    result = {'passed': True, 'top100_individual_notes': 100, 'age_universe': 4436,
              'eligible': 1773, 'professor_common_population': 1755,
              'professor_missing_scores': 18, 'source_hashes_unchanged': True,
              'age_attribution_and_ranks_verified': True, 'artifact_sha256': hashes}
    (OUT / 'verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'artifact_sha256'}, indent=2))

if __name__ == '__main__':
    run()
