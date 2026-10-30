# Ten stock-ranking research pilots — 31 October 2026

The completed pilots support keeping the active champion. Rank hysteresis is a useful UI candidate. Model-confidence abstention and meta-labeling did not earn development selection. New goal-probability forecasts have real target-dependent behavior but poor calibration/risk tradeoffs. The filing-metadata part could not be tested from accessible local files.

The application and incumbent model package were not changed. This report records local retrospective research, not a deployed ranking upgrade.

## Results by requested idea

| Idea | Decision | Evidence |
| --- | --- | --- |
| 1. Noise floor | Use as a measurement control | 35 fixed related policies; development 95% lucky-win hurdle 0.01013 IC / 0.630pp attainment. Not a universal future threshold. |
| 2. Disagreement confidence | Do not activate abstention | Development selected 100% retained coverage; lower disagreement did not improve development pair accuracy. |
| 3. Rank hysteresis | Promising UI research pilot | Margin .02: exposed Kendall tau 0.692 -> 0.755; observed IC delta +0.00093. Quarterly/monthly, not daily refresh validation. |
| 4. Goal probability | Do not replace incumbent | Corrected selected goal_volume: exposed attainment 22.96% -> 24.07%, selected-asset drawdown -31.38% -> -44.03%; Brier 0.3039 vs climatology 0.2856. |
| 5. SIP path dependence | Volatility hypothesis not robustly confirmed | Conditional volatility coefficient is uncertain in development; fractional-SIP coefficient is negative there. Recovery-duration association is descriptive and ex-post. |
| 6. Meta-labeling | Do not activate gate | Mature out-of-time Top3 logistic meta-labeler selected full coverage on development. No successful abstention policy. |
| 7. Volume / filing metadata | No promotion; filing test blocked | Volume in original ranking head: IC delta dev -0.00239, exposed +0.00305. Historical filing-submission timestamps unavailable. |
| 8. Correlation peers | No promotion; gain below noise | 25 calendar-aligned correlation peers. Original-head IC delta dev +0.00186, exposed -0.00203; sector evaluation retained. |
| 9. Kronos extractor | Do not add this extractor | Matched original-head IC delta dev -0.00480, exposed -0.00586; exposed attainment delta -0.905pp. Pretraining contamination risk. |
| 10. Historical look-alikes | No promotion; IC fell in both periods | 50 mature neighbors, PCA8 path embedding, same issuer excluded. Original-head IC delta dev -0.00051, exposed -0.00301. 250 current-snapshot neighbor examples saved. |

## Data, baseline and evaluation boundaries

Baseline application commit: `a216d6dd0af742b719cbe449ff2b2d2f4ef2ca5d`. Saved original champion plus its approved high-recency and SIP overlays is the anchor. Prepared data has 1,179,002 rows, 44 dates and nine investor profiles. Development is 2020–2023; 2024–2025 was already repeatedly exposed. There is no fresh holdout in this work. Most historical dates are quarterly; 2025 has monthly observations through August. Current artifacts describe the frozen **3 October 2026** snapshot, not today's market.

The recovered Yahoo OHLCV batches cover 4,346 identities. The build produced 132,125 usable stock/date windows, and excluded 622 price-basis disagreements from the new OHLCV feature families. Original model inputs and labels were preserved. Current-survivor identities, retrospective sector mapping, provider revisions and incomplete corporate-action certification limit every result. Outcomes are gross simulated whole-share SIP outcomes; the displayed drawdown statistic is an average of selected stocks' drawdowns, not portfolio drawdown or a realized investor result.

Primary model tables use equal dates and equal sector/profile queries, Top3, at least five usable classified peers, and identical rows across each model comparison. Probabilistic calibration tables are row-weighted on the same predictions. The meta-labeler has usable mature out-of-time training only from 2022 onward, so its development slice is 2022–2023. Missing/Unclassified cohorts are not claimed to have validated predictive ranks.

## Noise floor and confidence

The 35 policies are reconstructed from fixed saved families: original score, nine high adjustments, six continuity/risk complements, fifteen SIP adjustments and four confirmation policies. They are highly related score policies, not 35 independent learners. A centered simultaneous circular calendar-block bootstrap preserves model/date/profile/sector dependence, with 4,000 draws and 365/730-day sensitivity. The development observed best IC gain is only 0.000259, versus a 95% maximum-selection floor near 0.010. The observed best attainment gain is 0.035pp, versus approximately 0.630pp. Such tiny earlier wins do not clear this conditional hurdle.

