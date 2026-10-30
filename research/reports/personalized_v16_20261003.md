# Personalized V16 — 2026-10-03

## Verdict

**PROMISING CHALLENGER. Do not replace d499580. No deployment.** V16 repairs the average development 12M failure and passes all unchanged V15 gates, but calendar instability, high turnover, exposed research, and conditional current execution evidence prevent promotion.

## What failed in V15

The main diagnosis is **B: a systematic growth/history interaction at short lookbacks**, with regime dependence. It is not just one or two bad accidents, and the evidence does not establish that every part of the 12M correction is unreliable. Of16 development dates,7 lose median XIRR and13 worsen drawdown. There are231 substitutions (14.44 per date), spanning 151 promoted ISINs. The worst three dates account for 56.0% of gross return losses and 49.0% of gross drawdown losses; gains on other dates offset much of the loss. Thus concentrated return setbacks coexist with broadly worse drawdown.

Entrants average212 months of history versus146 for exits;4611 days since the high versus2386;91.1% below the high versus48.9%;42.3% annual volatility versus34.5%; and historical maximum drawdown−96.4% versus−67.0%. Entrants have weaker recent whole-share plan XIRR scores (4.86 versus12.19) and1Y growth (83.6% versus427.8%, highly skewed means). Almost all are fully observed: mean confidence99.89%, and only1 of231 entrants has less than60 months of history. Missing-field confidence therefore fails to flag this profile/model interaction. Affordability is not the driver: both groups have essentially100% utilization and zero unaffordable rate.

The post-lock feature-level mechanism audit confirms that promoted stocks receive most growth-family support from observed5Y (+0.271 average raw TreeSHAP),10Y (+0.109), and7Y (+0.039), while1Y is slightly negative. Demoted picks have observed5Y−0.008 and10Y−0.011. Long-history growth proxies swamp recent plan-return evidence in this profile. TreeSHAP explains model predictions; it is not causal outcome attribution. No identity features are used.

### Date-by-date autopsy and locked V16 repair

All deltas are fractions (multiply by100 for percentage points); higher drawdown delta is better. The market growth/volatility columns in the detailed CSV are contemporaneous cross-sectional proxies, not an externally reconstructed benchmark regime.

| decision_date | substitutions | xirr_delta | drawdown_delta | median_xirr_top20_delta | mean_asset_drawdown_top20_delta |
| --- | --- | --- | --- | --- | --- |
| 2020-03-31 | 14 | 0.2714 | -0.0598 | 0.2714 | -0.0639 |
| 2020-06-30 | 19 | 0.3706 | -0.1505 | 0.8570 | -0.0747 |
| 2020-09-30 | 15 | 0.2876 | -0.1289 | -0.1026 | -0.1026 |
| 2020-12-31 | 16 | -0.4308 | 0.0453 | 0.7375 | 0.0508 |
| 2021-03-31 | 16 | 0.4572 | -0.0917 | -0.0459 | -0.0080 |
| 2021-06-30 | 17 | -0.5376 | -0.0615 | -0.9674 | -0.0740 |
| 2021-09-30 | 13 | 0.2586 | 0.0806 | 0.3170 | 0.1215 |
| 2021-12-31 | 18 | -0.4100 | -0.2193 | -0.2445 | -0.0786 |
| 2022-03-31 | 15 | -0.5441 | -0.1744 | -0.3468 | -0.0761 |
| 2022-06-30 | 19 | -0.4718 | -0.1831 | 0.1512 | 0.0778 |
| 2022-09-30 | 16 | -0.1291 | -0.0077 | -0.1233 | 0.0482 |
| 2022-12-31 | 12 | 0.0251 | 0.0111 | 0.7707 | -0.0093 |
| 2023-03-31 | 13 | -0.7536 | -0.0065 | -0.7536 | 0.0075 |
| 2023-06-30 | 7 | 0.2477 | -0.0015 | 0.2727 | -0.0130 |
| 2023-09-30 | 11 | 0.0452 | -0.0672 | 0.1128 | -0.0144 |
| 2023-12-31 | 10 | 0.2475 | -0.0253 | -0.0354 | 0.0739 |

V15 return gains during the first three2020 dates do not excuse their drawdown losses. The2021Q4–2022Q2 losses are consecutive, and2023Q1 also loses75.36pp of median XIRR. This is consistent with regime-dependent generalization failure; regime causation is not proved.

### Stock substitutions and attribution

