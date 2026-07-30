# Stock Ranking Platform

An offline-first foundation for explainable Indian equity research. The
long-term product will compare sectors, rank stocks inside each sector, create
model portfolios, and evaluate them against benchmarks with scheduled
rebalancing.

This milestone implements only **Baseline V1**. It does not fetch market data,
construct portfolios, backtest results, or make investment recommendations.

## What Baseline V1 means

The source research discusses four signals: one-year price growth, three-year
CAGR, five-year CAGR, and recency of the recorded high. It does not clearly
define a final combined formula.

Baseline V1 therefore introduces a transparent project-specific approximation:
rank each signal within its sector and take the equal-weight mean of those four
ranks. Lower scores are better. This combined formula must not be described as
the paper's exact final algorithm.

Growth and CAGR values use decimal returns internally and in CSV output:
`0.15` means 15%.

The required input name `ath_date` means the date of the highest price recorded
during the dataset or study period. It is a true all-time-high date only when
the study period covers the stock's complete trading history.

See [docs/methodology.md](docs/methodology.md) for exact formulas, ranking
directions, and tie rules.

## Setup

Python 3.13 is required. From PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

Editable installation is required before testing or invoking the console
command.

## Run the rankings

```powershell
.\.venv\Scripts\stock-ranker.exe rank `
  --input data/input/synthetic_stocks.csv `
  --output-dir data/output `
  --top-n 5
```

The command creates:

- `data/output/full_rankings.csv`
- `data/output/top_5_rankings.csv`

It prints a concise summary and returns a non-zero exit status for invalid
input. Generated result files are ignored by Git.

Run the tests after editable installation:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Input contract

Names are exact and case-sensitive. The engine does not guess aliases.
Additional columns are accepted but omitted from canonical output.

| Column | Meaning |
| --- | --- |
| `ticker` | Nonblank synthetic or exchange ticker identifier |
| `company` | Nonblank company name |
| `sector` | Nonblank sector used as the ranking group |
| `as_of_date` | Observation date in ISO `YYYY-MM-DD` form |
| `current_price` | Positive finite price on the observation date |
| `close_1y_ago` | Positive finite comparison price one year earlier |
| `close_3y_ago` | Positive finite comparison price three years earlier |
| `close_5y_ago` | Positive finite comparison price five years earlier |
| `ath_date` | ISO date of the highest price recorded in the study period |

Every required value must be present. `(ticker, as_of_date)` must be unique,
and `ath_date` cannot be later than `as_of_date`.

## Output contract

Output contains the nine canonical input fields plus:

| Column | Meaning |
| --- | --- |
| `yoy_growth` | One-year decimal price return |
| `cagr_3y` | Three-year compound annual decimal return |
| `cagr_5y` | Five-year compound annual decimal return |
| `days_since_recorded_high` | Calendar days from recorded high to observation |
| `yoy_rank` | Within-sector descending YoY competition rank |
| `cagr_3y_rank` | Within-sector descending three-year CAGR rank |
| `cagr_5y_rank` | Within-sector descending five-year CAGR rank |
| `recorded_high_recency_rank` | Within-sector ascending recency rank |
| `baseline_score` | Equal-weight mean of the four ranks |
| `sector_rank` | Within-sector ascending baseline-score rank |
| `method_version` | Stable method identifier |

## Project structure

```text
src/stock_ranker/
  contracts.py       canonical column schemas
  validation.py      input normalization and validation
  ingestion.py       CSV loading
  metrics.py         Baseline V1 metric calculations
  ranking.py         within-sector ranks and combined score
  selection.py       deterministic top-N selection
  baseline.py        stable orchestration API
  exporting.py       full and top-N CSV output
  config.py          Baseline V1 configuration
  cli.py             installed command
  research_v2.py     future scoring interface
  portfolio.py       future construction/rebalancing interface
  backtesting.py     future backtest/benchmark interface
data/input/          committed synthetic input
data/output/         ignored generated results
docs/                methodology documentation
tests/               behavioral and command tests
```

## Synthetic sample and limitations

`data/input/synthetic_stocks.csv` contains 18 fictional companies across three
sectors. Its prices and performance patterns are invented for testing, include
a deliberate tie, and are not recommendations.

Baseline V1:

- uses supplied price snapshots rather than a price-history series;
- treats the supplied high date as a study-period recorded high;
- ignores volatility, drawdown, fundamentals, transaction costs, liquidity,
  survivorship bias, and corporate actions;
- does not score sectors, weight portfolios, compare benchmarks, or rebalance;
- is a research ranking, not financial advice or a prediction of returns.

## Next milestone

Research V2 should add validated historical and fundamental contracts, risk and
quality metrics, explicit weighted scoring, sector-first selection, portfolio
weighting, point-in-time backtesting, benchmark evaluation, transaction-cost
assumptions, and scheduled rebalancing. The current interface modules mark
those boundaries without returning fake results.
