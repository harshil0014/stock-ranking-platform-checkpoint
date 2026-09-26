# Personalized investing ownership research

Checkpoint: `097643b73d10f57a32cfb8ceb03d5edd17b6ddfe`. Research cutoff: 2026-09-18. Production untouched.

Recovered 746 profile rows across 463 identities; newly excluded 68 rows after integrity corrections; net gain 678.

| lookback_months | frozen_global_population | executable_available_before | executable_coverage_before_pct | executable_available_after | executable_coverage_after_pct | net_available_change | false_quarantines_removed | true_blocking_events_remaining | corporate_action_blocks | fractional_entitlement_blocks | other_unresolved |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 12 | 3808 | 3550 | 93.22478991596638 | 3747 | 98.39810924369748 | 197 | 207 | 37 | 13 | 24 | 24 |
| 36 | 3376 | 3056 | 90.52132701421802 | 3285 | 97.30450236966824 | 229 | 255 | 83 | 25 | 58 | 8 |
| 60 | 3027 | 2637 | 87.1159563924678 | 2889 | 95.4410307234886 | 252 | 284 | 131 | 40 | 91 | 7 |

## Model results

13 individual candidates, 25 fixed ensembles, and one ensemble learned strictly from matured training outcomes; six annual historical evaluation dates, nine profiles; strictly matured training labels. Best individual by shortfall: **lightgbm_lambdarank_score**. Best by rank IC: **hist_gradient_boosting_score**. Best combination by shortfall: **enhanced_goal+lightgbm_lambdarank@0.670-0.330**.

| candidate | rank_ic | target_achievement_top20 | target_shortfall_top20 | median_xirr_top20 |
| --- | --- | --- | --- | --- |
| lightgbm_lambdarank_score | -0.005698132898373 | 0.4435185185185185 | 0.0959633407256302 | 0.1245747212270296 |
| hist_gradient_boosting_score | 0.0092668490345475 | 0.3231481481481481 | 0.1405122841689152 | -0.014437136031608 |
| global_existing_score | -0.072441226341294 | 0.3388888888888889 | 0.1579375807643921 | -0.0601616654257662 |
| professor_whole_share_score | -0.0658829364622324 | 0.3527777777777778 | 0.1626010467219613 | 0.010513893177814 |
| enhanced_goal+lightgbm_lambdarank@0.670-0.330 | -0.0028857291132562 | 0.4361111111111111 | 0.076272210475479 | 0.1450575764641126 |

## Benchmark and interpretation

Sir workbook: 12/14 identities mapped; 0 usable purchase rows. Supplied-rank agreement over 10 comparable pairs: 0.23928181646454103. This is within-list agreement, not global ranking accuracy. Cached purchase/investment values do not support execution reproduction.

Data completeness and calculation integrity are materially improved. A superior investment policy is not established: previous performance was distorted by split double counting and temporal leakage. New comparisons use corrected outcomes, but retrospective selection, current-universe survivorship, omitted dividends/fees/slippage, and limited date blocks remain. No production promotion.

## Remaining evidence gaps

