# High-age-only optimization; SIP weight fixed

Development-selected variant: `near_high_age_0.001`. Activation gate: **DO NOT ACTIVATE**.

Comparator: the active dual_w0.01 + sip_risk_confirmed_0.01 champion, not the original research baseline. All prior components remain fixed.

## Increased influence

Only high-age influence increases; SIP and all existing components stay fixed. Each of four signal variants is tested at incremental coefficients 0.001, 0.002, 0.004 and 0.008, bounding the extra score contribution at +/-0.0005, +/-0.001, +/-0.002 and +/-0.004 respectively. These are score coefficients, not percentages of total model importance.

Four signal variants: inverse rolling-52-week high age, inverse available-history recorded-high age, their equal combination, and rolling-high age scaled by proximity (full increment at the high, zero at 20% below). All are within-sector percentiles with the existing activity/history guards. No ticker-specific exceptions.

## Literature

[Bhootra and Hur (2013)](https://doi.org/10.1016/j.jbankfin.2013.05.025) studies 52-week-high recency. [George and Hwang (2004)](https://doi.org/10.1111/j.1540-6261.2004.00695.x) studies proximity to the 52-week high. These motivate the rolling-age and proximity-conditioned hypotheses; neither establishes a lifetime-high-age penalty or recommends our coefficients. This is an adaptation, not an exact replication.

## Selection and safeguards

Sixteen candidates fixed before evaluation. Select by 2020-2023 expanded/capped equal-sector/profile Top3 utility, lock one, then assess 2024-2025. Utility weights: .4 rank IC, .25 NDCG, .15 achievement, .1 inverse shortfall, .1 drawdown; directional deltas/.01. Activation allows tradeoffs: positive weighted utility, ranking-only and equal-five sensitivities in BOTH periods; losses in XIRR, drawdown, achievement and directional shortfall must each stay within 0.1 percentage point. This is the predeclared net-benefit rule, not a universal guarantee. Raw/common and Top1/5 sensitivities are retained.

| Period | Model | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |
|---|---|---:|---:|---:|---:|---:|---:|
| development | current_champion | 34.677% | -25.485% | 58.034% | 0.051679 | 0.590276 | 0.025948 |
| development | dual_age_0.001 | 34.664% | -25.486% | 58.048% | 0.051692 | 0.590192 | 0.025947 |
| development | dual_age_0.002 | 34.520% | -25.482% | 57.977% | 0.051915 | 0.589880 | 0.025242 |
| development | dual_age_0.004 | 34.358% | -25.508% | 57.942% | 0.051982 | 0.589558 | 0.024735 |
| development | dual_age_0.008 | 34.267% | -25.513% | 57.916% | 0.052022 | 0.589287 | 0.024744 |
| development | near_high_age_0.001 | 34.679% | -25.485% | 58.048% | 0.051674 | 0.590293 | 0.025976 |
| development | near_high_age_0.002 | 34.669% | -25.490% | 58.034% | 0.051705 | 0.590255 | 0.025940 |
| development | near_high_age_0.004 | 34.648% | -25.490% | 58.012% | 0.051788 | 0.590227 | 0.025910 |
| development | near_high_age_0.008 | 34.487% | -25.498% | 57.920% | 0.052041 | 0.589687 | 0.025292 |
| development | recorded_age_0.001 | 34.660% | -25.485% | 58.039% | 0.051715 | 0.590169 | 0.025912 |
| development | recorded_age_0.002 | 34.653% | -25.489% | 58.026% | 0.051713 | 0.590198 | 0.025805 |
| development | recorded_age_0.004 | 34.324% | -25.503% | 57.933% | 0.051930 | 0.589534 | 0.024658 |
| development | recorded_age_0.008 | 34.280% | -25.507% | 57.890% | 0.052075 | 0.589147 | 0.024255 |
| development | rolling_age_0.001 | 34.670% | -25.489% | 58.048% | 0.051688 | 0.590281 | 0.025954 |
| development | rolling_age_0.002 | 34.499% | -25.483% | 57.951% | 0.051947 | 0.589862 | 0.025244 |
| development | rolling_age_0.004 | 34.373% | -25.510% | 57.951% | 0.051981 | 0.589522 | 0.024912 |
| development | rolling_age_0.008 | 34.387% | -25.527% | 57.916% | 0.052037 | 0.589449 | 0.024875 |
| recent | current_champion | -0.272% | -31.376% | 22.971% | 0.117905 | 0.637031 | 0.152471 |
| recent | near_high_age_0.001 | -0.297% | -31.383% | 22.942% | 0.117974 | 0.636946 | 0.152478 |

## Current rankings and verification

- All 4,436 stocks retain finite scores. Source SHA256 hashes and matched query populations verified; current exported scores reproduce to 1e-12.
- Two tests cover recency direction, incremental bounds, proximity gating, missing-data abstention and independence from future dates.
- NYKAA sector ranks: dual_age_0.001: 1, dual_age_0.002: 1, dual_age_0.004: 1, dual_age_0.008: 1, rolling_age_0.001: 1, rolling_age_0.002: 1, rolling_age_0.004: 1, rolling_age_0.008: 1, recorded_age_0.001: 1, recorded_age_0.002: 1, recorded_age_0.004: 1, recorded_age_0.008: 1, near_high_age_0.001: 1, near_high_age_0.002: 1, near_high_age_0.004: 1, near_high_age_0.008: 1.
- Historical dates were previously researched; no fresh validation. Survivor/sector bias, incomplete action certification and gross outcomes remain. All inputs are frozen dated signals; this round does not fetch new stock prices.
- Website unchanged by this experiment; existing user-approved recency/SIP champion remains active unless separately promoted.

Reproduce with `python research/runners/champion_age_only_20261017.py` and `python research/runners/report_age_only_20261017.py`. Detailed artifacts: `experiments/champion-age-only-20261017/`.
