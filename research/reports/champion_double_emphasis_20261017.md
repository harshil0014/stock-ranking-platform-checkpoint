# Stronger high-recency and SIP-profit emphasis

Development-selected variant: `strong_both`. Activation gate: **DO NOT ACTIVATE**.

Comparator: the active dual_w0.01 + sip_risk_confirmed_0.01 champion, not the original research baseline. All prior components remain fixed.

## Increased influence

The direct candidate doubles both overlays from coefficients .01 to .02. Each individual overlay can therefore move a score by at most ±.01, versus ±.005 previously. Risk/affordability and missing-data guards still apply. This does not make either factor dominant in the full model.

Other candidates double only when both existing signals agree in sign; scale that extra emphasis by the weaker signal; or require both agreeing adjustments to have magnitude at least .0025. They preserve existing weights elsewhere. No ticker-specific exceptions.

## Literature

[Bhootra and Hur (2013)](https://doi.org/10.1016/j.jbankfin.2013.05.025) motivates conditioning high-related signals on recency. [Grinblatt and Han (2005)](https://doi.org/10.1016/j.jfineco.2004.10.006) motivates gains relative to acquisition cost. The SIP proxy, confirmation gates and coefficients are engineering hypotheses, not exact paper replications or weights recommended by the papers.

## Selection and safeguards

Four candidates fixed before evaluation. Select by 2020–23 expanded/capped equal-sector/profile Top3 utility, lock one, then assess 2024–25. Utility weights: .4 rank IC, .25 NDCG, .15 achievement, .1 inverse shortfall, .1 drawdown; directional deltas/.01. Activation requires positive utility and no deterioration in any of the six primary aggregate measures in either period. This is an operational definition of no-degradation, not a universal guarantee. Raw/common and Top1/5 sensitivities are retained.

| Period | Model | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |
|---|---|---:|---:|---:|---:|---:|---:|
| development | agree_only | 34.665% | -25.490% | 58.008% | 0.051712 | 0.590180 | 0.025632 |
| development | agree_soft | 34.622% | -25.488% | 58.012% | 0.051732 | 0.590194 | 0.025688 |
| development | current_champion | 34.677% | -25.485% | 58.034% | 0.051679 | 0.590276 | 0.025948 |
| development | double_both | 34.444% | -25.515% | 57.885% | 0.052120 | 0.589426 | 0.024630 |
| development | strong_both | 34.685% | -25.480% | 58.069% | 0.051634 | 0.590357 | 0.025770 |
| recent | current_champion | -0.272% | -31.376% | 22.971% | 0.117905 | 0.637031 | 0.152471 |
| recent | strong_both | -0.297% | -31.431% | 22.977% | 0.118324 | 0.636527 | 0.152295 |

## Current rankings and verification

- All 4,436 stocks retain finite scores. Source SHA256 hashes and matched query populations verified; current exported scores reproduce to 1e-12.
- Two tests cover exact doubling, bounds, agreement gates, zero corrections and independence from outcome/company fields.
- NYKAA sector ranks: double_both: 1, agree_only: 1, agree_soft: 1, strong_both: 1.
- Historical dates were previously researched; no fresh validation. Survivor/sector bias, incomplete action certification and gross outcomes remain. All inputs are frozen dated signals; this round does not fetch new stock prices.
- Website unchanged by this experiment; existing user-approved recency/SIP champion remains active unless separately promoted.

Reproduce with `python research/runners/champion_double_emphasis_20261017.py` and `python research/runners/report_double_emphasis_20261017.py`. Detailed artifacts: `experiments/champion-double-emphasis-20261017/`.
