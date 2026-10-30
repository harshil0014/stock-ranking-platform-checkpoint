# V14 independent ranking model — research result

**Verdict: FROZEN CHAMPION RETAINS.** Production d499580 remains untouched. V14 is a separately trained LightGBM LambdaRank model; its features exclude the champion score/rank and stock identity.

## Evidence and selection

V12 provides 1,516,870 historical date/profile/security rows on 50 dates (2015-01-31 to 2025-08-31). The development model trains only on labels ending before 2020-03-31. Six initial label/parameter combinations, 15 goal blends of the leading configurations, and eight return-oriented extensions were compared on 16 decisions in 2020–2023. The return extension was declared after observing development median-XIRR losses, before any V14 post-development evaluation. The selected configuration was locked in `selection_lock_v3.json` (SHA256 `7c76ff6f7667e078cb55d1ad28628ebf9e83671bae468a8535bcb503b9523b45`) before V14's 2024–2025 evaluation. The final model trains only on labels ending strictly before 2024-03-31. All 2024–2025 dates were already exposed to earlier research: this is retrospective evaluation, not a new blind test.

Selected configuration: `balanced` relevance, `regularized` parameters, goal percentile weight 0.25, 713,541 final training rows across 306 date/profile groups. Label relevance is a weighted average of within-date/profile percentile return, reversed shortfall, drawdown, and achievement, bucketed 0–3. Exact weights and model parameters are in the machine artifacts. Overlapping 12-month outcomes share evidence: adjacent evaluation decisions overlap by 273–337 days. Rows are not independent trials.

The locked balanced label weights are {'xirr': 0.4, 'shortfall': 0.25, 'drawdown': 0.2, 'achievement': 0.15}; LightGBM parameters are {'n_estimators': 120, 'learning_rate': 0.035, 'num_leaves': 11, 'max_depth': 4, 'min_child_samples': 250, 'reg_lambda': 30, 'colsample_bytree': 0.8, 'lambdarank_truncation_level': 30}. Features cover contribution amount/count/frequency, horizon and target, historical plan score, whole-share affordability and cash use, adjusted price growth (strict 1Y/7Y/10Y where observed), 3Y/5Y, old highs, underwater duration, drawdown, volatility, explicit history completeness, and same-date percentiles. Historical price ratios use observations at or before the decision date with a seven-day anchor tolerance. Missing ranks remain missing; current professor values enter only current inference at equal priority. No historical sector label or current fundamental was backfilled.

## Development tournament

