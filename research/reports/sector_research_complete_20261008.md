# Sector ranking: full research and previous-model audit — 8 October 2026

## Result

> Superseded performance assessment: a corporate-action outcome defect was confirmed after this campaign. See `sector_champion_integrity_followup_20261008.md` for the simulator fix, guarded comparisons and final promotion decision. Earlier unfiltered wins below are retained for audit, not clean validation.

**A stronger base-profile Top-3 research challenger was built, but a universally superior replacement has not been established. Production remains unchanged.**

The frozen new candidate is `pair__catboost_defensive__ridge_defensive__0.05`: 95% of the prior full-coverage challenger, 2.5% defensive CatBoost relevance rank and 2.5% defensive ridge relevance rank. It scores all **4,436 project stocks**, using the existing 3 October 2026 snapshot. Seventeen stocks lack usable price evidence and receive a neutral tied prior; coverage does not imply confident forecasts or trade eligibility.

At the base7500 profile and Top-3 cutoff, it improves all five outcome metrics against both prior references across 2020–2023/2024–2025, common/expanded universes and raw/capped returns: **zero regressions in 80 comparisons**. Broader Top-1/3/5 testing has **24 regressions in 240 base-profile cells**, and the nine-profile transfer test has **465 regressions in 2,160 cells** (125 of 720 at Top-3). Therefore the narrower win is not an all-profile or whole-ranking victory.

## Research actually performed

- 50 CatBoost, XGBoost, Extra Trees, ridge and ensemble candidates; 72 annual endpoint-purged fits.
- 27 sector-specific partially pooled ridge candidates; 18 annual global/local expert sets.
- 198 small two-model blends, explicitly marked as adaptive after earlier results were seen.
- Signals include closing-high proximity/age, 52-week-high freshness and support, 12–1 and six-month momentum, downside volatility/frequency, historical drawdown, history length, observed growth rates, trading continuity and observation count, plus sector-relative percentiles and missing-evidence indicators. Current fundamental statements were not inserted into historical training.
- 24 profile-aware LightGBM blends, trained on all nine settings with amount/lookback/interval/target inputs and equal date-sector-profile weights. 24 annual fits; strict passes: **0**.
- **299 new candidate configurations** in this campaign. These counts are not independent statistical trials or evidence that all possible algorithms have been exhausted.

## Previous project models

The retained evidence inventory covers 355 CSV evidence artifacts and 1393 identifiers. 134 are numeric metadata labels. Identifiers also include repeated builds, component names and trial settings, so they must not be described as that many distinct trained models.

**37 recoverable policy labels were replayed** against the new and prior full-coverage challengers on matching sector/date/profile stocks. This covers up to 28 decision dates in 2020–2025; 2016–2019 data supplies earlier training rather than backcast predictions from a later fitted model. All nine profiles, Top-1/3/5, raw/capped returns and six metrics including rank IC are retained. Each comparison uses its own common population; different opponents can have different dates and stocks. Saved earlier scores are evaluated on one common outcome source, not falsely presented as full reproductions of their original trading pipelines.

Returns below are equal-profile/equal-sector averages of date-level median constituent SIP XIRRs. Drawdown is mean constituent drawdown. These are ranking diagnostics, not a realized portfolio XIRR, portfolio maximum drawdown or net-of-cost portfolio backtest.

| Earlier policy | Recent raw Top-3 XIRR: new | Earlier | Recent capped Top-3 XIRR: new | Earlier |
|---|---:|---:|---:|---:|
| Original Personalized policy | 2.43% | 8.68% | -0.42% | -0.85% |
| V17 | 2.43% | 42.65% | -0.42% | 4.42% |
| V17 refined | 2.43% | 47.03% | -0.42% | 5.61% |
| V18 rejected candidate | 2.43% | 46.32% | -0.42% | 5.46% |
| V15 | 2.43% | 29.54% | -0.42% | 2.78% |
| V16 | 2.43% | 27.82% | -0.42% | 2.64% |
| V14 | 2.43% | 53.31% | -0.42% | 6.59% |
| V17 ATH diagnostic | 2.43% | 49.86% | -0.42% | 6.22% |
| V17 peak context | 2.43% | 49.88% | -0.42% | 6.28% |
| Closing High confirmation | 3.16% | -0.19% | 0.66% | -0.95% |
| Closing High priority | 3.16% | -1.15% | 0.66% | -1.68% |
| Deep championship V1 | 1.97% | 2.23% | -5.80% | -4.43% |
| V12 | 2.43% | 20.47% | -0.42% | 0.43% |
| Archived catboost_yetirank_pairwise_blend_score | 4.39% | 3.21% | 4.22% | 3.01% |
| Archived xgboost_rank_ndcg_blend_score | 4.39% | 8.77% | 4.22% | 5.53% |
| Archived jump_blend_score | 4.39% | 6.70% | 4.22% | 4.41% |
| Archived volatility_blend_score | 4.39% | 8.54% | 4.22% | 4.66% |
| Archived hmm_blend_score | 4.39% | 9.53% | 4.22% | 4.89% |
| Archived jump_adwin_blend_score | 4.39% | 4.42% | 4.22% | 3.04% |
| Executable enhanced_carry_xirr_score | 2.43% | -5.77% | -0.42% | -7.26% |
| Executable enhanced_no_carry_xirr_score | 2.33% | -5.59% | -0.51% | -7.29% |
| Executable professor_whole_share_score | 2.85% | -5.26% | -0.38% | -6.73% |
| Executable enhanced_goal_score | 2.36% | -1.53% | -0.49% | -4.87% |
| Executable historical_target_frequency_score | 2.38% | -5.74% | -0.42% | -6.54% |
| Executable global_existing_score | 2.70% | -0.26% | -0.29% | -2.22% |
| Executable enhanced_plus_existing_score | 2.63% | -4.20% | -0.36% | -4.89% |
| Executable ridge_executable_score | 9.57% | 10.07% | -6.12% | -8.38% |
| Executable ridge_without_amount_features_score | 9.57% | 9.61% | -6.12% | -8.85% |
| Executable ridge_without_goal_score | 9.57% | 10.72% | -6.12% | -9.42% |
| Executable cluster_rank_aggregation_score | 11.46% | -3.18% | -5.16% | -7.26% |
| Executable hist_gradient_boosting_score | 9.57% | 21.77% | -6.12% | -7.19% |
| Executable lightgbm_lambdarank_score | 9.57% | -16.30% | -6.12% | -18.98% |
| V13 policy replay | 2.43% | 21.08% | -0.42% | 0.53% |
| Baseline four-factor formula replay | 3.18% | -2.20% | 0.59% | -2.71% |
| Production sector champion | 3.16% | 0.32% | 0.66% | -0.17% |
| Prior reviewed closing-high policy | 3.16% | -0.24% | 0.66% | -0.96% |
| Professor whole-share project policy | 2.85% | -5.26% | -0.38% | -6.73% |

