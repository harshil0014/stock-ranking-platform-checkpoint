# V18: bounded research beyond V17

## Verdict: V17 REMAINS BEST CHALLENGER

Best defensible research model: **V17 targeted ATH60 ensemble**. Frozen production champion remains **d499580**. Nothing deployed.

Compared 34 new configurations across10 trained families,8 registered pair/triple mixtures and6 seed/confidence controls. The reported new candidate is **regime_utility+neural_moe__0.1**; it is **rejected**, not a replacement for V17.

## Selection and complete comparison

All selection used2020–2023. Earlier trainable dates and already-exposed2024–2025 are contextual evaluation only. Mean XIRR had zero selection weight. Median-XIRR entries below are equal-weight averages of each date/profile Top20 median, not portfolio CAGR. Drawdown is mean selected-asset drawdown, not a simulated portfolio drawdown; less negative is better. All returns and rates are decimals.

| period | model | median_xirr_top20 | target_achievement_top20 | target_shortfall_top20 | mean_asset_drawdown_top20 | ndcg20 |
| --- | --- | --- | --- | --- | --- | --- |
| development_2020_2023 | champion | 0.3501 | 0.5618 | 0.0828 | -0.3540 | 0.5254 |
| development_2020_2023 | new | 0.5619 | 0.6090 | 0.0556 | -0.2669 | 0.5979 |
| development_2020_2023 | v17 | 0.5738 | 0.6014 | 0.0607 | -0.3064 | 0.5811 |
| early_2016_2019 | champion | -0.0526 | 0.2781 | 0.1545 | -0.3784 | 0.4917 |
| early_2016_2019 | new | -0.0160 | 0.2979 | 0.1345 | -0.3294 | 0.5425 |
| early_2016_2019 | v17 | -0.0386 | 0.2858 | 0.1424 | -0.3497 | 0.5244 |
| exposed_2024_2025 | champion | -0.0328 | 0.3454 | 0.1354 | -0.4428 | 0.5660 |
| exposed_2024_2025 | new | 0.4602 | 0.5704 | 0.0815 | -0.3906 | 0.7336 |
| exposed_2024_2025 | v17 | 0.3569 | 0.5375 | 0.0951 | -0.4083 | 0.7073 |

### New candidate acceptance checks

| check | passed |
| --- | --- |
| champion_strict | False |
| v17_return | False |
| v17_drawdown | True |
| v17_achievement | True |
| v17_shortfall | True |
| v17_ndcg | True |
| profile_return | False |
| profile_drawdown | True |
| utility_gain | True |
| three_years | True |

### Every development profile: new candidate minus V17

| profile | median_xirr_top20_delta | target_achievement_top20_delta | target_shortfall_top20_delta | mean_asset_drawdown_top20_delta | ndcg20_delta |
| --- | --- | --- | --- | --- | --- |
| lookback12 | -0.0437 | 0.0125 | 0.0011 | 0.0263 | 0.0023 |
| lookback60 | -0.0329 | -0.0062 | -0.0029 | 0.0360 | 0.0001 |
| target10 | -0.0273 | -0.0187 | -0.0054 | 0.0484 | 0.0114 |
| amount1000 | -0.0263 | 0.0187 | -0.0052 | 0.0482 | 0.0150 |
| amount50000 | -0.0116 | 0.0219 | -0.0053 | 0.0336 | 0.0211 |
| quarterly | -0.0090 | 0.0156 | -0.0056 | 0.0388 | 0.0252 |
| target30 | -0.0026 | -0.0000 | -0.0067 | 0.0396 | 0.0263 |
| weekly | 0.0064 | 0.0094 | -0.0073 | 0.0402 | 0.0213 |
| base7500 | 0.0401 | 0.0156 | -0.0087 | 0.0443 | 0.0288 |

## Historical coverage and robustness

44 trainable decision dates, all9 profiles;6 earlier2015 dates have no matured prior training labels and are explicitly unavailable. Training labels always mature strictly before each fitted decision block. V17/experimental candidates use annual development/exposed refits; frozen champion uses its original per-date recipe refits. Earlier contextual evaluation refits each date. See early_training_audit.json, training_audit.json and final_training_audit.json.

All7 robustness cohorts are evaluated for every profile and period: short history, full history, high volatility, deep drawdown, deep ATH, old ATH, recent ATH. Both within-cohort rankings and representation/outcomes inside overall Top20 are saved in all_cohorts.csv. Variant robustness, including the inherited V17 alternate seeds and per-date refits, is retained without concealing profile regressions. Year-block intervals are conditional diagnostics, not selection-adjusted significance claims.