| lookback_months | status | reason | profile_rows |
| --- | --- | --- | --- |
| 12 | INSUFFICIENT_HISTORY | nan | 4 |
| 12 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-513460.csv' | 1 |
| 12 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-521068.csv' | 1 |
| 12 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-526115.csv' | 1 |
| 12 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-530601.csv' | 1 |
| 12 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-530755.csv' | 1 |
| 12 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-531585.csv' | 1 |
| 12 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-531600.csv' | 1 |
| 12 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-540332.csv' | 1 |
| 12 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-543970.csv' | 1 |
| 12 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-544195.csv' | 1 |
| 12 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-544257.csv' | 1 |
| 12 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-544331.csv' | 1 |
| 12 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-544365.csv' | 1 |
| 12 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-544373.csv' | 1 |
| 12 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-544393.csv' | 1 |
| 12 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-544436.csv' | 1 |
| 12 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-544474.csv' | 1 |
| 12 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-544503.csv' | 1 |
| 12 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-544509.csv' | 1 |
| 12 | MISSING_EXECUTION_PRICE | nan | 1 |
| 12 | UNRESOLVED_CORPORATE_ACTION | DEMERGER | 9 |
| 12 | UNRESOLVED_CORPORATE_ACTION | PREFERENCE_SHARE_VALUATION_UNAVAILABLE | 1 |
| 12 | UNRESOLVED_CORPORATE_ACTION | RESULTING_SECURITY_VALUATION_UNAVAILABLE | 3 |
| 12 | UNRESOLVED_FRACTIONAL_ENTITLEMENT | FRACTIONAL_BONUS_ENTITLEMENT:2025-10-16 | 1 |
| 12 | UNRESOLVED_FRACTIONAL_ENTITLEMENT | OFFICIAL_MULTIPLIER_PRODUCED_FRACTIONAL_SHARES | 23 |
| 36 | INSUFFICIENT_HISTORY | nan | 6 |
| 36 | INVALID_HISTORY | [Errno 2] No such file or directory: 'data\\live_market\\history_cache\\BSE-513460.csv' | 1 |
| 36 | MISSING_EXECUTION_PRICE | nan | 1 |
| 36 | UNRESOLVED_CORPORATE_ACTION | DEMERGER | 17 |
| 36 | UNRESOLVED_CORPORATE_ACTION | PREFERENCE_SHARE_VALUATION_UNAVAILABLE | 1 |
| 36 | UNRESOLVED_CORPORATE_ACTION | RESULTING_FRACTION_SETTLEMENT_UNAVAILABLE:ITCHOTELS | 1 |
| 36 | UNRESOLVED_CORPORATE_ACTION | RESULTING_FRACTION_SETTLEMENT_UNAVAILABLE:RAYMONDLSL | 1 |
| 36 | UNRESOLVED_CORPORATE_ACTION | RESULTING_SECURITY_VALUATION_UNAVAILABLE | 4 |
| 36 | UNRESOLVED_CORPORATE_ACTION | SCHEME_OR_MERGER | 1 |
| 36 | UNRESOLVED_FRACTIONAL_ENTITLEMENT | FRACTIONAL_BONUS_ENTITLEMENT:2024-05-17 | 1 |
| 36 | UNRESOLVED_FRACTIONAL_ENTITLEMENT | FRACTIONAL_BONUS_ENTITLEMENT:2024-12-10 | 1 |
| 36 | UNRESOLVED_FRACTIONAL_ENTITLEMENT | FRACTIONAL_BONUS_ENTITLEMENT:2025-03-24 | 1 |
| 36 | UNRESOLVED_FRACTIONAL_ENTITLEMENT | FRACTIONAL_BONUS_ENTITLEMENT:2025-10-16 | 1 |
| 36 | UNRESOLVED_FRACTIONAL_ENTITLEMENT | OFFICIAL_MULTIPLIER_PRODUCED_FRACTIONAL_SHARES | 54 |
| 60 | INSUFFICIENT_HISTORY | nan | 6 |
| 60 | MISSING_EXECUTION_PRICE | nan | 1 |
| 60 | UNRESOLVED_CORPORATE_ACTION | DEMERGER | 29 |
| 60 | UNRESOLVED_CORPORATE_ACTION | PREFERENCE_SHARE_VALUATION_UNAVAILABLE | 1 |
| 60 | UNRESOLVED_CORPORATE_ACTION | RESULTING_FRACTION_SETTLEMENT_UNAVAILABLE:ITCHOTELS | 1 |
| 60 | UNRESOLVED_CORPORATE_ACTION | RESULTING_FRACTION_SETTLEMENT_UNAVAILABLE:RAYMONDLSL | 1 |
| 60 | UNRESOLVED_CORPORATE_ACTION | RESULTING_SECURITY_VALUATION_UNAVAILABLE | 4 |
| 60 | UNRESOLVED_CORPORATE_ACTION | SCHEME_OR_MERGER | 2 |
| 60 | UNRESOLVED_CORPORATE_ACTION | UNPARSED_CONSOLIDATION | 2 |
| 60 | UNRESOLVED_FRACTIONAL_ENTITLEMENT | FRACTIONAL_BONUS_ENTITLEMENT:2022-05-27 | 1 |
| 60 | UNRESOLVED_FRACTIONAL_ENTITLEMENT | FRACTIONAL_BONUS_ENTITLEMENT:2022-06-06 | 1 |
| 60 | UNRESOLVED_FRACTIONAL_ENTITLEMENT | FRACTIONAL_BONUS_ENTITLEMENT:2022-06-16 | 1 |
| 60 | UNRESOLVED_FRACTIONAL_ENTITLEMENT | FRACTIONAL_BONUS_ENTITLEMENT:2022-09-28 | 1 |
| 60 | UNRESOLVED_FRACTIONAL_ENTITLEMENT | FRACTIONAL_BONUS_ENTITLEMENT:2023-04-20 | 1 |
| 60 | UNRESOLVED_FRACTIONAL_ENTITLEMENT | FRACTIONAL_BONUS_ENTITLEMENT:2024-09-25 | 1 |
| 60 | UNRESOLVED_FRACTIONAL_ENTITLEMENT | FRACTIONAL_BONUS_ENTITLEMENT:2025-09-16 | 1 |
| 60 | UNRESOLVED_FRACTIONAL_ENTITLEMENT | FRACTIONAL_BONUS_ENTITLEMENT:2025-10-16 | 1 |
| 60 | UNRESOLVED_FRACTIONAL_ENTITLEMENT | FRACTIONAL_BONUS_ENTITLEMENT:2026-05-26 | 1 |
| 60 | UNRESOLVED_FRACTIONAL_ENTITLEMENT | FRACTIONAL_SPLIT_ENTITLEMENT:2022-02-21 | 1 |
| 60 | UNRESOLVED_FRACTIONAL_ENTITLEMENT | FRACTIONAL_SPLIT_ENTITLEMENT:2023-04-28 | 1 |
| 60 | UNRESOLVED_FRACTIONAL_ENTITLEMENT | OFFICIAL_MULTIPLIER_PRODUCED_FRACTIONAL_SHARES | 80 |

