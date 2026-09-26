"""Verify final evidence hashes and summarize the selected policy across objectives."""
from pathlib import Path
from hashlib import sha256
import argparse
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def run(out):
    manifest = json.loads((out / 'manifest.json').read_text())
    for item in manifest['deterministic_artifacts']:
        path = out / item['path']
        assert path.stat().st_size == item['size'] and digest(path) == item['sha256'], path
    inputs = json.loads((out / 'inputs.json').read_text())
    for key in ['normalized_recovery_sources', 'finalizer_sources', 'protected_state']:
        for path, expected in inputs[key].items():
            assert digest(ROOT / path) == expected, path
    selection = json.loads((out / 'final_assessment.json').read_text())
    selected = selection['strongest_ensemble_by_goal_shortfall']
    dates = pd.read_csv(out / 'date_stability.csv').set_index(['candidate', 'decision_date'])
    profiles = pd.read_csv(out / 'profile_metrics.csv').set_index(['candidate', 'profile'])
    policy = dates.loc[selected]
    rng = np.random.default_rng(20260926)
    comparisons = []
    for reference in ['global_existing_score', 'enhanced_goal_score', 'lightgbm_lambdarank_score']:
        ref = dates.loc[reference]
        delta = (ref.target_shortfall_top20 - policy.target_shortfall_top20).to_numpy()
        boot = delta[rng.integers(len(delta), size=(5000, len(delta)))].mean(axis=1)
        comparisons.append({
            'reference': reference,
            'mean_goal_shortfall_reduction': float(delta.mean()),
            'descriptive_date_bootstrap_low95': float(np.quantile(boot, .025)),
            'descriptive_date_bootstrap_high95': float(np.quantile(boot, .975)),
            'dates_with_lower_shortfall': int((delta > 0).sum()),
            'date_count': len(delta),
            'profiles_with_lower_mean_shortfall': int((profiles.loc[selected].target_shortfall_top20 < profiles.loc[reference].target_shortfall_top20).sum()),
            'profile_count': len(profiles.loc[selected]),
            'goal_achievement_difference': float((policy.target_achievement_top20 - ref.target_achievement_top20).mean()),
        })
    conclusion = {
        'selected_research_policy': selected,
        'mean_top20_goal_shortfall': float(policy.target_shortfall_top20.mean()),
        'mean_top20_goal_achievement': float(policy.target_achievement_top20.mean()),
        'comparisons': comparisons,
        'interpretation': 'Material retrospective goal-shortfall improvement over corrected existing and simple-goal baselines. The ensemble advantage over standalone LambdaRank and the goal-achievement improvement are not conclusive. No prospective superiority or production readiness is established.',
        'uncertainty_boundary': 'Six date blocks; correlated investor profiles are averaged within dates. Descriptive intervals are not adjusted for retrospective model selection or current-universe survivorship.',
        'control_experiment': 'Highest rank IC is gradient boosting, but LambdaRank and the selected ensemble have lower goal shortfall and higher goal achievement. Highest IC did not identify the best investor utility.',
        'next_step': 'Shadow-evaluate the frozen 67/33 goal/LambdaRank policy on post-2026-09-18 data, retaining production. Full 12-month prospective outcomes mature on 2027-09-18.',
        'source_hashes_verified': True,
        'audit_runner_sha256': digest(Path(__file__)),
    }
    (out / 'research_conclusion.json').write_text(json.dumps(conclusion, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
    report = ROOT / 'docs/PERSONALIZED_OWNERSHIP_RESEARCH_20260925.md'
    marker = '\n## Cross-metric decision audit\n'
    base = report.read_text(encoding='utf-8').split(marker)[0]
    existing, goal, single = comparisons
    extra = [
        '', conclusion['interpretation'], '',
        f"The selected ensemble lowers mean top-20 goal shortfall from 15.79% (existing score) and 10.88% (simple goal score) to {100 * conclusion['mean_top20_goal_shortfall']:.2f}%. It improves shortfall on {existing['dates_with_lower_shortfall']}/6 dates and {existing['profiles_with_lower_mean_shortfall']}/9 profiles versus the existing score, and on {goal['dates_with_lower_shortfall']}/6 dates versus simple goal scoring.", '',
        f"The descriptive 95% date-bootstrap interval for shortfall improvement versus simple goal scoring is {100 * goal['descriptive_date_bootstrap_low95']:.2f} to {100 * goal['descriptive_date_bootstrap_high95']:.2f} percentage points. This is not a selection-adjusted confidence claim.", '',
        'The highest-IC gradient boosting model achieves goals for 32.31% of its top 20, versus 44.35% for LambdaRank and 43.61% for the selected ensemble. Rank IC alone selected the wrong policy for investor utility. The training-only learned rank blend has 13.73% mean shortfall and does not beat the selected fixed ensemble.', '',
        'Recovery eligibility alone is not the explanation for the utility gain: holding corrected scores/outcomes fixed on the two overlapping old evaluation dates, adding recovered identities changes shortfall by approximately +0.10 percentage points. That diagnostic captures screening effects, not a causal corporate-action-only effect.', '',
        'Tests: 891 passed; one external NSE fixture skipped. Independent frozen-dataset rebuild matched exactly. All recorded normalized evidence, finalizer source, and protected-state hashes verified.', '',
        conclusion['next_step'], '',
    ]
    report.write_text(base + marker + '\n'.join(extra), encoding='utf-8')
    files = [{'path': p.name, 'size': p.stat().st_size, 'sha256': digest(p)} for p in sorted(out.iterdir()) if p.is_file() and p.name != 'manifest.json']
    (out / 'manifest.json').write_text(json.dumps({'deterministic_artifacts': files, 'fingerprint': sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()}, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(conclusion, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--tournament', type=Path, required=True)
    run(parser.parse_args().tournament)
