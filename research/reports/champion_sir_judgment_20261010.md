# Every-stock audit: full-coverage champion versus Sir — 10 October 2026

**This is agreement with my explicit company-evidence rubric, not an objective percentage of correct investments.** I applied the rubric to every available stock record. This does not claim 4,436 fresh company investigations; the inputs are the saved 3 October snapshot.

All **4,436 stocks** have an audit row and explanation. **4190** have enough evidence and sector peers for a relative judgment. The fair model-versus-Sir comparison contains **4092 stocks in 56 sectors**. Unclassified stocks, insufficient fundamentals and sectors with fewer than five judged peers receive no correctness verdict.

## Percentages

| Method | Within-sector pair agreement | Stocks within 10 percentile points of rubric rank |
|---|---:|---:|
| champion | 56.93% | 21.51% (880/4092) |
| sir | 52.55% | 22.48% (920/4092) |

If every stock pair receives equal weight instead of every sector, agreement is **56.20% for the champion** and **55.67% for Sir** across 366,679 pairs. Large sectors dominate that alternative, so it is reported separately.

Pair agreement gives one point for matching the rubric’s order of two stocks, zero for reversing it, and half for ties. The headline is an equal-sector mean. The placement percentage is stock-weighted on the same paired cohort; it measures the declared 10-percentile-point tolerance. Exact ordinal correctness is too strong a claim for this evidence.

Across sectors, pair-order verdicts with a two-percentage-point practical tie band: **{'CHAMPION': 28, 'WITHIN_2_PERCENTAGE_POINTS': 19, 'SIR': 9}**. Top-three company-quality verdicts using a two-point/100 tie band: **{'CHAMPION': 36, 'SIR': 12, 'WITHIN_2_POINTS_ON_100_SCALE': 8}**.

## What my judgment rewards

Equal 20% blocks for profitability, growth, safety, cash conversion and valuation. Each input is ranked within its sector. Banks, Finance and Insurance omit corporate cash/leverage measures and redistribute applicable weights. Missing inputs are neutral only when total evidence coverage is at least 60%; otherwise the stock is unjudged. Quality-, growth- and value-oriented alternatives test sensitivity.

The block definitions are informed by [Quality Minus Junk](https://www.aqr.com/Insights/Research/Working-paper/Quality-minus-Junk). This implementation is a declared judgment rubric, not a replication of that paper. It does not assess management integrity, pending litigation, auditor concerns, financial restatements or prospective catalysts comprehensively. Price momentum can rationally disagree with this fundamental-quality benchmark.

## Sensitivity

| Subset | Rubric | Champion pair agreement | Sir pair agreement | Stocks |
|---|---|---:|---:|---:|
| all_paired | growth | 56.09% | 55.31% | 4092 |
| all_paired | primary | 56.93% | 52.55% | 4092 |
| all_paired | quality | 58.06% | 52.70% | 4092 |
| all_paired | value | 56.19% | 51.75% | 4092 |
| complete_fundamentals | growth | 50.75% | 53.33% | 2968 |
| complete_fundamentals | primary | 51.16% | 50.08% | 2968 |
| complete_fundamentals | quality | 53.16% | 51.38% | 2968 |
| complete_fundamentals | value | 49.82% | 47.89% | 2968 |
| sir_24plus_observations | growth | 58.04% | 57.19% | 3390 |
| sir_24plus_observations | primary | 58.61% | 54.52% | 3390 |
| sir_24plus_observations | quality | 59.10% | 54.19% | 3390 |
| sir_24plus_observations | value | 58.22% | 53.93% | 3390 |

## Stock-by-stock conclusions

The audit includes actual model rank, Sir rank, rubric rank, matching-cohort ranks, both models’ per-stock pair agreement, rank gaps, four-weight rank ranges, five block scores, eight raw fundamental inputs, missing-evidence flags and a record-specific explanation. TOO_HIGH/TOO_LOW means relative to this rubric, not a buy/sell recommendation.

All-stock placement counts: `{"RANKED_TOO_HIGH_VS_RUBRIC": 1721, "RANKED_TOO_LOW_VS_RUBRIC": 1554, "WITHIN_10_PERCENTILE_POINTS": 915, "UNCLASSIFIED": 132, "INSUFFICIENT_FUNDAMENTALS": 112, "TOO_FEW_JUDGED_PEERS": 2}`.

## Sir’s evidence and verification

The professor benchmark is the saved full-universe generalization of his independent per-stock whole-share SIP arithmetic, using ₹7,500, 36 months and 30-day intervals. Slot-specific workbook cross-references do not generalize to an arbitrary universe. This comparison does not claim his screenshot ranks all these stocks.

Sir has **4293 numerical scores**. All are based on partial requested price observations; none has the full 36, and the maximum is 35. The stricter sensitivity requires at least 24 observations and a quote no more than 14 days old. These checks do not certify the underlying corporate-action history.

Recomputed the fundamental rubric from saved raw inputs, verified all blocks and weight alternatives, checked unique identities and sector matches, and reconciled per-stock pair scores to the sector totals. Replayed all 159,696 Sir trade rows, whole-share quantities, costs and final score arithmetic. Input and output hashes are retained. The live model was not changed.

## Files

- `experiments/champion-sir-judgment-20261010/all_4436_stock_audit.csv`
- `experiments/champion-sir-judgment-20261010/sector_comparisons.csv`
- `experiments/champion-sir-judgment-20261010/sector_verdicts.csv`
- `experiments/champion-sir-judgment-20261010/summary.csv`

## Specific judgments from the saved evidence

| Stock | Sector | Model rank among judged peers | Rubric rank | Rank range across weights | Evidence assessment |
|---|---|---:|---:|---|---|
| NYKAA | Retailing | 1 | 26 | 19 to 39 | Top rank looks aggressive under a fundamentals-and-valuation standard. Its old ATH alone is not a reason to reject it. |
| KALYANI | Agricultural, Commercial & Construction Vehicles | 1 | 10 | 6 to 14 | Top rank is questionable given flat-price activity, negative operating cash flow and elevated debt in the saved evidence. Sir has no score here, so this is outside the paired headline. |
| SHAILY | Consumer Durables | 47 | 48 | 27 to 102 | Close to the primary rubric rank, but the broad weight-sensitive range makes an exact rank claim weak. |
| TDPOWERSYS | Electrical Equipment | 7 | 42 | 35 to 57 | Ranks much higher than the quality/value rubric, with valuation the weakest block. Momentum may explain the disagreement; it does not prove a bad investment. |
| IONEXCHANG | Other Utilities | 1 | 17 | 16 to 17 | Strong disagreement persists across all tested weights. Negative cash flow and low valuation percentile warrant review of cash-flow timing and the underlying company accounts. |
| RAMRAT | Electrical Equipment | 2 | 83 | 73 to 85 | High model placement conflicts with the saved safety and cash-flow evidence. Review is warranted before trusting the top-sector label. |

My verdict: the champion agrees more with this rubric on broad within-sector pair ordering and Top-3 quality, but the small proportion near the rubric rank prevents calling its stock-by-stock ordering reliably correct. Sir is slightly ahead on the exact same 10-percentile placement test. The complete-fundamentals subset and alternative weights narrow or sometimes reverse the advantage; see the sensitivity table.
