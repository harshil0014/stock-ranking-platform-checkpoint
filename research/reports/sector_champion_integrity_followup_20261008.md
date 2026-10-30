# Sector championship: completed integrity follow-up — 8 October 2026

**Promotion decision: no clean replacement has been established. The frozen full-coverage candidate remains research-only.**

This follow-up supersedes performance conclusions in the earlier campaign report wherever they rely on the unfiltered outcome labels. It does not delete prior evidence or redefine a failed gate as success.

## Work completed

- 343 new candidate configurations across the campaign: 299 previous, 16 delayed-feedback sector selectors, and 28 action-guarded blends/pure rankers. Candidate configurations are correlated and adaptively researched, not independent validation trials.
- Recompared all 37 recoverable earlier policy labels, including V17, the baseline formula replay and professor whole-share policy, after applying the same outcome exclusions to both sides. All nine profiles, within-sector Top-1/3/5, raw/capped returns and six metrics are retained.
- All 24 new annual fits exclude outcome endpoints on or after their test-year start. All selector feedback matured before the ranking date. Arithmetic, sector aggregation and identical label masking were verified.
- Four pure learned rankers were also evaluated without blending the old anchor into their predictions. Their price-derived input features still require a complete source-history audit.

The closest guarded candidate, **profile_defensive_15_blend0.2**, has been fitted on all nine profiles using only matured, unflagged outcomes, frozen and exported for **4,436 stocks at base7500**. Reloading the saved model reproduces every score exactly. This is a concrete research deliverable, not a promotion or an all-profile current export.

## Confirmed data defect