Full champion and V15 Top20 lists are in `autopsy_12m_top20.csv`; every entry/exit pair, realized return/drawdown, ranks, and pre-decision feature state is in `autopsy_12m_substitutions.csv`. Drawdown contribution is exactly additive. Median-XIRR attribution uses512 fixed-seed permutation orders over deterministic rank-paired substitutions; paired attribution is approximate and depends on pairing, but its sum reproduces each exact date delta. It is not a claim that one stock independently caused that amount. The table shows the twelve worst drawdown pairs; ticker labels were attached after selection for readability and do not establish historical industry membership.

| decision_date | exit_ticker | entry_ticker | exit_xirr | entry_xirr | drawdown_attribution | median_xirr_attribution |
| --- | --- | --- | --- | --- | --- | --- |
| 2022-06-30 | BSE-539762 | BSE-540386 | 0.0986 | -0.2344 | -0.0426 | -0.0234 |
| 2020-03-31 | BSE-505336 | BSE-531574 | 0.3681 | 0.7268 | -0.0382 | 0.0271 |
| 2021-12-31 | BSE-539552 | BSE-531395 | 2.5941 | -0.6411 | -0.0377 | -0.0584 |
| 2022-03-31 | BSE-513496 | BSE-517356 | 0.6153 | -0.6055 | -0.0365 | -0.0759 |
| 2022-06-30 | BSE-539895 | BSE-523242 | 0.5639 | -0.1020 | -0.0362 | -0.0707 |
| 2020-06-30 | BSE-526638 | BSE-513295 | 42.2919 | 2.0847 | -0.0353 | -0.0021 |
| 2021-12-31 | BSE-501351 | PREMIER | 0.2967 | -0.4455 | -0.0345 | -0.0423 |
| 2022-03-31 | BSE-539552 | PREMIER | 1.2501 | -0.7282 | -0.0342 | -0.0806 |
| 2022-12-31 | BSE-539682 | BSE-531737 | 0.0823 | 0.5278 | -0.0336 | 0.0010 |
| 2022-06-30 | BSE-505336 | BSE-531465 | 0.3990 | -0.6975 | -0.0336 | -0.0649 |
| 2020-09-30 | BSE-504380 | BSE-531541 | 145.3807 | -0.5260 | -0.0329 | -0.2388 |
| 2021-12-31 | BSE-535910 | BSE-533149 | 0.6492 | -0.2122 | -0.0322 | -0.0564 |

### Feature-state concentration

Attributions below are mean-date contributions. States overlap and must not be summed. High volatility uses the entrant distribution upper quartile in this descriptive table; robustness cohorts use within-query universe upper quartiles.

| state | substitutions | mean_date_xirr_attribution | mean_date_drawdown_attribution |
| --- | --- | --- | --- |
| short_history | 1 | -0.0061 | -0.0019 |
| full_history | 230 | -0.0605 | -0.0631 |
| old_ath | 228 | -0.0637 | -0.0622 |
| recent_ath | 1 | -0.0061 | -0.0019 |
| deep_ath | 230 | -0.0713 | -0.0667 |
| deep_drawdown | 229 | -0.0651 | -0.0648 |
| high_volatility | 58 | -0.0525 | -0.0366 |

Historical sector/industry attribution is unavailable: no valid dated industry-membership source was supplied. Current industry concentration is separately available and was never backfilled into development.

### Actual ranking counterfactuals

The frozen V15 model was reranked after replacing each correlated family with query medians. This is a diagnostic, not a refit or causal experiment. Diagnostic replacement fills missing values; the selected V16 implementation explicitly preserves missing values, hence its result differs from the diagnostic.

| ablated_family | median_xirr_top20_delta | mean_asset_drawdown_top20_delta | target_shortfall_top20_delta |
| --- | --- | --- | --- |
| ath | 0.1905 | -0.0723 | 0.0052 |
| goal_user | -0.0240 | -0.0643 | 0.0041 |
| growth | 0.1148 | -0.0038 | -0.0093 |
| risk | -0.0995 | -0.0812 | 0.0130 |

Removing risk makes12M return and drawdown worse. Removing ATH improves return but leaves drawdown worse (−7.23pp); removing goal/user changes little of the drawdown loss. Growth-family neutralization is the only tested family diagnostic that improves both clearly. Therefore neither a broad defensive shift nor removing ATH is justified.

## Good versus bad profiles

