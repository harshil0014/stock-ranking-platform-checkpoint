# TabPFN + LightGBM sector-ranking research — 11 October 2026

Built with PriorLabs-TabPFN. Internal research experiment; weights license is retained alongside the artifacts.

This round expands the original two-score TabPFN experiment to 18 price/profile/component inputs and two-member TabPFN ensembles. TabPFN predicts historical outcomes or residual errors; LightGBM students learn mixtures of these soft predictions and observed outcomes. There is no gradient fine tuning of the TabPFN checkpoint.

## Design

- 60 predeclared candidates: 36 TabPFN/LightGBM hybrids and 24 matched pool/full-data LightGBM controls. Two student depths, three correction strengths and two soft-label proportions are tested. All teacher models use local v2 pretrained weights.
- Each teacher uses 768 mature historical context rows. Teachers directly score a disjoint 4,096-row past-data pool; no approximation grid is used. LightGBM students then score the entire historical and current universe. Student rankings are their own models, not a claim of exact TabPFN equivalence.
- Outcome targets remain within-sector return percentile or the existing balanced return/downside/shortfall percentile target. Residual correction starts from the champion sector percentile. No usable feature evidence means zero correction.
- Meta-training uses completed out-of-time component predictions. 2020–2021 retain the champion; actual replacement fits cover 2022–2025 and the current snapshot. Development selects three finalists based on regression counts, plus the highest whole-sector rank-IC hybrid and control and exact target/depth/correction-weight pool controls for the selected hybrids (deduplicated). The accuracy-leader/matched-control amendment was recorded before any development metrics were calculated. All finalists are locked before later-period metrics are calculated. Earlier research has already exposed these historical dates.

## Selected finalists

| Model | Improved cells | Regressed cells | Total | No-regression gate |
|---|---:|---:|---:|---|
| pfn_balanced_absolute_soft1.0_d3_w0.1 | 614 | 264 | 1296 | False |
| lgb_return_full_d3_w0.1 | 761 | 465 | 1296 | False |
| lgb_balanced_pool_d5_w0.1 | 725 | 549 | 1296 | False |
| pfn_balanced_residual_soft1.0_d5_w0.5 | 556 | 730 | 1296 | False |
| lgb_return_full_d3_w0.5 | 551 | 745 | 1296 | False |
| lgb_balanced_pool_d3_w0.1 | 720 | 538 | 1296 | False |
| lgb_balanced_pool_d5_w0.5 | 206 | 1088 | 1296 | False |

Cells span two periods, nine profiles, common/expanded universes, raw/capped returns, Top1/3/5 and six metrics. Counts are not independent statistical tests.

## Recent expanded-universe accuracy

| Model | Correct stock-pair order |
|---|---:|
| current_champion | 55.30% |
| lgb_balanced_pool_d3_w0.1 | 55.30% |
| lgb_balanced_pool_d5_w0.1 | 55.30% |
| lgb_balanced_pool_d5_w0.5 | 55.29% |
| lgb_return_full_d3_w0.1 | 55.31% |
| lgb_return_full_d3_w0.5 | 55.34% |
| pfn_balanced_absolute_soft1.0_d3_w0.1 | 55.30% |
| pfn_balanced_residual_soft1.0_d5_w0.5 | 55.30% |

Pair accuracy is later SIP-XIRR ordering, with ties given half credit; not a probability of investment gains.

## Recent expanded Top 3, capped XIRR