Sejal Glass has a retained 2021–2022 annualized SIP-return label of approximately **908,601%**. Replaying the old ledger reproduces it. The provider ledger includes a consolidation absent from the official ledger, so the simulator reverses a price adjustment without the corresponding holdings adjustment.
The [issuer annual report](https://sejalglass.co.in/document/Annual%20Report%202021-2022.pdf) documents 33,550,000 existing shares becoming 100,000. Inserting that event makes the simulator correctly stop with unresolved fractional entitlement; a corrected economic return cannot be asserted until entitlement mechanics are resolved.

**Implemented source fix:** `OfficialActionHistoryBook` now checks provider/official multiplier alignment by default and withholds metrics for investment windows crossing a mismatch. The real Sejal replay verifies that the original bad ledger now produces an unresolved-action status and no XIRR. The old result is reproducible only with an explicit forensic opt-out. Existing saved historical labels are not silently rewritten.

The alignment screen found **373 unresolved provider events** and excluded **7,486 finite outcome rows** across profiles. These are not unique stock counts. Not every mismatch is a proven error; dates, identity mappings and multipliers need adjudication. Matching events do not certify that all remaining data is correct.

## Final experiment results

| Family | Closest configuration by Top-3 gate | Top-3 regressions | All comparisons regressing |
|---|---|---:|---:|
| Action-guarded blends/pure models | profile_defensive_15_blend0.2 | 208/1080 | 737/3240 |
| Pure guarded rankers only | profile_defensive_15_blend1.0 | 249/1080 | 771/3240 |
| Delayed-feedback sector selector | router_y5_s24_t0.1_w0.25 | 315/1080 | 1154/3240 |

At base7500 on common stocks, the guarded 20% blend has capped Top-3 XIRR of 31.11% (2020–2023) and 0.51% (2024–2025), versus production at 30.83% and -0.79%. The older full-coverage open-model candidate has 31.35% and 0.83% on those same guarded cells. Thus the retrained model improves on production here but does not dominate its immediate predecessor. Recent mean constituent drawdown improves to -30.99%, versus production -33.16% and the earlier candidate -31.50%. These are retrospective diagnostics, not expected returns.

Selectors used the original outcome source and are retained as contaminated diagnostic experiments, not promotion evidence. Guarded models exclude unresolved labels during training and evaluation. Older anchor scores and historical input features were not rebuilt; blends can inherit those defects.

## Guarded comparisons with earlier policies

The following recent-period Top-3 values compare the earlier frozen CatBoost/ridge open-model candidate with each older policy; they are not results for the newly retrained 20% blend. Values average profiles and sectors equally. Each opponent has its own matched stock/date population. SIP constituent-median XIRR is a ranking diagnostic, not portfolio return. Capping each stock outcome to [-100%, +100%] is an additional sensitivity check.

| Earlier policy | New candidate, raw | Earlier, raw | New candidate, capped | Earlier, capped |
|---|---:|---:|---:|---:|
| Original Personalized policy | 1.15% | 5.79% | -0.99% | -1.16% |
| V17 | 1.15% | 25.45% | -0.99% | 3.79% |
| V17 refined | 1.15% | 30.03% | -0.99% | 4.98% |
| V18 rejected candidate | 1.15% | 29.46% | -0.99% | 4.88% |
| V15 | 1.15% | 19.18% | -0.99% | 2.17% |
| V16 | 1.15% | 18.87% | -0.99% | 2.13% |
| V14 | 1.15% | 24.01% | -0.99% | 5.86% |
| V17 ATH diagnostic | 1.15% | 32.11% | -0.99% | 5.61% |
| V17 peak context | 1.15% | 32.38% | -0.99% | 5.63% |
| Closing High confirmation | 2.40% | -0.73% | 0.08% | -1.41% |
| Closing High priority | 2.40% | -1.55% | 0.08% | -2.05% |
| Deep championship V1 | -0.76% | 1.19% | -6.41% | -5.18% |
| V12 | 1.15% | 9.65% | -0.99% | 0.02% |
| Archived catboost_yetirank_pairwise_blend_score | 4.68% | 3.16% | 4.52% | 2.96% |
| Archived xgboost_rank_ndcg_blend_score | 4.68% | 8.83% | 4.52% | 5.59% |
| Archived jump_blend_score | 4.68% | 6.61% | 4.52% | 4.33% |
| Archived volatility_blend_score | 4.68% | 8.37% | 4.52% | 4.50% |
| Archived hmm_blend_score | 4.68% | 9.67% | 4.52% | 5.03% |
| Archived jump_adwin_blend_score | 4.68% | 4.44% | 4.52% | 3.07% |
| Executable enhanced_carry_xirr_score | 1.15% | -6.28% | -0.99% | -7.64% |
| Executable enhanced_no_carry_xirr_score | 1.05% | -6.10% | -1.09% | -7.66% |
| Executable professor_whole_share_score | 1.20% | -5.91% | -0.96% | -7.19% |
| Executable enhanced_goal_score | 1.08% | -1.71% | -1.06% | -5.02% |
| Executable historical_target_frequency_score | 1.08% | -5.97% | -1.02% | -6.74% |
| Executable global_existing_score | 1.42% | -1.32% | -0.82% | -2.82% |
| Executable enhanced_plus_existing_score | 1.35% | -4.84% | -0.89% | -5.37% |
| Executable ridge_executable_score | 4.07% | 8.77% | -7.35% | -8.85% |
| Executable ridge_without_amount_features_score | 4.07% | 8.42% | -7.35% | -9.11% |
| Executable ridge_without_goal_score | 4.07% | 9.67% | -7.35% | -9.64% |
| Executable cluster_rank_aggregation_score | 5.69% | -6.13% | -6.36% | -8.46% |
| Executable hist_gradient_boosting_score | 4.07% | 12.80% | -7.35% | -8.09% |
| Executable lightgbm_lambdarank_score | 4.07% | -16.42% | -7.35% | -19.11% |
| V13 policy replay | 1.15% | 10.31% | -0.99% | 0.09% |
| Baseline four-factor formula replay | 2.62% | -2.42% | 0.20% | -2.87% |
| Production sector champion | 2.40% | -0.35% | 0.08% | -0.77% |
| Prior reviewed closing-high policy | 2.40% | -0.78% | 0.08% | -1.42% |
| Professor whole-share project policy | 1.20% | -5.91% | -0.96% | -7.19% |

## Interpretation and remaining promotion requirements

The full-coverage export contains 4,436 identities and reproduces exactly, but 17 have no usable price evidence and receive a neutral tied prior. Full coverage is not a reliability guarantee. The professor spreadsheet and the company-quality reasoning rubric are useful comparators, not ground truth about future performance.
The company-evidence rubric was rejoined to all 4,436 newly ranked identities; 4,316 have a finite rubric score and 120 remain unscored by that rubric. On common stocks its mean sector Top-3 score is 0.560270 for the guarded candidate versus 0.557853 for production and 0.557615 for the earlier open-model candidate. On the expanded cohort it is 0.575085 versus the earlier candidate at 0.576227. Expanded review admits sectors with five evidence-covered stocks even when production has fewer than five; it is not directly comparable to earlier reports restricting expanded sectors to production-covered groups. This rubric also shows tradeoffs, not universal improvement.
A clean promotion requires adjudicated corporate actions, rebuilt affected price features and outcome labels, and a predeclared evaluation on genuinely unexposed outcomes. The current-survivor universe, retrospective sector mapping and repeated historical model selection remain limitations. No amount of additional search on this panel removes them.

## Artifacts

- `experiments/sector-action-integrity-20261008/final_verification.json`: final evidence checks.
- `experiments/action-guarded-sector-20261008/trials.csv`: all 28 guarded candidates.
- `experiments/action-guarded-sector-20261008/current_all_stock_rankings.csv`: latest guarded challenger, all stocks, base7500.
- `experiments/action-guarded-sector-20261008/current_selection.json`: frozen fit, exact replay and explicit limitations.
- `experiments/action-guarded-sector-20261008/all_stock_evidence_review.csv.gz`: company-evidence rubric joined to all current rankings; `rubric_protocol.json` defines comparison populations.
- `experiments/action-guarded-legacy-sector-20261008/`: all 37 paired comparisons and sector-level details.
- `experiments/full-coverage-open-models-20261008/promotion_decision.json`: explicit no-promotion decision; frozen ranking and model bytes preserved.
- `experiments/full-coverage-open-models-20261008/current_all_stock_rankings.csv`: reproducible research ranking, not a certified champion.

Research methods include [CatBoost](https://proceedings.neurips.cc/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html), [XGBoost](https://doi.org/10.1145/2939672.2939785), [Extra Trees](https://doi.org/10.1007/s10994-006-6226-1), LightGBM, ridge and [delayed-feedback expert aggregation](https://proceedings.mlr.press/v128/korotin20a.html). These experiments do not exhaust every published model.