| label | params | goal_weight | eligible | utility | robustness_failed | delta_ndcg20 | delta_target_shortfall_top20 | delta_mean_asset_drawdown_top20 | weekly_shortfall_delta |
|---|---|---|---|---|---|---|---|---|---|
| balanced | regularized | 0.25000 | False | 0.07573 | False | -0.00914 | -0.02506 | 0.13230 | -0.02617 |
| goal | regularized | 0.25000 | False | 0.02297 | False | -0.03223 | -0.02230 | 0.12186 | -0.02861 |
| balanced | regularized | 0.50000 | False | 0.01390 | False | -0.02083 | -0.01886 | 0.09783 | -0.01617 |
| return | compact | 0.25000 | False | -0.00286 | False | -0.03824 | -0.02475 | 0.11671 | -0.02681 |
| return | regularized | 0.00000 | False | -0.02454 | False | -0.05867 | -0.02115 | 0.07936 | -0.02496 |
| return | compact | 0.50000 | False | -0.02630 | False | -0.04959 | -0.02178 | 0.10334 | -0.02338 |
| return | compact | 0.67000 | False | -0.05549 | False | -0.05551 | -0.01758 | 0.08712 | -0.01549 |
| balanced | regularized | 0.67000 | False | -0.08542 | False | -0.03603 | -0.01217 | 0.08841 | -0.01215 |
| goal | compact | 0.25000 | False | -0.08574 | False | -0.08289 | -0.01688 | 0.10775 | -0.01574 |
| goal | regularized | 0.50000 | False | -0.08752 | False | -0.05254 | -0.01338 | 0.09923 | -0.01510 |
| goal | regularized | 0.80000 | False | -0.09711 | False | -0.05947 | -0.01118 | 0.08645 | -0.01057 |
| goal | regularized | 0.67000 | False | -0.10270 | False | -0.05498 | -0.01146 | 0.09180 | -0.01223 |
| goal | compact | 0.67000 | False | -0.10568 | False | -0.07764 | -0.01569 | 0.08833 | -0.01828 |
| goal | compact | 0.80000 | False | -0.10883 | False | -0.07642 | -0.01449 | 0.08067 | -0.01547 |
| goal | compact | 0.50000 | False | -0.11086 | False | -0.08065 | -0.01605 | 0.09470 | -0.01603 |
| return | regularized | 0.50000 | False | -0.11806 | False | -0.07031 | -0.01621 | 0.08057 | -0.01362 |
| balanced | regularized | 0.80000 | False | -0.11827 | False | -0.04512 | -0.00807 | 0.07727 | -0.00845 |
| goal | compact | 0.00000 | False | -0.12495 | False | -0.09996 | -0.02554 | 0.15315 | -0.03004 |
| return | regularized | 0.67000 | False | -0.13000 | False | -0.07340 | -0.01510 | 0.06678 | -0.01212 |
| return | regularized | 0.25000 | False | -0.14397 | False | -0.07726 | -0.01906 | 0.10367 | -0.02024 |
| return | compact | 0.00000 | False | -0.16090 | False | -0.06571 | -0.02616 | 0.17606 | -0.03177 |
| balanced | regularized | 0.00000 | False | -0.19202 | False | -0.06608 | -0.02067 | 0.19321 | -0.02845 |
| goal | regularized | 0.00000 | False | -0.21599 | False | -0.07571 | -0.01534 | 0.16264 | -0.02231 |

Selected candidate on development (the median-XIRR loss violates selection eligibility):

| metric | champion | v14 | delta |
|---|---|---|---|
| coverage | 0.79290 | 0.79290 | 0.00000 |
| rank_ic | -0.02820 | -0.00491 | 0.02328 |
| ndcg20 | 0.52539 | 0.51626 | -0.00914 |
| pairwise_accuracy | 0.49130 | 0.49964 | 0.00834 |
| target_achievement_top20 | 0.56181 | 0.54271 | -0.01910 |
| target_shortfall_top20 | 0.08279 | 0.05773 | -0.02506 |
| median_xirr_top20 | 0.35009 | 0.26466 | -0.08544 |
| mean_xirr_top20 | 4.16498 | 5.43774 | 1.27275 |
| mean_asset_drawdown_top20 | -0.35396 | -0.22166 | 0.13230 |

## Known retrospective evaluation versus champion

Mean XIRR is reported for completeness and has zero selection weight because outliers can dominate it.

| metric | champion | v14 | delta |
|---|---|---|---|
| coverage | 0.88210 | 0.88210 | 0.00000 |
| rank_ic | 0.10318 | 0.13211 | 0.02893 |
| ndcg20 | 0.56597 | 0.71601 | 0.15004 |
| pairwise_accuracy | 0.53624 | 0.54938 | 0.01314 |
| target_achievement_top20 | 0.34537 | 0.41435 | 0.06898 |
| target_shortfall_top20 | 0.13538 | 0.07170 | -0.06368 |
| median_xirr_top20 | -0.03283 | 0.13365 | 0.16648 |
| mean_xirr_top20 | 12.49298 | 14.08893 | 1.59595 |
| mean_asset_drawdown_top20 | -0.44283 | -0.29080 | 0.15203 |

Profile deltas (V14 minus champion; drawdown improvement is positive):

| profile | ndcg20_delta | target_achievement_top20_delta | target_shortfall_top20_delta | median_xirr_top20_delta | mean_asset_drawdown_top20_delta |
|---|---|---|---|---|---|
| amount1000 | 0.17144 | 0.12083 | -0.06639 | 0.17279 | 0.12364 |
| amount50000 | 0.14971 | 0.02083 | -0.06583 | 0.14193 | 0.16691 |
| base7500 | 0.14184 | 0.06250 | -0.05853 | 0.12602 | 0.14980 |
| lookback12 | 0.21701 | 0.16250 | -0.10171 | 0.41159 | 0.20169 |
| lookback60 | 0.09961 | 0.01250 | -0.04085 | 0.16690 | 0.12886 |
| quarterly | 0.17450 | 0.12917 | -0.06552 | 0.17827 | 0.12511 |
| target10 | 0.13714 | 0.07083 | -0.05517 | 0.06806 | 0.15370 |
| target30 | 0.13988 | 0.03750 | -0.05949 | 0.11909 | 0.15030 |
| weekly | 0.11918 | 0.00417 | -0.05964 | 0.11371 | 0.16828 |

