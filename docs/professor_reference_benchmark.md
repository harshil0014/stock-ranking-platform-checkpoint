# Professor Reference Benchmark

## Verdict

- Methodology reproduction: **PARTIAL MATCH**.
- Research V2 improvement: **INSUFFICIENT EVIDENCE**.

The benchmark is reproducible from the supplied `Baba Venkeesh – Master Sheet
v2.1-Final` XLSX and the existing offline platform caches. It does not embed
company-specific expected values in application code.

## What the workbook actually does

All 23 worksheets were inspected, including formulas and cached values. The
stock-selection surface is `Stock Picker`, a personal 39-row ticker list (one
row is an empty `NSE:KEI` placeholder). Its comparable fields are:

| Reference field | Cell/formula behavior | Platform comparison |
|---|---|---|
| Current price | `GOOGLEFINANCE(ticker,"price")` | Latest adjusted close on/before the cached date |
| Recorded high | Imported ATH table with a weekly `GOOGLEFINANCE(...,"high",...,"weekly")` fallback | Maximum repaired adjusted daily close through the date |
| Recorded-high date | Imported ATH date or date of weekly Google high | Latest date of the maximum adjusted daily close |
| Recency | `TODAY()-ATH date` | Ranking date minus recorded-high date |
| 10Y/5Y/3Y/1Y performance | Screener.in table 5 via `IMPORTHTML`; displayed to whole percentage points | Exact calendar anchors and Baseline formulas |

The workbook's cached date is **2026-02-17** (`NAV-Auto!H1`). Google documents
that current `price` can be delayed and that historical `high` is a period high,
not an adjusted close. The platform intentionally retains its accepted repaired
Yahoo adjusted-close series. See the official
[GOOGLEFINANCE documentation](https://support.google.com/docs/answer/3093281)
and [yfinance price-repair documentation](https://ranaroussi.github.io/yfinance/advanced/price_repair.html).

The workbook does **not** contain a sector classification, sector rank,
combined score, or stock-selection rank formula. Columns headed `1` through
`5` are manual entries, and other sheets cover portfolio planning, SIPs,
heatmaps, annual rates and valuation views. Consequently, this project does
not invent or attribute a professor sector rank. Sector summaries below use
the platform's current official NSE Indices classification only.

One `RANK` formula exists in `SIP Portfolio!M8` for a portfolio-planning table;
it is not in `Stock Picker`, is not sector-based, and is not used as a stock
selection or Baseline benchmark rank.

## Identity and coverage

- Workbook SHA-256: `4beb8f53319c9f0dbcd2f08f265e82aa8e79d57bba0451a9ed9dab6769e42afc`
- Stock Picker rows: 39
- Exact current NSE-symbol matches: 33
- Unmatched without substitution: 6
  - BSE-only: `BOM:538566`, `BOM:514448`, `BOM:532742`
  - not in the current NSE universe: `NSE:JBCHEPHARM`, `NSE:TATAMOTORS`, `NSE:TINPLATE`
- Comparable classified Baseline rows: 26
- Current classified NSE universe: 750; Baseline eligible at the reference
  date: 551

Matching is exchange-and-symbol exact. No name similarity, successor security,
delisted-security replacement, BSE-to-NSE guess, or corporate-action successor
is silently substituted.

## Agreement

"Reported-precision match" means the platform value rounds to the workbook's
cached whole-percentage-point value (or the same rounded day count). This is
stricter than directional/rank agreement.

| Metric | Comparable | Precision matches | Match rate | Mean absolute difference | Spearman | Top-5 overlap |
|---|---:|---:|---:|---:|---:|---:|
| 1Y growth | 22 | 10 | 45.45% | 0.006294 | 0.999718 | 100% |
| 3Y CAGR | 26 | 8 | 30.77% | 0.008091 | 0.999487 | 100% |
| 5Y CAGR | 26 | 8 | 30.77% | 0.008042 | 0.993496 | 80% |
| Recorded-high recency | 26 | 3 | 11.54% | 44.526 days | 0.982558 | 80% |
| Current price (0.1%/₹0.05 tolerance) | 26 | 3 | 11.54% | ₹16.7169 | 0.998632 | 100% |
| Recorded-high price (same tolerance) | 26 | 0 | 0% | ₹860.8632 | 0.753846 | 60% |
| Recorded-high date | 26 | 10 | 38.46% | — | — | — |

The low exact percentages coexist with extremely high rank correlations. The
principal causes are displayed rounding, different external sources, exact
calendar anchors versus Screener periods, intraday/weekly nominal highs versus
adjusted daily closes, and timestamps that include fractions of a day.
Pandas' established average-rank implementation is used for Spearman-style
rank comparison; its tie behavior is documented in the
[pandas rank API](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.rank.html).

Sector-level metric rank correlations are mostly 0.96–1.00 where at least two
matched stocks exist. Single-stock sectors correctly have no correlation.

## Material discrepancy audit

- `BAJFINANCE` and `COFORGE`: workbook current prices reflect later split
  scales while cached ATH values remain on earlier nominal scales. The
  platform's adjusted series is scale-consistent, so it does not reproduce the
  nominal ATH/recency artifact.
- `ASIANPAINT` and `WIPRO`: high dates differ materially because the reference
  uses nominal intraday/weekly highs while the platform uses maxima of adjusted
  daily closes. Dividend adjustment can change which date is maximal.
- `TCS`: the high date agrees, while the cached price and rounded CAGR values
  differ because Google/Screener and the repaired Yahoo anchor series are not
  the same source or observation convention.
- Missing reference 1Y values are retained as missing. Missing fields and
  inactive/BSE-only identities are never imputed.

No Baseline formula, sector rank rule, Research V2 weight, eligibility rule, or
frozen research artifact was changed. These are real data/methodology
differences, not implementation defects.

## Research V2 and quant evidence

The accepted preregistered, outcome-blind 12-month walk-forward evaluation is
the fair comparison boundary:

- Research V2 mean sector-date Rank IC: `0.0`
- Matched-cohort Baseline mean sector-date Rank IC: `-0.0446581987`
- Pairwise accuracy: `53.85%` versus `50.00%`
- Primary sample: only **3 sector-date observations**

The point estimates are slightly higher for V2, but the primary sample is far
too small for a defensible improvement conclusion. Existing Qlib model
reproductions are synthetic contract/reproducibility evidence, not validation
against this real workbook or a claim of investment usefulness.

## Reproduce

```powershell
.\.venv\Scripts\stock-ranker.exe professor-reference `
  --workbook "C:\path\to\Baba Venkeesh - Master Sheet v2.1-Final.xlsx" `
  --output-dir data\professor_reference\current
```

Outputs include exact source cells/formulas, stock comparisons, sector and
metric summaries, audit verdicts, file hashes, and a deterministic benchmark
fingerprint. The generated directory is ignored; the source workbook is never
modified or committed.
