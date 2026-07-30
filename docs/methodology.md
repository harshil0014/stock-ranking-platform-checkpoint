# Baseline V1 Methodology

## Status and interpretation

Baseline V1 is a transparent approximation inspired by four signals described
in the source research. The research does not clearly specify a final combined
ranking formula, so this project introduces the equal-rank-mean rule below. It
is not the paper's exact final algorithm.

The CSV field remains named `ath_date` for compatibility. In this project it is
the date of the highest price **recorded in the dataset or study period**. It
may be called an all-time high only when the dataset spans the stock's entire
trading history.

## Metrics

For current price \(P_0\), prices one, three, and five years earlier
\(P_1, P_3, P_5\):

```text
yoy_growth = P0 / P1 - 1
cagr_3y = (P0 / P3) ** (1 / 3) - 1
cagr_5y = (P0 / P5) ** (1 / 5) - 1
days_since_recorded_high = as_of_date - ath_date
```

Growth and CAGR use decimal returns. For example, `-0.08` means -8%.
Recorded-high recency is an integer number of calendar days.

All prices must be finite and greater than zero. Both dates must use ISO
`YYYY-MM-DD`, and the recorded-high date cannot follow the observation date.

## Sector ranking and ties

Stocks are compared only with other rows in the same sector:

1. Rank YoY, three-year CAGR, and five-year CAGR descending.
2. Rank days since recorded high ascending.
3. Assign equal values the same competition rank (`1, 2, 2, 4`).
4. Calculate `baseline_score` as the arithmetic mean of the four ranks.
5. Rank that score ascending within the sector, again using competition ranks.
6. Sort results by sector, baseline score, and ticker.

Top-N output contains exactly N rows from each sector when that many exist.
If a tied score crosses the cutoff, alphabetical ticker order is the
deterministic selection tie-breaker. The tied stocks retain their equal
reported sector rank. When a sector contains fewer than N stocks, every stock
in that sector is returned.

The stable method identifier is:

```text
baseline_v1_equal_rank_mean
```

## Research limitations

The baseline operates on supplied snapshots and cannot verify that dates align
with exchange sessions or that the recorded high covers full trading history.
It does not account for dividends, splits, risk, drawdown, fundamentals,
liquidity, costs, taxes, portfolio weighting, or point-in-time bias.

Results are explainable research rankings. They are not investment
recommendations.