The exposed period is too short for a two-year-block estimate; that result is explicitly unavailable rather than a false zero uncertainty. Other model families require their own selection-noise calculation. For the corrected five-classifier family, the development attainment floor is about 6.3pp; the selected classifier's roughly 1.04pp development gain does not clear it. Four years of overlapping one-year outcomes still provide few independent temporal blocks, so these are conditional research hurdles, not guarantees.

| period | retained | pair_accuracy | agreement | selected |
| --- | --- | --- | --- | --- |
| development | 0.250000 | 0.506983 | 0.998085 | False |
| development | 0.500000 | 0.509165 | 0.995459 | False |
| development | 0.750000 | 0.509171 | 0.991301 | False |
| development | 1.000000 | 0.510023 | 0.979591 | True |
| exposed | 0.250000 | 0.562549 | 0.996915 | False |
| exposed | 0.500000 | 0.560228 | 0.993848 | False |
| exposed | 0.750000 | 0.558843 | 0.989660 | False |
| exposed | 1.000000 | 0.554950 | 0.977913 | True |

Pairs were sampled reproducibly within queries; model votes and stock rank dispersion were computed without outcomes. Development locked full coverage. The more attractive exposed-period selective curve was not used to change that choice.

## Hysteresis

Previous order is retained unless a crossing score gap exceeds the fixed margin. Candidate margins were 0, .0025, .005, .01 and .02. Development chose maximum Kendall stability subject to no more than .001 observed IC loss. Margin .02 won. It is a score margin, not a return threshold or a number of stock ranks.

| period | margin | raw_tau | kendall_tau | ic_delta |
| --- | --- | --- | --- | --- |
| development | 0.020000 | 0.609714 | 0.679084 | 0.000723 |
| exposed | 0.020000 | 0.691961 | 0.754803 | 0.000925 |

The observed IC improvement is below the predictive noise floor and is not claimed as an accuracy gain. This validates an engineering candidate at historical snapshot frequency; daily shadow validation and profile/model-version state handling remain necessary before website activation.

## Goal probability and the validity correction

Labels are `future SIP XIRR >= target CAGR`; these agree with existing zero-shortfall labels on the panel. Each annual base learner uses outcomes ending strictly before January of test-year minus two. The disjoint calibration block starts at that date and includes only outcomes mature before the test-year January. The fixed model has 120 LightGBM trees / 15 leaves. This conservative split gives calibration an independent time block and leaves less recent data for base training than the incumbent ranker.

The initial unconstrained run was preserved and failed probability ordering: harder goals sometimes received greater success probability. A separate `monotone_round` constrains target CAGR downward and analog attainment upward; sigmoid slopes must be nonnegative. A negative fitted calibration slope becomes the optimum constant forecast under that constraint. This is a recorded mathematical-validity correction, not fresh validation or an exposed-period winner search. All five corrected models passed the 10/20/30-percent target-order check on 84,184 matched stock/date cases. Constant forecasts have undefined Spearman correlation; `constant_probability_ic_audit.csv` reports defined coverage and an explicitly disclosed zero-association convention. The raw IC column in the machine-readable classifier summary averages only defined correlations, so use the audit for full-period IC comparisons.

Development selected **goal_volume** by goal attainment. Its exposed attainment gain is 1.105pp, while its average selected-stock drawdown deteriorates by 12.653pp. It fails the calibration/risk case for adoption.

| period | model | achievement | drawdown | selected |
| --- | --- | --- | --- | --- |
| development | active_champion | 0.576430 | -0.253245 | False |
| development | goal_analogs | 0.579397 | -0.347237 | False |
| development | goal_base | 0.582157 | -0.355248 | False |
| development | goal_combined | 0.581526 | -0.351478 | False |
| development | goal_peers | 0.583451 | -0.362441 | False |
| development | goal_volume | 0.586835 | -0.357087 | True |
| exposed | active_champion | 0.229649 | -0.313776 | False |
| exposed | goal_analogs | 0.235263 | -0.435142 | False |
| exposed | goal_base | 0.238596 | -0.439108 | False |
| exposed | goal_combined | 0.223216 | -0.433940 | False |
| exposed | goal_peers | 0.234854 | -0.436857 | False |
| exposed | goal_volume | 0.240702 | -0.440310 | True |