Rights lapse deliberately without subscription or sale; zero received proceeds is a policy assumption, not an observed entitlement quote. Exercise sensitivity uses record-date proxy cash and is hypothetical. Unknown resulting-security or fractional proceeds remain blocked. Resulting-company values use separate holdings and observed terminal prices; risk features remain parent-security features. Dividends are excluded from executable wealth and risk; the global baseline retains original adjusted features. Terminal adjusted values in overlay files are inferred only for schema compatibility; executable calculations use raw prices. No missing raw price was imputed.

Raw histories and documents, large prediction panels, and checkpoints remain outside Git. Compact audit artifacts and their source hashes are versioned.

Exact next step: shadow-run the frozen selected policy without changing production; evaluate genuinely prospective outcomes after 2026-09-18 and obtain missing fractional settlements/resulting-security quotes before claiming total-return completeness.

## Cross-metric decision audit

Material retrospective goal-shortfall improvement over corrected existing and simple-goal baselines. The ensemble advantage over standalone LambdaRank and the goal-achievement improvement are not conclusive. No prospective superiority or production readiness is established.

The selected ensemble lowers mean top-20 goal shortfall from 15.79% (existing score) and 10.88% (simple goal score) to 7.63%. It improves shortfall on 5/6 dates and 9/9 profiles versus the existing score, and on 6/6 dates versus simple goal scoring.

The descriptive 95% date-bootstrap interval for shortfall improvement versus simple goal scoring is 1.81 to 4.72 percentage points. This is not a selection-adjusted confidence claim.

The highest-IC gradient boosting model achieves goals for 32.31% of its top 20, versus 44.35% for LambdaRank and 43.61% for the selected ensemble. Rank IC alone selected the wrong policy for investor utility. The training-only learned rank blend has 13.73% mean shortfall and does not beat the selected fixed ensemble.

Recovery eligibility alone is not the explanation for the utility gain: holding corrected scores/outcomes fixed on the two overlapping old evaluation dates, adding recovered identities changes shortfall by approximately +0.10 percentage points. That diagnostic captures screening effects, not a causal corporate-action-only effect.

Tests: 891 passed; one external NSE fixture skipped. Independent frozen-dataset rebuild matched exactly. All recorded normalized evidence, finalizer source, and protected-state hashes verified.

Shadow-evaluate the frozen 67/33 goal/LambdaRank policy on post-2026-09-18 data, retaining production. Full 12-month prospective outcomes mature on 2027-09-18.
