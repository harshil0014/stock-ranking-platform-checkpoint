# Personalized executable ranking: final research as of 2026-09-18

**Status: RESEARCH_ONLY.** No model earned production promotion. This report uses the 2026-09-18 frozen universe and outcomes already mature by that date. `build-04` is the corrected official-action freeze and `build-02` is the final tournament; earlier new builds remain superseded research records.

## 1. New evidence and executable coverage

The four round-two batches contain 445 distinct events. Independent reconciliation found 311 previously evidenced, 112 already represented by official automatic multipliers, 16 newly specified complex actions, and 6 recovered consolidations. Their union covers all 445 core mechanics, with zero core event identities missing. This does **not** mean every event has reproducible cash settlement or resulting-security valuation.

| Window | Frozen population | Executable before | Executable after | Recovered rows | Coverage after | Corporate action blocks | Fraction blocks | Other unresolved |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 12m | 3,808 | 3,547 | 3,550 | +3 | 93.22% | 96 | 16 | 146 |
| 36m | 3,376 | 3,046 | 3,056 | +10 | 90.52% | 276 | 29 | 15 |
| 60m | 3,027 | 2,631 | 2,637 | +6 | 87.12% | 339 | 37 | 14 |

The incremental gain is 19 profile rows across 10 distinct identities. Remaining blockers are profile-specific: 112, 305 and 376 corporate-action or fractional rows at 12m, 36m and 60m respectively. The broader official ledger includes rights and demergers outside the 22 newly recovered terms; those remain blocked. Other unresolved rows arise from stale, missing, or invalid price history. `remaining_blockers.csv` and `blocker_reconciliation.csv` give the exact identities and reasons.

## 2. Economic treatment and evidence boundaries

Official splits, bonuses and consolidations use proven share ratios. Consolidation holdings are inspected at the event date; a fractional entitlement blocks only that execution/profile when its cash settlement cannot be reproduced. In particular, INE363L01045 uses the proven 2-old-to-1-new ratio but no invented fraction proceeds.

The base rights policy is **NO_SUBSCRIPTION / PASSIVE**. It injects no cash and creates no ordinary shares. The withdrawn INE125F01032 issue creates no allotment. Recovered completed rights use a zero separately valued entitlement as a conservative research scenario, not a claim that a transferable entitlement has zero market value. `rights_policy_sensitivity.csv` separately tests portfolio-cash-limited exercise at the record date where replay is possible: 58 profile/event rows are evaluable and 16 remain blocked. It injects no external cash. That proxy is not an actual subscription schedule and is excluded from model selection.

Demergers retain the original security and record resulting-company entitlement ratios in the normalized ledger; they remain valuation blockers unless resulting security history is reproducible. Vedanta's terms identify one share in each of four resulting businesses per original share. No value is assigned to those holdings. SIYSIL records the 4:1 and 3:1 preference-share series and is never converted into seven ordinary shares. The preference cash-flow value remains unavailable.

The leakage audit found no post-cutoff market outcomes or action dates in the final panels. Sector diagnostics use only exact official observations on 2020-03-31, 2021-03-31, 2022-03-31; the 2026-09-23 snapshot and modern labels were not projected backward. Later-collected documents were used only to document pre-cutoff events. The corrected freeze was rebuilt independently with the same deterministic fingerprint.

## 3. Individual models, fixed ensembles and investor utility

All 13 existing candidates were rerun on identical date/profile common cohorts: professor whole-share, enhanced no-carry XIRR, enhanced carry XIRR, enhanced goal, historical target frequency, global existing, enhanced plus existing, ridge executable, ridge without amount features, ridge without goal, cluster rank aggregation, HistGradientBoosting and LightGBM LambdaRank. The fixed family contains 25 preregistered rank-percentile combinations across 2, 3 and 4 components. No train-only learned ensemble was tested.

The tested ensemble families were goal + existing, goal + ridge, goal + LambdaRank, existing + ridge; goal + existing + ridge, goal + existing + LambdaRank, goal + ridge + LambdaRank; and goal + existing + ridge + LambdaRank. Pairs used 50/50, 67/33 and 33/67; triples used equal thirds and each 50/25/25 rotation; the four-part blend used equal quarters. `ensemble_metrics.csv` lists every fixed combination. `execution_diagnostics.csv` records cash utilization, affordability and execution counts; no complete historical slippage or fee series was available.

