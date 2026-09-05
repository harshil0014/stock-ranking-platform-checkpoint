# Final system status

> Current-count note (2026-08-29): this document records an earlier accepted
> build. The authoritative current cohort definitions and counts are in
> [Authoritative current data status](current_data_status_20260829.md).

## What this system is

`stock-ranking-platform` is an offline-first Indian-equity research website. It maintains a local accepted state from public exchange evidence, exact-identity secondary reference data, cached adjusted histories, and immutable research artifacts. It is research software, not a broker, real-time feed, recommendation service, or investment adviser.

The current accepted market state is dated **2026-08-21**. The website always displays the effective trading date and preparation timestamp. Page navigation never calls a remote provider.

## Data flow and safety

```text
NSE/BSE current files + NSE corporate filings + exact-identity fallbacks
  -> immutable raw evidence and SHA-256 inventory
  -> normalized exchange backbone / adjusted-history cache
  -> validated candidate market and company-fact snapshots
  -> atomic promotion
  -> read-only API and local website
```

An incomplete, structurally invalid, unexpectedly collapsed, or provider-failed candidate cannot replace the accepted state. The prior last-known-good snapshot continues to serve. Refresh runs are locked, resumable where provider work is large, and deterministic from accepted cached evidence.

## Sources and precedence

- Identity and current EOD market data: official NSE equity master and NSE/BSE CM-UDiFF bhavcopies, keyed by exchange identity and ISIN.
- Security-reference audit: the 2026-08-21 NSE MII security file (37,127 rows, 120 fields; SHA-256 `5c5edcfa278d743ee03ccee208bed1abae70d96e61051127cc8094b8f7a54451`) confirms ISIN, listing/status, issued-capital and action metadata. It contains no defensible sector/industry field, so it is not misused as a classification source.
- Size and official sector grouping: official NSE Indices constituent files.
- Financial statements, shareholding, actions, and documents: official NSE integrated/legacy results and XBRLs, Regulation 31 filings, corporate-action catalogues, and announcement/document indexes.
- Adjusted research history and secondary reference facts: exact exchange-symbol mappings through Yahoo/yfinance. These remain visibly secondary and never masquerade as exchange facts.
- Professor workbooks: preserved as supplied reference evidence; their identities, taxonomy, dates, formulas, and ranks remain separate from canonical model data.
- Screener.in: coverage checklist only. Automated collection is policy-disabled.

No name guessing, fuzzy substitution, fabricated value, zero-fill, imputation, or incompatible standalone/consolidated mixing is allowed.

## Classification

Historical research classifications remain frozen. Current browsing and Baseline coverage use `product_classification_v1` with this precedence:

1. `OFFICIAL`
2. independently evidenced primary classification when available
3. `EXACT_IDENTITY_SECONDARY_REFERENCE`
4. `UNCLASSIFIED`

The secondary tier requires a verified exchange symbol/ISIN identity and records provider and as-of date. It is never labelled official. Current-product Baseline rankings use the unchanged Baseline mathematics, but their broader, explicitly labelled universe must not be confused with historical research ranks.

## Models and evidence

- **Baseline V1:** unchanged 1Y return, 3Y CAGR, 5Y CAGR, and recorded/study-period-high recency; within-sector competition ranks; equal-weight mean of ranks.
- **Research V2:** unchanged nine-factor, point-in-time, within-sector weighted method and strict audited standalone evidence contract. Page completeness does not loosen V2 eligibility.
- **Professor Reference:** displayed as reference -> Baseline reproduction -> V2 extension, with disagreement provenance.
- **Historical validation and Quant Lab:** frozen walk-forward outcomes, fingerprints, IC/Rank-IC conventions, independent verification, and negative/inconclusive findings remain unchanged.

Filtering changes displayed rows only. It never recalculates canonical ranks.

## Current measured coverage

Accepted company-fact state contains 5,167 supported identities and 5,164 accepted current prices. Product classification covers 4,433 securities (750 official and 3,683 exact-identity secondary references), leaving 734 explicitly unclassified. Of the secondary tier, 3,346 rows come from the exact bulk bridge: 1,460 canonical NSE `.NS` identities and 1,886 official-code-and-ISIN-confirmed BSE `.BO` identities. Usable cached adjusted history covers 2,159 securities at 1Y, 1,893 at 3Y, and 1,685 at 5Y, including six targeted BSE professor/reference securities. The current-product Baseline ranks 1,237 securities; the frozen strict Research V2 ranks 34.

The bulk bridge fingerprint is `c4ce6b19f96b44544510bf0755309f5d379a12c7be48a48278ec7b2b8093fad0`; the resulting deterministic company-fact fingerprint is `8d678b6a9d7753a0902f5e32a7d1620dab56c59c079e4311db779e4606027932`. Yahoo supplies broad sector only. The BSE code, ISIN, and trading symbol establish BSE identity; they do not turn Yahoo's label into an official BSE four-level taxonomy assignment.

The official/combined fact layer currently exposes 2,242 annual statement issuers, 2,323 quarterly, 2,276 balance sheets, 2,237 cash flows, 2,478 shareholding records, 1,023 corporate-action issuers, and 2,007 annual-report/document links. Explicit EPS/P-E coverage is 2,219/2,211 after the cached XBRL taxonomy rebuild. Secondary reference coverage remains separately labelled.

These are evidence counts, not claims that all fields are comparable for every accounting family. Industrial ROCE and debt/equity are not forced onto banks, NBFCs, or insurers.

## Automatic refresh

The local Windows task is `StockRankingPlatform-WeekdayRefresh`. It runs Monday-Friday at 20:00 local IST and invokes the isolated market-data environment. The pipeline discovers the newest exchange date, avoids promotion when no newer data exists, updates bounded histories and provider backlogs, validates candidate coverage/fingerprints, promotes atomically, and rebuilds company facts.

Status and manual commands from the repository root:

```powershell
Get-ScheduledTask -TaskName StockRankingPlatform-WeekdayRefresh
Get-ScheduledTaskInfo -TaskName StockRankingPlatform-WeekdayRefresh
.\.venv-marketdata\Scripts\python.exe marketdata\runners\refresh_company_data.py --status
.\.venv-marketdata\Scripts\python.exe marketdata\runners\refresh_company_data.py
```

To register or repair the schedule:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File marketdata\scheduling\register_daily_refresh.ps1
```

## Local launch and reproduction

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\stock-ranker.exe website --host 127.0.0.1 --port 8765
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

The server is localhost-only by default. Generated market/provider/research evidence and environments are ignored, while source contracts, parsers, tests, and documentation are reviewable.

## Honest limitations

- Public current EOD reports are automatable; authoritative multi-year exchange archives may be subscription-controlled or exposed through less stable historical-report interfaces. Accepted Yahoo adjusted histories therefore remain necessary for broad corporate-action-aware research history.
- Broad BSE identity/current-price coverage is strong, but free authoritative BSE classification and adjusted-history coverage remain limited. BSE pages retain exact identity and rich evidence when available rather than receiving guessed sectors.
- Exact issuer-level accounting concepts vary across IND-AS, banking, NBFC, and insurance taxonomies. Missing or ambiguous ratios remain explicit.
- One-to-two-trading-day EOD latency is intentional. It is never represented as streaming real time.
- Source outages can delay freshness, but cannot destroy the last-known-good accepted state.