| Model | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |
|---|---:|---:|---:|---:|---:|---:|
| current_champion | -0.22% | -31.31% | 22.93% | 0.1176 | 0.6371 | 0.1521 |
| lgb_balanced_pool_d3_w0.1 | -0.01% | -31.28% | 23.04% | 0.1169 | 0.6376 | 0.1521 |
| lgb_balanced_pool_d5_w0.1 | -0.07% | -31.30% | 22.93% | 0.1173 | 0.6369 | 0.1521 |
| lgb_balanced_pool_d5_w0.5 | -1.38% | -31.70% | 22.21% | 0.1197 | 0.6293 | 0.1505 |
| lgb_return_full_d3_w0.1 | -0.20% | -31.31% | 22.96% | 0.1174 | 0.6373 | 0.1522 |
| lgb_return_full_d3_w0.5 | -0.02% | -31.73% | 23.62% | 0.1187 | 0.6366 | 0.1525 |
| pfn_balanced_absolute_soft1.0_d3_w0.1 | -0.19% | -31.30% | 22.93% | 0.1175 | 0.6373 | 0.1521 |
| pfn_balanced_residual_soft1.0_d5_w0.5 | -0.42% | -31.49% | 22.68% | 0.1191 | 0.6358 | 0.1515 |

## Decision and audit

Retained model: `rank_xendcg_balanced_blend0.25`. All 60 variants have finite scores for 4,436 stocks; only 4,303 have usable rebuilt price evidence. The snapshot is still 3 October 2026. The live UI was not changed.
Verified all 100 saved student/control fits by replaying complete historical/current inputs (maximum error 1.11e-16). All 15 teacher contexts, labels and disjoint teaching pools were checked against their source rows and strict outcome cutoffs. Each teacher repeated its first 256 direct predictions; full neural teacher pools were not all independently refitted.
Matched cohort stock counts and champion benchmark metrics reproduce the preceding evaluation. Active-year results, sector bootstrap dispersion, all development candidates and every current stock rank are exported separately. The bootstrap is descriptive on reused data; it is not fresh validation.
The saved missing-data, corporate-action and historical outcome limitations remain. A pretrained model does not repair incomplete evidence, guarantee future performance, or establish an objectively correct ranking.

## Research foundations

[TabPFN, Nature 2025](https://www.nature.com/articles/s41586-024-08328-6), [official TabPFN implementation](https://github.com/PriorLabs/TabPFN), [knowledge distillation](https://arxiv.org/abs/1503.02531), [LightGBM](https://lightgbm.readthedocs.io/en/latest/Parameters.html). The teacher/student residual combination is a project-specific adaptation, not a published finance strategy or the proprietary Prior Labs distillation engine.

Run `sector_tabpfn_hybrid_20261011.py` with steps `protocol`, `learn`, `development`, `recent`, then `finish_sector_tabpfn_hybrid_20261011.py`. All scripts are in `research/runners`; checkpoint and isolated dependency versions are inherited from the completed 10 October experiment.

## Matched teacher contribution

| Hybrid | Matched control | Improved cells | Regressed cells |
|---|---|---:|---:|
| pfn_balanced_absolute_soft1.0_d3_w0.1 | lgb_balanced_pool_d3_w0.1 | 656 | 598 |
| pfn_balanced_residual_soft1.0_d5_w0.5 | lgb_balanced_pool_d5_w0.5 | 1100 | 194 |

Controls use the same teaching pool, student depth, hard-label target and correction strength. Counts measure the teacher signal against its exact matched control, separately from the champion comparison.

## Accuracy uncertainty

| Development accuracy leader | Recent expanded pair-order delta | Descriptive sector-bootstrap 95% interval |
|---|---:|---:|
| pfn_balanced_residual_soft1.0_d5_w0.5 | -0.0071 percentage points | [-0.0333, +0.0158] |
| lgb_return_full_d3_w0.5 | +0.0377 percentage points | [-0.0422, +0.1151] |

These intervals span zero. The sector-bootstrap statistic averages sectors after available profiles and dates; headline accuracy averages sectors within each profile first. Neither corrects for repeated research on these dates.

Five focused tests passed for temporal cutoffs, sector/date isolation, missing-evidence fallback and learned-weight semantics. Stock-by-stock rank changes are in finalist_stock_rank_changes.csv.

The running evaluator had loaded code before the matched-control amendment was applied. The originally locked leaders were preserved; two deterministic matched controls were added and evaluated without selecting new leaders. The original lock and repair note are retained.
