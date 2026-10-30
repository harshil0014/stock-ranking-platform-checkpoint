# V17 trained personalized ranking model — 2026-10-03

**Research outcome: a materially improved trained challenger. Verdict: PROMISING CHALLENGER.** All nine development profiles improve median return, drawdown, and target shortfall versus champion. Frozen production remains d499580; this research did not deploy or authorize replacement.

## What was trained and why

The model combines two trained components: a monotone utility regressor on neutral percentile features and separate LambdaMART rankers for12/36/60-month investor lookbacks. Their prediction percentiles are averaged equally. The result provides at most30% of the final score, scaled by observed-field confidence; the champion supplies the remainder. Annual expanding fits use only labels whose endpoints precede the first decision date in that year. Current models are refitted on all labels mature before2026-10-03. All profiles have a12-month forward investment horizon; lookback is a separate input.

V15 froze its correction before2020 while the historical champion refreshed. V16 suppressed short-lookback growth inputs. V17 instead retrains, models investor lookbacks separately, and combines a return-oriented specialist with a constrained model. In the constrained component, better growth/goal fit cannot directly lower prediction and deeper/prolonged drawdowns cannot directly raise it. Missing values are neutral0.5 percentiles, with no age or source identity predictor. The raw specialist retains missing-value paths and nonlinear interactions; therefore this is not a mathematical guarantee of identical scores when evidence is removed. Missing evidence reduces correction confidence rather than imposing a fixed age penalty.

The initial ensemble had positive old/deep ATH response in the60M specialist. An additional development-only audit led to ATH sign constraints for that specialist. Other specialists already showed negative mean old/deep responses. Broad constraints and score caps were also tried and retained in the trial ledger; only the targeted60M repair met all fixed selection gates.

## Research and trial discipline

The search tested39 configurations across five documented rounds. Round1 compared refreshed V15, lookback specialists, neutral ranking, monotone regression, monotone ranking, and a trained neural RankNet. Round2 combined complementary predictions. Round3 constrained ATH relationships, round4 tested score bounds, and round5 targeted the identified60M interaction. Every round wrote its hypothesis/grid before evaluating its candidates. The gate thresholds were never relaxed. Every trial, including unsuccessful ones, remains in `complete_trial_ledger.csv`. This is adaptive development research with multiple-testing exposure, not a blind39-way contest.

