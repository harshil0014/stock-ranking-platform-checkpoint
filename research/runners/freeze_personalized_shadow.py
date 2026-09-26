"""Recover the exact d499580 model state and seal a prospective registration.

Reconstruction uses the original checkpoint rows and unchanged parameters; it
must reproduce all saved LambdaRank predictions. It is not model retuning.
"""
import os
for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
import numpy as np
import pandas as pd
from lightgbm import LGBMRanker, Booster
from stock_research.personalized_executable_tournament import FEATURES
from stock_research.personalized_shadow import digest, write_json, seal

COMMIT = 'd4995807163bef1ec4b297179e6c54a59c71f390'
TOURNAMENT = ROOT / 'experiments/personalized-final-tournament/build-04'


def build(output):
    output = Path(output)
    if output.exists():
        raise ValueError('Freeze directory already exists; never overwrite a registration')
    original_manifest = json.loads((TOURNAMENT / 'manifest.json').read_text())
    for item in original_manifest['deterministic_artifacts']:
        if digest(TOURNAMENT / item['path']) != item['sha256']:
            raise ValueError('Original tournament artifact changed: ' + item['path'])
    protocol = json.loads((TOURNAMENT / 'protocol.json').read_text())
    checkpoint = ROOT / 'experiments/personalized-final-tournament/checkpoints-03'
    paths = [checkpoint / f'{part}-{day}.csv.gz' for part, days in [('train', protocol['training_decision_dates']), ('validation', protocol['validation_decision_dates'])] for day in days]
    training = pd.concat([pd.read_csv(p, low_memory=False) for p in paths], ignore_index=True).drop_duplicates(['decision_date', 'profile_name', 'isin'])
    cutoff = protocol['current_profile_date']
    training = training.loc[pd.to_datetime(training.endpoint).lt(pd.Timestamp(cutoff)) & training.future_xirr.notna() & training.enhanced_carry_xirr_score.notna()].sort_values(['decision_date', 'profile_name', 'isin'], kind='stable')
    current = pd.read_csv(TOURNAMENT / 'current_profile_rankings.csv.gz', low_memory=False)
    features = pd.read_csv(checkpoint / f'current-{cutoff}.csv.gz', low_memory=False)
    if current.future_xirr.notna().any() or set(current.decision_date) != {cutoff} or pd.to_datetime(current.terminal_price_date).dropna().gt(cutoff).any():
        raise ValueError('Original current panel contains post-cutoff outcomes/prices')
    config = protocol['candidate_policy']
    model = LGBMRanker(**config['lightgbm_lambdarank'], random_state=int(config['seed']), n_jobs=1, verbosity=-1, deterministic=True, force_col_wise=True)
    labels = training.groupby(['decision_date', 'profile_name']).future_xirr.rank(pct=True).mul(4).clip(upper=3).astype(int)
    model.fit(training[FEATURES], labels, group=training.groupby(['decision_date', 'profile_name'], sort=False).size().to_list())
    valid = features.enhanced_carry_xirr_score.notna()
    recovered = features.loc[valid, ['profile_name', 'isin']].copy()
    recovered['reconstructed'] = model.predict(features.loc[valid, FEATURES])
    paired = current.merge(recovered, on=['profile_name', 'isin'], how='left', validate='one_to_one')
    error = float((paired.lightgbm_lambdarank_score - paired.reconstructed).abs().max())
    if not np.allclose(paired.lightgbm_lambdarank_score, paired.reconstructed, rtol=0, atol=1e-12, equal_nan=True):
        raise ValueError(f'Original LambdaRank reconstruction failed: max error {error}')
    ranks = current.groupby('profile_name')[['enhanced_goal_score', 'lightgbm_lambdarank_score']].rank(pct=True)
    reproduced = ranks.iloc[:, 0] * .67 + ranks.iloc[:, 1] * .33
    if not np.allclose(reproduced, current.selected_ensemble_score, rtol=0, atol=1e-12, equal_nan=True):
        raise ValueError('Original ensemble scores do not reproduce')
    output.mkdir(parents=True)
    shutil.copyfile(TOURNAMENT / 'current_profile_rankings.csv.gz', output / 'rankings.csv.gz')
    shutil.copyfile(checkpoint / f'current-{cutoff}.csv.gz', output / 'features.csv.gz')
    model.booster_.save_model(str(output / 'lambdarank.txt'))
    saved = Booster(model_file=str(output / 'lambdarank.txt'))
    if not np.array_equal(model.predict(features.loc[valid, FEATURES]), saved.predict(features.loc[valid, FEATURES])):
        raise ValueError('Serialized model changed predictions')
    strategies = {'challenger': 'selected_ensemble_score', 'goal': 'enhanced_goal_score', 'lambdarank': 'lightgbm_lambdarank_score', 'existing': 'global_existing_score', 'professor': 'professor_whole_share_score', 'carry_xirr': 'enhanced_carry_xirr_score'}
    selections, coverage = [], []
    for profile, group in current.groupby('profile_name', sort=True):
        for strategy, score in strategies.items():
            eligible = group.loc[group.status.eq('AVAILABLE') & group[score].notna()].sort_values([score, 'isin'], ascending=[False, True], kind='stable')
            chosen = eligible.head(20)
            coverage.append({'profile': profile, 'strategy': strategy, 'eligible': len(eligible), 'selected': len(chosen)})
            selections.extend({'profile': profile, 'strategy': strategy, 'rank': rank, 'isin': row['isin'], 'score': row[score]} for rank, (_, row) in enumerate(chosen.iterrows(), 1))
    pd.DataFrame(selections).to_csv(output / 'selections.csv', index=False, lineterminator='\n')
    pd.DataFrame(coverage).to_csv(output / 'selection_coverage.csv', index=False, lineterminator='\n')
    for name in ['protocol.json', 'inputs.json', 'model_audit.json', 'environment.json', 'final_assessment.json', 'research_conclusion.json']:
        shutil.copyfile(TOURNAMENT / name, output / ('original_' + name))
    source_paths = ['src/stock_research/personalized_executable_tournament.py', 'src/stock_research/personalized_official_actions.py', 'research/runners/run_personalized_official_action_tournament.py']
    for path in source_paths:
        if subprocess.check_output(['git', 'show', COMMIT + ':' + path]) != (ROOT / path).read_bytes():
            raise ValueError('Original challenger source differs from d499580: ' + path)
    write_json(output / 'config.json', {
        'challenger_commit': COMMIT, 'weights': [.67, .33], 'features': FEATURES,
        'prediction_as_of': cutoff, 'registration_date': '2026-09-26', 'prospective_origin': '2026-09-26',
        'checkpoints': {'3': '2026-12-26', '6': '2027-03-26', '12': '2027-09-26'},
        'latest_training_endpoint': str(training.endpoint.max()), 'profiles': protocol['profiles'],
        'engine_sha256': digest(ROOT / 'src/stock_research/personalized_shadow.py'),
        'original_sources': {p: digest(ROOT / p) for p in source_paths},
        'original_tournament_manifest_sha256': digest(TOURNAMENT / 'manifest.json'),
        'selection': 'Top 20 per profile/strategy; score descending, ISIN ascending tie break; no replacement or reranking. Baseline eligibility reported separately.',
        'budget': 'Independent SIP per selected security, not a 20-stock shared-budget portfolio. Each uses the full profile contribution, matching tournament utility.',
        'execution': 'Next observed nominal close within 7 days; whole shares; carry cash; no fees/slippage; no rights subscription/sale; resulting shares held; unknown economic terms block.',
        'dividends': 'Preserved as separate, non-reinvested received cash; excluded from primary price-only comparison.',
        'closed_checkpoint_rule': 'Run after endpoint calendar date. Do not use future prices. Corrections require new sealed revision directories.',
        'evidence_boundary': 'Original model selection is retrospective. Original observations are dated through 2026-09-18, but source publication availability on that historical date is not fully provable. Prospective evaluation begins at registration, never backdated.',
    })
    write_json(output / 'reproduction_audit.json', {'lambda_max_abs_error': error, 'model_roundtrip_exact': True, 'ensemble_reproduced': True, 'current_future_outcomes_absent': True, 'current_terminal_prices_through_cutoff': True, 'training_outcomes_strictly_matured': True, 'training_rows': len(training), 'checkpoint_sources': {p.relative_to(ROOT).as_posix(): digest(p) for p in paths + [checkpoint / f'current-{cutoff}.csv.gz']}, 'builder_sha256': digest(__file__)})
    print(json.dumps(seal(output), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