All nine profiles have the same12-month forward horizon. Lookback12/36/60 are investor observation windows, not different investment horizons. V15 improves median return in every profile except lookback12. Promoted-stock mean raw growth SHAP is+0.395 at12M versus+0.167 for base7500 and+0.104 at60M; ATH support is+0.201 versus+0.141 and+0.158. Actual promoted and demoted stock rows and goal/affordability states are retained in `autopsy_all_profile_stock_behavior.csv.gz` and `autopsy_profile_selection_composition.csv`. Different recent plan-return inputs and their interaction with long-history growth are more consistent with the evidence than missing-data sparsity.

| profile | median_xirr_top20_delta | mean_asset_drawdown_top20_delta | target_shortfall_top20_delta | ndcg20_delta |
| --- | --- | --- | --- | --- |
| amount1000 | 0.2563 | 0.0082 | -0.0218 | 0.0599 |
| amount50000 | 0.1757 | -0.0006 | -0.0254 | 0.0448 |
| base7500 | 0.3089 | 0.0129 | -0.0276 | 0.0551 |
| lookback12 | -0.0666 | -0.0650 | 0.0064 | -0.0335 |
| lookback60 | 0.1353 | 0.0315 | -0.0117 | 0.0240 |
| quarterly | 0.1364 | 0.0148 | -0.0168 | 0.0383 |
| target10 | 0.0552 | 0.0233 | -0.0206 | 0.0177 |
| target30 | 0.3191 | 0.0101 | -0.0298 | 0.0609 |
| weekly | 0.2267 | 0.0086 | -0.0329 | 0.0490 |

## Hypothesis, minimum change, and selection

`hypothesis_lock.json` and `candidate_definitions.json` were written before any V16 candidate evaluation. Exactly three retained-growth weights were tested:0,0.25,0.5. No new model training, feature search, stock rule, NYKAA target, or exposed-period tuning occurred. The same maturity-purged V15 model files are reused. All original gates and the utility were retained. Weight0 was the only eligible candidate; weights0.25 and0.5 still failed the12M drawdown gate. No grid expansion followed.

For each growth input c at lookback<=12, replace its observed value by `g*c + (1-g)*within_query_median(c)`; preserve NaN. Use the original eight-field evidence confidence and the original20% maximum champion-guided correction. Selected g=0. All longer-lookback scores are exactly V15. Champion carry-XIRR, goal, CAGR3/5, affordability, and price-drawdown foundation are unchanged. ATH, risk, and goal/user correction inputs are unchanged. This deliberately removes cross-sectional growth-level differentiation from the short-lookback correction, while keeping growth in the champion foundation; it is not a claim that growth is irrelevant. Missingness can still affect tree paths, but there is no prescribed missing-history score subtraction.

## Locked development results

Mean across16 dates per profile, then nine equally weighted profiles; not a pooled-stock median or a20-stock shared-budget portfolio. Independent SIP plans retain the existing execution/label definitions.

| metric | V15_12m_delta | V16_12m_delta | V16_all_profile_delta | exposed_V16_delta |
| --- | --- | --- | --- | --- |
| coverage | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| ndcg20 | -0.0335 | 0.0112 | 0.0401 | 0.0798 |
| target_achievement_top20 | -0.0125 | 0.0094 | 0.0497 | 0.1106 |
| target_shortfall_top20 | 0.0064 | -0.0065 | -0.0215 | -0.0285 |
| median_xirr_top20 | -0.0666 | 0.0544 | 0.1853 | 0.1899 |
| mean_asset_drawdown_top20 | -0.0650 | -0.0084 | 0.0111 | 0.0323 |
| rank_ic | 0.0219 | 0.0164 | 0.0252 | 0.0119 |
| pairwise_accuracy | 0.0062 | 0.0038 | 0.0089 | 0.0053 |

| profile | median_xirr_top20_delta | mean_asset_drawdown_top20_delta | target_shortfall_top20_delta | ndcg20_delta |
| --- | --- | --- | --- | --- |
| amount1000 | 0.2563 | 0.0082 | -0.0218 | 0.0599 |
| amount50000 | 0.1757 | -0.0006 | -0.0254 | 0.0448 |
| base7500 | 0.3089 | 0.0129 | -0.0276 | 0.0551 |
| lookback12 | 0.0544 | -0.0084 | -0.0065 | 0.0112 |
| lookback60 | 0.1353 | 0.0315 | -0.0117 | 0.0240 |
| quarterly | 0.1364 | 0.0148 | -0.0168 | 0.0383 |
| target10 | 0.0552 | 0.0233 | -0.0206 | 0.0177 |
| target30 | 0.3191 | 0.0101 | -0.0298 | 0.0609 |
| weekly | 0.2267 | 0.0086 | -0.0329 | 0.0490 |

