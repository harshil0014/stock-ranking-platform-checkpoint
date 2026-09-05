# Data Completeness Master Report

## Implemented official-exchange completion update — 22 August 2026

The prior architecture is now backed by a real bulk acquisition rather than a
small parser demonstration. The accepted official batch processed the complete
13,926-row NSE Integrated Filing window and 4,015 linked XBRLs. It raises
official normalized coverage to 2,146 annual statement issuers, 2,269
quarterly/YTD issuers, 2,205 balance sheets, 2,149 cash-flow statements, 2,464
shareholding issuers, 969 company pages with official actions and 2,007 pages
with an annual-report or official document link. Exact measured breakdowns by
full universe, NSE, BSE-only, professor cohort and ranked professor securities
are generated in `data/company_facts/reports/current/primary_secondary_coverage.csv`.

The 257 Yahoo-derived classifications were audited individually. All remain
useful display references but zero satisfied the primary-evidence rule for
ranking-grade derivation. They are labelled
`DERIVED_SECONDARY_REFERENCE_ONLY`; 750 classifications remain official and
4,086 remain unclassified. This is scientifically preferable to silently
turning a vendor label into model membership.

The accepted company-fact fingerprint, official-backbone fingerprint, raw
evidence inventory, Baseline exclusion waterfall and source-separated counts
are in the generated acceptance report. Baseline eligibility remains 568 and
strict Research V2 eligibility remains 34: page completeness improved without
changing either model.

Audit date: 19 August 2026  
Scope: the current `stock-ranking-platform`, its live NSE application universe, the BSE same-day file, the professor-supplied cohort, and the public/legitimate Indian-equity data ecosystem.  
Companion machine-readable matrix: `marketdata/specifications/data_source_matrix.json`

## Executive verdict

## Implemented autonomous slice (19 August 2026)

### Accepted provider-independent fact layer (21 August 2026)

The platform now also builds an immutable ISIN-keyed company-fact snapshot
from accepted local evidence. Snapshot
`02b92da17a629595977a62dace627ca62f4181fc5287926f9c15bc885a9ed522`
contains 5,093 rows and is tied to, but separate from, market bundle
`8a1ef7cd21703b989c33cd439f2147ab823a00b0c6bc76606da0b70de1d8a53b`.
It measures rather than implies coverage: 5,092 prices, 750 official
sector-tier classifications, 2,531 adjusted histories, 2,150/1,883/1,676
usable 1Y/3Y/5Y histories, 46 verified annual-report links, 44 normalized
audited annual facts, 568 Baseline-eligible securities and 34 strict V2
securities. Valuation, normalized quarterly statements, balance sheets, cash
flows and shareholding remain zero until evidence passes their contracts.

Company pages expose all categories with specific statuses and provenance.
Page completeness remains independent of model eligibility. See
`docs/company_information_coverage.md`.

The first production data-state slice is operational. It discovered the newest
official NSE trading date without an uploaded bhavcopy, stored hash-addressed
NSE/BSE evidence, rebuilt a candidate, ran structural/coverage/model/frozen-
evidence gates and atomically promoted bundle
`8a1ef7cd21703b989c33cd439f2147ab823a00b0c6bc76606da0b70de1d8a53b`.
The website now serves 5,093 exact-ISIN securities (2,553 NSE and 2,540
BSE-only traded stocks); 5,092 have a defensible current or latest-prior price.
Of these, 5,082 traded on 19-Aug-2026, three absent NSE quotes were recovered
from the same-day BSE quote by exact ISIN, and seven were recovered from the
official NSE full bhavcopy for 18-Aug-2026. It retained 568
Baseline-eligible stocks and the 34-name audited Research V2 cohort while
recomputing current price-derived V2 inputs through the unchanged engine.

This is **not** full completion of the source matrix. Classification remains
verified for 750 names. Adjusted-history caches now cover 2,531 of 2,553 NSE
identities (99.14%); broad BSE history, XBRL/shareholding and corporate-action
ledger ingestion remain future stages. BSE-only rows are identified and priced, but are intentionally not
classified or ranked until a versioned authoritative taxonomy and defensible
history mapping exist. The system therefore replaces a generic blank with an
exact status, but does not disguise missing evidence as completeness.

Refresh safety is transactional: readers see only the accepted pointer, raw
evidence and snapshots are immutable, repeated identical inputs are
idempotent, malformed/HTML/wrong-date sources are rejected, and a failed or
coverage-collapsed candidate leaves the previous last-known-good state active.
The local website initiates a bounded background check by default; explicit
`stock-ranker refresh`, `--dry-run`, and `--status` commands are also available.

The website can eliminate most generic `Unavailable`, `No data`, blank, and em-dash states, but it cannot truthfully make every security eligible for every model.

The decisive distinction is:

- **Page completeness:** identity, listing status, latest actual trade, basic classification, raw statements, filings, shareholding and source evidence can be made near-total for listed equities with a multi-source exchange-first pipeline.
- **Model eligibility:** a stock listed in 2024 cannot possess five years of public trading history in 2026; a bank or insurer need not have a meaningful industrial ROCE; and an issuer that did not disclose the exact Research V2 ratio cannot be made eligible without changing the accepted research contract.

