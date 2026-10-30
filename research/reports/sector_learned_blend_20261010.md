# Learned replacements for the current champion — completed 11 October 2026

Six replacements were tested within the retained champion: four nonnegative learned blends and two pretrained TabPFN v2 outer-blend replacements. Existing price engineering, stock identity, action checks and base components remain. This is a component replacement experiment, not a claim that every hand-written line has been replaced.

## What was learned

- Outer NNLS replaces the 75/25 guarded/LightGBM blend. Nested NNLS also replaces the guarded layer’s 80/20 weights. Targets are return percentile or the existing balanced return/drawdown/shortfall target.
- TabPFN uses the original v2 pretrained regressor checkpoint and two champion-component inputs. Context sizes 256/768 are sampled with equal query weighting. We adapt through in-context examples, without gradient fine tuning or finance-specific pretrained weights. One ensemble member is a CPU feasibility choice.
- Annual fits use completed, out-of-time component predictions only. 2020–2021 use the unchanged champion because mature out-of-time meta-training labels do not exist. Active replacement years are 2022–2025. Current models use mature feedback before 3 October 2026.
- TabPFN first attempts an audited bilinear grid approximation. Bounds and probe inputs use training-time information only. Fits failing the approximation check use direct neural inference for every test row. Five fits use the grid and five use direct inference, including both current 4,436-stock exports. Probe accuracy is not an exact guarantee for every interpolated row.

## Comparison with the current champion

Development-selected replacement: `nnls_outer_return`. Selection uses development Top-3 regression counts, then all development counts. Recent results are not used for selection.

| Replacement | Improved cells | Regressed cells | Total | Passes all cells? |
|---|---:|---:|---:|---|
| nnls_outer_return | 574 | 692 | 1296 | False |
| nnls_outer_balanced | 486 | 800 | 1296 | False |
| tabpfn_v2_context256 | 244 | 1050 | 1296 | False |
| nnls_nested_return | 356 | 936 | 1296 | False |
| nnls_nested_balanced | 363 | 925 | 1296 | False |
| tabpfn_v2_context768 | 199 | 1097 | 1296 | False |

Each cell is a period/profile/scope/return-treatment/Top-N/metric combination. Six metrics cover XIRR, drawdown, achievement, shortfall, NDCG and rank correlation. These cell counts are not independent statistical tests.

### Recent 2024–2025 expanded-universe Top 3, capped returns

| Model | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |
|---|---:|---:|---:|---:|---:|---:|
| current_champion | -0.22% | -31.31% | 22.93% | 0.1176 | 0.6371 | 0.1521 |
| nnls_nested_balanced | -0.43% | -31.62% | 22.82% | 0.1188 | 0.6356 | 0.1501 |
| nnls_nested_return | -0.44% | -31.87% | 22.90% | 0.1199 | 0.6335 | 0.1492 |
| nnls_outer_balanced | -0.29% | -31.36% | 22.76% | 0.1181 | 0.6369 | 0.1508 |
| nnls_outer_return | -0.21% | -31.34% | 22.86% | 0.1177 | 0.6376 | 0.1515 |
| tabpfn_v2_context256 | -4.20% | -36.32% | 22.42% | 0.1393 | 0.5935 | 0.0616 |
| tabpfn_v2_context768 | -0.51% | -32.36% | 23.32% | 0.1208 | 0.6281 | 0.1439 |

### Whole-sector pair ordering

| Scope | Period | Model | Correct pair order, ties half credit |
|---|---|---|---:|
| common | development | current_champion | 50.85% |
| common | development | nnls_outer_return | 50.83% |
| common | development | tabpfn_v2_context256 | 50.48% |
| common | development | tabpfn_v2_context768 | 49.46% |
| common | exposed | current_champion | 55.36% |
| common | exposed | nnls_outer_return | 55.35% |
| common | exposed | tabpfn_v2_context256 | 52.14% |
| common | exposed | tabpfn_v2_context768 | 55.06% |
| expanded | development | current_champion | 51.02% |
| expanded | development | nnls_outer_return | 51.02% |
| expanded | development | tabpfn_v2_context256 | 50.34% |
| expanded | development | tabpfn_v2_context768 | 49.50% |
| expanded | exposed | current_champion | 55.30% |
| expanded | exposed | nnls_outer_return | 55.29% |
| expanded | exposed | tabpfn_v2_context256 | 52.17% |
| expanded | exposed | tabpfn_v2_context768 | 55.06% |

Pair accuracy concerns later SIP XIRR ordering; it is not a probability of making money.

## Decision and verification

Retained model: `rank_xendcg_balanced_blend0.25`. 0 of six replacements satisfy every comparison against the champion. No live UI switch was made.
All six current variants score 4,436 unique stocks; 4303 have usable rebuilt price inputs. Scoring coverage does not fill the remaining data gaps. All exports retain input-status flags.
Reconstructed learned linear scores and interpolated scores and checked saved direct predictions across all 797,443 historical rows and current exports; maximum score error 2.98e-08. Both current TabPFN models were also independently refitted from their saved contexts and rerun directly for all 4,436 stocks. Historical direct predictions were not all independently rerun. Direct neural CSV scores reproduce bit-for-bit at their original float32 precision; the roughly 3e-8 float64 difference is decimal serialization, not a model discrepancy. Verified temporal cutoffs, current sector ranks, identical benchmark populations and unchanged champion metrics.

These dates and historical datasets have been researched repeatedly. This is not fresh holdout validation. Base components retain previously documented price/outcome limitations. The snapshot remains 3 October 2026. The new pretrained model cannot repair missing source data or make current ranking judgments objectively true.

## Sources and reproducibility

[TabPFN Nature paper](https://www.nature.com/articles/s41586-024-08328-6), [official implementation and v2 licensing](https://github.com/PriorLabs/TabPFN), [Super Learner](https://biostats.bepress.com/ucbbiostat/paper222/), [scikit-learn nonnegative regression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LinearRegression.html). The temporal stacking here is inspired by Super Learner; its original theoretical guarantees are not asserted.

Local TabPFN package 2.2.1 uses v2 weights under the Prior Labs License (Apache 2.0 plus attribution). Local isolated dependencies avoid changing application libraries. Telemetry is disabled. The checkpoint hash, contexts, fitted weights, inference grids, cutoff audits and protocol are retained in the experiment directory.

Run `python research/runners/sector_learned_blend_20261010.py learn`, then `evaluate`, then `python research/runners/finish_sector_learned_blend_20261010.py`. Dependencies for the worker are isolated in `experiments/premodel_dependencies_20261010`.
