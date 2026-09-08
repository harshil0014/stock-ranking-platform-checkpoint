# Current-product completeness recovery — 8 September 2026

## Scope and acceptance boundary

This is a current-product integration/recovery pass, not a change to scientific
methodology. No Screener scraping, synthetic values, new accounting derivations,
PIT promotions, or historical evaluations were performed. Existing dirty work
and the safety stash were preserved.

The current universe is **4,572**, not an older 4,431-universe report. All 4,572
exact ISINs and tickers remain unchanged. The effective market date is **7
September 2026**; source-specific financial periods remain explicit.

## Reproducible local build

Two independent offline company-fact builds produced identical CSV, coverage,
and manifest bytes. Evidence is under
`data/diagnostics/completeness_recovery_20260908/`.

* Starting company-fact fingerprint:
  `5266c4b586f7c4dc137818e9f0cb34117c9cc29d15925e9070ce16f20818c1d7`
* Candidate fingerprint:
  `192750680b401b0f08e778202835e4801e327ed84db4deb4da4624309dfdb787`
* Unchanged market fingerprint:
  `6dad2b7d600bdb4458bec10f854cdd69e815298369b703b0eaffeafdfb69e504`
* Unchanged accepted Screener bundle:
  `3277812548c02d401ab2cf032066203ba4a6234a020d94ae43e3b7f8994552d8`

`final-audit-verified/coverage_before_after.csv` includes every canonical
coverage metric. `all_field_changes.csv` records every changed value, with ISIN
and ticker. Per-category `remaining_missing_*.csv` files identify residuals.
The candidate was published atomically after verification. The prior snapshot
was retained. `promotion/acceptance.json` records promotion and all artifact
hashes; `accepted-http-smoke.json` records the post-promotion HTTP checks.

| Data family | Before | Candidate | Still missing |
|---|---:|---:|---:|
| Current price | 4567 | 4567 | 5 |
| Product classification | 4422 | 4422 | 150 |
| Market capitalization | 4331 | 4331 | 241 |
| Useful valuation evidence | 4233 | 4233 | 339 |
| Annual financials | 4326 | 4326 | 246 |
| Quarterly / balance sheet / cash flow, each | 4324 | 4324 | 248 |
| Shareholding | 4332 | 4332 | 240 |
| ROCE | 4218 | 4218 | 354 |
| ROE | 4110 | 4110 | 462 |
| Debt/equity | 4112 | 4112 | 460 |
| Profit growth | 4293 | 4293 | 279 |
| Provider-adjusted history | 4331 | 4349 | 223 |
| 1Y history usable | 3800 | 3818 | 754 |
| 3Y history usable | 3412 | 3430 | 1142 |
| 5Y history usable | 3126 | 3144 | 1428 |
| Annual report or official document | 2008 | 2453 | 2119 |
| Detailed workbook discovery | 4093 | 4093 | 479 |
| Screener normalized annual history | 4310 | 4310 | 262 |

These are category-availability counts, not a claim that every financial cell
in a workbook exists. Provider-adjusted history is explicitly **not** a fully
verified official corporate-action ledger. Absence of a recorded corporate
action also does not prove that an action should exist.

## Systemic fixes

1. Accepted normalized exchange financial/shareholding records carried official
   URLs, hashes and availability dates that the document index did not expose.
   Indexing these by exact ISIN recovers document coverage for 445 additional
   companies. There are 465 newly populated latest-document URLs; 20 already
   had another qualifying report link, hence they are not double-counted.
2. The annual-report stage could overwrite a valid document-index status when
   it found no annual filing. The document status now survives that case.
3. Source hashes now reach the document presentation payload.
4. Company details expose a structured identity profile without requiring
   provider-written prose. Optional prose remains optional, not fabricated.
5. Actual detail API sections carry a state and reason for every value. The UI
   exposes missing-field explanations. Numeric zero remains a genuine value.
6. The existing workbook-index union and exact-ISIN statement integration were
   preserved and regression-tested; no directory-only or fuzzy-name fallback
   was introduced.
7. BSE shareholding acquisition now requires an exact six-digit accepted BSE
   identifier, matching catalogue codes, and the actual filing's exact ISIN.
   Failure evidence is retained rather than only incrementing a counter.

No new financial formula was introduced. Existing accepted financial evidence
retains precedence. Current-product enrichment does not expand historical PIT
evidence.

## Why current Product Baseline changes

The full rebuild also sees 18 additional histories already in the local cache
before this pass. Product Baseline eligibility moves **2358 → 2360**:
`BSE-526477` and `BSE-526525`. Their cached histories start on 2002-02-14 and
2003-09-11 respectively and end on 2026-09-04. Sector-relative scores/ranks can
therefore change across their peers. All such changes are enumerated in the
field-change CSV; they are not attributed to the document fix.

Strict-live Baseline remains **571** and V2 remains **63**. The frozen market
bundle and V2 fields are unchanged. This is not a claim that today's Product
Baseline ranks must equal previously frozen research ranks.

## New official-source probe and quarantine

Five residual BSE shareholding catalogues and five original iXBRL attachments
were obtained. Independent source inspection found **four matching ISINs and
one conflicting ISIN**. Scrip 501622's filing explicitly contains
`INE492N01014`; the current security is `INE492N01022`. A matching scrip code
alone cannot justify substitution across this change.

All five remain **unpromoted**. The conflict is quarantined; the other four
remain accounting-review candidates. Original probe artifacts are preserved,
and `bse-probe-network/independent_identity_review.json` supersedes the initial
parser-success count for acceptance purposes. Five parser successes do not
mean five accepted records. No total-share or market-cap value was derived.

## Tests and remaining limitations

The actual localhost root, coverage API, and three real NSE/BSE detail endpoints
returned HTTP 200. The tested detail sections exposed 212–213 per-field states.
This is an HTTP/API smoke, not an exhaustive visual browser acceptance claim.
JavaScript syntax passed using explicit UTF-8 input to Node.

The final full suite passed **654 tests**, with 101 non-failing pandas
fragmentation warnings. The final test XML and HTTP smoke JSON are stored
beside the audits. A focused
test invocation without a fresh basetemp encountered a pre-existing Windows
directory-permission error; the full rerun uses a fresh GUID temporary folder.

Residual categories are not all proven impossible. In particular, 2119 missing
document links, 240 missing ownership categories, and missing official
financial coverage still warrant targeted work. The five-filing probe does
not establish exhaustive BSE coverage or independently validate the entire
existing backbone. Existing ratio gaps must not be filled from incompatible
bases, and missing publication clocks remain separate from current values.

**Verdict: PARTIAL for the overall data-recovery objective.** The local
integration fixes and deterministic candidate are delivered; the evidence
does not justify claiming complete official-source exhaustion or 100% numeric
coverage. The next narrow step is independent review of the four exact-ISIN
BSE candidates, followed by controlled residual acquisition with the new
filing-level identity gate—not broad unvalidated promotion.