The present largest gaps are acquisition-scope defects, not evidence that the data does not exist:

| Current application fact | Observed result |
|---|---:|
| NSE ordinary-security application universe | 2,397 |
| Same-day official NSE snapshot rows | 2,393 (99.83%) |
| Classified rows | 750 (31.29%) |
| Unclassified rows | 1,647 (68.71%) |
| Baseline V1 eligible | 567 (23.65% of all; 75.60% of classified) |
| Research V2 eligible | 34 (1.42%) |
| BSE stock rows on the same trade date | 4,939 |
| Unique same-day NSE/BSE traded ISIN union | at least 5,103 |

On that one-day, exactly measured denominator, BSE alone covers 4,939/5,103 (96.79%) of the union, NSE alone covers 2,393/5,103 (46.89%), and the two official files together cover 5,103/5,103 by construction. This is **not** 100% of all listed securities: companies with no trade on either exchange that day are outside that denominator. The companion JSON records every measured numerator, denominator and limitation; unmeasured provider claims are marked `TBD` instead of being converted into invented percentages.

SEBI's July 2026 bulletin reports 5,713 BSE-listed companies and 3,005 NSE-listed companies at 30 June 2026; these exchange totals overlap and must not be added. The same bulletin reports 4,678 BSE companies traded during June. These are population context, not a claim that every listed company traded on the audit date. [SEBI July 2026 bulletin and workbook](https://www.sebi.gov.in/reports-and-statistics/publications/jul-2026/sebi-bulletin-july-2026_103048.html)

The realistic outcome is therefore:

- near-total **truthful identity and descriptive-page coverage**;
- near-total **latest-known trade coverage for securities that have ever traded**, with the actual trade date and staleness shown;
- much higher **sector/basic-industry coverage**, especially on NSE;
- broad **raw financial-statement and shareholding coverage**;
- materially lower **five-year, corporate-action-adjusted and exact Research V2 eligibility**, for scientifically valid reasons.

## Implemented secondary-fact benchmark (22 August 2026)

The isolated Yahoo/yfinance 1.5.1 acquisition now produces hash-validated,
resumable observations, normalized statement facts and corporate-action
records. The full mapped-universe run requested 2,558 securities and retained
576 exact symbol/exchange/EQUITY matches, one rejected identity and 1,981
explicit transient provider failures after Yahoo invalidated its session crumb.
The successful rows added 573 profiles, 542 market caps/share counts, 575
valuation records, 593 annual-primary-or-secondary financial records, 564
quarterly records, 571 balance sheets, 571 cash-flow records, 548 holder
summaries and 450 corporate-action histories. The deterministic corrected
professor-plus-stratified benchmark achieved 345/346 exact identities before
the provider-wide failure.

These facts are marked `SECONDARY_REFERENCE`; official prices,
classifications and audited Research V2 evidence retain precedence. Baseline
eligibility remains 568 and strict V2 eligibility remains 34. The company-fact
fingerprint is
`9abc1fbdc92babe82b6a28fd87a35130efbc7c07498644f6edaacd62c7dd2b7f`.

No accepted Baseline V1 or Research V2 formula, eligibility rule, score, rank, historical cohort, or frozen research artifact was changed by this audit.

## What the repository does today

The current live bundle uses:

1. NSE EQ/BE/BZ securities as the application universe.
2. Four current NSE index constituent files (Nifty 100, Midcap 150, Smallcap 250 and Microcap 250) for sector/size coverage.
3. Official NSE and BSE UDiFF EOD snapshot rows, exact-ISIN cross-exchange
   fallback, and the nearest earlier official NSE full bhavcopy for honest
   latest-prior-trade display.
4. Exact `.NS` Yahoo mappings through `yfinance`, with `auto_adjust=False` and
   `repair=True`, for cached adjusted historical prices across the NSE spine.
5. A rigorously audited but narrow Nifty 50 standalone annual-report contract for current real Research V2 fundamentals.

That explains the gap profile:

- 2,531 of 2,553 NSE histories are now cached. Baseline eligibility remains
  568 because sector-relative ranking still requires an authoritative sector
  and complete anchors; page-history coverage is deliberately separate.
