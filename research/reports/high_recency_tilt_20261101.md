# Champion with stronger high-recency preference

Selected preference: **recency20**. This selection optimizes the requested preference within the frozen tradeoff budgets; it is not a demonstrated predictive improvement. Default champion remains unchanged. Exposed period was not evaluated.

Lower days since the last recorded closing high receives a higher within-sector percentile. Score = (1-w) × champion percentile + w × high-recency percentile. The champion already contains high-related information; these coefficients are additional explicit score weights, not total feature importance. Other professor factors receive no new explicit weight in this round.

## Development comparison, 2020–2023

Differences are challenger minus champion. Positive drawdown difference means less severe drawdown. Top3 statistics are date-balanced sector averages; Top20 portfolio comparisons use each candidate’s matched valid dates.

| Preference | High-recency gain (percentile points) | Mean high age change (days) | Changed sector Top3 | IC delta | Goal hit delta (pp) | Top3 drawdown delta (pp) | Top20 XIRR delta (pp) | Top20 drawdown delta (pp) | Portfolio dates | Qualifies |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| recency10 | +3.91 | -201.1 | 19.3% | -0.00299 | +0.28 | +0.15 | -1.02 | -0.36 | 16 | False |
| recency20 | +7.34 | -362.2 | 36.6% | -0.01223 | -0.25 | -0.11 | -1.45 | -0.76 | 16 | True |
| recency35 | +12.00 | -590.0 | 60.6% | -0.02981 | -1.06 | -0.88 | -0.42 | -0.86 | 15 | False |
| recency50 | +15.43 | -758.3 | 77.0% | -0.04911 | -1.00 | -1.40 | +1.21 | -0.88 | 15 | False |

## Selection and scope

Greatest weight passing all preregistered limits: positive recency gain, at least20% changed Top3 sets, IC loss<=0.02, goal-hit/stock drawdown/portfolio XIRR/portfolio drawdown worsening<=3pp, >=8 supported dates. No limits changed after results. These are user-preference tolerances, not significance thresholds.

Documented research attempts: 303 (four added). Registry remains incomplete; no full-history multiple-testing or predictive significance claim.

Development has already been reused adaptively. Overlapping cohorts, current-survivor universe, retrospective sector groups, recorded rather than certified lifetime highs, and missing/action-blocked observations limit conclusions. Portfolio replay uses existing next-open fills and100bp per side, with price-only adjusted histories and existing unresolved-action blocks. This round does not claim full corporate-action or dividend completeness. Joint complete Top3 cohorts are held fixed across this candidate family; portfolio pairs can differ in date support. See annual and failure CSVs.

Selected variant IC changes from 0.03105 to 0.01882. That is a 39.4% reduction in the small positive pooled IC: passing the absolute tolerance does not make this a negligible accuracy cost. Annual metrics must be read alongside the pooled preference choice.

## Saved snapshot preference ranking

Snapshot **2026-10-03**, 2396 eligible stocks in 50 sectors. Top3 membership changes in **22/50 sectors**; average overlap **83.33%**. Local CSV includes baseline and preference ranks, raw high age, and both score components. This is a stale saved snapshot, not live investment picks. Ineligible stocks are not silently assigned neutral factor values. No UI/default/ledger promotion.

Independent CSV review verified the file hash, unique stock count, every blend calculation and each sector’s deterministic preference ordering.

## Verification

7 runner checks passed: development-only dates, fixed four-candidate count, blend endpoints, monotonic recency direction, finite bounded scores, unique rows and prior ledger IDs preserved. Existing low-load governor enforced one compute thread,12.5% CPU cap and4s/2s duty cycle. No training or GPU.

Evidence: `experiments/high-recency-tilt-20261101/`; protocol: `research/protocols/high_recency_tilt_20261101.md`.