Date deltas (negative achievement/return/drawdown and positive shortfall are regressions):

| decision_date | ndcg20_delta | target_achievement_top20_delta | target_shortfall_top20_delta | median_xirr_top20_delta | mean_asset_drawdown_top20_delta |
|---|---|---|---|---|---|
| 2024-03-31 | 0.20565 | 0.18333 | -0.09755 | 0.34956 | 0.14923 |
| 2024-06-30 | 0.16526 | 0.06667 | -0.05580 | 0.10156 | 0.13141 |
| 2024-09-30 | 0.17194 | 0.11111 | -0.06299 | 0.17972 | 0.18272 |
| 2024-12-31 | 0.21544 | 0.20000 | -0.08588 | 0.26049 | 0.16814 |
| 2025-01-31 | 0.30972 | 0.25556 | -0.14009 | 0.43538 | 0.20690 |
| 2025-02-28 | 0.22284 | 0.11667 | -0.10420 | 0.40136 | 0.17794 |
| 2025-03-31 | 0.22891 | -0.03889 | -0.08345 | 0.16677 | 0.20575 |
| 2025-04-30 | 0.09675 | -0.03333 | -0.03287 | 0.01616 | 0.17845 |
| 2025-05-31 | 0.02013 | -0.07222 | -0.00013 | -0.15213 | 0.12814 |
| 2025-06-30 | 0.10589 | 0.02222 | -0.05267 | 0.12048 | 0.12819 |
| 2025-07-31 | 0.06962 | 0.02222 | -0.03511 | 0.07781 | 0.07701 |
| 2025-08-31 | -0.01172 | -0.00556 | -0.01343 | 0.04065 | 0.09051 |

Selected Top-20 composition by historical cohort (outcomes within the selected cohort are in the CSV):

| model | cohort | share_of_all_top20 | target_shortfall | median_xirr | mean_drawdown |
|---|---|---|---|---|---|
| champion | cohort_short_history | 0.04352 | 0.17533 | -0.12258 | -0.42697 |
| champion | cohort_no_true_5y | 0.06250 | 0.14306 | 0.01887 | -0.43938 |
| champion | cohort_high_downside | 0.42870 | 0.17036 | -0.15629 | -0.47596 |
| champion | cohort_old_ath | 0.61667 | 0.13403 | -0.01966 | -0.45784 |
| champion | cohort_deep_below_ath | 0.65509 | 0.14527 | -0.05239 | -0.46722 |
| v14 | cohort_short_history | 0.00000 |  |  |  |
| v14 | cohort_no_true_5y | 0.02407 | 0.00000 | 3.76879 | -0.27649 |
| v14 | cohort_high_downside | 0.00648 | 0.08046 | 0.01927 | -0.35917 |
| v14 | cohort_old_ath | 0.22083 | 0.03976 | 0.76668 | -0.34842 |
| v14 | cohort_deep_below_ath | 0.17500 | 0.03349 | 1.24994 | -0.39193 |

## Current inference on trusted equal-priority data

The same V14 model scored the frozen current plan cohort with the professor current overlay as a normal trusted fallback. The professor provenance field is retained only in the source audit, never fed into the model. Risk-only raw BSE fallback values were excluded from model inputs for 1 profile rows. This mixes the frozen 2026-09-18 plan snapshot with later current professor fills, so it is an illustrative current-data research inference, not a point-in-time backtest. Current inference does not alter the website.

| top_n | champion_missing_true_5y | v14_missing_true_5y | overlap | turnover |
|---|---|---|---|---|
| 20 | 0.70000 | 0.00000 | 4 | 0.80000 |
| 50 | 0.34000 | 0.00000 | 15 | 0.70000 |
| 100 | 0.22000 | 0.04000 | 32 | 0.68000 |