Sources that informed the design: [cross-sectional learning to rank](https://arxiv.org/abs/2012.07149), [nonlinear asset-pricing interactions](https://www.nber.org/papers/w25398), [ranking-loss comparison](https://arxiv.org/abs/2204.01500), [LightGBM objectives and monotone constraints](https://lightgbm.readthedocs.io/en/stable/Parameters.html), and [backtest overfitting](https://escholarship.org/uc/item/4w1110bb). [MASTER](https://arxiv.org/abs/2312.15235) and [TabPFN](https://github.com/PriorLabs/TabPFN) were investigated. Neither pretrained checkpoint was used; direct local training avoids an unaudited financial pretraining history, and documented CPU TabPFN scale is poorly matched to this panel. Published investment results were not assumed to transfer here.

## Development results

Metrics average within-date/profile Top20 outcomes, then average over16 dates and nine equally weighted profiles. XIRR is the mean of date-level Top20 medians, not mean stock return. Drawdown is mean realized asset drawdown, not portfolio drawdown. Independent full-budget SIP plans follow the existing simulator. Values are fractions; multiply by100 for percentage points.

| metric | development_V17_delta | development_V16_delta | exposed_V17_delta |
| --- | --- | --- | --- |
| coverage | 0.0000 | 0.0000 | 0.0000 |
| ndcg20 | 0.0557 | 0.0401 | 0.1413 |
| target_achievement_top20 | 0.0396 | 0.0497 | 0.1921 |
| target_shortfall_top20 | -0.0221 | -0.0215 | -0.0403 |
| median_xirr_top20 | 0.2237 | 0.1853 | 0.3898 |
| mean_asset_drawdown_top20 | 0.0476 | 0.0111 | 0.0345 |
| rank_ic | 0.0272 | 0.0252 | 0.0229 |
| pairwise_accuracy | 0.0097 | 0.0089 | 0.0086 |

| profile | median_xirr_top20_delta | mean_asset_drawdown_top20_delta | target_achievement_top20_delta | target_shortfall_top20_delta |
| --- | --- | --- | --- | --- |
| amount1000 | 0.2351 | 0.0307 | 0.0250 | -0.0216 |
| amount50000 | 0.3074 | 0.0397 | 0.0500 | -0.0235 |
| base7500 | 0.2883 | 0.0339 | 0.0500 | -0.0219 |
| lookback12 | 0.2951 | 0.0390 | 0.0844 | -0.0264 |
| lookback60 | 0.0138 | 0.0879 | -0.0031 | -0.0186 |
| quarterly | 0.2724 | 0.0479 | 0.0312 | -0.0203 |
| target10 | 0.0613 | 0.0712 | 0.0031 | -0.0196 |
| target30 | 0.2853 | 0.0390 | 0.0656 | -0.0247 |
| weekly | 0.2544 | 0.0388 | 0.0500 | -0.0225 |

Development median XIRR improves22.37pp overall, drawdown4.76pp, shortfall2.21pp, and target achievement3.96pp. The12M-lookback profile gains29.51pp median XIRR and3.90pp drawdown; V15 lost6.66pp and6.50pp respectively. V17 improves aggregate return and drawdown over V16, though V16 has higher aggregate achievement gain. Every profile has positive median-return and drawdown deltas in the selected annual-fit result. All original gates plus nonnegative returns in every profile and nonnegative12M drawdown pass.

## Stability and uncertainty

The exact final model was checked with two additional seeds and refits at every decision date. These results do not select a lucky seed; deployed-research inference keeps seed20261003 and the locked formula. Failures of the stricter check, if any, remain visible below.

| variant | original_gates_pass | strict_gates_pass | median_return_delta | drawdown_delta | 12m_return_delta | 12m_drawdown_delta | worst_profile_return_delta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| seed20261004 | True | False | 0.2116 | 0.0452 | 0.4065 | 0.0223 | -0.0161 |
| seed20261005 | True | False | 0.1545 | 0.0473 | 0.4245 | 0.0063 | -0.0040 |
| per_date | True | False | 0.1756 | 0.0500 | 0.4210 | 0.0107 | -0.0183 |

Year-block intervals use only four calendar blocks and do not adjust for adaptive model selection. They quantify conditional development variation; they do not establish future profitability.

| scope | metric | delta | p025 | p975 |
| --- | --- | --- | --- | --- |
| ALL | median_xirr_top20 | 0.2237 | 0.0856 | 0.3199 |
| ALL | mean_asset_drawdown_top20 | 0.0476 | -0.0005 | 0.0947 |
| lookback12 | median_xirr_top20 | 0.2951 | 0.2429 | 0.3473 |
| lookback12 | mean_asset_drawdown_top20 | 0.0390 | 0.0208 | 0.0615 |
| weekly | median_xirr_top20 | 0.2544 | 0.1052 | 0.3434 |
| weekly | mean_asset_drawdown_top20 | 0.0388 | -0.0224 | 0.0997 |

Robustness is evaluated for every profile and short/full history, high volatility, deep drawdown, deep ATH, old ATH, and recent ATH. Both within-cohort Top20 metrics and cohort share/outcomes inside the overall Top20 are saved. High-volatility within-cohort drawdown remains a weakness; it is not hidden by the overall risk improvement.

| cohort | model | share_overall_top20 | median_xirr_top20 | mean_asset_drawdown_top20 |
| --- | --- | --- | --- | --- |
| short_history | champion | 0.0670 | 0.1565 | -0.3716 |
| short_history | v17 | 0.0813 | 0.1837 | -0.3634 |
| full_history | champion | 0.9295 | 0.3279 | -0.3551 |
| full_history | v17 | 0.9128 | 0.5376 | -0.2981 |
| high_volatility | champion | 0.2313 | 0.4733 | -0.4325 |
| high_volatility | v17 | 0.0594 | 0.5194 | -0.4503 |
| deep_drawdown | champion | 0.8316 | 0.4292 | -0.3685 |
| deep_drawdown | v17 | 0.8347 | 0.5257 | -0.3150 |
| deep_ath | champion | 0.6038 | 0.4536 | -0.3943 |
| deep_ath | v17 | 0.6931 | 0.5034 | -0.3240 |
| old_ath | champion | 0.6316 | 0.4530 | -0.3799 |
| old_ath | v17 | 0.7382 | 0.5414 | -0.3146 |
| recent_ath | champion | 0.2108 | 0.2193 | -0.3304 |
| recent_ath | v17 | 0.1708 | 0.2445 | -0.3168 |

## Turnover

The model is still a substantial correction. It qualifies under the original high-turnover exception, which requires NDCG gain>=0.03 and shortfall improvement>=0.02. It should not be described as a low-turnover replacement.

| comparison | top_n | overlap_fraction | mean_absolute_rank_movement |
| --- | --- | --- | --- |
| v17_vs_champion | 20 | 0.4563 | 238.1418 |
| v17_vs_champion | 50 | 0.5315 | 238.1418 |
| v17_vs_champion | 100 | 0.6002 | 238.1418 |
| v17_vs_v15 | 20 | 0.5149 | 192.1793 |
| v17_vs_v15 | 50 | 0.5951 | 192.1793 |
| v17_vs_v15 | 100 | 0.6509 | 192.1793 |
| v17_vs_v16 | 20 | 0.5226 | 192.9820 |
| v17_vs_v16 | 50 | 0.6044 | 192.9820 |
| v17_vs_v16 | 100 | 0.6574 | 192.9820 |

## Exposed supporting evaluation

The2024–2025 period was already exposed in earlier experiments. It was accessed for V17 only after `selection_lock.json` was written and was never used to revise the selected model. The aggregate table above reports these results separately; full profile/date scores are in `exposed_*`. Historical evaluation refits annually with labels strictly mature before each year’s first decision. Differences from earlier V15/V16 fixed evaluation fits are therefore model-plus-training-policy differences.

| profile | median_xirr_top20_delta | mean_asset_drawdown_top20_delta | target_shortfall_top20_delta |
| --- | --- | --- | --- |
| amount1000 | 0.2479 | 0.0261 | -0.0363 |
| amount50000 | 0.5566 | 0.0269 | -0.0473 |
| base7500 | 0.4147 | 0.0342 | -0.0388 |
| lookback12 | 0.5098 | 0.0843 | -0.0659 |
| lookback60 | 0.2679 | 0.0235 | -0.0244 |
| quarterly | 0.2921 | 0.0310 | -0.0392 |
| target10 | 0.3842 | 0.0150 | -0.0292 |
| target30 | 0.3401 | 0.0363 | -0.0410 |
| weekly | 0.4945 | 0.0333 | -0.0405 |

## Current V7 rankings and behavior

Current inference reuses the immutable audited V15 V7 whole-share feature replay, restores original float32 feature types, and scores newly trained V17 models. Original plan quarantines remain. No current value is copied backward into historical dates. Top20/50/100, full ranks, largest movers, composition, personalization, current industry concentration, peer context, and feature-family sensitivity are saved. Model-score reproduction is verified to numerical precision.

| comparison | top_n | overlap | mean_absolute_rank_movement |
| --- | --- | --- | --- |
| v17_vs_champion | 20 | 15 | 225.5380 |
| v17_vs_champion | 50 | 31 | 225.5380 |
| v17_vs_champion | 100 | 63 | 225.5380 |
| v17_vs_v15 | 20 | 11 | 164.6035 |
| v17_vs_v15 | 50 | 31 | 164.6035 |
| v17_vs_v15 | 100 | 69 | 164.6035 |
| v17_vs_v16 | 20 | 11 | 164.6035 |
| v17_vs_v16 | 50 | 31 | 164.6035 |
| v17_vs_v16 | 100 | 69 | 164.6035 |

| model | profile | top_n | missing_true5y | median_1y_growth | median_3y_growth | median_days_high | mean_ath_distance | mean_max_drawdown | mean_volatility | mean_confidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| champion | base7500 | 20 | 0.8500 | 0.4332 | 0.4675 | 27.0000 | -0.1105 | -0.5073 | 0.3810 | 0.8938 |
| champion | lookback12 | 20 | 0.6500 | 0.3667 | 0.2115 | 796.5000 | -0.4159 | -0.6399 | 0.4280 | 0.9187 |
| v15 | base7500 | 20 | 0.6500 | 0.5492 | 0.5647 | 29.0000 | -0.1771 | -0.5618 | 0.3797 | 0.9187 |
| v15 | lookback12 | 20 | 0.8000 | 0.5895 | 0.5915 | 344.5000 | -0.3321 | -0.6829 | 0.4779 | 0.8875 |
| v16 | base7500 | 20 | 0.6500 | 0.5492 | 0.5647 | 29.0000 | -0.1771 | -0.5618 | 0.3797 | 0.9187 |
| v16 | lookback12 | 20 | 0.8500 | 0.6820 | 0.3479 | 29.5000 | -0.2567 | -0.6478 | 0.4488 | 0.8938 |
| v17 | base7500 | 20 | 0.9000 | 0.4220 | 0.4431 | 34.5000 | -0.1454 | -0.4751 | 0.3634 | 0.8875 |
| v17 | lookback12 | 20 | 0.7000 | 0.6911 | 0.6079 | 344.5000 | -0.3085 | -0.6274 | 0.4418 | 0.8688 |

| model | profile | top20_overlap_base | mean_absolute_rank_change |
| --- | --- | --- | --- |
| v17 | amount1000 | 19 | 32.2771 |
| v17 | amount50000 | 20 | 24.3175 |
| v17 | base7500 | 20 | 0.0000 |
| v17 | lookback12 | 3 | 660.3428 |
| v17 | lookback60 | 1 | 446.9084 |
| v17 | quarterly | 20 | 69.4134 |
| v17 | target10 | 19 | 45.8721 |
| v17 | target30 | 20 | 39.3780 |
| v17 | weekly | 19 | 38.6988 |

ATH behavior is tested by each-stock counterfactuals anchored to the original query feature/prediction distributions:30 days/5% below high versus1825 days/70% below high, with derived age-depth fields updated and champion score fixed. This is a conditional synthetic audit, not a causal experiment or a fully realizable stock path. Current results below are reported even when a retrained model differs from the development fit. No current diagnostic changes selection.

| profile | mean_score_change | median_score_change | negative_fraction | positive_fraction |
| --- | --- | --- | --- | --- |
| amount1000 | -0.0060 | -0.0037 | 0.8795 | 0.0000 |
| amount50000 | -0.0060 | -0.0037 | 0.8792 | 0.0000 |
| base7500 | -0.0059 | -0.0036 | 0.8796 | 0.0000 |
| lookback12 | -0.0185 | -0.0159 | 0.9430 | 0.0033 |
| lookback60 | -0.0236 | -0.0251 | 0.9554 | 0.0000 |
| quarterly | -0.0060 | -0.0037 | 0.8792 | 0.0000 |
| target10 | -0.0059 | -0.0036 | 0.8789 | 0.0000 |
| target30 | -0.0059 | -0.0036 | 0.8796 | 0.0000 |
| weekly | -0.0059 | -0.0036 | 0.8795 | 0.0000 |

### NYKAA diagnostic only

Current base rank: V17 **5**, refreshed champion 5, V15 6, V16 6. Frozen September reference1 and V14 reference213 were never targets. Current1Y growth35.06%,3Y growth30.60%, ATH distance-21.80%, days since high1765, underwater duration1765, volatility27.75%, and confidence87.5%. Historical plan attainment1.211. The full NYKAA CSV includes fundamentals, peer percentiles, all user-profile ranks, and current input evidence; `nykaa_component_contributions.csv` gives raw component TreeSHAP, which is not additive rank attribution.

Current ROCE/ROE and industry-relative diagnostics are retained from V7; they are not trained historical predictors because dated publication and historical classification evidence are unavailable. Current sector comparisons are not backfilled into development.

## Reproduction, integrity, and limits

See `REPRODUCE.md` and `model_definition.json`. Four final correction model files plus the frozen champion define inference. `score_current_replay` reproduces scores without training. Current replay and V7 hashes, training endpoints, input feature lists, all selection protocols, and all outcomes are auditable.

Protected hashes cover frozen champion, V14, V15, V16, historical inputs, and tracked production/website files. No Railway or deployment command was issued. Final verification is in `integrity_audit.json`; `manifest.json` hashes the completed artifacts, runner, and report.

The study retains frozen-universe survivorship/selection exposure, provider-revision and publication-time uncertainty, overlapping label dependence, and adaptive-search overfitting risk. All known evaluation periods are honestly labeled exposed. Current official-action authority ends2026-09-18; later action completeness is not proved. An improved research model is not proof of deployable investment superiority.

**Outcome:** A trained, reproducible model materially improves the prior development frontier and repairs12M return/drawdown while retaining meaningful growth, ATH, confidence, and user personalization. Production remains unchanged. Forward unexposed evidence and execution-data completeness are the remaining conditions for a justified production promotion.
