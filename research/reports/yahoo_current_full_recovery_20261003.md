# Yahoo current full recovery — 2026-10-03

Base: `experiments\current-data-recovery-20261003\current_company_facts_recovered_v6_full_screener.csv.gz`. Final: `experiments\current-data-recovery-20261003\current_company_facts_recovered_v7_full_yahoo.csv.gz`.

Universe 4,436; Yahoo symbol with observed adjusted price 4,346 (97.97%); current usable histories 4,345; stale histories 0; unresolved symbols 90; no-data histories 90; one-row histories 1.
NSE current 2,575; BSE current 1,770. Blanks-only feature fills 25,686 across 4,345 stocks (212 in original V6 columns; 25,474 in new current aliases). Separate Yahoo diagnostic columns add 229,961 nonblank cells.

## Coverage

| Feature | Before | After | New |
|---|---:|---:|---:|
| 1Y | 4,185 | 4,186 | 1 |
| 3Y | 3,805 | 3,807 | 2 |
| 5Y | 3,573 | 3,577 | 4 |
| 7Y | 3,393 | 3,404 | 11 |
| 10Y | 2,960 | 2,981 | 21 |
| history_months | 0 | 4,345 | 4,345 |
| 52W high | 4,374 | 4,422 | 48 |
| 52W low | 4,374 | 4,422 | 48 |
| ATH | 4,397 | 4,422 | 25 |
| ATH date | 4,397 | 4,422 | 25 |
| days since ATH | 4,397 | 4,422 | 25 |
| distance below ATH | 0 | 4,345 | 4,345 |
| max drawdown | 0 | 4,345 | 4,345 |
| current drawdown | 0 | 4,345 | 4,345 |
| underwater duration | 0 | 4,345 | 4,345 |
| downside volatility | 0 | 4,047 | 4,047 |
| realized volatility | 0 | 4,047 | 4,047 |

## Method

Yahoo adjusted close drives returns, drawdowns, volatility and adjusted ATH. Raw high/low drive raw-price high fields. Strict annual anchors use the latest observation on or before the calendar anchor, within seven days, and annualize over actual elapsed days. Shorter momentum uses exact observed interval return. Stale means the last Yahoo close is more than seven calendar days before 2026-10-03; stale histories contribute no blank fills. Volatility uses daily log returns and 252 trading days; downside deviation uses zero target and the same annualization. All dates and features stop at 2026-10-03.

True 5Y 3,108; true 7Y 2,931; true 10Y 2,524. Listing date proves fewer than five years for 985 stocks.

## Missingness and discrepancies

Per-stock reasons are in `yahoo_remaining_missing.csv`; aggregates are in `yahoo_missing_reason_codes.csv`. Discrepancies are audit only; existing professor, Screener and accepted provider cells are preserved.
- high_52w: 4,297 comparable; median absolute difference 0.00 price units; p90 22.05 price units; over 10% relative difference 378.
- latest_price: 4,343 comparable; median absolute difference 4.31 price units; p90 61.75 price units; over 10% relative difference 787.
- low_52w: 4,297 comparable; median absolute difference 0.00 price units; p90 4.50 price units; over 10% relative difference 194.
- product_baseline_cagr_3y: 3,403 comparable; median absolute difference 2.31 percentage points; p90 9.79 percentage points; over 10% relative difference 2,044.
- product_baseline_cagr_5y: 3,104 comparable; median absolute difference 1.71 percentage points; p90 7.25 percentage points; over 10% relative difference 1,673.
- product_baseline_yoy_growth: 3,823 comparable; median absolute difference 5.33 percentage points; p90 25.82 percentage points; over 10% relative difference 2,636.
- recorded_high: 4,320 comparable; median absolute difference 0.00 price units; p90 9.99 price units; over 10% relative difference 297.

## Five Screener nonmatches

- TRUSTWAVE SECURITIES LIMITED: TRUSTWAVE.BO — CURRENT_HISTORY; last 2026-10-02.
- MIDWEST ENERGY LIMITED: REMAGNET.BO — CURRENT_HISTORY; last 2026-10-01.
- Naturite Agro Products Limited: NAPL.BO — CURRENT_HISTORY; last 2026-10-01.
- Kalyani Commercials Limited: KALYANI.NS — CURRENT_HISTORY; last 2026-10-02.
- Taal Tech Limited: TAALTECH.NS — CURRENT_HISTORY; last 2026-10-01.

## Integrity

All V6 nonblank cells were compared before and after serialization. This runner writes only the current recovery directory and this report. Existing historical panels, frozen champion artifacts, production, website and Railway were not written.