The base-profile Top 20 changes 16 of 20 names and selects no security without observed true 5Y history. This may be an age overcorrection; it is one reason current behavior does not justify promotion. Current sector labels are used here only for diagnostics:

| model | top_n | sector_hhi | largest_sector | largest_sector_share |
|---|---|---|---|---|
| champion | 20 | 0.07500 | Consumer Cyclical | 0.10000 |
| champion | 50 | 0.06000 | Pharmaceuticals & Biotechnology | 0.12000 |
| champion | 100 | 0.04980 | Consumer Cyclical | 0.09000 |
| v14 | 20 | 0.07500 | Finance | 0.15000 |
| v14 | 50 | 0.08000 | Pharmaceuticals & Biotechnology | 0.20000 |
| v14 | 100 | 0.05180 | Pharmaceuticals & Biotechnology | 0.14000 |

Known-evaluation adjacent-date Top-20 turnover: champion 0.798, V14 0.470. These 12-month windows overlap heavily, so stability is descriptive.

Base profile current Top 20 (Top 50 and Top 100 for every profile are separate CSV artifacts):

| v14_rank | ticker | company | champion_rank | has_true_5y |
|---|---|---|---|---|
| 1.00000 | TITAN | Titan Company Limited | 40.00000 | 1.00000 |
| 2.00000 | JSWSTEEL | JSW Steel Limited | 54.00000 | 1.00000 |
| 3.00000 | GRASIM | Grasim Industries Limited | 49.00000 | 1.00000 |
| 4.00000 | TORNTPHARM | Torrent Pharmaceuticals Limited | 42.00000 | 1.00000 |
| 5.00000 | FEDERALBNK | The Federal Bank  Limited | 32.00000 | 1.00000 |
| 6.00000 | EICHERMOT | Eicher Motors Limited | 44.00000 | 1.00000 |
| 7.00000 | MARICO | Marico Limited | 109.00000 | 1.00000 |
| 8.00000 | BAJFINANCE | Bajaj Finance Limited | 76.00000 | 1.00000 |
| 9.00000 | SHRIRAMFIN | Shriram Finance Limited | 16.00000 | 1.00000 |
| 10.00000 | HINDALCO | Hindalco Industries Limited | 66.00000 | 1.00000 |
| 11.00000 | DIVISLAB | Divi's Laboratories Limited | 75.00000 | 1.00000 |
| 12.00000 | BSE-519413 | DATIWARE MARITIME INFRA LIMITE | 12.00000 | 1.00000 |
| 13.00000 | PRIVISCL | Privi Speciality Chemicals Limited | 15.00000 | 1.00000 |
| 14.00000 | CHOLAFIN | Cholamandalam Investment and Finance Company Limited | 34.00000 | 1.00000 |
| 15.00000 | BSE-511185 | RAJVI LOGITRADE LIMITED | 18.00000 | 1.00000 |
| 16.00000 | BSE-540718 | AAYUSH ART AND BULLION LIMITED | 90.00000 | 1.00000 |
| 17.00000 | AXISBANK | Axis Bank Limited | 381.00000 | 1.00000 |
| 18.00000 | RADICO | Radico Khaitan Limited | 25.00000 | 1.00000 |
| 19.00000 | ASAHIINDIA | Asahi India Glass Limited | 45.00000 | 1.00000 |
| 20.00000 | APOLLOHOSP | Apollo Hospitals Enterprise Limited | 105.00000 | 1.00000 |

NYKAA diagnostic (base7500): [{'champion_rank': 1.0, 'v14_rank': 213.0, 'days_since_recorded_high': 1752.0, 'distance_from_recorded_high': -0.20063375, 'downside_volatility_1y': 0.16925497, 'history_months': 58.250515}]. Its identity did not enter training or selection.

## What V14 learned