12M median-XIRR delta rises−6.66→+5.44pp; drawdown delta improves−6.50→−0.84pp, recovering87.0% of the disadvantage. Achievement rises−1.25→+0.94pp and shortfall switches+0.64→−0.65pp. Aggregate return improves18.53pp, achievement4.97pp, shortfall2.15pp, and drawdown1.11pp versus champion. Weekly and the other seven longer-lookback profiles are exactly V15, so this fix introduces no new profile regression there.

**The repair is uneven.** June2021’s12M return deficit worsens from−53.76 to−96.74pp; March2023 remains−75.36pp. The12M drawdown average passes the−1pp tolerance by only0.16pp. Four-year block bootstrap intervals include regression; these are descriptive intervals from only four dependent calendar blocks, not proof of statistical superiority.

| metric | p025 | p975 |
| --- | --- | --- |
| coverage_delta | 0.0000 | 0.0000 |
| ndcg20_delta | -0.0084 | 0.0387 |
| target_achievement_top20_delta | -0.0156 | 0.0375 |
| target_shortfall_top20_delta | -0.0158 | 0.0029 |
| median_xirr_top20_delta | -0.1680 | 0.3054 |
| mean_asset_drawdown_top20_delta | -0.0332 | 0.0118 |
| rank_ic_delta | -0.0034 | 0.0361 |
| pairwise_accuracy_delta | -0.0028 | 0.0104 |

Robustness outputs cover every profile and short/full history, high volatility, deep drawdown, deep ATH, old ATH, and recent ATH. See `development_cohorts_by_profile.csv` and `development_12m_cohorts.csv`. Within-cohort Top20 metrics differ from shares and outcomes of cohorts inside the overall Top20; both are reported. Aggregate high-volatility within-cohort drawdown is slightly worse than champion; recent-ATH within-cohort median return is slightly worse. These shared V15 weaknesses were not erased by an average repair.

## Turnover

V16 is targeted relative to V15: aggregate development Top20 overlap93.89%;94.47% for50 and95.51% for100. Within12M alone, Top20 overlap with V15 is45.0%, so the local repair is substantial. Relative to champion, aggregate Top20 overlap remains only40.14%, using the unchanged high-turnover exception (NDCG gain>=0.03 and shortfall improvement>=0.02). It is not low-turnover in absolute terms.

| comparison | top_n | overlap_fraction | mean_absolute_rank_movement |
| --- | --- | --- | --- |
| v15_vs_champion | 20 | 0.3969 | 207.6857 |
| v15_vs_champion | 50 | 0.4806 | 207.6857 |
| v15_vs_champion | 100 | 0.5765 | 207.6857 |
| v16_vs_champion | 20 | 0.4014 | 208.0189 |
| v16_vs_champion | 50 | 0.4706 | 208.0189 |
| v16_vs_champion | 100 | 0.5638 | 208.0189 |
| v16_vs_v15 | 20 | 0.9389 | 17.2536 |
| v16_vs_v15 | 50 | 0.9447 | 17.2536 |
| v16_vs_v15 | 100 | 0.9551 | 17.2536 |

## Current V7 research inference — after selection lock

The immutable V15 whole-share V7 replay was reused and its model scores reproduced to floating-point precision before applying V16. The V7 file hash and the feature-replay/model hashes are recorded. This uses the fresh V7/Yahoo feature and plan replay, not the stale September plan rows.29,295 rows are scored across39,924 company/profile rows; original quarantine is preserved. Official action authority ends September18, and absence of later non-split actions is not proved. Current outputs remain conditional research.