The strongest individual by mean rank IC and lowest mean goal shortfall is `hist_gradient_boosting_score`: IC 0.0346, top-20 goal achievement 56.1%, mean shortfall 0.0551. The best fixed ensemble by mean shortfall is `enhanced_goal+ridge_executable+lightgbm_lambdarank@0.333-0.333-0.333`: IC 0.0295, goal achievement 66.1%, shortfall 0.0439. It beats the simple goal/existing combination on these frozen descriptive measures, but the effect has only two independent validation dates and previously exposed outcomes.

| Control | Candidate | Mean rank IC | Top-20 goal achievement | Mean top-20 shortfall |
|---|---|---:|---:|---:|
| strongest_individual_rank_ic | `hist_gradient_boosting_score` | 0.0346 | 56.1% | 0.0551 |
| strongest_individual_goal_achievement | `cluster_rank_aggregation_score` | 0.0187 | 67.2% | 0.0754 |
| strongest_individual_lowest_shortfall | `hist_gradient_boosting_score` | 0.0346 | 56.1% | 0.0551 |
| strongest_fixed_ensemble_goal_achievement | `enhanced_goal+ridge_executable+lightgbm_lambdarank@0.333-0.333-0.333` | 0.0295 | 66.1% | 0.0439 |

The strongest individual rank IC also has the lowest individual shortfall, but the highest individual goal-achievement rate belongs to a different model. Higher correlation therefore did not uniformly imply a higher fraction of investors meeting their target. The fixed ensemble improves average shortfall and attainment, while its IC is below the strongest individual. No single metric determines the decision.

`profile_metrics.csv`, `paired_deltas.csv`, and `uncertainty.csv` show date/profile variation and paired comparisons. The 18 profile-date rows derive from only two decision-date blocks; the reported bootstrap intervals are descriptive, not independent confirmation. No claim of a statistically established production improvement is made.

## 4. Ablation and recovery contribution

Positive values below mean the full version reduced mean top-20 shortfall; negative values mean the component worsened it in this comparison.

| Component comparison | Shortfall improvement |
|---|---:|
| amount_execution_features | -0.0013 |
| goal_features | -0.0019 |
| risk_feature_price_drawdown | -0.0150 |
| existing_score | -0.0290 |
| lambda_rank_component | +0.0184 |
| corporate_action_recovery | +0.0033 |

The corporate-action recovery increased executable coverage and changed the HistGradientBoosting validation shortfall only modestly. The pre/post comparison changes the common cohort slightly, so its model delta is descriptive. Risk and goal feature ablations are post-selection diagnostics and were not used to pick the winner.

## 5. Professor workbook comparison

The supplied workbook is an external benchmark. The candidate definitions, ensemble family, and weights were frozen before any workbook read. The corrected build's selection followed that fixed rule without workbook inputs, after an earlier superseded run had already read the workbook. Of 14 displayed rows, 11 have exact exchange-code identity matches. All 14 cached investment/share-purchase rows have zero investment, leaving 0 usable purchase histories and 0 exact execution reproductions. Missing cached purchase inputs are classified as unavailable workbook input, not model failure. The workbook cached date (2026-08-21) also differs from the research date (2026-09-18), and its GoogleFinance calendar and price cells cannot be reproduced from the cache.

The supplied ordering is a separate comparison from the workbook's cached SIP `RANK` formula. Only 9 exact matched supplied-rank pairs have a selected individual score; within that overlap, descriptive Spearman agreement is 0.603. The supplied list has no known global rank scope, so this is not global ranking accuracy. Row-level diagnostics distinguish missing workbook inputs, identity gaps, accounting definitions, residual cash and corporate-action uncertainty; no unexplained discrepancy is inferred from blank cells.

## 6. Decision and next evidence

**No production change.** The status is `RESEARCH_ONLY`; promotion is `INSUFFICIENT_EVIDENCE`. Complex models show useful descriptive signals, but the two exposed validation dates, incomplete historical event cash values, missing historical sector intervals, absent historical slippage/fees, and unavailable workbook purchase cache prevent a production claim.

Next: obtain actual rights subscription timing and proceeds, resulting-company price/listing histories, SIYSIL preference cash-flow valuation, and a recalculated workbook with cached purchase and contribution rows. Preserve the frozen 2026-09-18 model and wait for genuinely prospective 12-month outcomes after 2027-09-18 before reconsidering promotion.