Large raw-return advantages can depend on extreme cached outcomes. Both treatments are shown; capping is a sensitivity test, not a data repair. Drawdown, achievement, shortfall, NDCG, rank IC and every sector/profile result remain in the CSVs. No older model is declared defeated simply because another metric looks better.

### Considered but not honestly comparable on this panel

| Family | Evidence treatment |
|---|---|
| Original strict Baseline V1 / Research V2 | Different exact dates, dated fundamentals and original eligible cohorts. The separate four-factor formula replay is labeled as a replay, not a reproduction of Research V2. No blanket superiority claim. |
| Early factor V1–V3, broad chronological price ML and V5 | Native chronological price-return studies retained; their original dates/labels do not match this SIP panel. Extra Trees, ridge and LightGBM algorithm families were also retested in the new campaign. |
| Greenblatt India and complete-universe evidence tiers | Current screens/coverage policies; no matched point-in-time performance history supplied. |
| Discarded history, hybrid, successor and fixed-blend trial settings | All retained identifiers/native results considered; not every discarded trial retained stock-level predictions. Missing results are not wins. |
| Prospective protocols | Do not infer matured out-of-sample performance from a protocol or a sealed score file. |
| Qlib TRA, DoubleEnsemble and metric-tool integrations | Synthetic/adaptor or infrastructure evidence is not an evaluated Indian-stock strategy. |

This is an inventory of retained local evidence and previously recovered Git archives. It cannot recover unrecorded or deleted work, and does not claim to have tested every published model.

## Data and reasoning checks

- Current frozen scores and ranks were independently reproduced for all 4,436 identities. All 72 saved first-round annual fits were replayed and all 50 initial candidate metric tables reproduced to 1e-12, without retraining. Existing 34 regression tests plus the new batched-evaluator test passed.
- Evidence confidence measures feature completeness only. HIGH is not calibrated forecast confidence or certification that corporate actions are fully reconciled. Unclassified stocks retain an explicit unclassified-pool scope rather than a verified sector rank.
- The existing independent company-quality rubric was joined to every current stock. Its Top-3 means for production/prior/new are 0.557853/0.557300/0.557615 on common stocks and 0.557853/0.564227/0.567194 on the expanded universe. This rubric is a transparent evidence check, not human or AI ground truth about future returns.
- A concrete corporate-action concern was found in Sejal Glass: its [2021–22 annual report](https://sejalglass.co.in/document/Annual%20Report%202021-2022.pdf) documents a major share consolidation within the window of an extreme cached outcome. Holdings/cash flows require reconciliation; source prices or labels were not silently changed.
- All dates have been researched before. Annual endpoint purging prevents direct future-outcome training leakage, but it does not undo repeated model-selection exposure. Current sector classifications and a surviving universe also limit historical claims.

## Research foundations

[CatBoost, NeurIPS 2018](https://proceedings.neurips.cc/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html), [XGBoost, KDD 2016](https://doi.org/10.1145/2939672.2939785), [Extra Trees, Machine Learning 2006](https://doi.org/10.1007/s10994-006-6226-1), and [LightGBM ranking documentation](https://lightgbm.readthedocs.io/en/latest/Parameters.html). These support methods, not a promise of profitable stock selection.

## Saved deliverables

- `experiments/full-coverage-open-models-20261008/current_all_stock_rankings.csv`: complete new research ranking.
- `experiments/full-coverage-open-models-20261008/current_sector_top3_review.csv`: company-evidence review.
- `experiments/all-model-sector-audit-20261008/equal_profile_summary.csv`: previous-policy comparisons by period.
- `experiments/all-model-sector-audit-20261008/sectors_*.csv.gz`: each sector/profile result.
- `experiments/profile-aware-sector-20261008/trials.csv`: all profile-aware trials.
- `experiments/all-model-sector-audit-20261008/verification.json`: independent arithmetic, temporal and reproduction checks.

Run `python research/runners/final_sector_research_audit_20261008.py` to regenerate this report after all experiment runners complete. Extra Trees fitted models were losslessly archived with hash verification to recover disk space. Disposable caches were temporarily removed; the primary prediction caches were subsequently restored from the saved fits and verified against all 50 original result tables. Model parameters, fitted artifacts and trial results remain reproducible.