| profile | comparison | top_n | overlap | mean_absolute_rank_movement |
| --- | --- | --- | --- | --- |
| base7500 | v15_vs_champion | 20 | 12 | 211.8110 |
| base7500 | v15_vs_champion | 50 | 28 | 211.8110 |
| base7500 | v15_vs_champion | 100 | 61 | 211.8110 |
| lookback12 | v15_vs_champion | 20 | 4 | 236.0255 |
| lookback12 | v15_vs_champion | 50 | 28 | 236.0255 |
| lookback12 | v15_vs_champion | 100 | 54 | 236.0255 |
| base7500 | v16_vs_champion | 20 | 12 | 211.8110 |
| base7500 | v16_vs_champion | 50 | 28 | 211.8110 |
| base7500 | v16_vs_champion | 100 | 61 | 211.8110 |
| lookback12 | v16_vs_champion | 20 | 6 | 200.8592 |
| lookback12 | v16_vs_champion | 50 | 35 | 200.8592 |
| lookback12 | v16_vs_champion | 100 | 56 | 200.8592 |
| base7500 | v16_vs_v15 | 20 | 20 | 0.0000 |
| base7500 | v16_vs_v15 | 50 | 50 | 0.0000 |
| base7500 | v16_vs_v15 | 100 | 100 | 0.0000 |
| lookback12 | v16_vs_v15 | 20 | 15 | 126.6461 |
| lookback12 | v16_vs_v15 | 50 | 31 | 126.6461 |
| lookback12 | v16_vs_v15 | 100 | 73 | 126.6461 |

Base7500 remains V15: champion overlap12/20,28/50,61/100; V15/V16 overlap100%. Current12M V16/V15 overlap15/20,31/50,73/100. Full rankings include all three scores/ranks; Top20/50/100 and largest movers are saved for all profiles.

| profile | model | scored | missing_true_5y_top20 | median_history_months | median_days_since_high | mean_distance_high | mean_historical_max_drawdown | median_1y_growth | median_3y_growth | mean_volatility | mean_confidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base7500 | champion | 3238 | 0.8500 | 54.9815 | 27.0000 | -0.1105 | -0.5073 | 0.4332 | 0.4675 | 0.3810 | 0.8938 |
| lookback12 | champion | 3687 | 0.6500 | 58.1355 | 796.5000 | -0.4159 | -0.6399 | 0.3667 | 0.2115 | 0.4280 | 0.9187 |
| base7500 | v15 | 3238 | 0.6500 | 58.3326 | 29.0000 | -0.1771 | -0.5618 | 0.5492 | 0.5647 | 0.3797 | 0.9187 |
| lookback12 | v15 | 3687 | 0.8000 | 49.1663 | 344.5000 | -0.3321 | -0.6829 | 0.5895 | 0.5915 | 0.4779 | 0.8875 |
| base7500 | v16 | 3238 | 0.6500 | 58.3326 | 29.0000 | -0.1771 | -0.5618 | 0.5492 | 0.5647 | 0.3797 | 0.9187 |
| lookback12 | v16 | 3687 | 0.8500 | 48.0986 | 29.5000 | -0.2567 | -0.6478 | 0.6820 | 0.3479 | 0.4488 | 0.8938 |

Base Top20 missing true Yahoo5Y remains65% (champion85%). Current12M missing5Y is85% in V16 versus80% V15 and65% champion: the fix does not hard-filter young stocks, but history quality still needs attention. Current12M median1Y growth rises58.95→68.20%, median days since high falls344.5→29.5, and mean historical maximum drawdown improves−68.29→−64.78%. These are input composition diagnostics, not future outcome evidence. Current industry concentration and peer fundamentals are diagnostic only.

### ATH and user behavior survive

Current median-family sensitivity reranks stocks and changes the ATH-family Top20; growth calibration leaves the other feature families active. A post-lock synthetic ATH age/depth/duration audit compares30 days/5% below high with1825 days/70% below high, recomputing derived ATH depth fields while fixing all other inputs. The current12M raw correction declines for100% of scored rows, median−0.0882; base declines for99.88%, median−0.0836. This supports meaningful negative old/deep evidence without an identity or automatic rejection rule. It is a synthetic sensitivity, not a causal experiment; specific stocks can have positive ATH SHAP conditional on their other features.

| profile | scenario_vs_recent_near | raw_correction_median_change | negative_fraction |
| --- | --- | --- | --- |
| base7500 | old_near | -0.0557 | 0.9972 |
| base7500 | recent_deep | -0.0836 | 0.9549 |
| base7500 | old_deep | -0.0836 | 0.9988 |
| lookback12 | old_near | -0.0557 | 1.0000 |
| lookback12 | recent_deep | -0.0836 | 0.9580 |
| lookback12 | old_deep | -0.0882 | 1.0000 |

User personalization remains: current lookback12/base overlap8/20 and60M/base1/20. Amount, frequency, and target changes retain the existing distinct rankings. Direct goal/user family replacement changes current Top20, and growth calibration does not wash out the user input features.

