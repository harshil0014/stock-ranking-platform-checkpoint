# Stock Ranking Platform

An offline-first foundation for explainable Indian equity research. The
long-term product will compare sectors, rank stocks inside each sector, create
model portfolios, and evaluate them against benchmarks with scheduled
rebalancing.

The repository implements **Baseline V1** and the offline, point-in-time
**Research V2** scoring engine. It does not fetch live data, rank sectors,
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

## Run Research V2

Research V2 uses three independent offline datasets:

```powershell
.\.venv\Scripts\stock-ranker.exe research-v2 `
  --universe data\input\v2_universe.csv `
  --prices data\input\v2_prices.csv `
  --fundamentals data\input\v2_fundamentals.csv `
  --ranking-date 2026-06-30 `
  --output-dir data\output\v2 `
  --top-n 5
```

It creates `full_research_v2_rankings.csv`,
`top_5_research_v2_rankings.csv`, and
`research_v2_eligibility_report.csv`.

Required names are exact and case-sensitive:

```text
Universe:     ticker, company, sector
Prices:       ticker, date, adjusted_close
Fundamentals: ticker, period_end, available_date,
              roce, debt_to_equity, profit_growth_yoy
```

Returns, fundamentals, volatility, and drawdown use decimal representation.
`available_date` is when a fundamental version became public. Future records
are removed before stock-level numeric validation, preventing future malformed
values from contaminating earlier results.

The sample contains only fictional companies and deliberately includes a
fundamental revision, future records, a scoring tie, and an ineligible leverage
value. See
[docs/research_v2_methodology.md](docs/research_v2_methodology.md) for all
formulas, eligibility rules, weights, and point-in-time behavior.

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
  research_v2.py     Research V2 metrics, eligibility, and scoring
  v2_config.py       V2 weights and settings
  v2_contracts.py    V2 schemas
  v2_validation.py   V2 structural validation
  v2_exporting.py    V2 result exporting
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

Research V2 adds price, risk, and fundamental scoring but remains dependent on
the coverage, accuracy, publication dates, and classifications in its supplied
offline files. Its component scores express relative ordinal position within a
sector, not the magnitude of financial superiority. Cross-sector comparisons
would be misleading.

## Next milestone

Qlib Linear has been reproduced twice with the official v0.9.7 implementation
on a frozen offline synthetic pipeline. The Qlib LightGBM diagnostic proved
that an uninitialized workflow fails after training at `R.log_metrics`. The
official local-recorder path then initialized Qlib successfully, but installed
MLflow rejected its filesystem store before fitting because the additional
`MLFLOW_ALLOW_FILE_STORE=true` opt-in was initially absent. After explicit
authorization for LightGBM child processes only, two fresh official runs
completed and matched predictions and both feature-importance measures exactly
at the fixed `1e-12` tolerance. This is synthetic-only reproduction evidence.
Alpha158 and real-market work remain later and require approved data
provenance. Portfolio construction and performance claims remain out of scope.

## Open-source quant research layer

The additive [`research/`](research/) layer provides leakage-aware feature,
label, signal, and chronological-split contracts; deterministic provenance
fingerprints; planned experiment manifests; Qlib-free signal adapters; and
cross-sectional IC/Rank IC evaluation. It installs a separate
`stock-research` command and leaves both `stock-ranker rank` and
`stock-ranker research-v2` unchanged.

Qlib is not a product dependency. The verified upstream package pin is
`pyqlib==0.9.7` (tag `v0.9.7`, commit `da920b7`). Its isolated Python 3.12
environment has a captured complete `pip freeze` and passing import smoke
checks. The Python 3.13 `.venv` must not contain Qlib, LightGBM, or PyTorch.

Use `stock-research reproduce-qlib-linear --dry-run` to validate the complete
plan without training or writing run artifacts. A full invocation performs two
independent official Qlib runs and compares each with genuine Research V2
signals. See
[research/docs/qlib_linear_reproduction.md](research/docs/qlib_linear_reproduction.md).

Evaluation compares models only when their
`evaluation_protocol_fingerprint` matches. Model families keep independent
configuration and dataset fingerprints. Primary ICIR is unannualized; a
default annualization factor of 252 applies only when frequency is explicitly
daily. Other frequencies produce null annualized values unless a positive
factor is explicitly supplied.

The project intentionally has no licence yet. Owner licence selection is a
blocker to public distribution. Synthetic fixtures and scores are research
contract tests, not trained results, portfolio claims, or investment advice.
