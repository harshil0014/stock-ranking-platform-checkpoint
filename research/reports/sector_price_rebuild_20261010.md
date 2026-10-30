# Sector ranking: rebuilt-price experiment — 10 October 2026

**Selected research candidate: `rank_xendcg_balanced_blend0.25`. Strict gate passed: False.**

## What changed

- Rebuilt price signals directly from the provider split-adjusted close, avoiding the earlier inconsistent split-unadjustment path. Source files are hashed. This is not certification of provider data or a complete official-action reconstruction.
- Signals cover closing-high proximity/recency, frequency of new highs, time near highs, breakout strength, trend slope/fit, path efficiency, multi-horizon momentum, jump concentration, downside volatility, tail losses, drawdown, stale prices and sector-relative context.
- All features use observations at or before the decision date. Unresolved adjustment events inside the feature window and prices older than 14 days produce missing evidence, not invented strength.
- Historical training uses the older CSV receipts. Current-only features use the later frozen website raw-price package, whose hashes and override order are recorded separately. The September18 cache is not presented as fresh October evidence.
- Fixed the action guard for frozen runtime books created without the simulator constructor: adjustment transitions are recovered from their stored nominal/provider-price ratio and checked against official events. This avoids both a missing-attribute crash and a silent guard bypass.
- Tested rank_xendcg, top-focused LambdaRank and absolute-error regression, with return and balanced targets. Six annual folds give 36 fits; four blend settings give 24 candidates. All nine profiles are included.
- The prior broad gate is retained, with the latest guarded challenger added as a reference. Candidates are selected by development-period Top-3 regression count, then development-wide regression count. All historical dates were already exposed in earlier research; this is not a fresh holdout.

Historical metrics require at least five jointly scored, outcome-covered stocks in a sector/date/profile. Unclassified stocks are excluded from those metrics. Current exports still retain all identities, including smaller sectors and the explicitly unclassified pool; their inclusion is not historical validation.

## Results

The selected candidate regresses in **202 / 1512 Top-3 cells** and **761 / 4536 total cells** against four reference policies on matching populations. 0 of 24 candidates pass the complete gate.

| Period | Capped base7500 Top-3 XIRR | Mean constituent drawdown | Whole-sector rank IC |
|---|---:|---:|---:|
| development: sector_incumbent | 30.83% | -27.06% | -0.0189 |
| development: guarded_previous | 31.11% | -25.32% | 0.0161 |
| development: rank_xendcg_balanced_blend0.25 | 31.24% | -25.06% | 0.0279 |
| exposed: sector_incumbent | -0.79% | -33.16% | 0.1302 |
| exposed: guarded_previous | 0.51% | -30.99% | 0.1479 |
| exposed: rank_xendcg_balanced_blend0.25 | 0.73% | -30.56% | 0.1485 |

These are equal-sector averages of within-sector SIP diagnostics, not portfolio return or a forecast. Rank IC evaluates the whole scored sector rather than only its top stocks.

## Current export and verification

All **4,436 stocks** receive a research score at base7500 on the **3 October 2026 snapshot**. Rebuilt inputs are usable for **4303** stocks. Status counts: `{"USABLE_PROVIDER_BASIS": 4303, "NO_PRICE": 118, "UNRESOLVED_ACTION_IN_FEATURE_WINDOW": 15}`. The pure rebuilt component is neutral where evidence is unavailable; a blended score can still inherit old-model evidence and its defects.
- Reloading the saved model reproduces current scores exactly. The audit verifies all training cutoffs, feature timestamps, full coverage, ranking arithmetic, trial gates and sector aggregation.
- The existing company-evidence rubric is joined to every new ranking, with missing rubric scores retained. Top-three sector reviews and shared-cohort rubric comparisons are saved separately; reused company evidence is not future-return ground truth.
- Five new feature tests, 23 simulator/ownership tests (including two new frozen-runtime checks), and two separate integrity tests passed. They cover future-price independence, scale invariance, event windows, stale prices, sector isolation and runtime guard compatibility.
- The website custom-profile recomputation and HTTP/API test passed after the frozen-runtime guard fix.
- The live UI is unchanged. A failed broad gate does not authorize a clean-champion label.

## Research foundations

