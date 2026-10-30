# V17 refined — final research result

## Decision

**PROMISING CHALLENGER: V17 refined ensemble wins this research round.** No subsequent candidate earned V18: one specialist addition passed development but failed the locked robustness checks. d499580 remains frozen production. Nothing deployed.

## What changed

| issue | result |
| --- | --- |
| Available but unranked | 161/161 recovered;0 AVAILABLE rows unranked; original scored values and coverage-onlyTop 20 preserved. |
| Corporate-action freshness | Public NSE catalogue and1,861/1,861 BSE receipts through 2026-10-04; 7 new actions; 5 automatic and 2 blocked pending mechanics.4,346/4,436 exact-symbol provider split receipts. Source coverage is verified, not a guarantee of unreported-event completeness. |
| 60M instability | Seven-seed ATH-constrained ensemble with confidence-weighted 35% correction; leave-one-seed-out, alternate-seed and per-date returns above champion. |
| High-volatility drawdown | Development improves 0.377 percentage points versus V17; remains weaker than d499580. Per-date and alternate-seed direction survives. |
| Extreme ATH/growth | Retained growth signal and conditional ATH logic; all profiles have negative average old/deep-high sensitivity, with a small 12M exception fraction; no company-specific or hard age penalty. |

## Original V17 vs refined V17 vs d499580

Equal-weight averages across date/profile baskets. Median XIRR is the average of each Top 20 basket median, not portfolio CAGR. Drawdown is average selected-asset drawdown, not a portfolio backtest. Rates below are decimals; less negative drawdown is better. Mean XIRR has zero selection weight.

| period | model | median_xirr_top20 | target_achievement_top20 | target_shortfall_top20 | mean_asset_drawdown_top20 | ndcg20 |
| --- | --- | --- | --- | --- | --- | --- |
| development_2020_2023 | d499580 | 0.3501 | 0.5618 | 0.0828 | -0.3540 | 0.5254 |
| development_2020_2023 | V17 refined | 0.5863 | 0.6118 | 0.0574 | -0.2835 | 0.5972 |
| development_2020_2023 | V17 | 0.5738 | 0.6014 | 0.0607 | -0.3064 | 0.5811 |
| early_2016_2019 | d499580 | -0.0526 | 0.2781 | 0.1545 | -0.3784 | 0.4917 |
| early_2016_2019 | V17 refined | -0.0327 | 0.2917 | 0.1383 | -0.3391 | 0.5315 |
| early_2016_2019 | V17 | -0.0386 | 0.2858 | 0.1424 | -0.3497 | 0.5244 |
| exposed_2024_2025 | d499580 | -0.0328 | 0.3454 | 0.1354 | -0.4428 | 0.5660 |
| exposed_2024_2025 | V17 refined | 0.5317 | 0.5611 | 0.0905 | -0.4053 | 0.7190 |
| exposed_2024_2025 | V17 | 0.3569 | 0.5375 | 0.0951 | -0.4083 | 0.7073 |

### Every development profile: refined minus original V17

| profile | median_xirr_top20_delta | target_achievement_top20_delta | target_shortfall_top20_delta | mean_asset_drawdown_top20_delta | ndcg20_delta |
| --- | --- | --- | --- | --- | --- |
| amount1000 | -0.0093 | 0.0062 | -0.0015 | 0.0352 | 0.0076 |
| amount50000 | 0.0180 | 0.0125 | -0.0020 | 0.0192 | 0.0126 |
| base7500 | 0.0402 | 0.0219 | -0.0069 | 0.0315 | 0.0281 |
| lookback12 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| lookback60 | 0.0080 | 0.0156 | 0.0007 | 0.0086 | 0.0075 |
| quarterly | -0.0097 | 0.0219 | -0.0027 | 0.0282 | 0.0196 |
| target10 | 0.0306 | -0.0094 | -0.0025 | 0.0240 | 0.0146 |
| target30 | 0.0372 | 0.0125 | -0.0067 | 0.0321 | 0.0300 |
| weekly | -0.0023 | 0.0125 | -0.0076 | 0.0275 | 0.0249 |

## Robustness and remaining weakness

All 44 trainable dates and 9 profiles were evaluated;6 initial 2015 dates have no matured prior labels. All 7 cohorts are evaluated for each profile in each period. Full per-date, profile and cohort tables are in evaluation/.2024–2025 was already exposed and never selected weights. Earlier 2016–2019 is contextual evaluation. Nested calendar-year bootstrap intervals are conditional and do not correct for adaptive selection.

