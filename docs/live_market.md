# LIVE MARKET product data contract

LIVE MARKET is a changing current product snapshot. It is deliberately
separate from the frozen, reproducible RESEARCH LAB.

## Universe and identity

The primary universe is the official NSE “Securities available for Equity
segment” CSV. The adapter retains the ordinary main-board `EQ`, `BE`, and `BZ`
series with exact `symbol + series + ISIN` identity. ETF, mutual-fund, REIT,
InvIT, debt, preference-share, warrant, and SME lists are not merged into the
ranking universe. The scope is called **ALL NSE**, never all Indian exchanges.

Official NSE Indices constituent files assign disjoint size labels:

- LARGE — Nifty 100
- MID — Nifty Midcap 150
- SMALL — Nifty Smallcap 250
- MICRO — Nifty Microcap 250
- OTHER NSE — active ordinary equities outside those sets

The four files also provide source classification labels. Only exact,
source-driven labels are used. Stocks without an exact classification remain
`UNCLASSIFIED`, stay searchable, and are excluded from sector-relative ranking.
No company-name inference or fuzzy identity matching is allowed.

## Latest snapshot

The official NSE CM-UDiFF Common Bhavcopy Final provides EOD open, high, low,
close/latest price, previous close, day change, day percentage, volume, traded
value, and transaction count. The website says **Latest Market Snapshot** and
shows trading date, acquisition time, source, and freshness. It never calls the
file a licensed real-time feed. Missing matches remain visible as
`PRICE_UNAVAILABLE`.

## Price histories and models

`marketdata/runners/prepare_live_market.py` uses the existing market-data
policy: Yahoo Finance via `yfinance`, exact `.NS` mapping, `period=max`, daily
interval, `auto_adjust=False`, `repair=True`, and the provider-maintained
adjusted-close series. Cache files are per ticker, writes are atomic, retries
are bounded, and a failed stock cannot abort the market.

Baseline V1 is calculated by the existing unchanged engine only when current
Sector classification, current price validation, and 1/3/5-year history gates
pass. The recorded-high search begins no earlier than the official NSE security
listing date. Scores and ranks remain meaningful only within the current
sector; lower Baseline score is better.

Research V2 is not extrapolated market-wide. The prepared product reuses the
accepted `nse_audited_standalone_fundamentals_v1` result where it exists. All
other stocks remain visible with `FUNDAMENTALS_UNAVAILABLE` or their accepted
specific exclusion reason. No substitute ratios or zero-filled fundamentals
are introduced.

## Prepared bundle and refresh

The ignored `data/live_market/current/` directory contains:

- `live_market.csv` — canonical browsing, snapshot, ranking, and eligibility rows;
- `bundle_manifest.json` — sources, file hashes, counts, failures, dates,
  acquisition timestamps, model coverage, and product fingerprint.

The website never performs acquisition. Refresh from PowerShell, then reload:

```powershell
.\.venv-marketdata\Scripts\python.exe marketdata\runners\prepare_live_market.py
```

Use `--no-download` for a deterministic cache-only rebuild. The manifest
distinguishes universe size, price-ready count, Baseline eligibility, and V2
eligibility, so partial provider coverage is never hidden.

## Scientific and user boundary

LIVE MARKET is research screening, not advice. It offers no buy/sell action,
target price, guaranteed return, portfolio result, or universal cross-sector
rank. RESEARCH LAB continues to show the unchanged frozen protocol, blind
predictions, historical reconstruction, evaluation, and robustness evidence.
