# Stock Ranking Platform

Latest research: [Second round, 31 October 2026](research/reports/round2_20261031.md), following the [ten original pilots](research/reports/ten_hypotheses_20261031.md). Sector shuffle and risk objectives did not pass; daily hysteresis missed its lag gate. The incumbent application and model package are unchanged.

[Prospective ledger](https://github.com/harshil0014/stock-ranking-platform-checkpoint/tree/prospective-ledger): append-only records and daily exchange metadata capture are active. Frozen October 3 scores remain stale; the fresh twelve-month score holdout has not started.

Latest source and research checkpoint: [31 October 2026](docs/github_checkpoint_20261031.md). The current UI offers Baseline, Sector Champion, Closing High, Personalized, and Personalized V17. The sections below retain the earlier canonical baseline documentation.

## Canonical product

The primary website exposes two active ranking modes:

- **Baseline**, the reference current-market ranking.
- **Personalized**, the frozen `d499580` champion using 67% Goal and 33% sealed
  LightGBM LambdaRank with the user's contribution amount, lookback, interval,
  target CAGR, and supported 12-month horizon.

Personalized now shows each genuine result's overall rank and its position among
genuine Personalized peers in the same accepted product sector. Product fallbacks
retain their sector and separate Baseline sector rank without receiving a
Personalized rank. See [the sector-ranking contract and audit](docs/personalized_sector_ranking_20260927.md).

Research V2 and rejected challengers remain versioned as historical research,
validation, methodology, and provenance evidence. They are not active product
ranking choices. The large personalized runtime pack is mounted outside Git at
`research/runtime/personalized-ui-d499580.npz` and must match SHA-256
`515eac8ffc555a571406a4a41f9d931a016cb6280871a3d89f59846d2692ed0c`.

The latest reconciled current-data counts and their exact cohort definitions
are recorded in
[docs/current_data_status_20260829.md](docs/current_data_status_20260829.md).

The accepted universe now has a separate confidence-aware completion layer:
all 4,436 identities have a sector, completed fields and a full-sector rank,
with zero blank cells in the completed artifact. Every estimate is cell-coded
and the original accepted snapshot is preserved unchanged. See
[the complete-universe report](docs/complete_universe_completion_20260920.md).

The final Complete Universe architecture was compared with pre-existing frozen
Codex judgments across 3,987 independently orderable identities and 213,345
within-scope pairs, with honestly measured agreement of 95.0158%. All 4,436
identities have a stock-by-stock audit row; the 449 that lacked a pre-frozen
independent order are reviewed but are not added to the agreement denominator. See
[the complete internal ranking audit](docs/complete_internal_ranking_audit_20260918.md).

An offline-first foundation for explainable Indian equity research. The
long-term product will compare sectors, rank stocks inside each sector, create
model portfolios, and evaluate them against benchmarks with scheduled
rebalancing.

The repository implements the confidence-aware **Complete Universe** product
ranking, preserves **Baseline V1**, and retains the offline, point-in-time
**Research V2** scoring engine. A separate isolated adapter can acquire and
freeze real historical prices; normal product execution never fetches them.
The project does not rank sectors, construct portfolios, backtest results, or
make investment recommendations.

## Professor workbook reference benchmark

The optional offline `professor-reference` command audits the supplied Baba
Venkeesh Master Sheet XLSX, preserves exact cell/formula provenance, joins only
exact current NSE symbols, and compares its cached 1Y/3Y/5Y and ATH-recency
fields with a same-date Baseline V1 reconstruction. It never invents a
professor sector rank: the workbook has no sector taxonomy or computed ranking
formula. The prepared website Methodology view shows the three-stage boundary
**Professor Reference → Baseline V1 → Research V2** by current NSE sector.

```powershell
.\.venv\Scripts\stock-ranker.exe professor-reference `
  --workbook "C:\path\to\Baba Venkeesh - Master Sheet v2.1-Final.xlsx" `
  --output-dir data\professor_reference\current
```

The observed reference verdict is **PARTIAL MATCH** and the independent
Research V2 verdict is **INSUFFICIENT EVIDENCE** because the preregistered
12-month comparison has only three sector-date observations. See
[the full benchmark audit](docs/professor_reference_benchmark.md).

The newer OK Strategy v4.3 workbook is audited separately with
`stock-ranker professor-strategy`. It extracts the explicit SIP profit/loss
rank and cached CAGR/industry evidence with exact cell provenance, compares the
exact 14-stock cohort without fuzzy substitutions, and reports `PARTIAL MATCH`.
See [the OK Strategy audit](docs/professor_ok_strategy_v4_3.md). Screener is
supported only through an optional dated, user-supplied export matched by exact
NSE/BSE code; the product does not scrape Screener or treat it as an API.

The separately supplied 99-security acceptance cohort is audited without fuzzy
identity matching and displayed beside canonical model statuses. Its result is
98 resolved, one legitimately provider-unavailable, no unresolved identity,
and **NOT REPRODUCIBLE FROM AVAILABLE METHODOLOGY** for the undisclosed global
ranking formula. See [the supplied-cohort audit](docs/professor_supplied_acceptance.md).

## Live Market and Research Lab website

Launch the read-only application locally from the repository root:

```powershell
.\\.venv\\Scripts\\python.exe -m stock_ranker.webapp --port 8765
```

Then open `http://127.0.0.1:8765/`. **LIVE MARKET** is the default practical
screen; **RESEARCH LAB** preserves the frozen professor-facing evidence. The
dependency-free server binds to loopback by default and reads prepared outputs without
changing the accepted observed snapshot, Research V2, or walk-forward calculations. Its Overview,
Rankings, Historical, Validation, Provenance, Methodology, and Status views are
available both locally and in the permanent container deployment. See
`docs/professor_competition_demo.md` for the walkthrough and artifact requirements.

The legacy analysis API retains its committed **SYNTHETIC RESEARCH TEST**
fixtures and canonical upload contracts for regression compatibility. The
Complete Universe estimates are always labelled through cell-level provenance
and never overwrite observed facts. Integrity-mismatched local artifacts still
produce a controlled status. Normal page navigation fetches no market data and
makes no investment recommendation.

LIVE MARKET resolves an atomic accepted-state pointer under the ignored
`data/live_market/` evidence store. Startup and hosted serving are read-only by
default. Refresh is an explicit opt-in maintenance action; a failed or partial
refresh cannot replace the last-known-good bundle. The accepted universe uses
exact ISIN identity under `listed_ordinary_company_equity_v1`: company-issued
ordinary equity only, with funds/ETFs, debt/government securities, preference
and other non-equity securities, listed trusts, rights entitlements, and
alternate/DVR classes excluded with an auditable reason. Dual listings are not
duplicated and BSE-only names never receive invented NSE tickers. Previously
unclassified or data-incomplete securities remain browsable and now receive
confidence-adjusted ranks. Inferred sectors and completed fields are explicitly
estimate-coded and never overwrite the accepted observed layer.

The preserved pre-completion Baseline coverage uses explicit evidence routing. Securities
with all four original inputs remain in the unchanged `PRIMARY_5Y` ranking.
Shorter accepted histories may enter `REDUCED_3Y` (1Y growth, 3Y CAGR and high
recency), `REDUCED_1Y` (1Y growth and high recency), or guarded
`RECENCY_ONLY` rankings. Each reduced tier is ranked only against same-sector
peers in that exact tier, carries a visible confidence label, and cannot change
or compete directly with primary ranks. Recency-only admission requires at
least 20 real observations spanning 30 calendar days. Missing classifications,
unsafe price continuity, or shorter evidence remain unranked in that strict
legacy view. The production Complete Universe layer ranks all accepted identities
separately and labels every estimate. Neither route expands frozen historical or
PIT eligibility.

## Permanent hosting

The supported permanent deployment is the read-only Docker Compose service in
`compose.yaml`. It validates the frozen release fingerprints before starting,
runs unprivileged with a read-only root filesystem, mounts large evidence stores
read-only from durable host storage, and exposes `/api/health` as a fail-closed
readiness probe.

```sh
cp .env.example .env
docker compose build --pull
docker compose up -d
curl --fail http://127.0.0.1:8765/api/health
```

See [the permanent deployment runbook](docs/permanent_deployment.md) for evidence
volume layout, TLS reverse-proxy requirements, refresh isolation and rollback.

The same refresh can be run or inspected explicitly:

```powershell
.\.venv\Scripts\stock-ranker.exe refresh --status
.\.venv\Scripts\stock-ranker.exe refresh --dry-run
.\.venv\Scripts\stock-ranker.exe refresh
```

Raw downloads and accepted snapshots are immutable and hashed. The runner
rejects HTML error pages, stale/wrong-date files, schema drift, identity
duplicates, implausible coverage changes, model-eligibility collapses and
frozen-research drift. It caches one provider-history CSV per exact `.NS`
symbol and updates only stale histories. Page navigation itself remains
offline; it reads one internally consistent accepted bundle. See
[the LIVE MARKET data contract](docs/live_market.md).

The legacy `/api/analyze` endpoint retains the one-day official market adapter
for an official NIFTY constituent CSV and corresponding NSE CM-UDiFF Common
Bhavcopy Final ZIP. The adapter
joins `Symbol + Series + ISIN Code` to `TckrSymb + SctySrs + ISIN`, validates
every constituent, and exports only the canonical matched snapshot. It never
extracts the ZIP into the repository and never fetches live data.

This real snapshot view deliberately does not run Baseline V1 or Research V2.
One trading day cannot supply YoY, three- or five-year CAGR, recorded-high
recency, or point-in-time fundamentals.

For the prepared real demonstration, open **Rankings** and choose **Baseline
V1**. The website validates the local frozen bundle and reads the accepted
Baseline V1 result without internet access. Its stock explanation shows the four
metric ranks, combined score, sector rank, exclusions, provenance, and a real
NIFTY 50 CSV export.

This mode is labelled **REAL HISTORICAL PRICE RESEARCH**. It uses Yahoo `Adj
Close` from a `yfinance==1.5.1` repaired max-history fetch and independently
checks terminal prices against the supplied official NSE 07-Aug-2026 snapshot.
The adjusted series includes upstream dividend adjustments. No project
corporate-action formula is applied. The universe is the current supplied
NIFTY 50 snapshot, not a survivorship-bias-free historical universe, and the
result is not a walk-forward backtest. See
[the real-history methodology](docs/real_historical_baseline.md).

For the point-in-time accounting view, choose **Research V2** in Rankings and
inspect a company or open Provenance. The offline view combines the accepted frozen price
bundle with official NSE Integrated Filing metadata and XBRL selected using
exchange dissemination time through `2026-08-07 15:30:00 IST`. It displays
every company, explicit exclusions, filing provenance, and a rank-only
Baseline V1 comparison. The scoring model remains **Research V2**; its separate
real-accounting input contract is **NSE Audited Standalone Fundamentals v1**
(`nse_audited_standalone_fundamentals_v1`). Baseline and Research V2 raw scores
have different directions and scales and are never subtracted.

The Integrated Filing XBRLs alone could not provide all three canonical
fundamentals. A second conservative stage therefore audits official NSE-hosted
FY2025-26 annual-report PDFs with isolated `pypdf` extraction. It accepts only
manually reviewed audited standalone statutory disclosures on one consistent
basis: explicit issuer ROCE, explicit debt-to-equity, and current/comparable
reported PAT. Candidate text, ROA, ROE, ROEV, ROIC, derived ratios, and other
substitutes remain exclusions. The frozen contract admits 34 of 50 companies.
Standalone was selected for the broadest internally consistent audited
statutory-ratio coverage, not because standalone economics are universally
superior to consolidated economics. See
[the real Research V2 methodology](docs/real_research_v2.md).

The comparison preserves the original Baseline sector rank for context and
also recalculates unchanged Baseline V1 on exactly the Research-V2-eligible
cohort. Rank movement is computed only from that matched Baseline rank to the
Research V2 rank. Singleton sectors are labelled non-informative.

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
  real_research_v2.py safe NSE XBRL parsing and frozen real V2 bundle boundary
  data_state.py      transactional market acceptance and last-known-good state
  company_facts.py   ISIN-keyed facts and immutable accepted snapshots
  portfolio.py       future construction/rebalancing interface
  backtesting.py     future backtest/benchmark interface
data/input/          committed synthetic input
data/output/         ignored generated results
docs/                methodology documentation
tests/               behavioral and command tests
```

## Company information coverage

The local website reads a provider-independent accepted company-fact snapshot,
not Screener.in or a live page scraper. Build it from cached accepted evidence:

```powershell
.\.venv\Scripts\stock-ranker.exe company-facts --dry-run
.\.venv\Scripts\stock-ranker.exe company-facts
.\.venv\Scripts\stock-ranker.exe data-refresh --dry-run
.\.venv\Scripts\stock-ranker.exe data-refresh --status
.\.venv\Scripts\stock-ranker.exe data-backfill --resume --retry-errors
```

The measured 5,093-security coverage and exact unresolved categories are in
[`docs/company_information_coverage.md`](docs/company_information_coverage.md).
Company-page richness is separate from Baseline and strict Research V2
eligibility; missing facts carry precise statuses rather than guessed or
zero-filled values.

The unified refresh checks official exchange data, acquires a bounded,
identity-validated secondary-fact batch in the isolated market-data
environment, then atomically rebuilds the coherent fact state. Use
`data-refresh --full-backfill` for a resumable all-market secondary pass.
Provider failures retain the previous accepted state. Screener remains
policy-disabled as an automated source under its published terms and robots
rules; see [`docs/open_source_data_foundation.md`](docs/open_source_data_foundation.md).

The implemented [official exchange backbone](docs/official_exchange_backbone.md)
uses bulk NSE filing/shareholding/action/document catalogues, linked XBRLs and
official BSE endpoints. It keeps raw evidence in immutable ignored batches,
separates official facts from secondary references, and gradually drains a
rate-limit-aware Yahoo backlog. Website navigation remains entirely offline.

Strict PIT fundamental scaling is documented in
[`docs/pit_fundamental_scale.md`](docs/pit_fundamental_scale.md). The new
workflow discovers official NSE annual-report metadata for the full
Baseline-ready V2-gap population, downloads only bounded frozen batches, and
generates page-level accounting review packets. It never treats extracted
numbers as accepted facts or updates frozen Research V2 automatically. Official
symbol/name history is normalized as exact identity evidence; possible ISIN
transitions remain quarantined and never splice price histories automatically.

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

The official Qlib DoubleEnsemble attempt on the same frozen synthetic protocol
trained three submodels but produced a constant test signal, so it stopped
before run 2 and remains `adoption_specified`. Accepted Linear and LightGBM
evidence is unchanged.
