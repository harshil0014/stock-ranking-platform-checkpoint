# Champion upgrade: modest closing-high recency emphasis

Selected patch: **dual_w0.01**. Overall tradeoff gate: **DO NOT ADOPT**.

## Research basis

Bhootra and Hur (2013), *The timing of 52-week high price and momentum*, studies the timing of the high directly. George and Hwang (2004) studies proximity. These support testing recency alongside proximity; they do not establish our mixture weights, Indian sector performance or an all-time-high-age penalty. [Recency paper](https://www.sciencedirect.com/science/article/pii/S0378426613002446), [proximity paper](https://onlinelibrary.wiley.com/doi/full/10.1111/j.1540-6261.2004.00695.x).

## Exact changes tested

- Preserved all existing champion models and component weights. Applied C_new = C + w*(H - 0.5).
- H = 60% inverse-age percentile + 25% high-proximity percentile + 15% momentum percentile, computed within date/profile/sector.
- Compared rolling 52-week closing high, available-history recorded closing high, and equal combination of the two.
- Tested w = .01, .025 and .05: maximum absolute score change .005, .0125 and .025 respectively. These are score adjustments, not percentage-point changes in predictive accuracy.
- Recency dominates this added signal only. Existing champion feature effects are nonlinear, so this does not assert a total-model recency weight.
- Requires usable price evidence, at least 252 observations and 365 history days, active-volume fraction >=80%, positive-volume lag <=14 days, complete signal inputs and >=5 eligible peers.
- Missing evidence yields zero correction. No age values are overwritten; no company-specific exception is added.

## Selection and tradeoff policy

Nine configurations were compared on 2020–2023 development dates. One was locked before evaluation on 2024–2025. Preference utility weights: rank IC .40, NDCG .25, goal achievement .15, inverse shortfall .10, drawdown .10; directional changes normalized by .01. XIRR selection weight is zero, but returns are reported.

Acceptance requires positive development and later utility, positive later equal-weight and ranking-only sensitivities, and at most 1 percentage point aggregate deterioration in drawdown/achievement. This permits individual regressions; it is a declared engineering preference, not universal investment utility.

Development utility: -0.01858. Later utility: 0.00195. Later ranking-only: 0.01526; equal-weight: -0.01086.

## Results

Expanded universe, capped returns, sector Top3; equal sector/profile cells. SIP XIRR remains a historical diagnostic, not a cost-complete portfolio return.

| Period | Score | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |
|---|---|---:|---:|---:|---:|---:|---:|
| development | current_champion | 34.751% | -25.435% | 58.034% | 0.05158 | 0.59093 | 0.02617 |
| development | dual_w0.01 | 34.752% | -25.462% | 58.052% | 0.05161 | 0.59054 | 0.02596 |
| recent | current_champion | -0.220% | -31.308% | 22.930% | 0.11756 | 0.63713 | 0.15216 |
| recent | dual_w0.01 | -0.266% | -31.343% | 22.901% | 0.11777 | 0.63715 | 0.15245 |

## Sector/profile dispersion

| Period | Improving non-return cells | Regressing non-return cells | Tied |
|---|---:|---:|---:|
| development | 408 | 568 | 1399 |
| recent | 491 | 471 | 1413 |

## Verification and limitations

- Source-file SHA256 hashes verified. Same query population sizes for all compared scores. Current scores reproduce from exported evidence to <=1e-12.
- Three tests pass for direction/bounds, missing/illiquid/small-group abstention and independence from future-date inputs.
- All 4,436 stocks remain numerically covered; 133 missing-evidence scores exactly preserve the champion. Current snapshot is 3 October 2026 and base7500; historical evidence covers nine profiles.
- Stored high ages are inherited provider-basis features. A recorded high is a maximum within available history, not independently certified lifetime ATH. Full-history corporate-action integrity is not newly certified by this experiment.
- A recent rolling high can coexist with an old recorded high. That distinction is preserved.
- Current-universe and retrospective-sector bias remain. All historical dates were already exposed during prior research. This is not fresh out-of-sample validation.
- No website was switched or existing champion artifact overwritten. A research-gate pass would justify prospective confirmation, not a universal superiority claim.

## Artifacts and reproduction

Run `python research/runners/champion_high_recency_20261017.py`, then `python research/runners/report_champion_high_recency_20261017.py`. Artifacts: `experiments/champion-high-recency-20261017/` contains protocol, development lock, all historical candidate scores, query metrics, raw/common sensitivities, sector/profile deltas, complete current rankings and sector Top3.
