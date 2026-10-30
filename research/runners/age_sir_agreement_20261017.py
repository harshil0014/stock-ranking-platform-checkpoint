"""Descriptive current-sector agreement; not a return or accuracy benchmark."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'experiments/champion-age-only-20261017'


def main():
    source = OUT / 'current_all_4436_audit.csv'
    x = pd.read_csv(source)
    x = x[np.isfinite(x.professor_whole_share_score) & ~x.sip_action_blocked & x.sector.ne('Unclassified')].copy()
    x = x[x.groupby('sector').isin.transform('size').ge(5)]
    selected = json.loads((OUT / 'decision.json').read_text())['selected']
    models = ['current_champion'] + [c[:-5] for c in x if c.endswith('_rank') and c.startswith(('dual_age_', 'rolling_age_', 'recorded_age_', 'near_high_age_'))]
    rows = []
    for sector, z in x.groupby('sector'):
        z = z.sort_values('isin')
        sir = set(z.sort_values('professor_whole_share_score', ascending=False, kind='stable').head(5)['isin'])
        for model in models:
            top = set(z.sort_values(model, ascending=False, kind='stable').head(5)['isin'])
            rows.append(dict(sector=sector, n=len(z), model=model,
                             spearman=z[model].corr(z.professor_whole_share_score, method='spearman'),
                             kendall=z[model].corr(z.professor_whole_share_score, method='kendall'),
                             shared_top5=len(top & sir)))
    detail = pd.DataFrame(rows)
    detail.to_csv(OUT / 'sir_age_agreement_by_sector.csv', index=False)
    summary = detail.groupby('model')[['spearman', 'kendall', 'shared_top5']].mean()
    summary['top5_overlap_percent'] = summary.shared_top5 * 20
    baseline = summary.loc['current_champion']
    for col in ['spearman', 'kendall', 'top5_overlap_percent']:
        summary['delta_' + col] = summary[col] - baseline[col]
    summary.to_csv(OUT / 'sir_age_agreement_summary.csv')
    old = pd.read_csv(ROOT / 'experiments/champion-sip-profit-20261017/sir_agreement_by_sector.csv')
    np.testing.assert_allclose(baseline.spearman, old.after.mean(), atol=1e-12)
    assert len(x) == 3164 and x.sector.nunique() == 53
    assert detail[detail.model.eq('current_champion')].shared_top5.sum() == 89
    a = detail[detail.model.eq('current_champion')].set_index('sector')
    b = detail[detail.model.eq(selected)].set_index('sector')
    delta = b.spearman - a.spearman
    counts = dict(improved=int((delta > 1e-12).sum()), unchanged=int((delta.abs() <= 1e-12).sum()), worsened=int((delta < -1e-12).sum()))
    lines = ['# Extra high-age weight: agreement with professor-style ranking', '',
             f'Development-selected candidate: `{selected}`. Website unchanged.', '',
             'Same 3,164 matched stocks across 53 sectors; finite professor-style SIP profit, no action block, known sector and at least five peers. Sector statistics receive equal weight. Fixed ISIN tie-breaking for Top 5. The excluded 1,272 names are not assigned invented professor ranks.', '',
             'This uses the preserved professor-style SIP profit calculation, not a fresh calculation from the original Excel/Google Finance sheet. Similarity is not investment accuracy or future performance. Rankings use the frozen October 3 snapshot and default profile.', '',
             '| Variant | Spearman | Kendall | Top 5 overlap | Change in Spearman |',
             '|---|---:|---:|---:|---:|']
    for name, row in summary.iterrows():
        lines.append(f'| {name} | {row.spearman:.9f} | {row.kendall:.9f} | {row.top5_overlap_percent:.5f}% | {row.delta_spearman:+.9f} |')
    lines += ['', f'Selected candidate sector correlation changes: {counts}.', '',
              'Baseline correlation and 89/265 Top 5 shared slots reproduce the earlier audit. All 16 variants are shown descriptively; none is newly selected using this comparison. Five-stock sectors necessarily have 100% Top 5 overlap.', '',
              'Source SHA256: ' + hashlib.sha256(source.read_bytes()).hexdigest()]
    (ROOT / 'research/reports/age_sir_agreement_20261017.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(summary.to_string())
    print(counts)


if __name__ == '__main__':
    main()

