# V15 champion-guided personalized challenger

**Verdict: FROZEN CHAMPION RETAINS.** Frozen d499580 remains the production champion.

Selected `balanced_return__confidence_only__0.2`: learned return/goal correction with maximum strength 20%, reduced when evidence is missing. Original champion judgment remains the foundation. No company identity or source provenance enters the model.

## Locked research design

Four correction models (two return-oriented labels and two history-feature recipes), each at four fixed blend strengths, were compared on 16 development decisions in 2020–2023. Correction training for development uses only endpoints before 2020-03-31. Final research training uses endpoints before 2024-03-31. The selected candidate is locked before V15 final evaluation. All 2024–2025 outcomes have been exposed to prior research, and are described here as known retrospective evaluation. Adjacent 12-month outcomes overlap; year-block uncertainty has only two evaluation years.

The historical champion benchmark is the existing maturity-purged replay of d499580's frozen seven-feature recipe and 67/33 goal/ranker blend. It uses weights fitted only on outcomes matured before each historical decision, rather than applying the September 2026 frozen weights backward. Current inference uses the exact frozen d499580 model and verifies that it reproduces its original stored scores before input refresh.

The median-XIRR loss floor was derived from champion-only date variability and capped at 2.5 percentage points before candidate evaluation. Profile floors and weekly/12M goal/risk limits are fixed in `protocol_lock.json`. Forward horizon is 12 months for every supported profile; lookback length is separately 12/36/60 months. This corrects V14's conflation of lookback with horizon.

Development gate: False; known evaluation gate: True. No threshold was changed after outcomes were evaluated.

| candidate | eligible | utility | median_xirr_top20_delta | target_shortfall_top20_delta | mean_asset_drawdown_top20_delta | top20_overlap |
| --- | --- | --- | --- | --- | --- | --- |
| balanced_return__confidence_only__0.2 | False | 0.0479 | 0.1719 | -0.0200 | 0.0049 | 0.3969 |
| balanced_return__confidence_only__0.1 | False | 0.0441 | 0.1204 | -0.0182 | 0.0084 | 0.5507 |
| balanced_return__confidence_only__0.3 | False | 0.0430 | 0.1733 | -0.0203 | 0.0015 | 0.3007 |
| return__explicit_history__0.2 | False | 0.0392 | 0.1841 | -0.0124 | -0.0209 | 0.4253 |
| return__explicit_history__0.1 | False | 0.0381 | 0.1746 | -0.0087 | -0.0231 | 0.5757 |
| return__explicit_history__0.3 | False | 0.0381 | 0.1699 | -0.0168 | -0.0127 | 0.3427 |
| return__confidence_only__0.3 | False | 0.0374 | 0.1518 | -0.0178 | -0.0117 | 0.3323 |
| return__confidence_only__0.2 | False | 0.0314 | 0.1338 | -0.0122 | -0.0238 | 0.4090 |

The decisive development failure is the 12M-lookback profile: median Top-20 XIRR loses 6.66 percentage points, shortfall rises 0.64 points, and mean drawdown worsens 6.50 points. Weekly development return improves 22.67 points. Aggregate gains cannot compensate for this failed 12M profile.

## Known evaluation against champion

| metric | champion | v15 | delta |
| --- | --- | --- | --- |
| coverage | 0.8821 | 0.8821 | 0.0000 |
| ndcg20 | 0.5660 | 0.6422 | 0.0762 |
| target_achievement_top20 | 0.3454 | 0.4500 | 0.1046 |
| target_shortfall_top20 | 0.1354 | 0.1090 | -0.0264 |
| median_xirr_top20 | -0.0328 | 0.1485 | 0.1813 |
| mean_asset_drawdown_top20 | -0.4428 | -0.4121 | 0.0307 |
| rank_ic | 0.1032 | 0.1146 | 0.0114 |
| pairwise_accuracy | 0.5362 | 0.5413 | 0.0051 |