[ICML 2023: Which Tricks are Important for Learning to Rank?](https://proceedings.mlr.press/v202/lyzhin23a.html) motivates testing ranking losses directly. [Poh et al.](https://arxiv.org/abs/2012.07149) studies cross-sectional learning to rank in finance. [LightGBM documentation](https://lightgbm.readthedocs.io/en/latest/Parameters.html) defines the implemented objectives and truncation controls. These sources justify hypotheses, not performance claims on Indian stocks.

## Saved artifacts

- `experiments/sector-price-rebuild-20261010/current_all_stock_rankings.csv`
- `experiments/sector-price-rebuild-20261010/trials.csv`
- `experiments/sector-price-rebuild-20261010/selected_sector_query_metrics.csv.gz`
- `experiments/sector-price-rebuild-20261010/verification.json`

## All earlier-policy comparisons — completed

All **37 recoverable earlier policy labels** were compared to **rank_xendcg_balanced_blend0.25** on matching finite stocks and guarded outcome labels. These comparisons use the newly selected model, not the preceding challenger. The audit verified every sector aggregation and all directional deltas.

The candidate is nonworse in every recorded cell against **0 of 37 policies**. Across the complete older-policy panel there are **5002 regressions in 23652 comparisons**. Missing original model evidence is not treated as a victory.

Recent (2024–2025), capped Top-3 metrics below average sectors and profiles equally. Opponent populations can differ; this is a paired comparison per row, not one cross-opponent league table.

| Earlier policy | New XIRR | Earlier XIRR | New drawdown | Earlier drawdown |
|---|---:|---:|---:|---:|
| Original Personalized policy | -0.25% | -1.16% | -31.46% | -40.38% |
| V17 | -0.25% | 3.79% | -31.46% | -38.79% |
| V17 refined | -0.25% | 4.98% | -31.46% | -38.43% |
| V18 rejected candidate | -0.25% | 4.88% | -31.46% | -37.91% |
| V15 | -0.25% | 2.17% | -31.46% | -39.21% |
| V16 | -0.25% | 2.13% | -31.46% | -39.20% |
| V14 | -0.25% | 5.86% | -31.46% | -34.74% |
| V17 ATH diagnostic | -0.25% | 5.61% | -31.46% | -38.07% |
| V17 peak context | -0.25% | 5.63% | -31.46% | -38.07% |
| Closing High confirmation | 0.59% | -1.41% | -30.56% | -33.93% |
| Closing High priority | 0.59% | -2.05% | -30.56% | -34.59% |
| Deep championship V1 | -5.18% | -5.18% | -32.98% | -41.48% |
| V12 | -0.25% | 0.02% | -31.46% | -39.97% |
| Archived catboost_yetirank_pairwise_blend_score | 5.78% | 2.96% | -33.71% | -38.84% |
| Archived xgboost_rank_ndcg_blend_score | 5.78% | 5.59% | -33.71% | -43.95% |
| Archived jump_blend_score | 5.78% | 4.33% | -33.71% | -40.10% |
| Archived volatility_blend_score | 5.78% | 4.50% | -33.71% | -41.04% |
| Archived hmm_blend_score | 5.78% | 5.03% | -33.71% | -42.20% |
| Archived jump_adwin_blend_score | 5.78% | 3.07% | -33.71% | -42.17% |
| Executable enhanced_carry_xirr_score | -0.25% | -7.64% | -31.43% | -48.25% |
| Executable enhanced_no_carry_xirr_score | -0.24% | -7.66% | -31.44% | -48.35% |
| Executable professor_whole_share_score | -0.14% | -7.19% | -31.85% | -48.13% |
| Executable enhanced_goal_score | -0.25% | -5.02% | -31.47% | -41.98% |
| Executable historical_target_frequency_score | -0.23% | -6.74% | -31.33% | -43.21% |
| Executable global_existing_score | 0.37% | -2.82% | -30.96% | -45.76% |
| Executable enhanced_plus_existing_score | 0.22% | -5.37% | -31.14% | -43.93% |
| Executable ridge_executable_score | -6.33% | -8.85% | -32.04% | -44.45% |
| Executable ridge_without_amount_features_score | -6.33% | -9.11% | -32.04% | -44.43% |
| Executable ridge_without_goal_score | -6.33% | -9.64% | -32.04% | -44.83% |
| Executable cluster_rank_aggregation_score | -5.18% | -8.46% | -31.44% | -45.04% |
| Executable hist_gradient_boosting_score | -6.33% | -8.09% | -32.04% | -45.67% |
| Executable lightgbm_lambdarank_score | -6.33% | -19.11% | -32.04% | -44.82% |
| V13 policy replay | -0.25% | 0.09% | -31.46% | -39.98% |
| Baseline four-factor formula replay | 1.24% | -2.87% | -30.03% | -41.01% |
| Production sector champion | 0.59% | -0.77% | -30.56% | -33.21% |
| Prior reviewed closing-high policy | 0.59% | -1.42% | -30.56% | -33.93% |
| Professor whole-share project policy | -0.14% | -7.19% | -31.85% | -48.13% |

All comparisons and per-sector files are in `experiments/sector-price-rebuild-20261010/legacy-comparison/`. The previous inventory of non-comparable native studies and missing score policies still applies; this does not claim to have recreated every discarded or unpublished model.

**Final promotion status: NOT_APPROVED.** No live ranking-model switch was made.