| period | model | median_xirr_top20 | mean_asset_drawdown_top20 |
| --- | --- | --- | --- |
| early_2016_2019 | d499580 | -0.0967 | -0.4992 |
| early_2016_2019 | V17 | -0.0613 | -0.4933 |
| early_2016_2019 | V17 refined | -0.0712 | -0.4922 |
| development_2020_2023 | d499580 | 0.4733 | -0.4325 |
| development_2020_2023 | V17 | 0.5194 | -0.4503 |
| development_2020_2023 | V17 refined | 0.5342 | -0.4466 |
| exposed_2024_2025 | d499580 | -0.1346 | -0.4656 |
| exposed_2024_2025 | V17 | -0.0936 | -0.4589 |
| exposed_2024_2025 | V17 refined | -0.0846 | -0.4579 |

The high-volatility drawdown weakness is reduced, not eliminated relative to d499580. Development gains are not prospective evidence. Both frozen-universe survivorship and provider revision timing remain limitations. Current fundamentals and peers are diagnostic-only because dated historical snapshots are unavailable. No present-day values were backfilled.

Robustness details:

| variant | 60M_median_return_vs_champion | highvol_drawdown_vs_matched_V17 | aggregate_median_return_vs_matched_V17 | passed |
| --- | --- | --- | --- | --- |
| seed20261004 | 0.0213 | 0.0020 | 0.0355 | True |
| per_date | 0.0462 | 0.0034 | 0.0615 | True |

## Current 4,436-stock universe

39,924 rows retain all 4,436 stocks and 9 profiles. 29,817 are ranked; unresolved price/action/history cases keep explicit reasons. Freshness repair adds 540 previously unranked rows and blocks 18 formerly ranked rows (two identities across 9 profiles), net +522. The repaired model is applied to observed V7 prices at the frozen 2026-10-03 decision, with official-action retrieval through 2026-10-04.

Model-onlyTop 20 stability is measured against the same corrected data. Data-driven entries are reported separately: the 12M Top 20 retains 15/20 after newly verified stocks enter, while its model scores receive no new correction. Base profile retains 18/20 after model refinement.

| profile | top20_overlap | mean_absolute_rank_change |
| --- | --- | --- |
| amount1000 | 0.9000 | 76.7379 |
| amount50000 | 0.9000 | 76.8392 |
| base7500 | 0.9000 | 76.6298 |
| lookback12 | 1.0000 | 0.0000 |
| lookback60 | 0.8500 | 61.4101 |
| quarterly | 0.9500 | 77.3196 |
| target10 | 0.9500 | 75.9781 |
| target30 | 0.9000 | 77.1370 |
| weekly | 0.9000 | 76.4833 |

| profile | old_scored | new_scored | recovered | newly_quarantined | top20_overlap | mean_rank_move |
| --- | --- | --- | --- | --- | --- | --- |
| amount1000 | 3246 | 3304 | 60 | 2 | 1.0000 | 32.7441 |
| amount50000 | 3244 | 3296 | 54 | 2 | 1.0000 | 29.4531 |
| base7500 | 3238 | 3293 | 57 | 2 | 1.0000 | 30.7043 |
| lookback12 | 3687 | 3772 | 87 | 2 | 0.7500 | 55.7558 |
| lookback60 | 2913 | 2960 | 49 | 2 | 0.8500 | 29.8176 |
| quarterly | 3245 | 3304 | 61 | 2 | 1.0000 | 35.1292 |
| target10 | 3238 | 3293 | 57 | 2 | 1.0000 | 30.5000 |
| target30 | 3238 | 3293 | 57 | 2 | 1.0000 | 30.9910 |
| weekly | 3246 | 3302 | 58 | 2 | 1.0000 | 32.7734 |

### Base profileTop 20

