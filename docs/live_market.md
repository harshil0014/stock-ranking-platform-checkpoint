# LIVE MARKET product data contract

LIVE MARKET is a changing current product snapshot. It is deliberately
separate from the frozen, reproducible RESEARCH LAB.

## Universe and identity

The NSE spine is the official “Securities available for Equity segment” CSV.
The `listed_ordinary_company_equity_v1` contract retains `EQ`, `BE`, and `BZ`
only when the security also has a company-issued (`INE`) ISIN with NSDL
security code `01` (equity) and is not an explicit DVR/alternate class. Series
alone is deliberately insufficient because NSE documents that ETFs can trade
in `EQ`.

The official BSE CM-UDiFF stock file is subjected to the same ISIN contract
before it can add a BSE-only security. A dual-listed ISIN remains one canonical
security and a BSE-only company uses `BSE-<scrip code>` rather than an invented
NSE symbol. Mutual funds/ETFs, government and debt instruments, preference and
other non-equity company securities, REIT/InvIT/trust units, rights
entitlements, and alternate security classes are excluded. Every rejection is
written to `ranking_universe_exclusions.csv` with a deterministic reason code;
every retained row carries the contract version and `ELIGIBLE_ORDINARY_EQUITY`.
This is a ranking universe of listed ordinary company shares—not a claim to
include every exchange instrument, suspended/delisted company, or SME issue.

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

Official NSE and BSE CM-UDiFF bhavcopies provide EOD open, high, low,
close/latest price, previous close, day change, day percentage, volume and
other exchange fields where supplied. The website says **Latest Market Snapshot** and
shows trading date, acquisition time, source, and freshness. It never calls the
file a licensed real-time feed. An absent NSE same-day row may use a same-day
BSE quote only after exact ISIN identity, or the nearest earlier official NSE
full-bhavcopy row after exact symbol and series identity. The row retains its
actual exchange, source and trade date. Remaining gaps stay
`PRICE_UNAVAILABLE`; these display fallbacks do not enter NSE Baseline scoring.

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

The ignored `data/live_market/` state store contains:

- `accepted_state.json` — atomic pointer to the last accepted snapshot;
- `snapshots/<date>-<fingerprint>/` — immutable canonical bundle and manifest;
- `evidence/raw/<provider>/<date>/` — immutable source bytes;
- `staging/` — candidates that cannot be served until every gate passes;
- `last_refresh_attempt.json` — accepted, rejected, failed, or no-new-data result.

The local website starts a bounded isolated refresh check by default while
serving the accepted state immediately. Disable it with `--no-auto-refresh`.
Run the same operation explicitly with:

```powershell
.\.venv\Scripts\stock-ranker.exe refresh
```

Discovery probes recent weekdays for a validated official NSE bhavcopy, then
acquires the corresponding current identity/classification inputs, optional
BSE bhavcopy and nearest earlier NSE full bhavcopy. Downloads are rejected before storage when they are truncated,
HTML, wrong-date or wrong-schema. Promotion requires identity uniqueness,
price coverage of at least 90%, non-collapsed classification and model
eligibility, consistent dates and unchanged frozen V2 evidence. An outage or
rejected candidate leaves the previous pointer untouched. Repeated identical
refreshes are idempotent.

## Scientific and user boundary

LIVE MARKET is research screening, not advice. It offers no buy/sell action,
target price, guaranteed return, portfolio result, or universal cross-sector
rank. RESEARCH LAB continues to show the unchanged frozen protocol, blind
predictions, historical reconstruction, evaluation, and robustness evidence.