| period | model | brier | log_loss | mean_probability | actual_frequency |
| --- | --- | --- | --- | --- | --- |
| development | goal_base | 0.335177 | 0.903038 | 0.447769 | 0.561424 |
| development | goal_volume | 0.334948 | 0.902840 | 0.448041 | 0.561424 |
| development | goal_peers | 0.333295 | 0.899321 | 0.415196 | 0.561424 |
| development | goal_analogs | 0.333715 | 0.899358 | 0.444053 | 0.561424 |
| development | goal_combined | 0.331757 | 0.895206 | 0.414971 | 0.561424 |
| development | climatology | 0.332722 | 0.901299 | 0.423000 | 0.561424 |
| exposed | goal_base | 0.304977 | 0.807781 | 0.579041 | 0.223415 |
| exposed | goal_volume | 0.303860 | 0.805422 | 0.577460 | 0.223415 |
| exposed | goal_peers | 0.309739 | 0.816708 | 0.588319 | 0.223415 |
| exposed | goal_analogs | 0.297887 | 0.791696 | 0.572322 | 0.223415 |
| exposed | goal_combined | 0.303298 | 0.802303 | 0.581300 | 0.223415 |
| exposed | climatology | 0.285648 | 0.764959 | 0.557554 | 0.223415 |

Climatology uses only the earlier calibration block's hit frequency. Lower Brier/log loss is better; even this simple forecast beats all corrected feature classifiers in the exposed period. Tree constraints enforce target direction but do not establish calibration under a changed market distribution. Target-rank changes are real in the research prototype, not fabricated personalization:

| model | matched_stock_dates | probability_changes | rank_changes | monotone_target_probability_fraction |
| --- | --- | --- | --- | --- |
| goal_analogs | 84184 | 48221 | 43735 | 1.000000 |
| goal_base | 84184 | 48221 | 43684 | 1.000000 |
| goal_combined | 84184 | 60514 | 54251 | 1.000000 |
| goal_peers | 84184 | 60514 | 54742 | 1.000000 |
| goal_volume | 84184 | 48221 | 43425 | 1.000000 |

## New information inside the original ranking model

These are separate ablations of the existing **25% price ranking head**, using its original 180-tree balanced `rank_xendcg` recipe and strictly mature annual training. The remaining champion components, high overlay and SIP overlay stay fixed. The 70-feature control replays the original head; the volume, correlation-peer, look-alike and combined variants change only input columns. This avoids conflating new information with the classifier objective.

Development selects **head_peers** by IC. All other fixed variants are diagnostics, not exposed-period selection candidates.

| period | model | rank_ic | achievement | drawdown | selected |
| --- | --- | --- | --- | --- | --- |
| development | active_champion | 0.022318 | 0.576430 | -0.253245 | False |
| development | head_analogs | 0.021813 | 0.570556 | -0.254589 | False |
| development | head_combined | 0.023487 | 0.568495 | -0.252799 | False |
| development | head_control | 0.022318 | 0.576430 | -0.253245 | False |
| development | head_peers | 0.024176 | 0.569446 | -0.252860 | True |
| development | head_volume | 0.019933 | 0.569365 | -0.254491 | False |
| exposed | active_champion | 0.155387 | 0.229649 | -0.313776 | False |
| exposed | head_analogs | 0.152373 | 0.228772 | -0.315616 | False |
| exposed | head_combined | 0.151289 | 0.228012 | -0.316248 | False |
| exposed | head_control | 0.155387 | 0.229649 | -0.313776 | False |
| exposed | head_peers | 0.153353 | 0.230936 | -0.313959 | True |
| exposed | head_volume | 0.158433 | 0.230585 | -0.315020 | False |

| calendar_block_days | replicates | familywise_95 | familywise_99 | median_lucky_win | dates | models | observed_best_delta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 365 | 4000 | 0.005546 | 0.007005 | 0.001814 | 16 | 4 | 0.001857 |
| 730 | 4000 | 0.005223 | 0.005876 | 0.001093 | 16 | 4 | 0.001857 |