| winner_rank | ticker | company |
| --- | --- | --- |
| 1.0000 | MWL | Mangalam Worldwide Limited |
| 2.0000 | BSE-543373 | Shri Venkatesh Refineries Limi |
| 3.0000 | ANANDRATHI | Anand Rathi Wealth Limited |
| 4.0000 | NYKAA | FSN E-Commerce Ventures Limited |
| 5.0000 | SJS | S.J.S. Enterprises Limited |
| 6.0000 | BSE-543953 | Khazanchi Jewellers Limited |
| 7.0000 | ABSLAMC | Aditya Birla Sun Life AMC Limited |
| 8.0000 | BSE-543543 | B-RIGHT REALESTATE LIMITED |
| 9.0000 | NUVAMA | Nuvama Wealth Management Limited |
| 10.0000 | STEELCAS | Steelcast Limited |
| 11.0000 | TEGA | Tega Industries Limited |
| 12.0000 | AARTIPHARM | Aarti Pharmalabs Limited |
| 13.0000 | YATHARTH | Yatharth Hospital & Trauma Care Services Limited |
| 14.0000 | BSE-519413 | DATIWARE MARITIME INFRA LIMITE |
| 15.0000 | ACUTAAS | Acutaas Chemicals Limited |
| 16.0000 | BSE-521036 | SOURCE INDUSTRIES (INDIA) LTD. |
| 17.0000 | SHYAMMETL | Shyam Metalics and Energy Limited |
| 18.0000 | BSE-543616 | Trident Lifeline Limited |
| 19.0000 | KRISHIVAL | Krishival Foods Limited |
| 20.0000 | PRUDENT | Prudent Corporate Advisory Services Limited |

Top 20/50/100 for all profiles: current_top20.csv, current_top50.csv, current_top100.csv. Full coverage/reasons: final_current_rankings.csv.gz.

## NYKAA

| profile_name | original_v17_rank | v17_refreshed_rank | winner_rank | days_since_recorded_high | distance_from_recorded_high | strict_cagr_1y | cagr_3y | evidence_confidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| amount1000 | 5.0000 | 5.0000 | 4.0000 | 1765.0000 | -0.2180 | 0.3506 | 0.3060 | 0.8750 |
| amount50000 | 5.0000 | 5.0000 | 5.0000 | 1765.0000 | -0.2180 | 0.3506 | 0.3060 | 0.8750 |
| base7500 | 5.0000 | 5.0000 | 4.0000 | 1765.0000 | -0.2180 | 0.3506 | 0.3060 | 0.8750 |
| lookback12 | 35.0000 | 43.0000 | 43.0000 | 1765.0000 | -0.2180 | 0.3506 | 0.3060 | 0.8750 |
| lookback60 | nan | nan | nan | 1765.0000 | -0.2180 | 0.3506 | 0.3060 | 0.8750 |
| quarterly | 5.0000 | 5.0000 | 4.0000 | 1765.0000 | -0.2180 | 0.3506 | 0.3060 | 0.8750 |
| target10 | 2.0000 | 2.0000 | 2.0000 | 1765.0000 | -0.2180 | 0.3506 | 0.3060 | 0.8750 |
| target30 | 5.0000 | 5.0000 | 5.0000 | 1765.0000 | -0.2180 | 0.3506 | 0.3060 | 0.8750 |
| weekly | 5.0000 | 5.0000 | 4.0000 | 1765.0000 | -0.2180 | 0.3506 | 0.3060 | 0.8750 |

NYKAA moves from original base rank 5 to refined rank 4. This was not a target. Its strong recent growth and goal fit coexist with an old high and missing true 5Y history. 60M remains insufficient-history; no price history is fabricated. Current fundamental/peer evidence is in nykaa_peer_context.csv and current_peer_diagnostics.csv.

## Search scope and reproducibility

130 repair configurations, 20 subsequent challenger configurations, and the earlier 34-candidate tournament are preserved. Failed candidates and exact gates remain in research_ledger.csv and per-round details. Current stability was a veto after development/robustness selection, never a weight-fitting target. There is no claim of having proved a global optimum.

Runners: research/runners/v17_refinement_20261004.py and v17_refinement_actions_20261004.py. Immutable protocols, selection locks, model weights, raw public-source receipts, maturity audits, numerical score reproduction, feature-family sensitivities, peer diagnostics and a SHA256 manifest accompany this report. Coverage repair writes research artifacts only; production application code is untouched.

Sources: [NSE corporate actions](https://www.nseindia.com/companies-listing/corporate-filings-actions), [BSE corporate actions](https://www.bseindia.com/corporates/corporates_act.html). Exact API URLs and raw-response hashes are recorded in actions/summary.json.

The legacy personalized-v18-20261003 directory names an earlier tournament, not an awarded V18 model. Historical coverage stays frozen for fair comparisons; the goal-window coverage repair applies to current inference only.
