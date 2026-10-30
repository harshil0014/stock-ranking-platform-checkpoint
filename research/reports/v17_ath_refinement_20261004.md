# V17 ATH-age refinement research

## Decision

**V17 REMAINS BEST CHALLENGER — V17 refined retained.**

Completed 120 configurations across separately locked rounds: 48 smooth ATH-age adjustments, 24 blends using four newly trained age-aware models, and 48 conditional expert blends. Development gate passes: 0. Website and frozen champion unchanged.

The user requested stronger days-since-high influence. This experiment tested that preference without targeting a company or choosing weights from current rankings. A lower NYKAA rank is not a selection criterion.

## What was tested

- Saturating age alone; age with ATH distance; age with depth and recovery; age with depth and momentum. Six strengths, full-profile and 36-month routes. No hard age cutoff.
- Four retrained families: monotone age-aware utility, unconstrained age interactions, return-focused age model, and residual correction. Expanding annual training with outcome endpoints strictly before each scored year.
- Nine profiles and all 16 development dates (2020–2023). Mean XIRR has zero selection weight. No 2024–2025 results used for selection.
- Post-lock evaluation covers 44 valid decision dates, all nine profiles, seven robustness cohorts plus the complete universe. Current evaluation includes all 4,436 V7 stocks.
- Prior 2020–2023 experimentation creates model-selection overfitting risk. 2024–2025 is exposed, not a fresh holdout. No NEW CHAMPION claim is available from this research alone.

## Historical comparison

Metrics are averages across decision-date/profile groups; XIRR is the average of each group's Top20 median, not mean stock XIRR. Drawdown is negative: closer to zero is better.

| Period | Model | Top20 median XIRR | Target achievement | Target shortfall | Mean asset drawdown | NDCG@20 |
|---|---|---:|---:|---:|---:|---:|
| development | New ATH candidate (diagnostic) | 59.96% | 61.28% | 5.44% | -26.79% | 0.6040 |
| development | d499580 | 35.01% | 56.18% | 8.28% | -35.40% | 0.5254 |
| development | V17 refined | 58.63% | 61.18% | 5.74% | -28.35% | 0.5972 |
| development | Original V17 | 57.38% | 60.14% | 6.07% | -30.64% | 0.5811 |
| early | New ATH candidate (diagnostic) | -3.40% | 28.65% | 13.96% | -33.37% | 0.5303 |
| early | d499580 | -5.26% | 27.81% | 15.45% | -37.84% | 0.4917 |
| early | V17 refined | -3.27% | 29.17% | 13.83% | -33.91% | 0.5315 |
| early | Original V17 | -3.86% | 28.58% | 14.24% | -34.97% | 0.5244 |
| exposed | New ATH candidate (diagnostic) | 55.66% | 57.64% | 8.67% | -40.31% | 0.7305 |
| exposed | d499580 | -3.28% | 34.54% | 13.54% | -44.28% | 0.5660 |
| exposed | V17 refined | 53.17% | 56.11% | 9.05% | -40.53% | 0.7190 |
| exposed | Original V17 | 35.69% | 53.75% | 9.51% | -40.83% | 0.7073 |

Locked diagnostic candidate: `age_monotone_0.1_all`. Failed development checks: champion, profile_return. A diagnostic candidate is not promoted because it looks attractive on one metric.

## Profile weaknesses of the new candidate

| Profile | Change in median XIRR (percentage points) | Change in drawdown (percentage points) |
|---|---:|---:|
| amount1000 | +1.87 | +1.21 |
| amount50000 | -0.01 | +1.53 |
| base7500 | +0.30 | +2.48 |
| lookback12 | +13.00 | +1.14 |
| lookback60 | -6.11 | +1.61 |
| quarterly | -1.62 | +2.01 |
| target10 | +3.00 | +1.62 |
| target30 | -0.67 | +0.70 |
| weekly | +2.15 | +1.73 |

## NYKAA and ATH data

NYKAA's adjusted closing high is 1 December 2021. The stored 1,765 days is measured to the last quote; it is 1,767 days at the 3 October decision date. Corporate-action-adjusted execution history independently agrees with the high and distance. Its 2022 bonus does not explain away the old high.
All 4,345 usable provider histories exactly reproduced the stored age and distance. 203 histories contain repeated equal highs: the frozen feature takes the first occurrence. This is a documented feature-definition limitation; changing it only for current inference would introduce a training/inference mismatch. NYKAA is not one of these tie cases.

| Profile | V17 refined rank | New candidate diagnostic rank | Final retained rank |
|---|---:|---:|---:|
| amount1000 | 4 | 5 | 4 |
| amount50000 | 5 | 6 | 5 |
| base7500 | 4 | 6 | 4 |
| lookback12 | 43 | 27 | 43 |
| lookback60 | Unranked | Unranked | Unranked |
| quarterly | 4 | 6 | 4 |
| target10 | 2 | 5 | 2 |
| target30 | 5 | 6 | 5 |
| weekly | 4 | 6 | 4 |

## Current Top20 (default profile)

1. MWL, 2. BSE-543373, 3. ANANDRATHI, 4. NYKAA, 5. SJS, 6. BSE-543953, 7. ABSLAMC, 8. BSE-543543, 9. NUVAMA, 10. STEELCAS, 11. TEGA, 12. AARTIPHARM, 13. YATHARTH, 14. BSE-519413, 15. ACUTAAS, 16. BSE-521036, 17. SHYAMMETL, 18. BSE-543616, 19. KRISHIVAL, 20. PRUDENT

Top20/50/100 for every profile: `experiments/v17-ath-refinement-20261004/current_top20.csv`, `current_top50.csv`, `current_top100.csv`.

## Sources and interpretation

Academic work supports investigating high-price proximity and recency as signals, not assigning an arbitrary penalty to old all-time highs. The 52-week high and the all-time high are different concepts.

- George & Hwang, The 52-Week High and Momentum Investing: https://onlinelibrary.wiley.com/doi/full/10.1111/j.1540-6261.2004.00695.x
- The timing of 52-week high price and momentum: https://www.sciencedirect.com/science/article/pii/S0378426613002446
- Nykaa issuer bonus record-date filing: https://www.nykaa.com/media/wysiwyg/2021/Investors-Relations/pdfs/stock-exchange-filling/Intimation-of-Record-date-for-Bonus-Issue.pdf

## Audit trail

`protocol.json`, `trials.csv`, `details.json`, `training_audit.json`, `development_lock.json`, `robustness_lock.json`, `final_diagnostic_lock.json`, `all_period_profile_cohort_metrics.csv`, `provider_ath_reproduction.csv`, `current_stability.csv`, and `decision.json` reside in the experiment directory.

Original V17, V17 refined, runtime manifest and d499580 hashes remained unchanged. No stock-identity inputs, current fundamental backfills into history, deployed ranking changes, or exposed-period weight selection.