- Classification ends at the index-file boundary, leaving 1,647 names unclassified even though NSE says its four-tier industry structure classifies every listed company and quote pages expose Basic Industry. [NSE industry classification](https://www.nseindia.com/static/products-services/industry-classification)
- Research V2 is available for the 34 issuers that passed the accepted audited-standalone contract; 2,347 other live rows were never taken through an all-market fundamentals pipeline. This is not proof that those companies lack statements.

Ten of the eleven current NSE same-day snapshot gaps were resolved without
symbol guessing: three through same-security BSE quotes and seven through the
immediately prior NSE session. `KALYANI` remains `PRICE_UNAVAILABLE`; the
absence of a validated recent exchange observation is shown rather than
converted to a stale or unrelated number.
- The four same-day snapshot gaps (`BNALTD`, `KALYANI`, `LAKPRE`, `THACKER`) mean “no row in that day's bhavcopy,” not “no security data exists.” Official NSE pages expose a listing/status/latest-trade record for representative cases.

## The non-negotiable identity model

The platform should resolve identity once, then let independent field providers attach evidence to that identity.

Use an effective-dated graph with:

- security key: ISIN plus exchange and exchange security identifier;
- exchange aliases: NSE symbol/series and BSE scrip code/group;
- issuer key: CIN and, where available, LEI;
- effective dates: listing, suspension, relisting, symbol/name change, merger/demerger and delisting;
- relationship types: same security on two exchanges, successor, predecessor, spun-off entitlement and renamed security.

The NSE/BSE common MII security file is the best first spine because its specification covers NSE-listed and BSE-exclusive securities, rather than forcing a fabricated NSE symbol onto a BSE-only company. [NSE MII common master circular](https://nsearchives.nseindia.com/content/circulars/MSD67344.pdf) [current MII master specification](https://nsearchives.nseindia.com/web/mediaattachment/2026-04/NSE-Masters_Data-v1.8_20260428121249.pdf)

Cross-check it with:

- [NSE securities, name changes and symbol changes](https://www.nseindia.com/static/market-data/securities-available-for-trading);
- the [BSE equity security master format](https://www.bseindia.com/markets/MarketInfo/DownloadAttach.aspx?attachedId=e99e2ca5-95d7-4173-83da-7774412bbb2d&id=20220531-44);
- the [SEBI ISIN directory](https://www.sebi.gov.in/isin/isin.html), [NSDL security search](https://nsdl.com/participant/securities-company-search), [NSDL UDiFF files](https://nsdl.com/udiff) and [CDSL securities listing](https://www.cdslindia.com/Investors/Securities-Listing.aspx);
- [MCA company master data](https://data.gov.in/catalog/company-master-data) for CIN, company status and corporate identity. MCA data is released under the [Government Open Data Licence - India](https://ap.data.gov.in/godl), but it is not itself a trading-security master.

Never fuzzy-substitute a company, strip punctuation, or use a current ticker as a historical permanent key.

## Field-by-field source architecture

### 1. Identity, listing and status

| Priority | Source | Use |
|---|---|---|
| Primary | Common MII master + NSE/BSE masters | Exact ISIN, exchange identifiers, names, series/group, security type, listing state/date, face value and issued capital |
| Free fallback | NSDL/CDSL/SEBI ISIN directories | Independent ISIN/security-status confirmation |
| Corporate fallback | MCA master + issuer filing | CIN, company status, incorporation and issuer evidence |
| Paid fallback | Official NSE/BSE master-data product | Contracted systematic production feed and redistribution rights |

The result should distinguish `ACTIVE`, `SUSPENDED`, `DELISTED`, `PERMITTED_TO_TRADE`, `SME`, `ETF`, `REIT/INVIT`, partly paid and ordinary equity. It should not collapse all instruments into “stock.”

### 2. Latest/EOD price and trading activity

Primary sources are the official NSE and BSE UDiFF bhavcopies. The BSE file already raises the audited one-date stock coverage from 2,393 NSE rows to a 5,103-ISIN lower-bound union. SEBI curates the official exchange price/volume and historical links. [SEBI equity cash-market source directory](https://www.sebi.gov.in/curation/equity_cash_market.html)

Fallback order:

1. same-date primary-listing exchange UDiFF;
2. same-date other-exchange quote for the identical ISIN, labelled with that exchange;
3. latest official trade on or before the requested date, with actual trade date and age;
4. contracted authorized vendor or authenticated broker source;
5. precise terminal status.

The UI must separate:

- `NO_TRADE_ON_SNAPSHOT_DATE` — security exists but did not trade that day;
- `LATEST_TRADE_STALE` — last trade is older than a stated threshold;
- `SUSPENDED` or `DELISTED`;
- `NEVER_TRADED`;
- `SOURCE_TEMPORARILY_UNAVAILABLE` — acquisition failed, not a security fact.

Do not call EOD or delayed data live/streaming. If true live display becomes necessary, use an exchange agreement or an authorized vendor. NSE itself says real-time data may be taken directly or from an authorized vendor. [NSE real-time data subscription](https://www.nseindia.com/static/market-data/real-time-data-subscription)

### 3. Raw historical prices, volume and liquidity

Use exchange raw data first:

- [NSE all reports](https://www.nseindia.com/all-reports) and [paid EOD/historical data](https://www.nseindia.com/static/market-data/eod-historical-data-subscription);
- [BSE security price history](https://www.bseindia.com/markets/equity/EQReports/StockPrcHistori.aspx?flag=0);
- locally retained daily UDiFF files, each hashed and dated.

Weekly and monthly bars should be deterministic resamples of accepted daily bars, not independently mixed vendor series. Delivery percentage, turnover, trade count and zero-trade days remain distinct liquidity fields.

Cheap authenticated fallbacks exist, but their terms and adjustment semantics matter:

- Upstox V3 documents daily history from January 2000, with up to a decade per request. [Upstox historical candles V3](https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/)
- DhanHQ covers NSE/BSE/MCX and documents 100,000 data requests/day. [DhanHQ API limits](https://dhanhq.co/docs/v2/) [Dhan historical data](https://dhanhq.co/docs/v2/historical-data/)
- Zerodha Kite Connect provides historical candles and live data for ₹500/month per app, but requires an active trading account. [Kite pricing](https://support.zerodha.com/category/trading-and-markets/general-kite-api/articles/what-are-the-charges-for-kite-apis) [Kite historical API](https://kite.trade/docs/connect/v3/historical/)

These are inexpensive internal-validation sources, not presumed public-redistribution licences.

### 4. Adjusted prices, returns, CAGR, volatility, drawdown and ATH

Maintain three non-interchangeable objects:

1. `exchange_raw_close` — official traded close;
2. `split_adjusted_close` — price-continuity series;
3. `total_return_adjusted_close` — distributions reinvested under a documented convention.

Every computed return/CAGR/volatility/drawdown record must identify which object it used. Price ATH should state whether it is raw price, split-adjusted price, or total-return index; these answer different questions. `ath_date` remains the recorded/study-period high date and is a true all-time high only when the retained series spans the security's complete valid history.

Construct a corporate-action evidence ledger from:

- [NSE corporate actions](https://www.nseindia.com/companies-listing/corporate-filings-actions);
- BSE corporate actions and announcements;
- NSDL UDiFF corporate actions;
- the issuer's scheme/circular for a merger or demerger.

Simple splits/bonuses can eventually use a separately reviewed adjustment engine. Rights issues, demergers, mergers, special distributions and successor histories require action-specific adjudication. A blank corporate-action response is not proof that no action occurred.

Yahoo/yfinance can remain a research cross-check—the project obtained all 750 targeted series—but it is not an independent official source, its endpoints/terms are unsuitable as a public-product foundation, and inherited pre-listing history has already caused a real BAJAJFINSV defect. A listing/security-history boundary must come from official evidence.

For paid adjusted data, Global Datafeeds is the strongest India-specific candidate: it represents itself as an authorized NSE/BSE vendor and documents split-adjusted history, but dividend-total-return semantics and every hard ISIN must pass a trial. [Global Datafeeds](https://globaldatafeeds.in/) [history API](https://globaldatafeeds.in/global-datafeeds-apis/global-datafeeds-apis/rest-api-documentation/function-gethistory/)

### 5. Sector, industry and peers

NSE states that every listed company is classified in a four-tier structure: macro-economic sector, sector, industry and basic industry, reviewed annually and based primarily on audited consolidated revenue. [NSE industry classification](https://www.nseindia.com/static/products-services/industry-classification)

Recommended policy:

- acquire the official Basic Industry for all NSE securities;
- store the hierarchy version/effective date;
- derive upper tiers only through that official versioned hierarchy;
- obtain a BSE classification feed or preserve BSE's own taxonomy for BSE-only names;
- use issuer/MCA business activity only as provenance or a separately labelled fallback taxonomy;
- define peers within one stated taxonomy/version and never mix peer systems silently.

This is the single highest-return completeness improvement: it targets 1,647 current unclassified rows. It also prevents the present index-membership proxy from incorrectly implying that everything outside Nifty 100/150/250/250 is “small cap.”

### 6. Market capitalisation, share count and size

NSE quote pages expose total and free-float market capitalisation, face value, listing date, status and Basic Industry. The MII/security master can provide issued capital, while share-capital and Regulation 31 filings provide denominator evidence.

Store separately:

- authorised capital;
- issued capital;
- paid-up capital;
- shares outstanding;
- free-float shares/IWF;
- total market cap;
- free-float market cap;
- value date and price exchange.

Never multiply today's price by a stale or differently defined share count. Size is a dated classification. If the product means Nifty 100/Midcap 150/Smallcap 250/Microcap 250 membership, say so. If it means market-cap percentile, preregister and version that independent definition.

Comprehensive historical index constituent data is a licensed NSE Indices product containing identifiers, market capitalisation, weights and prices. [NSE Indices data subscription](https://www.nseindia.com/static/nse-indices/index-data-subscription)

### 7. Financial statements and valuation inputs

The best free evidence is issuer-filed, taxonomy-aware data:

1. NSE Regulation 33 XBRL/iXBRL;
2. BSE financial-result/XBRL copy for BSE-only or dual-listed fallback;
3. exact exchange-filed annual report;
4. issuer investor-relations document;
5. MCA public document;
6. sector regulator for banks/insurers;
7. licensed fundamentals vendor.

NSE publishes distinct taxonomies/templates for Ind AS issuers, banks, NBFCs and insurers; one flat tag dictionary is not sufficient. [NSE XBRL taxonomy and filing information](https://www.nseindia.com/static/companies-listing/xbrl-information) SEBI curates both exchange financial-results and shareholding sources. [SEBI corporate-filings directory](https://www.sebi.gov.in/curation/corporate_filings.html)

Each fact must carry:

- issuer/security identity;
- source document URL and SHA-256;
- filing/available timestamp;
- period start/end and annual/quarterly duration;
- instant vs duration context;
- currency, scale and unit;
- standalone vs consolidated basis;
- audited/reviewed status;
- original taxonomy concept and label;
- revision/restatement lineage;
- extraction method and confidence.

Revenue, PAT, EPS, book value, debt, equity, cash flow and margins can then be displayed broadly. EBITDA/operating profit and free cash flow require a published definition or a versioned derivation contract—never a vendor label stripped of definition.

ROE, ROCE, debt-to-equity and growth rates should prefer an explicit issuer-disclosed value with formula. A derived value must be labelled `DERIVED`, name its numerator/denominator/averaging convention and cannot silently enter the accepted Research V2 contract.

Valuation ratios require aligned dates:

- P/E: same-date price divided by trailing/forward EPS with basis and period;
- P/B: same-date price and per-share book value with share-count basis;
- EV/EBITDA: enterprise-value date, debt/cash definitions and EBITDA convention;
- dividend yield: declared/paid window and price date.

If these are not aligned, show source components instead of a deceptively precise ratio.

### 8. Banks, NBFCs and insurers

Do not remove blanks by forcing industrial-company ratios onto financial institutions.

- RBI DBIE provides bank annual accounts, profitability, asset quality and performance indicators. [RBI DBIE](https://dbieold.rbi.org.in/DBIE/) [RBI bank-data guide](https://www.rbi.org.in/Scripts/bs_viewcontent.aspx?Id=624)
- IRDAI's public-disclosure regime requires insurer balance sheets, revenue accounts, P&L, analytical ratios and specified annual five-year disclosures on insurer websites. [IRDAI public-disclosure requirements](https://irdai.gov.in/document-detail?documentId=374643)
- NBFC financial results use a dedicated taxonomy; leverage must retain the reporting definition.

Use sector-specific page cards (net interest margin, GNPA/NNPA, capital adequacy for banks; solvency, premium, claims and persistency where applicable for insurers). For a conventional ROCE field, `NOT_APPLICABLE_TO_BANKING_TAXONOMY` is better data than a fabricated number.

### 9. Shareholding and ownership

Use NSE/BSE Regulation 31 shareholding XBRL as primary evidence for promoter, public and institutional categories, pledged shares and total shares. Preserve quarter, filing timestamp, denominator, category taxonomy and revisions. An FPI/MF/insurance comparison across time is invalid if categories changed without a crosswalk.

Issuer annual reports and depository evidence are fallbacks; aggregator percentages are validation aids only unless their source filing and basis are supplied.

### 10. Annual reports and hard PDF extraction

Evidence ladder:

1. structured XBRL/iXBRL fact;
2. alternate exchange's identical structured filing;
3. exchange-filed text PDF;
4. issuer-hosted identical annual report;
5. OCR plus table extraction;
6. MCA public document;
7. archived official/issuer copy with original URL, archive timestamp and hash.

Use [Arelle](https://github.com/Arelle/Arelle) as the preferred Apache-2.0 XBRL/iXBRL processor. For PDFs, [Docling](https://github.com/docling-project/docling), [Camelot](https://github.com/camelot-dev/camelot), [pdfplumber](https://github.com/jsvine/pdfplumber) and OCRmyPDF/Tesseract are mature extraction components, not evidence providers. Every accepted PDF fact still needs page/table/label/period/unit checks. Extraction confidence must never manufacture acceptance.

### 11. Historical point-in-time research

The production display pipeline and historical research pipeline should share identity/provenance code but not data-selection semantics.

For every ranking date:

- load the security master and universe effective on that date;
- load the then-effective sector classification;
- use only filings with `available_date <= ranking_date`;
- preserve later revisions without back-propagating them;
- use the actual historical index membership, not today's survivors;
- keep labels/outcomes physically separate until predictions are frozen.

NSE Indices offers historical constituent data by subscription; public historical index values alone are not enough to reconstruct constituent membership. [NSE Indices subscription](https://www.nseindia.com/static/nse-indices/index-data-subscription) Internet Archive-style copies may recover a missing official file but are opportunistic, not a complete source; store original URL, archive timestamp and hash.

## Difficult-security cross-checks

| Case | Finding | Required behavior |
|---|---|---|
| `BNALTD` | Official NSE quote identifies it as permitted to trade, lists Basic Industry Tea & Coffee and a 20 Apr 2026 listing; a prior quote was visible even though the 7 Aug bhavcopy row was absent. | `NO_TRADE_ON_SNAPSHOT_DATE`; show last actual trade/date, classification and short-history reason. [NSE quote](https://www.nseindia.com/get-quote/equity/BNALTD/B-%26-A-Limited) |
| `THACKER` | Official NSE quote identifies permitted-to-trade status and Basic Industry Other Financial Services. | Same latest-trade fallback; do not call the stale price current. [NSE quote](https://www.nseindia.com/get-quote/equity/THACKER/Thacker-%26-Company-Limited) |
| `LAKPRE` | Official quote records listing 26 Sep 2006 and Basic Industry Auto Components. | History/source acquisition issue is distinct from listing-age insufficiency. [NSE quote](https://www.nseindia.com/get-quotes/equity?symbol=LAKPRE) |
| `KALYANI` | Official filings exist but the same-day bhavcopy has no row. | Resolve official identity/status, then latest trade; if none, say precisely why. |
| `JIOFIN` | Official NSE listing date is 21 Aug 2023. | Three- and five-year model anchors in Aug 2026 are physically impossible; retain `INSUFFICIENT_3Y_HISTORY`. [NSE quote](https://www.nseindia.com/get-quote/equity/JIOFIN/Jio-Financial-Services-Limited) |
| `SAILIFE` | Official listing circular establishes it as a new listing. | No donor/pre-listing history; show exact horizon shortfall. [NSE listing circular](https://nsearchives.nseindia.com/content/circulars/CML65628.pdf) |
| `GVT&D` and `M&M` | Official symbols contain ampersands and exact ISINs. | URL-encode exact symbols; never normalize punctuation into a guessed ticker. [GVT&D quote](https://www.nseindia.com/get-quote/equity/GVT%26D/GE-Vernova-T%26D-India-Limited) [M&M quote](https://www.nseindia.com/get-quotes/equity?symbol=M%26M) |
| `DELTON` | BSE-only identity resolved exactly as scrip `504240`; official BSE close ₹459.90 on 7 Aug 2026 and five years of raw BSE history were retrieved. | Use BSE identifier/ISIN and raw BSE data; do not invent an NSE symbol or call raw history total-return adjusted. |
| `BAJAJFINSV` | Yahoo supplied pre-listing observations; NSE listing boundary is 26 May 2008. | Truncate valid security history at authoritative listing boundary; never accept donor history merely because a provider returns it. |
| `HDFCBANK` / `SBILIFE` | Banking/insurance taxonomies differ materially from Ind AS industrial statements. | Show regulator-specific facts; do not fabricate conventional ROCE/debt fields to gain V2 eligibility. |

The 99-name professor cohort provided an additional hard-case audit: all 99 identities/current prices were resolved (91 NSE and eight BSE-only), but only 53 had the current index-based classification and only 38 were Baseline eligible. That confirms price resolution is already tractable; classification, adjustment evidence and legitimate listing horizons are the limiting layers.

## Open-source components worth reusing

| Component | Reuse | Important boundary |
|---|---|---|
| Arelle | XBRL/iXBRL parse, contexts, units, taxonomy validation | Processor, not data; keep raw filing and taxonomy version |
| nselib | Convenience access to NSE public reports | Wrapper around NSE, not an independent source; endpoint/licence risks remain |
| jugaad-data | NSE/BSE/RBI download helpers and UDiFF support | Wrapper, not independent evidence; pin and inspect each endpoint |
| BseIndiaApi / bseindia wrappers | Candidate BSE endpoint adapters | Unofficial wrappers; inspect licence, tests and endpoint drift before adoption |
| Docling | Modern PDF layout/table/OCR extraction | Candidate facts require deterministic evidence validation |
| Camelot | Extract tables from text PDFs and expose extraction quality | Does not solve scanned PDFs or semantic fact selection by itself |
| pdfplumber | Text, coordinates and table primitives | Low-level parser; project must implement evidence checks |
| OCRmyPDF + Tesseract | Add/search OCR text layer to scans | OCR errors remain possible; never accept ratios without page/cell validation |

Do not adopt a package merely because it calls itself an NSE API. Trace every wrapper to its real upstream. Multiple packages that scrape the same NSE endpoint are one source dependency, not redundancy.

## Candidate paid fallbacks and the minimal-cost path

Paid data is justified only after a frozen hard-case bake-off and a licence review.

### Lowest-cost internal validation

- **Zerodha Kite Connect:** ₹500/month per app for historical plus live data, with an active Zerodha account. Good for independent candle checks; public-product redistribution is not granted by the retail subscription. [Official pricing](https://support.zerodha.com/category/trading-and-markets/general-kite-api/articles/what-are-the-charges-for-kite-apis)
- **Upstox or Dhan:** authenticated broker APIs with deep documented candle history/large data limits. Good for exact-ISIN coverage tests; obtain written use/redistribution permission before product display.

### Best India-specific production candidate

- **Global Datafeeds:** authorized NSE/BSE vendor with price, historical and fundamental APIs. Request a narrow EOD/historical/corporate-data quote and a redistribution clause, then test every frozen hard case. Its documentation warns that some corporate endpoints expose only short windows, so it is not automatically a historical point-in-time fundamentals solution. [Data availability](https://globaldatafeeds.in/global-datafeeds-apis/global-datafeeds-apis/introduction/type-of-data-available/)
- **TrueData:** credible authorized alternative. API costs/rights require a quote; do not cite the public desktop subscription as API/redistribution pricing. [TrueData APIs](https://www.truedata.in/market-data-apis) [public pricing](https://www.truedata.in/price)

### Low-cost global candidates, conditional

- **Twelve Data:** lists XNSE and XBOM EOD on its Grow tier; test Indian ISIN, delisted-history, actions and statements before adoption. Personal pricing is not a production licence. [Exchange coverage](https://twelvedata.com/exchanges?level=pro) [pricing](https://twelvedata.com/pricing)
- **EODHD:** inexpensive global EOD/fundamental plans, but commercial/internal use and redistribution use separate pricing. India coverage and statement quality need a trial. [API overview](https://eodhd.com/financial-apis/quick-start-with-our-financial-data-apis) [commercial pricing](https://eodhd.com/commercial-pricing)

### Authoritative but not cheap

Direct NSE/BSE EOD, historical, corporate, master and index products are the legal/lineage gold standard for a public commercial website. NSE's current policy requires a relevant agreement and sets separate commercial terms; its tariffs distinguish display medium and use. [NSE data policy](https://www.nseindia.com/static/market-data/nse-data-policy) [NSE products/tariff](https://www.nseindia.com/static/market-data/products-tariff) BSE likewise offers a formal API/feed portal and tariff. [BSE market-data portal](https://marketdata.bseindia.com/) [BSE tariff](https://www.bseindia.com/downloads1/Information_Products_Pricing_Sheet.pdf)

For normalized Indian fundamentals and long-history research, **CMIE Prowess**, **Capitaline** and **ACE Equity** are serious commercial bake-off candidates rather than last-mile retail scrapes. CMIE says ProwessIQ covers about 50,000 companies, all NSE/BSE-traded companies, more than 3,500 fields and time series from 1989. [CMIE ProwessIQ](https://www.cmie.com/kommon/bin/sr.php?kall=wproducts&portal_code=030010010100000000000000000000000000000000000&prd=prowessiq&tabno=7010) The last public CMIE price located in this audit was ₹180,000/year for ProwessIQ effective January 2023, so a current research/bulk/API/redistribution quote is mandatory. [CMIE published 2023 prices](https://cmie.com/kommon/bin/sr.php?dt=20221027153401&kall=warticle&msec=066) Capitaline states coverage above 35,000 listed and unlisted companies, normalized statements, shareholding, actions and more than ten years of financials. [Capitaline](https://capitaline.com/Index.aspx) ACE Equity is another India-focused candidate, but pricing/API/point-in-time rights require a direct quote. [ACE Equity Nxt](https://www.aceequitynxt.com/)

These databases may be the most defensible paid solution for historical normalized fundamentals, but they are not automatically the cheapest production API. Test exact ISIN coverage, original-source lineage, standalone/consolidated basis, restatements, `available_date`, delisted names and redistribution rights. Screener.in is useful for human cross-checks and premium CSV exports but officially offers no API, so scraping it is not a production data architecture. [Screener export documentation](https://support.screener.in/article/28-export-screen-results)

The cheapest defensible route is not “buy a terminal.” It is:

1. free official exchange/depository/SEBI/MCA/regulator data for offline research and linked provenance;
2. a narrowly scoped broker API for internal cross-checking only;
3. one authorized India vendor for the remaining price/history gaps and production display rights;
4. per-document MCA purchases only for missing high-value issuer filings;
5. a broader licensed fundamentals/point-in-time product only if measured failures justify it.

## Legal and redistribution boundary

This is a data-engineering audit, not legal advice. Before public deployment, maintain a rights register per field/source/use:

- internal research/cache;
- derived metric display;
- raw value display;
- bulk download/export;
- redistribution to third parties;
- historical retention;
- attribution and document-link requirements.

NSE explicitly requires an agreement for subscribers and treats commercial access/dissemination under its Data Sharing and Usage Policy. Public accessibility is not permission to republish a full feed. Broker credentials likewise do not confer redistribution rights. Issuer filings should generally be linked and cited with extracted facts; do not assume the right to mirror every PDF.

The OGD/MCA master is the notable open-data exception, subject to GODL attribution. Open-source parser licences govern software reuse, not the rights in the documents they parse.

## Target architecture

```text
raw immutable acquisition
  exchange/depository/MCA/issuer/vendor objects + URL + retrieval time + hash
                         |
effective-dated identity spine (ISIN/security/exchange/CIN/aliases/actions)
                         |
field evidence store
  value + unit + period + available_date + basis + taxonomy + source + confidence
                         |
field-specific resolver
  primary -> free fallback -> second fallback -> licensed fallback -> precise reason
                         |
canonical views
  quote | price history | statements | shareholding | evidence | model inputs
                         |
models (unchanged contracts) and website
  value, freshness, source, basis, explanation; never silent substitution
```

Resolver rules:

1. A higher-priority source does not overwrite a lower source without preserving both observations and the selection reason.
2. Conflicting official sources create `SOURCE_CONFLICT`, not an arbitrary winner.
3. A stale value may be displayed when safe, but its as-of date and stale badge are mandatory.
4. Missing is field-specific. One failed annual-report ratio must not blank the price, shareholding or raw statement page.
5. Display completeness and scoring eligibility are independent.
6. Every acquisition is reproducible from an immutable raw object, parser/config version and canonical fingerprint.

## Precise terminal states instead of generic blanks

The UI should render an explanation card even when there is no number:

- `5-year history impossible: listed 21 Aug 2023`;
- `No trade on 7 Aug 2026; latest official trade 30 Jun 2026`;
- `Security suspended by BSE; last official close retained for history only`;
- `Explicit ROCE not disclosed in the audited standalone FY2025-26 report`;
- `ROCE not applicable under the banking/insurance model taxonomy`;
- `Annual report found; table extraction failed on scanned pages 142–145`;
- `Corporate action unresolved: demerger allocation requires issuer scheme review`;
- `Historical sector unavailable for this ranking date; excluded to prevent look-ahead`;
- `Value withheld from public display: source licence does not permit redistribution`.

These states improve the page rather than hide scientific limitations.

## Prioritized implementation programme

### Phase 0 — rights and measurement

- freeze the current 2,397 NSE and 5,103 one-day union audits;
- create the source-rights register;
- define active, listed, traded, suspended and delisted denominators;
- build a hard-case fixture covering the securities above plus bank, insurer, NBFC, SME, BSE-only, renamed and demerged cases.

### Phase 1 — identity and price (largest immediate user benefit)

- ingest MII/NSE/BSE masters and alias changes;
- ingest both UDiFF files;
- add latest-official-trade fallback with age;
- expose NSE and BSE quotes separately for dual listings;
- audit daily coverage and exact reason counts.

### Phase 2 — classification and page facts

- acquire Basic Industry across NSE;
- version the official hierarchy;
- obtain BSE taxonomy coverage or preserve an explicitly different BSE taxonomy;
- add official listing/status, market cap, face value and 52-week fields;
- never label all residual names small-cap.

### Phase 3 — history and actions

- archive daily UDiFF/raw history;
- build action/identity ledger;
- enforce official listing/history boundaries;
- retain Yahoo only as a test oracle/fallback while trialling an authorized adjusted-history vendor;
- quarantine complex reorganisations.

### Phase 4 — filings, statements and ownership

- use Arelle across every NSE/BSE taxonomy family;
- ingest Regulation 31 shareholding;
- add issuer/cross-exchange/MCA document fallbacks;
- expose raw facts broadly while preserving strict Research V2 input acceptance.

### Phase 5 — sector-specific pages and historical research

- bank/NBFC/insurer fact cards;
- historical effective-dated masters/classifications/constituents;
- point-in-time filing availability and revision store;
- paid historical constituent/fundamental data only where coverage measurement proves necessary.

## Acceptance metrics for the future implementation

Publish these daily/quarterly; do not claim 100% without measuring the denominator:

- unique listed ISIN coverage by exchange/status;
- same-day price coverage and latest-trade coverage by age bucket;
- identity conflicts and unresolved aliases;
- four-tier classification coverage by exchange;
- raw-history start/end, gaps and valid 1Y/3Y/5Y availability;
- corporate-action verified/unresolved counts;
- statement-document availability and structured-fact coverage by taxonomy;
- PDF extraction and human-adjudication rates;
- shareholding coverage by quarter;
- model-eligible counts separated from descriptive-page coverage;
- point-in-time available-date coverage per historical ranking date;
- source licence status for every publicly displayed field.

Run a periodic source bake-off on a frozen set and record exact-ISIN coverage, values, dates, action handling, latency, failure rate, licence and cost. Marketing claims never substitute for that audit.

## Single-source dependencies to remove

1. Current NSE-only universe: add BSE/MII identity union.
2. NSE same-day bhavcopy for “current” price: add BSE same-day and latest official trade.
3. Four index files for all classification: add official Basic Industry/hierarchy and BSE taxonomy.
4. Yahoo for adjusted history: add official raw/actions plus a contractually verified adjusted source.
5. One annual-report location/parser: add structured XBRL, dual-exchange, issuer, OCR and MCA ladder.
6. Today's index constituents for historical research: acquire effective-dated historical constituent data.
7. One industrial ratio schema for all issuers: use taxonomy-specific financial-company views.

## Final assessment

**Data-completeness architecture: PASS, with licensing and measured-ingestion work still required.** The public ecosystem contains enough authoritative evidence to make ordinary company pages richly populated for most Indian listed securities. The present application has already demonstrated exact identity/current-price resolution for a difficult 99-security cohort and 99.83% same-day NSE snapshot coverage.

**Literal universal numeric completeness: impossible and scientifically undesirable.** New listings cannot have long history, no-trade/suspension periods have no same-day price, some issuer ratios are undisclosed or inapplicable, difficult corporate actions can prevent defensible adjusted histories, historical constituents may require licensed archives, and public redistribution may require paid rights.

The correct product objective is therefore **near-total truthful coverage**, not “100% numbers”: retrieve every legitimate field through an explicit fallback ladder, retain provenance and dates, and replace every remaining generic blank with the exact reason the evidence cannot support a value.
