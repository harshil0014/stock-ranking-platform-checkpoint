# Champion improvement: small peer-context feature patch

Completed 17 October 2026. This changes the existing ranking component in an isolated research experiment; it does not introduce a new product/model selector.

## Decision

Selected internal patch: **peer_risk**. Decision: **RETAIN_UNMODIFIED_CHAMPION**.

Selection was locked on development 2020–2023 before evaluating 2024–2025. Those later dates were already exposed in earlier project research, so this is not fresh validation.

## What changed

- Kept the champion formula C = 0.75 G + 0.25 R and all inherited G components unchanged.
- Added leave-one-out, same-date sector deviations to R: momentum, closing-high distance/persistence, downside volatility and drawdown. Tested strength-only, risk-only and combined ablations.
- Kept the original rank_xendcg objective, 180 trees, hyperparameters, balanced relevance target and mature-label training rules.
- This borrows the peer-context idea from [FinGAT](https://arxiv.org/abs/2106.10159) and [HIST](https://arxiv.org/abs/2110.13716); it is not a graph-model reproduction.
- Peer statistics count each company once, exclude the company itself and invalid evidence, and become missing with fewer than four valid peers or constant peers. No new outcome enters feature construction.

## Aggregate results

Expanded universe, capped-return Top3; equal sector/profile aggregation. XIRR is the inherited SIP diagnostic, not a cost-complete portfolio return. Lower shortfall is better.

| Period | Component patch | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |
|---|---|---:|---:|---:|---:|---:|---:|
| development | current_champion | 34.75% | -25.43% | 58.03% | 0.05158 | 0.59093 | 0.02617 |
| development | peer_both | 34.43% | -25.61% | 57.39% | 0.05206 | 0.58920 | 0.02418 |
| development | peer_risk | 34.25% | -25.55% | 57.69% | 0.05204 | 0.59065 | 0.03239 |
| development | peer_strength | 34.24% | -25.57% | 57.58% | 0.05198 | 0.58952 | 0.02610 |
| exposed | current_champion | -0.22% | -31.31% | 22.93% | 0.11756 | 0.63710 | 0.15211 |
| exposed | peer_risk | -0.58% | -31.39% | 22.73% | 0.11931 | 0.63375 | 0.14748 |

## Matched metric/profile comparisons

These overlapping cells are diagnostic comparisons, not independent statistical tests. XIRR has no selection weight; return regressions remain a promotion veto.

| Stage | Patch | Non-return improvements | Non-return regressions | Top3 non-return regressions | XIRR regressions | Pass |
|---|---|---:|---:|---:|---:|---|
| development | peer_risk | 228 | 310 | 127 | 59 | False |
| development | peer_strength | 177 | 363 | 141 | 54 | False |
| development | peer_both | 148 | 392 | 150 | 54 | False |
| recent | peer_risk | 156 | 376 | 138 | 74 | False |

## Verification and coverage

- 15 serialized fit receipts verified; each training endpoint precedes its cutoff. Predictions were checked against saved model replay in the runner.
- Three feature tests pass: no cross-date/profile contamination, valid leave-one-out population, and small/constant-sector behavior.
- Query populations match exactly for every compared model in each common/expanded and raw/capped evaluation.
- 4,436 unique current stocks with finite scores; 133 unavailable-evidence scores exactly preserve the champion fallback. Current snapshot remains 3 October 2026.
- 3300 current stock sector ranks change under the selected research patch. Score preservation on fallback rows does not guarantee their ordinal ranks stay fixed when peers move.
- No website or existing champion artifact was overwritten. Current exports cover base7500; historical evaluation covers all nine profiles.
- Current-universe and retrospective sector limitations remain; this patch does not repair underlying data availability or corporate-action defects.

## Reproduce and inspect

Run `python research/runners/champion_peer_context_20261017.py`, then `python research/runners/report_champion_peer_context_20261017.py`. Outputs are in `experiments/champion-peer-context-20261017/`: protocol, development lock, model receipts, query-level metrics, sector/profile deltas, all-stock audit, rank changes and within-sector Top1/3/20/100.

## User-authorized tradeoff review

The user subsequently allowed regressions when benefits outweigh costs. Accordingly, the strict gate above is only a diagnostic; a separate net-benefit analysis is authoritative for this follow-up.

Before computing that analysis, the recorded preference weights were rank IC 40%, NDCG 25%, achievement 15%, inverse shortfall 10%, drawdown 10%. Each directional difference is divided by .01. XIRR has zero selection weight. These are engineering preferences, not an objective definition of investment quality.

Quarter-, half- and full-strength application of the locked risk-context patch were compared. Strength was selected on development only; later outcomes did not choose a different winner. Equal-weight and ranking-only sensitivities were also reported.

Selected: peer_risk_strength1.0. Development net-benefit score 0.1751; later-period score -0.3247. Accept patch: False.

The selected patch loses on every reported aggregate later-period dimension, so rejection does not depend on demanding zero individual regressions. Its later ranking-only and equal-weight utilities are also negative. These utility values are dimensionless preference scores, not accuracy percentages.

The tradeoff analysis averages sector/profile cells directly; the earlier table first aggregates through the original profile summary. Small numerical differences reflect weighting order and are preserved explicitly rather than silently combined.

Reproduce with `python research/runners/champion_tradeoff_review_20261017.py`. See `tradeoff_review/protocol.json`, `lock.json`, `decision.json`, and full common/expanded, raw/capped Top1/3/5 deltas. The champion remains unchanged because this particular modification does not deliver a robust net benefit.
