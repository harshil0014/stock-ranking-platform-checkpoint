# Personalized short-history challenger, 2026-10-01

## Decision

**Keep the frozen `d499580` 67% Goal / 33% LambdaRank champion.** The leading
history-aware hybrid corrects the current short-history concentration and wins
most aggregate retrospective metrics, but it fails the profile-specific target
shortfall and achievement guardrails. It is a research challenger, not a
production replacement. No production model, service, accepted state, or
deployment was changed.

## Construction and evidence

The first tournament retrained LambdaRank with five feature recipes and four
parameter settings, at 60%, 67%, and 73% Goal weights (60 combinations). The
existing Goal feature and whole-share execution panel were retained. Training
labels were admitted only when their endpoint preceded the decision date. Model
selection used 2023-06-30 and 2023-12-31 validation decisions; 2025-03-31 and
2025-06-30 were previously exposed supplementary checks. The strongest initial
aggregate candidate had material supplementary profile failures. A further
40-combination exploratory grid blended it with the frozen champion and applied
a general age-confidence penalty. This second grid was examined on the exposed
2025 outcomes, so its apparent performance has **no clean holdout claim**.

The reported hybrid uses 40% frozen champion score and 60% of the history-aware
60% Goal / 40% LambdaRank score, then subtracts `0.40 ×
(1 − min(history_months/60, 1)) × (1 − cagr_5y_observed)` from the percentile
score. Its effective Goal weight before that penalty is 62.8%. The new ranker
uses 80 trees, learning rate 0.04, seven leaves, depth three, minimum child
size 120, and L2 regularization 15. It uses the original execution features
plus days since recorded high, distance from that high, full-history maximum
drawdown, history length, since-listing CAGR, and the observed 5Y flag. The
historical features are computed only from prices observed by each decision
date. Frozen official terminal repairs provide observed 2026-09-18 adjusted
closes where the provider cache stops earlier.

For a stock with no true 5Y anchor, `cagr_5y` is an **estimate**, not a price
reconstruction: `min(history_months/60,1) × clipped_since_listing_CAGR +
(1 − min(history_months/60,1)) × contemporaneous_sector_median_observed_5Y_CAGR`.
The estimate clips the short-sample CAGR to [−75%, 100%] and sector median to
[−50%, 50%]. `history_months`, `since_listing_cagr`, and `cagr_5y_source`
(`OBSERVED`, `ESTIMATED`, or `NO_VALID_HISTORY`) are retained. No synthetic
prelisting observation is created. The sector labels come from the accepted
current snapshot, so retrospective sector membership is a limitation.

The baseline uses the original chronological champion-policy predictions on
the retrospective dates and the exact sealed champion rows on the current
date. The sealed current 67/33 scores reproduce to `2.22e-16` maximum error.
The earlier current tournament checkpoint has different Goal values from the
sealed current rows; the challenger current inference starts from the **sealed**
rows. Coverage is scored on the same eligible row cohort.

## Champion versus leading challenger

Each value is the mean over two decision dates × nine profiles. Delta is
challenger minus champion. Higher is better except target shortfall and the
magnitude of negative drawdown. Mean XIRR is particularly sensitive to extreme
historical corporate-action outcomes and was capped in model selection.

| Metric | Validation champion | Validation challenger | Δ | Exposed 2025 champion | Exposed 2025 challenger | Δ |
|---|---:|---:|---:|---:|---:|---:|
| Coverage | 80.24% | 80.24% | 0.00 pp | 82.97% | 82.97% | 0.00 pp |
| Rank IC | 0.02757 | 0.02621 | −0.00136 | 0.15467 | 0.16432 | +0.00965 |
| NDCG@20 | 0.50117 | 0.55117 | +0.05000 | 0.62682 | 0.68536 | +0.05854 |
| Pairwise accuracy | 51.94% | 51.63% | −0.31 pp | 54.87% | 55.11% | +0.24 pp |
| Top-20 target achievement | 58.33% | 60.83% | +2.50 pp | 39.72% | 38.33% | **−1.39 pp** |
| Top-20 target shortfall | 6.03% | 4.19% | −1.84 pp | 12.90% | 12.07% | −0.83 pp |
| Mean Top-20 XIRR | 132.09% | 376.21% | +244.12 pp | 869.76% | 907.52% | +37.76 pp |
| Median Top-20 XIRR | 33.91% | 41.27% | +7.36 pp | 4.66% | 5.42% | +0.76 pp |
| Mean Top-20 asset drawdown | −34.56% | −33.90% | +0.66 pp | −42.58% | −39.47% | +3.11 pp |

The 2023 validation Rank IC decline is 4.9% relative; pairwise accuracy falls
0.6% relative. The exposed aggregate achievement decline is 3.5% relative.
The aggregate utility gains are real within this retrospective calculation, but
the profile failures below are too large to treat as secondary noise.

## Short-history and missing-value audit, current base profile

