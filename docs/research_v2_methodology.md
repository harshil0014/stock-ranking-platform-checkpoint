# Research V2 Point-in-Time Methodology

## Purpose and boundary

Research V2 is an offline, explainable stock-scoring method. It uses only
prices and fundamental records available on a selected ranking date and ranks
eligible stocks against other eligible stocks in the same sector.

The component weights and scoring method are project assumptions, not formulas
directly prescribed by the original research paper. Scores from different
sectors must not be treated as a cross-sector ranking. These research results
are not financial advice, forecasts, or investment recommendations.

## Input contracts

Required names are exact and case-sensitive.

```text
Universe:     ticker, company, sector
Prices:       ticker, date, adjusted_close
Fundamentals: ticker, period_end, available_date,
              roce, debt_to_equity, profit_growth_yoy
```

Universe tickers are unique and represent the supplied classification snapshot
for the ranking date. The price natural key is `(ticker, date)`. The
fundamental natural key is `(ticker, period_end, available_date)`, allowing
multiple revisions for the same reporting period.

Dates use ISO `YYYY-MM-DD`. Prices must be finite and positive. Percentages,
returns, volatility, and drawdown use decimals: `0.15` means 15% and `-0.10`
means -10%.

## Point-in-time processing

Schemas, identifiers, keys, and dates are validated first. Prices after the
ranking date and fundamentals whose `period_end` or `available_date` is after
the ranking date are then removed. Stock-level numeric validation occurs only
after that filtering.

Thus, a future malformed numeric value cannot change an earlier calculation.
A malformed date remains a structural error because its point in time cannot
be determined safely.

For each ticker, select the greatest eligible fundamental `period_end`, then
the greatest eligible `available_date` for that period. This selects the latest
revision actually public on the ranking date.

## Metrics and windows

Current, one-year, three-year, and five-year anchors use the latest adjusted
close on or before their calendar target. Each must be no more than seven
calendar days before its target.

```text
return_1y = current / one_year_anchor - 1
cagr_3y = (current / three_year_anchor) ** (1 / 3) - 1
cagr_5y = (current / five_year_anchor) ** (1 / 5) - 1
```

Recorded-high recency is the number of calendar days since the latest
occurrence of the greatest adjusted close supplied through the ranking date.
It is a lifetime all-time high only when the supplied history covers the
stock's complete trading life.

One-year annualized volatility is the sample standard deviation (`ddof=1`) of
daily simple returns from the one-year anchor through the current observation,
multiplied by `sqrt(252)`.

Three-year maximum drawdown is:

```text
drawdown_t = adjusted_close_t / running_peak_t - 1
max_drawdown_3y = minimum trailing drawdown_t
```

Drawdown is zero or negative. Values nearer zero are less severe and receive
the better directional rank.

## Eligibility

Nothing is imputed. Every universe stock receives an eligibility row. Reasons
cover missing or stale anchors, invalid prices, insufficient volatility
observations, missing fundamentals, invalid fundamental values, and invalid
leverage.

Negative debt-to-equity is ineligible because an ordinary lower-is-better rule
would incorrectly reward that condition. Only eligible stocks enter scoring.

## Rank-based component scores

Within each sector and metric, calculate average ranks:

- Descending for one-year return, three-/five-year CAGR, maximum drawdown,
  ROCE, and profit growth.
- Ascending for recorded-high recency, annualized volatility, and
  debt-to-equity.

Let `best_rank` be the minimum observed average rank and `worst_rank` the
maximum. When more than one distinct value exists:

```text
component_score =
    100 * (worst_rank - average_rank)
    / (worst_rank - best_rank)
```

The best value or tied-best group receives 100. The worst value or tied-worst
group receives 0. Equal raw values receive equal scores. When every value is
equal, or only one eligible stock exists, assign 50.

This method uses ranks, never distances between raw financial values.
Component scores represent relative within-sector position, not the magnitude
of financial superiority.

## Weights and final score

| Component | Weight |
| --- | ---: |
| One-year return | 10% |
| Three-year CAGR | 10% |
| Five-year CAGR | 10% |
| Recorded-high recency | 5% |
| Annualized volatility | 12.5% |
| Maximum drawdown | 12.5% |
| ROCE | 15% |
| Debt-to-equity | 10% |
| Profit growth | 15% |

Weights must be finite, nonnegative, and total exactly 100%.

```text
weighted_contribution = component_score * weight / 100
research_v2_score = sum(all nine weighted contributions)
```

Final scores receive descending within-sector competition ranks. Tied scores
retain equal ranks. Output is ordered by sector, final score descending, and
ticker ascending; ticker breaks only ordering and top-N cutoff ties.

## Limitations and later milestones

Research V2 cannot verify exchange calendars, adjustment quality, source
provenance, survivorship bias, historical classification changes, or complete
trading-history coverage. It does not rank sectors, construct portfolios,
compare benchmarks, backtest, or rebalance.

The next milestone should introduce sector/index histories and sector-level
scoring. Portfolio construction and point-in-time backtesting remain later
milestones.