| model | profile | top20_overlap_with_base | mean_absolute_rank_displacement | mean_absolute_percentile_change |
| --- | --- | --- | --- | --- |
| v16 | amount1000 | 18 | 28.7733 | 0.0084 |
| v16 | amount50000 | 19 | 10.8911 | 0.0033 |
| v16 | base7500 | 20 | 0.0000 | 0.0000 |
| v16 | lookback12 | 8 | 649.7656 | 0.1674 |
| v16 | lookback60 | 1 | 421.2242 | 0.1226 |
| v16 | quarterly | 18 | 71.4759 | 0.0220 |
| v16 | target10 | 17 | 49.7641 | 0.0154 |
| v16 | target30 | 19 | 42.2001 | 0.0130 |
| v16 | weekly | 19 | 36.7440 | 0.0112 |

### NYKAA diagnostic only

Base ranks: frozen September champion1; refreshed champion5; V15=V16=6; prior V14 reference213. No targeted rank was sought. Trusted current growth is35.06%1Y and30.60%3Y; true5Y is unavailable. It is21.80% below its recorded high, with1765 days since high and underwater. Annual volatility27.75%, downside17.05%; plan attainment1.21, historical goal-window achievement75%, utilization99.96%, confidence87.5%. Strong recent return and goal fit maintain the champion foundation. Original correction raw family SHAP is ATH+0.07995, growth−0.01453, risk−0.04070, and goal/user−0.04283: the model does not impose blanket rejection for an old high. Current ROCE17.23%, ROE15.29%, both about87th percentile among15 E-Retail/E-Commerce peers;3Y growth about85th percentile among69 Retailing names. Fundamentals/peers do not cause its trained score. Detailed features and ranks for every user profile are in the NYKAA artifacts.

## Exposed2024–2025 supporting evidence

This period was already known in earlier research. It was accessed for V16 only after the selection lock; it is not blind validation and was not used for tuning. Aggregate median-XIRR delta+18.99pp, achievement+11.06pp, shortfall−2.85pp, drawdown+3.23pp, NDCG+0.07975.12M return+30.37pp and drawdown+5.91pp. Every unchanged development gate passes here, but these results do not authorize promotion. Full profile/date, cohort, score, and turnover outputs are saved separately under `exposed_2024_2025_*`.

## Integrity and evidence limits

No V14, V15, frozen champion, tracked production/website, or Railway configuration was edited; no deployment or service write occurred. Protected artifacts are hashed before and verified after the experiment in `integrity_audit.json`. No current V7 values or current fundamentals/classifications enter historical rows. Historical score inputs use dated price windows; reused correction fits are maturity-purged before2020-03-31 for development and2024-03-31 for exposed evaluation; current fit labels mature before2026-10-03. Champion historical comparisons use maturity-purged refits of its frozen recipe rather than applying future2026 weights backward.

This is not proof of a fully unbiased point-in-time investment study: the frozen research universe retains survivorship/selection exposure, provider revisions and historical publication availability are not fully proved, overlapping12-month labels correlate dates, and current post-ledger action completeness is conditional. No identity feature or NYKAA rule exists. All three candidates and selection rules were locked before current/exposed evaluation. The post-lock feature/ATH audits did not alter selection.

## Reproduction and artifacts

See `REPRODUCE.md`. The runner writes only V16 artifacts and this report. `manifest.json` covers the runner, report, locks, results, and audit files. Protected inputs are recorded separately. The completed experiment is frozen: reproduce in a separate checkout/output directory; do not overwrite locks.

## Answers

**Why did V15 fail?** At12M, its correction strongly promoted long-history, deeply underwater names through5Y/7Y/10Y growth signals, displacing stronger recent plan-return picks. High observed-field confidence did not detect the mismatch; losses were regime-dependent and drawdown deterioration broad.

**What changed?** Only short-lookback correction growth levels are calibrated to query medians; NaNs, original confidence, champion foundation, ATH, risk, and user-goal inputs are preserved.

**Did it fix the problem?** It repairs the average return loss and87% of the drawdown disadvantage, passes the locked gates, and leaves the other eight profiles unchanged. It does not fix every date or eliminate all cohort/turnover risks.

**Does it deserve to replace d499580?** No. It is a promising research challenger requiring unexposed validation and stronger execution evidence before replacement.
