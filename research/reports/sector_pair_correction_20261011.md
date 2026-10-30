# CatBoost pairwise sector correction - 11 October 2026

## What changed

Added a PairLogit correction layer starting from the existing champion sector percentile. This is a new objective and role for CatBoost; earlier research already tested CatBoost YetiRank as a standalone ranking component. Four learners combine return/balanced pair targets with uniform/mistake-emphasized pairs. Three correction strengths produce 12 candidates, alongside two previously evaluated LightGBM controls. CatBoost is open-source gradient boosting trained here, not a downloaded financial pretrained model.

Training samples up to 1,500 complete date/profile/sector queries and 64 distinct stock pairs per query. Every query contributes the same total pair weight. The mistake variant doubles misordered-pair weights before normalization. All new training uses matured outcomes and historical out-of-time component scores. Baseline addition semantics and serialized predictions are verified.

2020-2021 retain the champion because no mature meta-training outcomes are available. Correction fits cover 2022-2025 plus the current frozen 2026-10-03 snapshot. All 4,436 stocks receive scores; 4,303 have usable current price features. The other 133 retain zero correction and explicit evidence flags. Their ordinal rank can still move when peers move. Unclassified/small groups remain in exports but are excluded from the historical sector metrics.

Development 2020-2023 selects a whole-sector rank-IC leader and a Top3 conservative leader before recent 2024-2025 evaluation. These dates have been exposed by earlier research; this is not fresh validation. The base champion itself was also selected using reused historical evidence. This experiment cannot establish unbiased prospective performance.

## All benchmark cells

| Model | Improved | Regressed | Tied | Passes no-regression gate |
|---|---:|---:|---:|---|
| catpair_return_mistakes_w0.1 | 650 | 628 | 18 | False |
| catpair_return_uniform_w0.1 | 659 | 615 | 22 | False |
| lgb_return_full_d3_w0.1 | 761 | 465 | 70 | False |
| lgb_return_full_d3_w0.5 | 551 | 745 | 0 | False |

Each model has 1,296 cells: two periods, nine profiles, Top1/3/5, common/expanded populations, raw/capped returns and six metrics. They are correlated comparisons, not independent tests.

## Recent whole-sector pair-order accuracy

| Model | Correct pair order |
|---|---:|
| catpair_return_mistakes_w0.1 | 55.3063% |
| catpair_return_uniform_w0.1 | 55.3073% |
| current_champion | 55.3024% |
| lgb_return_full_d3_w0.1 | 55.3051% |
| lgb_return_full_d3_w0.5 | 55.3393% |

Pair accuracy compares subsequent SIP-XIRR order within the same sector/date/profile; ties earn half credit. It is not an investment success probability.

## Recent expanded Top3, capped returns

| Model | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |
|---|---:|---:|---:|---:|---:|---:|
| catpair_return_mistakes_w0.1 | -0.45% | -31.41% | 22.87% | 0.1179 | 0.6367 | 0.1519 |
| catpair_return_uniform_w0.1 | -0.36% | -31.40% | 22.82% | 0.1181 | 0.6361 | 0.1522 |
| current_champion | -0.22% | -31.31% | 22.93% | 0.1176 | 0.6371 | 0.1521 |
| lgb_return_full_d3_w0.1 | -0.20% | -31.31% | 22.96% | 0.1174 | 0.6373 | 0.1522 |
| lgb_return_full_d3_w0.5 | -0.02% | -31.73% | 23.62% | 0.1187 | 0.6366 | 0.1525 |

## Descriptive uncertainty

| Candidate | Mean sector pair-order delta (pp) | 95% sector-resampling interval (pp) |
|---|---:|---:|
| catpair_return_mistakes_w0.1 | +0.0038 | [-0.0150, +0.0210] |
| catpair_return_uniform_w0.1 | +0.0049 | [-0.0054, +0.0147] |
| lgb_return_full_d3_w0.1 | +0.0026 | [+0.0008, +0.0048] |
| lgb_return_full_d3_w0.5 | +0.0377 | [-0.0444, +0.1140] |

The bootstrap averages profiles within each sector, then sectors; the main accuracy table averages sectors within each profile, then profiles. Missing sector/profile combinations can therefore produce slightly different deltas. These intervals describe reused-sample dispersion; they do not correct for repeated model searches.

## Decision and verification

0 finalists passed the no-regression gate. The existing champion remains in the live system; this experiment does not replace it. All 20 saved CatBoost models replayed across all historical/current scores, with maximum error 2.22e-16. Cutoffs, training identities, pair orientation and query boundaries, prior control scores, all benchmark query counts, and every current rank passed verification. Three focused tests passed. All current scores and ranks are exported, with stock-level rank changes and sector-level accuracy differences.

## Sources

- [CatBoost peer-reviewed algorithm paper](https://proceedings.neurips.cc/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html).
- [Official pairwise ranking objectives](https://catboost.ai/docs/en/concepts/loss-functions-ranking).
- [Official baseline training and inference examples](https://catboost.ai/docs/en/concepts/python-usages-examples).

Run: python research/runners/sector_pair_correction_20261011.py learn; then development; then recent; then python research/runners/finish_sector_pair_correction_20261011.py.
