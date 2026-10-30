# Fixed recency weight: complementary signal experiment

Decision: **REVERT EXPERIMENT; retain unchanged champion**. Development-selected configuration: `continuity_0.001`.

## What stayed fixed

The previous dual-high adjustment remains exactly C + .01 × (.60 recency + .25 proximity + .15 momentum − .5). Recency uses the equal combination of inverse ages of the 52-week closing high and available-history recorded closing high. Its .006 coefficient was not reduced, normalized away or retuned. It is the largest coefficient in the added signal, not a claim about total nonlinear champion importance.

## Literature and adaptations

- [Da, Gurun and Warachka (2014), Frog in the Pan](https://doi.org/10.1093/rfs/hhu003): motivated continuity proxies (trend efficiency, fit quality, inverse largest-jump share). This is not the exact paper estimator.
- [Daniel and Moskowitz (2016), Momentum crashes](https://doi.org/10.1016/j.jfineco.2015.12.002): motivated downside/volatility controls. Our within-sector stock-level proxies are not a replication of their portfolio strategy.
- Continuity, risk, and their equal combination were each tested with weight .001 or .003. The entire complement remains smaller than the .006 recency coefficient. Existing champion components remain frozen.

## Selection and evidence

Six predefined configurations, selected on 2020–2023 before evaluating the selected candidate on 2024–2025. Equal-sector/profile Top3 utility: 40% rank IC, 25% NDCG, 15% achievement, 10% inverse shortfall, 10% drawdown, each change divided by .01. XIRR reported but not optimized. Same population and nine historical profiles. Acceptance also requires positive development/recent utility and positive recent ranking-only/equal-five sensitivities; individual regressions are allowed.

| Candidate | Development utility |
|---|---:|
| continuity_0.001 | -0.021874 |
| risk_0.001 | -0.027386 |
| combined_0.001 | -0.029799 |
| risk_0.003 | -0.060748 |
| combined_0.003 | -0.066523 |
| continuity_0.003 | -0.073229 |

| Period | Score | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |
|---|---|---:|---:|---:|---:|---:|---:|
| development | current_champion | 34.751% | -25.435% | 58.034% | 0.051583 | 0.590934 | 0.026167 |
| development | continuity_0.001 | 34.753% | -25.462% | 58.052% | 0.051594 | 0.590451 | 0.025928 |
| recent | current_champion | -0.220% | -31.308% | 22.930% | 0.117560 | 0.637130 | 0.152163 |
| recent | continuity_0.001 | -0.271% | -31.346% | 22.895% | 0.117789 | 0.637183 | 0.152431 |

Recent weighted utility: 0.000694; ranking-only: 0.016072; equal-five: -0.012778. These preference scores are not percentage accuracy gains.

## Verification and limits

- All 4,436 current stocks have finite scores; missing-evidence fallback remains exactly unchanged. Current snapshot remains 3 October 2026.
- Exported current scores reproduced within 1e-12. Bounds, fixed age coefficient, missing-data abstention and future-date independence covered by two passing tests. Historical query membership matched across compared scores.
- Provider-basis prices and available-history highs are inherited; no new corporate-action certification. Retrospective sector/current-survivor bias remains.
- All historical periods were previously researched. This is exploratory evidence, not fresh validation. No single overall improvement percentage or universal superiority claim is justified.
- Website and existing champion artifacts unchanged. Rejected experimental outputs retained for reproducibility, not used in production.

## Reproduction

`python research/runners/champion_recency_complements_20261017.py` then `python research/runners/report_champion_recency_complements_20261017.py`. Outputs under `experiments/champion-recency-complements-20261017/`.
