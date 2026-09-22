"""Chronological development diagnostics. Previously exposed history is not a lockbox."""
from __future__ import annotations

import numpy as np
import pandas as pd


def verify_personalized_run(directory):
    from hashlib import sha256
    import json
    from pathlib import Path
    root = Path(directory).resolve()
    manifest = json.loads((root / 'manifest.json').read_text())
    artifacts = manifest['artifacts']
    if sha256(json.dumps(artifacts, sort_keys=True).encode()).hexdigest() != manifest['fingerprint']:
        raise ValueError('personalized manifest fingerprint mismatch')
    names = [a['path'] for a in artifacts]
    required = {'summary.json', 'protocol.json', 'inputs.json', 'runtime.csv', 'current_base.csv.gz', 'professor_workbook_audit.json'}
    if len(names) != len(set(names)) or not required.issubset(names):
        raise ValueError('incomplete or duplicate artifact inventory')
    for entry in artifacts:
        p = (root / entry['path']).resolve()
        if p.parent != root or not p.is_file() or p.stat().st_size != entry['size'] or sha256(p.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError(f'personalized artifact changed: {entry["path"]}')
    summary = json.loads((root / 'summary.json').read_text())
    if summary.get('production_changed') is not False or summary.get('locked_test_opened') is not False:
        raise ValueError('research-only boundary violated')
    frame = pd.read_csv(root / 'current_base.csv.gz')
    if len(frame) != summary['universe'] or frame['isin'].isna().any() or frame['isin'].duplicated().any():
        raise ValueError('full-universe identity coverage mismatch')
    return summary


FEATURES = ['xirr_score', 'goal_score', 'price_drawdown', 'cagr_3y', 'cagr_5y']


def chronological_split(panel, validation_start='2022-01-01'):
    dates = pd.to_datetime(panel.decision_date, errors='raise')
    maturity = pd.to_datetime(panel.endpoint, errors='raise')
    if (maturity <= dates).any():
        raise ValueError('outcomes must mature after decisions')
    # Purge every profile/security of a date if any outcome has not matured.
    group_end = maturity.groupby(dates).transform('max')
    train = dates.lt(validation_start) & group_end.lt(validation_start)
    validation = dates.ge(validation_start)
    if not train.any() or not validation.any():
        raise ValueError('empty chronological partition')
    return train, validation


def ranking_metrics(frame, score, top_n=20):
    """Within-date/profile statistics; pairwise ties earn half credit."""
    full = len(frame)
    f = frame[[score, 'future_xirr', 'future_shortfall', 'future_drawdown', 'isin']].dropna()
    if len(f) < 3:
        return {'n': len(f), 'coverage': len(f) / max(full, 1)}
    x = f[score].to_numpy()
    y = f.future_xirr.to_numpy()
    # Deterministic all pairs for small groups, a fixed evenly spaced subset otherwise.
    idx = np.linspace(0, len(f) - 1, min(len(f), 400), dtype=int)
    dx, dy = x[idx, None] - x[None, idx], y[idx, None] - y[None, idx]
    mask = np.triu(np.ones_like(dx, dtype=bool), 1) & (dy != 0)
    pair = np.where(dx * dy > 0, 1., np.where(dx == 0, .5, 0.))[mask]
    # Stable identity tie breaks; report tie rate because capped goal scores can tie.
    ordered = f.sort_values([score, 'isin'], ascending=[False, True], kind='stable')
    top = ordered.head(top_n)
    relevance = f.future_xirr.rank(pct=True)
    gains = relevance.loc[top.index].to_numpy()
    ideal = relevance.nlargest(len(top)).to_numpy()
    discount = np.log2(np.arange(2, len(top) + 2))
    ic = f[score].rank().corr(f.future_xirr.rank()) if f[score].nunique() > 1 else np.nan
    return {'n': len(f), 'coverage': len(f) / max(full, 1), 'rank_ic': ic,
            'ndcg20': float((gains / discount).sum() / (ideal / discount).sum()),
            'pairwise_accuracy': float(pair.mean()) if len(pair) else np.nan,
            'target_achievement_top20': float(top.future_shortfall.eq(0).mean()),
            'target_shortfall_top20': float(top.future_shortfall.mean()),
            'mean_xirr_top20': float(top.future_xirr.mean()),
            'median_xirr_top20': float(top.future_xirr.median()),
            'mean_asset_drawdown_top20': float(top.future_drawdown.mean()),
            'tie_fraction': 1 - f[score].nunique() / len(f)}


def fit_challengers(panel):
    """Fixed hyperparameters, train-only transforms, query groups by date/profile.

    LightGBM is an optional isolated research dependency. No test labels or
    current fundamentals are accepted as features. Ablations use the same cohort.
    """
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    train, validation = chronological_split(panel)
    training = panel.loc[train & panel.future_xirr.notna() & panel.xirr_score.notna()].sort_values(['decision_date', 'profile_name', 'isin']).copy()
    output = panel.loc[validation].copy()
    audits = []
    groups = {'ridge_personalized': FEATURES,
              'ridge_without_xirr': [c for c in FEATURES if c != 'xirr_score'],
              'ridge_without_goal': [c for c in FEATURES if c != 'goal_score'],
              'ridge_without_risk': [c for c in FEATURES if c != 'price_drawdown'],
              'ridge_without_cagr': [c for c in FEATURES if not c.startswith('cagr')],
              'ridge_goal_only': ['goal_score']}
    for name, features in groups.items():
        features = [c for c in features if training[c].notna().any()]
        model = make_pipeline(SimpleImputer(strategy='median', add_indicator=True), StandardScaler(), Ridge(alpha=100.))
        model.fit(training[features], training.future_xirr.clip(-1, 3))
        output[name + '_score'] = pd.Series(model.predict(output[features]), index=output.index).where(output.xirr_score.notna())
        audits.append({'candidate': name, 'features': features, 'train_rows': len(training),
                       'latest_training_endpoint': training.endpoint.max(), 'alpha': 100.})
    # Learn correlated groups only on training features; aggregate each group once.
    correlation = training[FEATURES].corr(method='spearman').abs()
    clusters = []
    pending = set(FEATURES)
    while pending:
        component = {min(pending)}
        while True:
            enlarged = component | {c for c in pending if any(correlation.loc[c, k] >= .85 for k in component)}
            if enlarged == component:
                break
            component = enlarged
        clusters.append(sorted(component))
        pending -= component
    normalized = output.groupby(['decision_date', 'profile_name'])[FEATURES].rank(pct=True)
    cluster_scores = pd.concat([normalized[cs].mean(axis=1).where(normalized[cs].notna().all(axis=1)) for cs in clusters], axis=1)
    output['cluster_rank_aggregation_score'] = cluster_scores.mean(axis=1).where(cluster_scores.notna().all(axis=1))
    audits.append({'candidate': 'cluster_rank_aggregation', 'training_correlation_threshold': .85, 'clusters': clusters,
                   'status': 'RESEARCH ONLY', 'interpretation': 'All inputs are price-derived; clusters do not establish independent economic causes'})
    try:
        from lightgbm import LGBMRanker
        labels = training.groupby(['decision_date', 'profile_name']).future_xirr.rank(pct=True).mul(4).clip(upper=3).astype(int)
        model = LGBMRanker(n_estimators=60, num_leaves=7, max_depth=3, learning_rate=.05,
                          min_child_samples=80, reg_lambda=10., random_state=20260922,
                          n_jobs=1, verbosity=-1, deterministic=True, force_col_wise=True)
        sizes = training.groupby(['decision_date', 'profile_name'], sort=False).size().to_list()
        model.fit(training[FEATURES], labels, group=sizes)
        output['lambdarank_score'] = pd.Series(model.predict(output[FEATURES]), index=output.index).where(output.xirr_score.notna())
        audits.append({'candidate': 'lambdarank', 'features': FEATURES, 'train_rows': len(training),
                       'importance': dict(zip(FEATURES, model.feature_importances_.tolist())),
                       'parameters': {'n_estimators': 60, 'num_leaves': 7, 'max_depth': 3, 'seed': 20260922}})
    except ImportError:
        audits.append({'candidate': 'lambdarank', 'status': 'INSUFFICIENT EVIDENCE', 'reason': 'optional dependency absent'})
    return output, audits


def block_uncertainty(metrics, *, draws=2000):
    """Resample whole decision dates, not correlated securities or profiles."""
    rng = np.random.default_rng(20260922)
    records = []
    for (candidate, cohort), group in metrics.groupby(['candidate', 'cohort']):
        if 'rank_ic' not in group:
            continue
        values = group.groupby('decision_date').rank_ic.mean().dropna().to_numpy()
        if len(values) < 2:
            continue
        sample = values[rng.integers(0, len(values), size=(draws, len(values)))].mean(axis=1)
        records.append({'candidate': candidate, 'cohort': cohort, 'decision_date_blocks': len(values),
                        'mean_rank_ic': float(values.mean()), 'bootstrap_low95': float(np.quantile(sample, .025)),
                        'bootstrap_high95': float(np.quantile(sample, .975)),
                        'status': 'DESCRIPTIVE_ONLY_OVERLAPPING_OUTCOMES_TOO_FEW_BLOCKS'})
    return pd.DataFrame(records)


def evaluate(panel):
    metrics, correlations, selections = [], [], []
    candidates = [c for c in panel if c.endswith('_score')]
    for (day, profile), group in panel.groupby(['decision_date', 'profile_name'], sort=True):
        common = group.dropna(subset=candidates + ['future_xirr', 'future_shortfall', 'future_drawdown'])
        for candidate in candidates:
            for cohort, data in [('available', group), ('common', common)]:
                metrics.append({'decision_date': day, 'profile': profile, 'candidate': candidate,
                                'cohort': cohort, **ranking_metrics(data, candidate)})
            chosen = group.dropna(subset=[candidate]).sort_values([candidate, 'isin'], ascending=[False, True]).head(20)
            selections.append({'decision_date': day, 'profile': profile, 'candidate': candidate,
                               'identities': chosen['isin'].tolist()})
        corr = group[candidates].corr(method='spearman')
        for i, left in enumerate(candidates):
            for right in candidates[i + 1:]:
                correlations.append({'decision_date': day, 'profile': profile, 'left': left, 'right': right,
                                     'spearman': corr.loc[left, right], 'pair_count': int(group[[left, right]].notna().all(axis=1).sum())})
    turnover = []
    for candidate in candidates:
        for profile in panel.profile_name.unique():
            sequence = [s for s in selections if s['candidate'] == candidate and s['profile'] == profile]
            for before, after in zip(sequence, sequence[1:]):
                a, b = set(before['identities']), set(after['identities'])
                turnover.append({'candidate': candidate, 'profile': profile, 'date': after['decision_date'],
                                 'top20_replacement_fraction': 1 - len(a & b) / max(len(a), len(b), 1)})
    return pd.DataFrame(metrics), pd.DataFrame(correlations), pd.DataFrame(turnover)