### Development cohort comparison (all profiles)

| cohort | model | share_overall_top20 | median_xirr_top20 | mean_asset_drawdown_top20 |
| --- | --- | --- | --- | --- |
| short_history | champion | 0.0670 | 0.1565 | -0.3716 |
| short_history | v17 | 0.0813 | 0.1837 | -0.3634 |
| short_history | new | 0.0788 | 0.2214 | -0.3573 |
| full_history | champion | 0.9295 | 0.3279 | -0.3551 |
| full_history | v17 | 0.9128 | 0.5376 | -0.2981 |
| full_history | new | 0.9167 | 0.5242 | -0.2626 |
| high_volatility | champion | 0.2313 | 0.4733 | -0.4325 |
| high_volatility | v17 | 0.0594 | 0.5194 | -0.4503 |
| high_volatility | new | 0.0177 | 0.5333 | -0.4408 |
| deep_drawdown | champion | 0.8316 | 0.4292 | -0.3685 |
| deep_drawdown | v17 | 0.8347 | 0.5257 | -0.3150 |
| deep_drawdown | new | 0.8052 | 0.4878 | -0.2807 |
| deep_ath | champion | 0.6038 | 0.4536 | -0.3943 |
| deep_ath | v17 | 0.6931 | 0.5034 | -0.3240 |
| deep_ath | new | 0.6639 | 0.4852 | -0.2834 |
| old_ath | champion | 0.6316 | 0.4530 | -0.3799 |
| old_ath | v17 | 0.7382 | 0.5414 | -0.3146 |
| old_ath | new | 0.7215 | 0.5125 | -0.2736 |
| recent_ath | champion | 0.2108 | 0.2193 | -0.3304 |
| recent_ath | v17 | 0.1708 | 0.2445 | -0.3168 |
| recent_ath | new | 0.1698 | 0.2689 | -0.3096 |

## Current inference

All4,436 V7 stocks ×9 profiles =39,924 rows retained; 29,295 winner scores. Unscored/quarantined rows remain in current_rankings.csv.gz with their existing reasons. Top20/50/100 files are for the winning model across all9 profiles; separate new-candidate lists retain the rejected alternative for review. Scores reproduced from saved models to numerical precision.

Base profile Top20:

| winner_rank | ticker | isin | strict_cagr_1y | days_since_recorded_high | distance_from_recorded_high |
| --- | --- | --- | --- | --- | --- |
| 1.0000 | MWL | INE0JYY01029 | 0.6071 | 8.0000 | -0.0336 |
| 2.0000 | BSE-543373 | INE0HLJ01013 | 0.7887 | 0.0000 | 0.0000 |
| 3.0000 | SJS | INE284S01014 | 0.5875 | 38.0000 | -0.1569 |
| 4.0000 | ANANDRATHI | INE463V01026 | 0.4601 | 23.0000 | -0.0502 |
| 5.0000 | NYKAA | INE388Y01029 | 0.3506 | 1765.0000 | -0.2180 |
| 6.0000 | BSE-543953 | INE0OWC01011 | 0.2736 | 42.0000 | -0.1216 |
| 7.0000 | ABSLAMC | INE404A01024 | 0.3266 | 100.0000 | -0.1522 |
| 8.0000 | BSE-543543 | INE0IZQ01016 | 2.0802 | 186.0000 | -0.1001 |
| 9.0000 | STEELCAS | INE124E01038 | 0.3994 | 1.0000 | -0.0550 |
| 10.0000 | YATHARTH | INE0JO301016 | 0.4446 | 8.0000 | -0.1106 |
| 11.0000 | NUVAMA | INE531F01023 | 0.3636 | 69.0000 | -0.1408 |
| 12.0000 | AARTIPHARM | INE0LRU01027 | -0.0846 | 2.0000 | -0.0044 |
| 13.0000 | ACUTAAS | INE00FF01025 | 1.3405 | 90.0000 | -0.1342 |
| 14.0000 | TEGA | INE011K01018 | -0.0379 | 689.0000 | -0.0454 |
| 15.0000 | BSE-543616 | INE0MKA01014 | -0.0104 | 3.0000 | -0.0821 |
| 16.0000 | BSE-519413 | INE673U01014 | 2.2823 | 8191.0000 | -0.8928 |
| 17.0000 | PRUDENT | INE00F201020 | 0.2078 | 31.0000 | -0.1511 |
| 18.0000 | RRKABEL | INE777K01022 | 0.9711 | 31.0000 | -0.1401 |
| 19.0000 | PAYTM | INE982J01020 | 0.5048 | 13.0000 | -0.1048 |
| 20.0000 | KRISHIVAL | INE0GGO01015 | -0.1048 | 345.0000 | -0.2147 |

