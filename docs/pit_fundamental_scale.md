# PIT-safe fundamental scale readiness

## What changed

The platform now separates three stages that were previously easy to conflate:

1. **Complete population discovery** finds every exact-ISIN NSE security that is
   Baseline-ready but lacks strict Research V2 fundamentals.
2. **Metadata-only annual-report discovery** checks official NSE filing metadata
   for the whole population without downloading thousands of PDFs.
3. **Bounded evidence batches** download only a deterministic, sector-diverse
   review batch from frozen metadata. A report candidate is never promoted into
   Research V2 automatically.

This preserves `nse_audited_standalone_fundamentals_v1`: exact identity, direct
audited standalone ROCE and debt-equity disclosure, comparable current/prior
annual profit, period end, and an exchange dissemination timestamp are still
mandatory. No formula, proxy, imputation, or financial-sector reinterpretation
was added.

## Full-population result at 21 August 2026

The accepted company-fact snapshot contains **1,198** exact-ISIN NSE securities
that are Baseline-ready and not V2-eligible, across 30 sectors.

| Gate | Securities |
|---|---:|
| Official FY2025-26 report available by cutoff | 640 |
| Non-financial standard-probe population | 1,051 |
| Non-financial report available by cutoff | 541 |
| Financial-services review population | 147 |
| Financial-services report available | 99 |
| No eligible FY2025-26 report by cutoff | 558 |

The 541 non-financial reports are the defensible immediate scale ceiling before
document-level evidence review. Financial-services issuers remain a distinct
economic-applicability review; conventional ROCE and leverage are not forced on
them merely to raise coverage.

An independent BSE announcement fallback was tested on 50 deterministic
NSE-no-report securities. Exact active BSE ISIN mappings existed broadly
(1,128/1,198 across the population), but 49/50 probe securities had no annual-
report announcement in the same window. The only mention was a shareholder
letter referring to the annual report, which remains attachment-review evidence
rather than a report or accepted fact. BSE is therefore retained as a useful
edge fallback, not presented as a bulk replacement for missing NSE filings.

### Bounded 250-report evidence run

All 250 selected official reports downloaded successfully from the frozen NSE
metadata. The pypdf 6.15.0 audit extracted 237; 13 malformed-cross-reference
PDFs remain explicit extraction failures after strict and lenient parsing. One
pathological report required more than five minutes but completed inside the
fixed 15-minute ceiling. Of the complete bounded batch:

| Evidence gate | Securities |
|---|---:|
| PDF extracted | 237 |
| Exact current ISIN proven in extracted report text | 197 |
| ROCE locator present | 227 |
| Debt-equity locator present | 235 |
| Profit locator present | 233 |
| Exact ISIN plus all three disclosure locators | **187** |
| Accepted automatically | **0** |

The remaining packet statuses are 40 reports without the exact current ISIN in
extractable text, seven missing ROCE, two missing profit, one missing both ROCE
and debt-equity, and 13 extraction failures. The 187 complete packets reduce
review from whole-document searching to hash-anchored pages and snippets. Their
numeric tokens remain explicitly untrusted search aids. The packet fingerprint
is `215553eb9c802fa2f819e3a84937de453648b1356b8b8d19ab9468cefd3b97f3`.

This is sufficient to recommend scaling independent accounting review in
bounded queues. It is not evidence that all 187 will pass standalone basis,
unit, period, formula, comparable-profit, and leverage checks. The prior fixed
14-report validation yielded 13 complete direct disclosures and 12 records
usable under unchanged V2 numeric rules, which is encouraging validation—not a
license to auto-promote the new queue.

## Historical availability boundary

The same official metadata was audited against the frozen walk-forward dates.
Only a real `disseminationDateTime` on or before the cutoff counts. Date-looking
archive filenames do not count as availability evidence.

| Ranking date | Explicitly timed reports | Non-financial standard probes | Reports present but timestamp unresolved |
|---|---:|---:|---:|
| 2022-08-05 | 50 | 41 | 1,085 |
| 2023-08-07 | 60 | 50 | 1,087 |
| 2024-08-07 | 284 | 240 | 889 |
| 2025-08-07 | 523 | 434 | 652 |
| 2026-08-21 | 640 | 541 | 3 |

This is a current-universe readiness audit, not a historical-universe cohort and
not an outcome evaluation. Older missing timestamps can only be rescued with an
exact official announcement attachment and its exchange dissemination time—the
existing walk-forward rescue rule—not by guessing from a PDF or URL.

## Identity continuity

Official NSE symbol and company-name change files are now normalized into exact
transition evidence. The first full run found 491 symbol transitions and 553
name transitions covering 698 current NSE securities. Corporate-action rows
also exposed 227 historical-ISIN candidates. Those candidates are quarantined
for review: **zero price histories were automatically spliced across an ISIN
change**. This prevents a rename helper from becoming an unreviewed corporate-
reorganization assumption.

Primary evidence:

- [NSE annual-report filings](https://www.nseindia.com/companies-listing/corporate-filings-annual-reports)
- [NSE securities and official name/symbol change files](https://www.nseindia.com/static/market-data/securities-available-for-trading)
- [MCA Schedule III ratio-disclosure amendment](https://www.mca.gov.in/Ministry/pdf/ScheduleIIIAmendmentNotification_24032021.pdf)

## Operational boundary and next scale gate

Generated PDFs, extracted text, metadata matrices, and identity ledgers remain
ignored evidence. The current 34-stock frozen V2 cohort and all historical
research fingerprints remain unchanged. Scaling should proceed in bounded
batches, requiring deterministic extraction, exact ISIN-in-document evidence,
standalone-basis adjudication, direct ratio labels/values/formulas, comparable
profit periods, and an independent review decision. Only reviewed records may
enter a newly versioned current-data snapshot; frozen experiments never advance
because a current filing arrives.