| Scored cohort | Champion share without true 5Y | Hybrid share without true 5Y |
|---|---:|---:|
| Entire scored universe | 7.99% | 7.99% |
| Top 20 | **90%** | **5%** |
| Top 50 | 46% | 10% |
| Top 100 | 29% | 6% |

The frozen ranker's `cagr_5y` contribution averaged **+0.2348** on the 260
currently scored rows with missing 5Y CAGR (median +0.2274), versus **−0.0405**
on rows with observed 5Y CAGR. The hybrid's new ranker has zero missing
`cagr_5y` values on scored rows. This is strong evidence of the current
missing-value shortcut; it is an attribution diagnostic, not a causal claim
about investment outcomes.

The requested NYKAA audit is a **diagnostic only**; its identity is not used in
features, training, score rules, or selection. Its true observed history is
58.25 months; since-listing CAGR is −2.07%, the Retailing observed 5Y median is
−0.89%, and its estimated 5Y growth proxy is **−2.03%**. The original 5Y value
was NaN. The frozen ranker assigned **+0.3058** of raw score contribution to
that missing 5Y feature. The new ranker assigns **−0.0039** to the estimated 5Y
value, **−0.0733** to history length, and **−0.0649** to days since high;
distance from high contributes +0.0901. Raw LightGBM contributions are not
percentile-blend contributions. Its overall base-profile position moves from
**1 to 105**. Within Retailing it remains **1 to 1**, so the sector position
alone does not show the reduction in absolute rank.

| Retailing position | Champion | Hybrid |
|---:|---|---|
| 1 | NYKAA | NYKAA |
| 2 | ETERNAL | ETERNAL |
| 3 | V2RETAIL | V2RETAIL |
| 4 | CARTRADE | CARTRADE |
| 5 | NAUKRI | NAUKRI |
| 6 | MEDPLUS | ARVINDFASN |
| 7 | ARVINDFASN | VMART |
| 8 | VMART | DMART |
| 9 | DMART | JUSTDIAL |
| 10 | TRENT | MEDPLUS |

## Profile regressions

All nine amount, lookback (12/36/60 months), interval, and 10/20/30% target
profiles were evaluated at both validation and both exposed dates. The full
36-block file is `profile_slices.csv`. Values below are challenger minus
champion, averaged across the two dates in each partition. Positive achievement
and negative shortfall are favorable.

| Profile | Validation achievement Δ | Validation shortfall Δ | Exposed achievement Δ | Exposed shortfall Δ |
|---|---:|---:|---:|---:|
| ₹1,000 amount | −2.5 pp | −1.95 pp | +2.5 pp | −2.05 pp |
| ₹7,500 base | +12.5 pp | −3.25 pp | **−12.5 pp** | +0.04 pp |
| ₹50,000 amount | +12.5 pp | −3.00 pp | 0.0 pp | −1.94 pp |
| 12-month lookback | +10.0 pp | −3.11 pp | +35.0 pp | −10.05 pp |
| 60-month lookback | −7.5 pp | **+1.84 pp** | −7.5 pp | **+2.21 pp** |
| Weekly interval | +2.5 pp | −2.76 pp | −5.0 pp | **+1.49 pp** |
| Quarterly interval | 0.0 pp | −0.86 pp | +2.5 pp | −1.38 pp |
| 10% target | **−10.0 pp** | **+1.29 pp** | **−12.5 pp** | **+0.89 pp** |
| 30% target | +5.0 pp | −4.75 pp | **−15.0 pp** | **+3.34 pp** |

The exposed 30% target and 60-month lookback shortfall increases violate the
harder investor-utility constraints despite an aggregate shortfall improvement.
The target 10/30% achievement losses are much larger than the desired 1–3%
relative tolerance. Thus **the frozen champion is the recommended winner**.
The hybrid is worth retaining as research evidence for the short-history fix,
but requires a new, profile-robust fit and genuinely new evaluation period
before any replacement decision.

## Artifacts and checks

- `research/runners/personalized_history_challenger.py`: history feature build,
  chronology-safe LambdaRank tournament, frozen current audit.
- `research/runners/personalized_history_hybrid.py`: exploratory blend grid and
  full comparison.
- `experiments/personalized-history-challenger/v6/`: 60-combination tournament,
  current history features, new ranker and diagnostic audit.
- `experiments/personalized-history-challenger/hybrid-v4/`: 40-combination
  exploratory grid, before/after metrics, 36 profile blocks, current ranks and
  contributions.
- `tests/test_personalized_history_challenger.py`: observed versus estimated
  5Y history and risk-feature check; passed (`1 passed`). Both research scripts
  passed Python compilation. No deployment or champion replacement occurred.

This remains retrospective, current-universe, price-only research. The exposed
2025 slices are not independent validation, and the large mean XIRRs require
careful interpretation. The 2026-09-18 current ranking has no matured
prospective 12-month outcome.