## NYKAA diagnostic

| profile_name | champion_rank | v17_rank | new_rank | winner_rank | strict_cagr_1y | cagr_3y | days_since_recorded_high | distance_from_recorded_high | evidence_confidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| amount1000 | 5.0000 | 5.0000 | 4.0000 | 5.0000 | 0.3506 | 0.3060 | 1765.0000 | -0.2180 | 0.8750 |
| amount50000 | 5.0000 | 5.0000 | 4.0000 | 5.0000 | 0.3506 | 0.3060 | 1765.0000 | -0.2180 | 0.8750 |
| base7500 | 5.0000 | 5.0000 | 4.0000 | 5.0000 | 0.3506 | 0.3060 | 1765.0000 | -0.2180 | 0.8750 |
| lookback12 | 9.0000 | 35.0000 | 24.0000 | 35.0000 | 0.3506 | 0.3060 | 1765.0000 | -0.2180 | 0.8750 |
| lookback60 | nan | nan | nan | nan | 0.3506 | 0.3060 | 1765.0000 | -0.2180 | 0.8750 |
| quarterly | 5.0000 | 5.0000 | 3.0000 | 5.0000 | 0.3506 | 0.3060 | 1765.0000 | -0.2180 | 0.8750 |
| target10 | 2.0000 | 2.0000 | 3.0000 | 2.0000 | 0.3506 | 0.3060 | 1765.0000 | -0.2180 | 0.8750 |
| target30 | 6.0000 | 5.0000 | 4.0000 | 5.0000 | 0.3506 | 0.3060 | 1765.0000 | -0.2180 | 0.8750 |
| weekly | 5.0000 | 5.0000 | 4.0000 | 5.0000 | 0.3506 | 0.3060 | 1765.0000 | -0.2180 | 0.8750 |

No NYKAA or company-identity predictor or ranking override exists. The diagnostic is after selection. Five-year missingness reduces evidence confidence; it does not impose a bad-company penalty. ATH age, depth and underwater duration enter learned interactions; reported conditional sensitivities retain both favorable and unfavorable exceptions.

Current peer/fundamental context is preserved in v17_current_peer_diagnostics.csv. It explains the current universe only. No current Screener, professor, Yahoo fundamentals or industry classifications were copied backward. The lack of dated historical fundamentals means this requirement cannot honestly be claimed as a validated historical ranking contribution.

## Weaknesses and stopping

V17 has conditional profile instability under alternate seeds/refit schedules and can worsen drawdown inside the high-volatility cohort. Current and early-period weaknesses are visible in the full tables. No model earns production promotion from this evidence.

The sensible registered search was completed, rather than extending thresholds or optimizing exposed dates. This is a bounded research conclusion within the available data and compute, not proof that no better model exists. A larger unbounded adaptive search on the same exposed dates would not create independent evidence.

- Development adaptivity:39 prior V17 and34 additional V18 configurations. No untouched validation.
- Fixed-universe survivorship and provider revision risks remain.
- Current corporate-action completeness after2026-09-18 remains unproved; existing quarantine retained.
- Small number of calendar regimes; block intervals do not adjust for adaptive selection.

## Reproduction

Runner: research/runners/personalized_v18_20261003.py. Stages: prepare, round1, early_predictions, round2, robustness, final_scores, evaluation, diagnostics, report, audit. Lock-writing stages intentionally refuse to overwrite locks. Existing frozen V17 inputs and d499580 are hashed and read-only. No deployment or production code changes.

## Research sources

- [Ranking, quantile, robust regression and constraints.](https://lightgbm.readthedocs.io/en/stable/Parameters.html)
- [Market-conditioned feature relevance; adapted as regime features and neural gating, not replication.](https://arxiv.org/abs/2312.15235)
- [Pairwise/listwise asset ranking alternatives.](https://arxiv.org/abs/2012.07149)
- [Nonlinear return predictors.](https://www.nber.org/papers/w25398)
- [Bounded ledger and explicit adaptive development limitations.](https://escholarship.org/uc/item/4w1110bb)