| feature | gain | split | family |
|---|---|---|---|
| price_drawdown | 7178.69740 | 56 | base_goal_execution |
| history_months | 2014.53754 | 104 | history_growth_risk |
| pct_observed_cagr_5y | 1588.31919 | 106 | relative |
| pct_downside_volatility_1y | 1455.46370 | 67 | relative |
| pct_cagr_3y | 1412.77794 | 86 | relative |
| realized_volatility_1y | 1326.12198 | 40 | history_growth_risk |
| original_cagr_5y | 1109.90141 | 83 | base_goal_execution |
| strict_cagr_10y | 1094.68993 | 53 | history_growth_risk |
| recorded_high_price_derived | 878.93664 | 40 | derived_personalization_missingness |
| pct_history_months | 851.06260 | 53 | relative |
| cagr_3y | 769.35071 | 34 | base_goal_execution |
| full_history_max_drawdown | 743.47510 | 31 | history_growth_risk |
| pct_distance_from_recorded_high | 586.68834 | 50 | relative |
| downside_volatility_1y | 520.22934 | 33 | history_growth_risk |
| strict_cagr_7y | 439.52122 | 20 | history_growth_risk |
| history_start_cagr | 419.10002 | 31 | history_growth_risk |
| pct_full_history_max_drawdown | 403.40125 | 25 | relative |
| momentum_6m | 389.19248 | 19 | history_growth_risk |
| terminal_price | 370.60162 | 38 | base_goal_execution |
| pct_strict_cagr_1y | 352.12772 | 40 | relative |

Family gain totals:

| family | gain | split |
|---|---|---|
| base_goal_execution | 9691.26766 | 234 |
| history_growth_risk | 9072.03467 | 474 |
| relative | 6929.15278 | 452 |
| derived_personalization_missingness | 878.93664 | 40 |

Current-cohort mean absolute TreeSHAP contributions (deterministic 1-in-20 row sample):

| feature | mean_abs_shap |
|---|---|
| price_drawdown | 0.11796 |
| original_cagr_5y | 0.07874 |
| history_months | 0.06579 |
| cagr_3y | 0.06569 |
| pct_downside_volatility_1y | 0.04739 |
| realized_volatility_1y | 0.03213 |
| pct_cagr_3y | 0.03102 |
| pct_distance_from_recorded_high | 0.02944 |
| pct_days_since_recorded_high | 0.02579 |
| strict_cagr_10y | 0.02482 |
| pct_observed_cagr_5y | 0.02480 |
| strict_cagr_7y | 0.01992 |
| momentum_6m | 0.01961 |
| pct_strict_cagr_1y | 0.01893 |
| recorded_high_price_derived | 0.01860 |

A tree can move a stock based on combinations of plan affordability, historical goal performance, growth, history age, distance from highs, underwater duration, and downside volatility. Gain describes fitted split usage, not a causal effect or guaranteed direction. Missing history is passed as NaN with explicit flags; missing relative percentiles remain NaN.

## Integrity and limits

Panel SHA256 `c0b2f5f66836c487340237cc1df231e2f3d2835febcb09b84c0adffb1ab57371`; prepared PIT feature SHA256 `b5fa0a1f0229bde692b2c07e0a05cfe91f7501a9deeba6c4bcd9109f00d36fb7`; frozen manifest SHA256 `f9919146a1dc5a0584f5c23a5ab288668b13298cc8f4bbf46a2b89c65d754035`. Frozen current-model predictions and blend reproduce to below 1e-12 absolute error. Original source dates and provider V2 panel remain unchanged. No present-day professor value or sector was used on historical rows, and no future outcome, endpoint, identity, or champion score was a V14 feature. The historical champion comparator is the existing maturity-purged V12 walk-forward reproduction of d499580 logic; it is not a fresh deployment of the frozen 2026 model into its own training past. This limits exact historical comparability. Current inference uses the actual frozen 2026 champion output with research-only current professor values. Model selection saw 16 overlapping development dates, and all later V12 dates were already known in prior research. A fresh, independent future period is required for promotion.

The known-evaluation robustness gate passed, but no development candidate met the predeclared eligibility rule. The selected candidate lost 8.54 percentage points of median Top-20 XIRR during development. Its later model had more matured training history and did much better retrospectively, yet those later dates were previously exposed and the current Top-20 turnover is high. These facts prevent promotion. No production, Railway, website, or frozen champion file changed.