| profile | median_xirr_top20_delta | target_achievement_top20_delta | target_shortfall_top20_delta | mean_asset_drawdown_top20_delta |
| --- | --- | --- | --- | --- |
| amount1000 | 0.0567 | 0.0708 | -0.0222 | 0.0348 |
| amount50000 | 0.3479 | 0.1375 | -0.0361 | 0.0306 |
| base7500 | 0.1719 | 0.1125 | -0.0256 | 0.0352 |
| lookback12 | 0.2258 | 0.1125 | -0.0298 | 0.0446 |
| lookback60 | 0.1356 | 0.0667 | -0.0120 | 0.0129 |
| quarterly | 0.1019 | 0.1083 | -0.0256 | 0.0197 |
| target10 | 0.2364 | 0.1333 | -0.0298 | 0.0221 |
| target30 | 0.1477 | 0.1083 | -0.0288 | 0.0375 |
| weekly | 0.2076 | 0.0917 | -0.0276 | 0.0392 |

Cohort results, date/year regressions, turnover and two-year block uncertainty are in the accompanying CSVs. Coverage is evaluated on the same date/profile security rows; unavailable execution and label rows are retained in its denominator.

The security universe follows the existing frozen research cohorts, not a reconstructed historical constituent universe. Survivorship/selection bias and contemporaneous availability of all historical provider revisions are not eliminated. Feature windows and outcome maturity are checked, but this evidence cannot establish a fully untouched investment trial.

Known-evaluation date regressions:

| decision_date | median_xirr_top20_delta | target_shortfall_top20_delta | mean_asset_drawdown_top20_delta |
| --- | --- | --- | --- |
| 2025-05-31 | -0.0161 | 0.0112 | 0.0245 |
| 2025-08-31 | -0.1118 | 0.0390 | -0.0335 |

## Current V7 inference

All 4,436 V7 securities are considered across nine profiles. Plans are replayed at 2026-10-03 using observed Yahoo closes; 29,295 profile/security rows receive both scores. Original trusted V7 1Y/3Y/5Y/7Y/10Y rates receive equal current priority, regardless of professor/Screener/Yahoo provenance. True-history flags describe observed Yahoo history separately.

Current whole-share plan mechanics use the audited official action catalogue through 2026-09-18 and provider split ledger. Prior nominal-price anchors are cross-checked against refreshed Yahoo and mismatches are quarantined. Absence of other corporate actions after 2026-09-18 is not proven; the current ranking is conditional research inference, and this limitation must be resolved before promotion. Current replayed champion ranks can differ from its frozen September ranks due to updated inputs; both ranks are retained.

| top_n | overlap | turnover | mean_absolute_rank_movement |
| --- | --- | --- | --- |
| 20 | 12 | 0.4000 | 211.8110 |
| 50 | 28 | 0.4400 | 211.8110 |
| 100 | 61 | 0.3900 | 211.8110 |

| model | missing_true_5y_fraction | median_days_since_ath | median_distance_below_ath | mean_max_drawdown | median_growth1y |
| --- | --- | --- | --- | --- | --- |
| champion | 0.8500 | 27.0000 | -0.1008 | -0.5073 | 0.4332 |
| v15 | 0.6500 | 29.0000 | -0.1008 | -0.5618 | 0.5492 |

Base profile Top 20:

| v15_rank | ticker | company | champion_rank | frozen_champion_rank | has_true_5y |
| --- | --- | --- | --- | --- | --- |
| 1.0000 | BSE-543373 | Shri Venkatesh Refineries Limi | 3.0000 | 4.0000 | 0.0000 |
| 2.0000 | BSE-543543 | B-RIGHT REALESTATE LIMITED | 2.0000 | 5.0000 | 0.0000 |
| 3.0000 | ANANDRATHI | Anand Rathi Wealth Limited | 11.0000 | 54.0000 | 0.0000 |
| 4.0000 | BSE-543953 | Khazanchi Jewellers Limited | 15.0000 | 9.0000 | 0.0000 |
| 5.0000 | AVALON | Avalon Technologies Limited | 9.0000 | 11.0000 | 0.0000 |
| 6.0000 | NYKAA | FSN E-Commerce Ventures Limited | 5.0000 | 1.0000 | 0.0000 |
| 7.0000 | BSE-543860 | J.A. Finance Limited | 20.0000 | 1148.0000 | 0.0000 |
| 8.0000 | LAURUSLABS | Laurus Labs Limited | 24.0000 | 31.0000 | 1.0000 |
| 9.0000 | MWL | Mangalam Worldwide Limited | 4.0000 |  | 0.0000 |
| 10.0000 | STEELCAS | Steelcast Limited | 17.0000 | 18.0000 | 0.0000 |
| 11.0000 | PAYTM | One 97 Communications Limited | 6.0000 | 8.0000 | 0.0000 |
| 12.0000 | SGIL | Synergy Green Industries Limited | 28.0000 | 48.0000 | 1.0000 |
| 13.0000 | YATHARTH | Yatharth Hospital & Trauma Care Services Limited | 8.0000 | 14.0000 | 0.0000 |
| 14.0000 | PRIVISCL | Privi Speciality Chemicals Limited | 19.0000 | 21.0000 | 1.0000 |
| 15.0000 | PTCIL | PTC Industries Limited | 43.0000 | 7.0000 | 0.0000 |
| 16.0000 | BSE-539682 | Mobavenue AI Tech Limited | 52.0000 | 66.0000 | 1.0000 |
| 17.0000 | BSE-540515 | KANUNGO FINANCIERS LIMITED | 33.0000 | 43.0000 | 1.0000 |
| 18.0000 | BSE-519413 | DATIWARE MARITIME INFRA LIMITE | 56.0000 | 15.0000 | 1.0000 |
| 19.0000 | RRKABEL | R R Kabel Limited | 21.0000 |  | 0.0000 |
| 20.0000 | BSE-514318 | JATTASHANKAR INDUSTIES LTD. | 53.0000 | 67.0000 | 1.0000 |

## Learned behaviour and peer context

ATH influence: True; history-family domination: False; risk-family domination: False; material user-profile sensitivity: True. Exact TreeSHAP feature/family contributions and within-query family counterfactuals are supplied. Their shares describe the correction model; the champion still supplies most of the final score. Counterfactuals are correlated-feature diagnostics, not causal claims.

Current quality and industry percentiles cover growth, ROCE, ROE, ROIC, margin, debt, PE, ATH, volatility and momentum. Peer groups require at least five names. These are a diagnostic layer because historical publication dates and historical classification memberships are unavailable; they cannot safely supply a trained ranking correction yet.

## NYKAA diagnostic

| v15_rank | champion_rank | frozen_champion_rank | days_since_recorded_high | distance_from_recorded_high | current_drawdown_duration_days | strict_cagr_1y | cagr_3y | has_true_5y | downside_volatility_1y | enhanced_goal_score | industry | peer_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6.0000 | 5.0000 | 1.0000 | 1765.0000 | -0.2180 | 1765.0000 | 0.3506 | 0.3060 | 0.0000 | 0.1705 | -0.0001 | E-Retail/ E-Commerce | 15 |

NYKAA remains high because its champion foundation retains strong recent growth (35.1% 1Y and 30.6% 3Y) and strong historical plan fit: the current replay's wealth is 121.1% of its target, 75% of rolling goal windows achieved the target, and cash utilization is 99.96%. The high is 4.84 years old and price remains 21.8% below it, with 1,765 underwater days. These are observed evidence, rather than an automatic exclusion. True 5Y/7Y/10Y rates are unavailable; annualized recent volatility is 27.7%.

The correction moves NYKAA from refreshed champion #5 to V15 #6. Its conditional ATH-family TreeSHAP sum is +0.0799; growth, risk and goal/user contributions are -0.0145, -0.0407, and -0.0428. Thus the model has not learned a blanket penalty for an old high. These explain the raw correction score, not an additive decomposition of rank positions.

Current diagnostic ROCE is 17.23% and ROE 15.29%, both at about the 87% percentile among 15 E-Retail/E-Commerce peers. Its 3Y growth is at the 85% percentile within the 69-company Retailing group. Fundamentals and peers are not trained ranking inputs. Neither the frozen #1 nor V14's #213 was a target; no identity-specific tuning occurred.

## Integrity and verdict

23,007 protected files were hashed before and after; none changed. d499580, V14, production HEAD, website, Railway configuration and historical panels are unchanged. Historical model inputs come only from decision-dated price/plan features; V7 is loaded only for current inference and diagnostics. No current professor/Screener/Yahoo value was copied to historical dates. Protocol and selection locks, models, all important outputs and this report are hashed in `manifest.json`.

FROZEN CHAMPION RETAINS. Development eligibility and the fixed return/goal/risk/profile gates determine the result. No promotion or deployment was performed.
