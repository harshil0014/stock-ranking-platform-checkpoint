# Full-coverage sector ranking accuracy — 10 October 2026

Research accuracy leader: **regression_l1_balanced_blend1.0** (rebuilt). Selected by development-period whole-sector rank correlation across nine profiles, with equal sector/date weighting and both comparison scopes. The original multi-metric promotion gate is unchanged.

Scores cover **4,436 / 4,436 stocks**. Usable rebuilt price inputs cover **4303 / 4,436** on the **3 October 2026 snapshot**. The remaining stocks have explicitly marked missing/unsafe inputs and a neutral new-model component; blended rankings can inherit older model evidence. A finite score is not complete data coverage.

## Whole-sector ordering accuracy

Pair accuracy is the fraction of within-sector stock pairs correctly ordered by their later SIP XIRR, awarding half credit to ties. It is not the probability of a stock gaining. Common scope uses the production-scored cohort; expanded scope compares the full-coverage policies on identical outcome-covered peers. Sectors need at least five peers; unclassified stocks are excluded from historical metrics.

| Scope | Period | Model | Pair accuracy |
|---|---|---|---:|
| common | development | accuracy_candidate | 51.05% |
| common | development | frozen_challenger | 50.29% |
| common | development | guarded_previous | 50.49% |
| common | development | open_model | 50.31% |
| common | development | rebuilt_selected | 50.85% |
| common | development | sector_incumbent | 49.48% |
| common | development | yeti_selected | 50.63% |
| common | exposed | accuracy_candidate | 54.45% |
| common | exposed | frozen_challenger | 54.96% |
| common | exposed | guarded_previous | 55.18% |
| common | exposed | open_model | 55.00% |
| common | exposed | rebuilt_selected | 55.36% |
| common | exposed | sector_incumbent | 54.69% |
| common | exposed | yeti_selected | 55.21% |
| expanded | development | accuracy_candidate | 51.48% |
| expanded | development | frozen_challenger | 50.24% |
| expanded | development | guarded_previous | 50.59% |
| expanded | development | open_model | 50.26% |
| expanded | development | rebuilt_selected | 51.02% |
| expanded | development | yeti_selected | 50.67% |
| expanded | exposed | accuracy_candidate | 54.48% |
| expanded | exposed | frozen_challenger | 54.52% |
| expanded | exposed | guarded_previous | 55.05% |
| expanded | exposed | open_model | 54.62% |
| expanded | exposed | rebuilt_selected | 55.30% |
| expanded | exposed | yeti_selected | 54.98% |

## Rank correlation and Top-3 outcomes

These aggregate development/recent summaries average both scopes for full-coverage models; production has common scope only. Use the paired scope-specific files for direct comparisons. XIRR here is an equal-sector SIP diagnostic, not a realizable portfolio return.

| Period | Model | Rank IC | Top-3 XIRR (raw) | Drawdown |
|---|---|---:|---:|---:|
| development | guarded_previous | 0.0141 | 37.40% | -25.47% |
| exposed | guarded_previous | 0.1450 | 1.42% | -31.46% |
| development | open_model | 0.0064 | 38.07% | -25.87% |
| exposed | open_model | 0.1374 | 1.71% | -32.12% |
| development | regression_l1_balanced_blend1.0 | 0.0348 | 45.22% | -25.05% |
| exposed | regression_l1_balanced_blend1.0 | 0.1310 | 20.76% | -32.63% |
| development | sector_incumbent | -0.0185 | 34.45% | -26.91% |
| exposed | sector_incumbent | 0.1318 | -0.35% | -33.21% |

## Broad gate and interpretation

This accuracy leader has **674 / 1512 Top-3 regressions**, and **1990 / 4536 total regressions** against four references over profiles, scopes, periods, raw/capped returns and six metrics. Strict gate: **False**. Accuracy selection does not erase those tradeoffs.

All historical dates have been exposed in earlier research; neither recent performance nor this development-selected result is a fresh holdout. Financial data adjustments remain partially unresolved and affected input/outcome windows are excluded. The company-evidence rubric is reused diagnostic evidence, not an independent oracle. Professor-formula comparisons are in the separate older-policy audit.

## Research and reproducibility

The continuation evaluates 24 LightGBM blend configurations and eight CatBoost configurations from 48 annual fits. Features include closing-high persistence/recency, breakout strength, momentum, trend consistency, jump concentration, downside risk and sector-relative strength. Training outcomes must finish before each annual test fold.

[ICML 2023 ranking research](https://proceedings.mlr.press/v202/lyzhin23a.html), [cross-sectional financial learning to rank](https://arxiv.org/abs/2012.07149), [LightGBM parameters](https://lightgbm.readthedocs.io/en/latest/Parameters.html), and [CatBoost ranking objectives](https://catboost.ai/docs/en/concepts/loss-functions-ranking?lang=en) motivated the tested objectives. They do not certify this market or dataset.

The saved model and exported CSV reproduce scores within 1e-15. Full rankings, input-confidence labels, all-stock company-evidence reviews, sector Top-3 reviews, per-profile accuracy, all 32 candidate summaries and artifact hashes are retained in `experiments/sector-accuracy-20261010/`. The live ranking model has not been switched.
