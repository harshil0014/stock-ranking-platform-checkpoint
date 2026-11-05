# Champion rank-error correction and benchmark audit

Four annual models learned future within-sector SIP return percentile minus the champion percentile, using only labels mature before each test year. Two fixed policies use the same predicted correction, either directly or with professor-factor constraints on sectorTop3. This is adaptive development research following earlier results. No2024–2025scores were computed for these new policies.

## Development results, 2020–2023

| Policy | RankIC | Goal hit delta pp | Professor alignment delta pp | SectorTop3 sets changed | Top20XIRR gain pp | Top20DD gain pp | Matched dates |
|---|---:|---:|---:|---:|---:|---:|---:|
| champion | 0.032179 | +0.000 | +0.000 | 0.00% | +0.00 | +0.00 | 16 |
| error_corrected_raw | 0.032154 | +0.087 | -0.255 | 3.13% | +5.53 | +0.66 | 16 |
| error_corrected_professor | 0.032180 | +0.000 | +0.000 | 0.00% | +5.44 | +0.60 | 16 |

The constrained policy leaves every sectorTop3 set unchanged. Its globalTop20gain therefore comes from changing which sector leaders enter a cross-sector portfolio. It is not evidence of better within-sector Top3 picks. Ranking IC is essentially unchanged. Positive DDdelta means lower drawdown. The reference above is the existing within-sector-percentile-normalized champion used by these research pilots.

## Stronger benchmark controls

Many sector leaders share a normalized score of1.0. Earlier globalTop20replays break exact ties byISIN, so the global portfolio can be sensitive to that convention. After seeing the correction gain, we added a raw-champion-score portfolio and100random boundary-tie controls. Selections were made before checking outcomes. Unknown selected outcomes block that observation with no replacement. Each pair reports its own matched support. This is a diagnostic, not an additional selection step.
- error_corrected_raw versus champion: +5.53pp on16matched dates.
- error_corrected_raw versus champion_raw_global: +14.12pp on15matched dates.
- error_corrected_professor versus champion: +5.44pp on16matched dates.
- error_corrected_professor versus champion_raw_global: +14.02pp on15matched dates.
- error_corrected_raw versus100tie-control draws: median mean matched XIRR delta +4.03pp, range[-1.77,+9.07]pp. Matched support ranges16–16dates. These random controls measure tie sensitivity on adaptively reused dates and do not supply independent validation.
- error_corrected_professor versus100tie-control draws: median mean matched XIRR delta +3.94pp, range[-1.87,+8.98]pp. Matched support ranges16–16dates. These random controls measure tie sensitivity on adaptively reused dates and do not supply independent validation.

## Concentration checks

- error_corrected_raw: median date gain +0.00pp,winsorized +5.76pp,worst leave-one-date-out +4.33pp,worst leave-one-security-out +4.25pp. Descriptive block95%interval[+1.13,+9.62]pp.
- error_corrected_professor: median date gain +0.00pp,winsorized +5.67pp,worst leave-one-date-out +4.23pp,worst leave-one-security-out +4.16pp. Descriptive block95%interval[+1.11,+9.47]pp.

Removed stock allocations stay as0%cash in both portfolios, with no refill. Single-stock terminal labels reproduce the existing actual-next-open portfolioXIRRs to1e-8before attribution. Raw-control and tie-control returns use that same verified terminal-wealth aggregation,100bp per side and identical monthly30daycashflows. These are overlapping12monthcohorts and a survivor-only,five-year-factor-complete sample. No fresh validation or proprietary-software comparison is claimed.

## Relation to the earlier locked candidate

The earlier risk_constrained_high policy was locked before its2024–2025transfer test. It gained2.34pp in development but lost0.78pp in later matchedTop20XIRR, with3.61ppworse drawdown. That lock and all failed results are retained. The error-correction policies were designed afterward and are evaluated only on development here. This distinction is required when reading the apparently larger correction gain.

## Verification

Nine residual/optimizer tests passed before this round. Fold receipts prove all training label endpoints preceded the corresponding test year. Four LightGBMmodels use one compute thread and fixed settings. Model files stay in ignoredwork with SHA256fold receipts. The actual professor-constrained output memberships are evaluated by the existing shared replay. The production website and prospective ledger retain their existing model configuration.

## Double-cost diagnostic

The same frozen selections were replayed using actual adjusted opens at200bp per side, after primary results. No scores or stock sets were changed.
- error_corrected_raw: Top20SIPXIRR gain +5.36pp,drawdown gain +0.70pp,16matched dates.
- error_corrected_professor: Top20SIPXIRR gain +5.28pp,drawdown gain +0.64pp,16matched dates.

## Distribution across dates

The professor-preserving policy improves7of16dates, ties8, and loses1. Its median date improvement is zero. Annual average differences are 2020: +0.00pp, 2021: +0.00pp, 2022: +12.32pp, 2023: +9.45pp.