Volume features are 5/21-day abnormal volume, high-proximity interaction, volume trend, zero-volume fraction and median traded-value proxy. This is an adaptation of a hypothesis, not a replication of the [high-volume return-premium paper](https://doi.org/10.1111/0022-1082.00349). Daily inputs never extend beyond the decision date.

Peers are the 25 most correlated other stocks, using calendar-aligned daily returns and at least 200 overlapping observations. The features measure peer returns and own lag. 129,118 stock/dates have peer features, including 2,526 Unclassified stock/dates. The benchmark retains its sector evaluation; this does not validate replacing all sector groups or guarantee performance on small/Unclassified groups. It is a simple relation-feature adaptation, not a reproduction of [Hou's information-diffusion study](https://doi.org/10.1093/rfs/hhm003).

Look-alikes use PCA8 learned only from outcome-mature libraries, on 64 samples of normalized 252-observation paths. Fifty cosine neighbors supply matching-profile realized SIP return, attainment, dispersion and distance. Same-issuer matches are excluded. Each donor's outcome ends strictly before the query-year cutoff; overlapping donor paths are not independent observations. The 250 explainable current-snapshot examples use only donor outcomes ending before 3 October 2026 (latest endpoint 31 August 2026). They are examples, not live recommendations.

## Kronos feature extraction

Official [Kronos](https://github.com/shiyu-coder/Kronos) code and pinned mini/tokenizer weight revisions are recorded in `kronos_weight_receipt.json`. A hash-selected, outcome-independent 512-stock pilot yielded 14,723 usable windows. The final and mean hidden states are frozen; PCA16 is fitted only on each fold's training windows. Inputs are the last 252 OHLCV observations, with close times volume as a traded-value proxy. No weights are fine-tuned.

The matched original ranking-head comparison is the relevant feature test:

| period | model | rank_ic | achievement | drawdown |
| --- | --- | --- | --- | --- |
| development | active_champion | 0.015453 | 0.552144 | -0.286522 |
| development | kronos_head | 0.001693 | 0.557436 | -0.295505 |
| development | matched_head | 0.006491 | 0.558303 | -0.299226 |
| exposed | active_champion | 0.164887 | 0.264830 | -0.375156 |
| exposed | kronos_head | 0.163776 | 0.261507 | -0.376982 |
| exposed | matched_head | 0.169639 | 0.270560 | -0.377889 |

Kronos loses to its matched head on IC in both periods. The extra classifier-context experiment is also retained. A certified pretraining cutoff was not established; historical temporal contamination is a risk, so these tests cannot certify a clean foundation-model edge. Rejecting this extractor in this pilot does not prove that all price-history information is exhausted.

## SIP paths, metadata and verification

The path regression controls endpoint return with splines, plus sector/date fixed effects, then examines realized volatility, time underwater and recovery duration. It uses the existing base7500 whole-share outcomes and an independent monthly fractional-SIP simulation. Development whole-share volatility coefficient is +.0194 per standard deviation, with a year-cluster wild-bootstrap interval spanning zero; the fractional-SIP coefficient is -.0153 and also uncertain. Recovery duration is associated with SIP outcomes conditional on endpoint, but these are ex-post explanatory variables, not available future trading features. Only four development and two exposed year clusters exist; the intervals do not establish reliable significance.

The original `data/marketdata`, `data/company_facts` and `data/point_in_time` paths cannot be enumerated because their junction targets are unavailable. Recovered metadata contained 132 corporate actions with zero populated broadcast dates. Ex-dates do not establish filing dates. Filing frequency, gaps and lateness require the actual historical submission metadata, covered periods and applicable deadline definitions. No proxy was fabricated; that subtest is blocked.

Seven research unit tests cover bootstrap degeneracy, maximum-selection behavior, ties, hysteresis, metric parity and negative calibration-slope correction. Saved classifiers/calibrators independently replay within 1e-12 on 500 rows per goal round. Training/calibration endpoints and analog donor maturity are audited. The corrected CDF is checked across all matched target profiles. The original ranking-head control checks all annual saved scores. No full application suite or deployment validation is claimed, because application serving code and incumbent runtime are unchanged.

Reproduction uses `PYTHONPATH=src` and the existing CPU `.venv`; GPU extraction uses `.venv-gpu-research-20261011`. Clone the official Kronos code to `work/ten-hypotheses-20261031/Kronos` and check out code revision `67b630e67f6a18c9e9be918d9b4337c960db1e9a` before running its loader. Start with `ten_hypotheses_20261031.py prepare`, then feature build / peers / analogs / path, noise / confidence / hysteresis / meta / goal, the separate monotone wrapper, original-head ablations, and Kronos download / extraction / matched tests. `review_ten_hypotheses_20261031.py` verifies maturity, calibration ordering and serialized replay; this report compiler reads fixed results only. The huge input panels, histories and feature arrays remain local, with source hashes. Compact summaries, protocols, audits and source are suitable for version control.

Method references: [scikit-learn calibration and proper probability scores](https://scikit-learn.org/stable/modules/calibration.html), [LightGBM monotonic constraints](https://lightgbm.readthedocs.io/en/stable/Parameters.html#monotone_constraints). Framework documentation supports implementation choices; it is not evidence of Indian-stock forecasting performance.
