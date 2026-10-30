# Sector ranking: rebuilt-price experiment — 10 October 2026

**Selected research candidate: `yeti_ndcg3_balanced_blend0.1`. Strict gate passed: False.**

## What changed

- Rebuilt price signals directly from the provider split-adjusted close, avoiding the earlier inconsistent split-unadjustment path. Source files are hashed. This is not certification of provider data or a complete official-action reconstruction.
- Signals cover closing-high proximity/recency, frequency of new highs, time near highs, breakout strength, trend slope/fit, path efficiency, multi-horizon momentum, jump concentration, downside volatility, tail losses, drawdown, stale prices and sector-relative context.
- All features use observations at or before the decision date. Unresolved adjustment events inside the feature window and prices older than 14 days produce missing evidence, not invented strength.
- Historical training uses the older CSV receipts. Current-only features use the later frozen website raw-price package, whose hashes and override order are recorded separately. The September18 cache is not presented as fresh October evidence.
- Fixed the action guard for frozen runtime books created without the simulator constructor: adjustment transitions are recovered from their stored nominal/provider-price ratio and checked against official events. This avoids both a missing-attribute crash and a silent guard bypass.
- Tested CatBoost YetiRank:mode=NDCG;top=3, with return and balanced targets. Six annual folds give 12 fits; four blend settings give 8 candidates. All nine profiles are included.
- The prior broad gate is retained, with the latest guarded challenger added as a reference. Candidates are selected by development-period Top-3 regression count, then development-wide regression count. All historical dates were already exposed in earlier research; this is not a fresh holdout.

Historical metrics require at least five jointly scored, outcome-covered stocks in a sector/date/profile. Unclassified stocks are excluded from those metrics. Current exports still retain all identities, including smaller sectors and the explicitly unclassified pool; their inclusion is not historical validation.

## Results

The selected candidate regresses in **417 / 1512 Top-3 cells** and **1147 / 4536 total cells** against four reference policies on matching populations. 0 of 8 candidates pass the complete gate.

| Period | Capped base7500 Top-3 XIRR | Mean constituent drawdown | Whole-sector rank IC |
|---|---:|---:|---:|
| development: sector_incumbent | 30.83% | -27.06% | -0.0189 |
| development: guarded_previous | 31.11% | -25.32% | 0.0161 |
| development: yeti_ndcg3_balanced_blend0.1 | 31.07% | -25.04% | 0.0202 |
| exposed: sector_incumbent | -0.79% | -33.16% | 0.1302 |
| exposed: guarded_previous | 0.51% | -30.99% | 0.1479 |
| exposed: yeti_ndcg3_balanced_blend0.1 | 0.13% | -30.63% | 0.1458 |

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

- `experiments/sector-yetirank-20261010/current_all_stock_rankings.csv`
- `experiments/sector-yetirank-20261010/trials.csv`
- `experiments/sector-yetirank-20261010/selected_sector_query_metrics.csv.gz`
- `experiments/sector-yetirank-20261010/verification.json`
