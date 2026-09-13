# Official financial recovery workflow

This implements the collection/review boundary in the supplied **Verified
Financial Recovery Pack Research Plan**. It does not add fictitious values or
weaken the product/research contracts. A missing field remains missing until
the evidence is sufficient.

## Run or resume on Windows

From the repository, run `marketdata\runners\run_financial_recovery.cmd`.
Run only one instance at a time. It uses the existing market-data environment
for collection and the separate `.venv-recovery` with Arelle 2.44.7 for offline
extraction. Product dependencies are unchanged. The installation receipt with
package download hashes is in the pack; no paid account is used.

Output: `data/recovery_packs/official_financial_tail_20260908/`.
Targets are frozen from the four-way intersection of annual, quarterly,
balance-sheet and cash-flow gaps: 244 exact ISINs, 234 BSE and 10 NSE.
The target SHA-256 is
`067f9810a8a877ff344704573e16bd0aff73b0d5e8a6640e82ed968be97200ab`.
Changing targets in place is rejected; a new universe requires a fresh pack.

## Official routes and actual findings

The old BSE `Comp_Results.aspx` page currently returns an application shell.
Inspecting its public JavaScript identified the corporate route and the exact
`Corp_FinanceResult_ng_new/w` request used by the site. Discovery preserves
the response, issuer code, filing row, source link and catalogue creation time.
The standalone `XMLName` link is distinct from `Consol_XMLName`.
Some linked XML files return 404 while their official iXBRL HTML counterparts
work. The collector follows the latter directly without browser automation.

For NSE, `collect-nse-cached` verifies the SHA-256 receipt of the existing
`official-backbone-20260822-07` catalogue, filters exact symbols and the explicit
`Integrated Filing- Financials` type, then verifies ISIN in the linked document.
It does not use governance filings as financial statements. The catalogue's
original date window is retained: missing from this cache is not missing forever.

Up to four unique recent iXBRL documents per BSE issuer are collected in this
pass. This is bounded collection, not proof that every annual historical
period has been recovered. An empty catalogue is not proof that no official
annual report exists. NSE shell pages may still require structured catalogue
discovery or manual official-file caching; global navigation is not treated
as company evidence.

Shareholding uses the existing official BSE catalogue and parser, with exact
catalogue-code and filing-ISIN checks. A changed ISIN under the same scrip code
is quarantined, not silently linked. The previously retained five-filing probe
can be imported using `seed-probe --seed <probe directory>`; hashes are checked
and original evidence is not modified.

## Safety and review stages

* One serial collector; two seconds between uncached requests, finite timeouts,
  at most three attempts per task, persisted per-task progress and a cooldown.
* HTTP blocking breaks the acquisition loop. It is not called "no record".
* Cached raw evidence is content-addressed and hash-verified. Completed tasks
  are skipped. `collect --offline` makes no network requests.
* Only HTTPS official NSE/BSE domains are allowed, including redirects.
* Raw bytes and historical progress remain available. New discovery uses
  `financial_discovery_v2.json` instead of rewriting the earlier HTML probe.
* Outputs are **review-only**. There is no accepted-state write or promotion
  function in this workflow.

Arelle handles inline numeric transformations, scale/sign, periods, units and
dimensions. Its output is deliberately labelled
`REVIEW_ONLY_DTS_NOT_VALIDATED`: taxonomy loading is disabled for offline
reproducibility, and parser diagnostics are retained. This is not full XBRL
taxonomy or accounting validation. No proprietary/custom accounting formula
is introduced.

`financial_review_facts.csv` uses existing concept aliases, preserves unknown
concepts and dimensional qualifiers, and keeps standalone/consolidated basis.
It is **not** `financial_facts.csv` accepted input. The accepted facts export
remains empty. In particular, `Fld_CreateDate` is recorded as a catalogue
timestamp, not silently promoted into a verified dissemination clock.

## What must happen before product import

For each candidate, resolve taxonomy and parser errors, independently check
the accounting context/basis/unit, distinguish consolidated and standalone
values, resolve revisions and conflicting duplicates, and verify any needed
publication timestamp. Segment/related-party dimensions must not be treated
as company totals. Review balance/cash reconciliations where their inputs are
present. Do not derive ratios just because related-looking figures exist.

No ROCE formula, market-cap derivation or V2 evidence promotion is performed
here. Financial-company semantics remain subject to the existing contracts.
Current product and historical PIT approval remain separate decisions.

## Inspect the pack

* `targets.csv`: exact target identities and official discovery URLs.
* `requests/` and `raw/`: receipt metadata and source-hashed evidence.
* `progress.json`: initial discovery/ownership outcomes and retry state.
* `financial_discovery_v2.json`: official financial catalogue and filing results.
* `arelle_review_v2/`: original-hash-linked offline extraction and diagnostics.
* `financial_review_facts.csv`: normalized **review** rows, not accepted values.
* `shareholding_review.csv`: explicit ownership values awaiting review.
* `unresolved.csv`: attempted/not-attempted states, not invented terminal causes.
* `validation_report.json`, `raw_inventory.json`: counts and source hashes.
* `issuer_recovery_audit.csv`: one row for every target, exact remaining action,
  periods, observed bases, conflicts, and separate ownership status.
* `recovery_audit.json`: inventory validation and canonical extraction fingerprint.
* `independent_numeric_checks.csv`: a separate HTML/Decimal numeric-transform
  check, not accounting approval.
* `determinism_verification.json`: independent Arelle re-extractions and two
  byte-identical offline review builds. Parser logs are retained but excluded
  from numerical reproducibility because they are diagnostics, not facts.

## Completed collection and conservative acceptance boundary

The resumed batch checked all **244 financial targets**. It retained **751
documents** for 208 issuers, with **28 documents quarantined by the exact-ISIN
gate**. The remaining 36 targets split into 29 without linked iXBRL in the BSE
catalogue and seven without a financial link in the bounded cached NSE catalogue.
These are route-specific failures, not proof that information cannot exist.

There are **114,184 review facts for 203 issuers**. Four identity-matched NSE
pages are rendered HTML tables, not usable inline-XBRL instances; they produce
no facts and remain explicit extraction gaps. The numeric cross-check covered
**106,882 facts with zero mismatches**. The other **7,302 facts were not
independently verified by that limited transform checker**. No conflicting
numeric values were found within identical concept/context/unit keys inside
each parsed document; cross-document revisions still require accounting review.

Ownership collection produced **227 review candidates**, seven quarantines,
and ten NSE discovery-only outcomes. Neither family is automatically promoted.
All **2,948 raw/cache inventory entries** passed size/SHA-256 checks.

**Verdict: PARTIAL recovery, not completed financial acceptance.** The next
step is taxonomy/context/unit/revision validation of the cached candidates,
followed by a separately reviewed current-product import. Publication-clock
approval remains an additional historical-PIT gate. The rendered NSE pages
need their structured XML or table-specific extraction; this workflow does not
invent numbers from them. No additional manual download is needed to start
reviewing the 203 issuers whose raw evidence is already preserved here.

Accepted current-product coverage remains unchanged: 4,572 identities, 4,567
prices, 4,326 annual statements, 4,324 quarterly/balance-sheet/cash-flow coverage,
4,332 shareholding records, 2,360 Product Baseline eligible, 571 strict-live
Baseline eligible, and 63 strict V2 eligible. The accepted company-fact
fingerprint remains
`192750680b401b0f08e778202835e4801e327ed84db4deb4da4624309dfdb787`;
market fingerprint remains
`6dad2b7d600bdb4458bec10f854cdd69e815298369b703b0eaffeafdfb69e504`
(trading date 2026-09-07). **New accepted facts: zero**, deliberately.

To repeat the complete offline reproducibility audit:

```text
.venv-recovery\Scripts\python.exe marketdata\runners\verify_financial_recovery_pack.py --pack data\recovery_packs\official_financial_tail_20260908 --all
```

Final verification on 2026-09-09: **41 focused tests passed; 672 full product
tests passed** with cache disabled and a fresh GUID temporary directory.
All **723 cached review extractions** reproduced canonically in a separate
process, and both offline builds had identical artifact bytes. Local HTTP
checks passed for the homepage, health, dashboard fingerprint, company-fact
coverage, and RELIANCE detail; JavaScript syntax passed. Accepted snapshot
artifact hashes and the accepted pointer remained unchanged. `git diff --check`
passed. No staging, commit, push, branch change, or safety-stash operation was
performed. The existing remote was neither changed nor used.

For tomorrow's presentation, use the unchanged accepted website data. Do not
claim that candidate extraction has expanded validated coverage. The honest
demonstration is an operational evidence-recovery pipeline alongside the
existing research platform—not a fabricated complete database.

References: [BSE financial results](https://www.bseindia.com/corporates/Comp_Results.aspx),
[NSE XBRL information](https://www.nseindia.com/static/companies-listing/xbrl-information),
[Arelle supported Python API](https://arelle.readthedocs.io/en/latest/python_api/python_api.html).

## Uploaded BSE tail: current/reference integration

The subsequent `bse_remaining.zip` intake extends this same recovery pack;
the zero-acceptance figures above describe the earlier automated extraction.
`financial_recovery_pack.py ingest-manual --pack <pack> --archive <zip>`
reuses cached source bytes and the existing XBRL normalizer. Independent PDFium
text is prepared with `review_manual_pdfium.py` in `.venv-accounting-audit`;
PDF statement rows require agreement with the separate pypdf layout extraction.
No filenames establish identity. Exact embedded ISIN or exact scrip code with
supporting legal-name evidence is required. Conflicting disclosures, ambiguous
columns, restatements, unsupported units and unverified identities stay quarantined.

The authoritative results are `manual_latest.json`, its hash-verified batch
`manual_validation.json`, `manual_company_audit.csv`, and
`still_missing_after_manual_ingest.csv`. `load_current_reference` validates
the accepted normalized CSV and its raw evidence hashes for downstream recovery
use. These facts are **current/reference only**, with explicit financial periods;
old reports are not described as fresh. No official dissemination clock has been
invented, no historical PIT record has been added, and no accepted website snapshot
or ranking has been overwritten. Integration into the recovery acceptance boundary
is not automatic promotion into the live product.

The residual lists missing *accepted* fields, not proof that those fields are
absent from the supplied PDFs. Remaining document/context review should use the
existing uploads before requesting any further download. Two unresolved document
identities require an authoritative CIN-to-ISIN/scrip link; company-name resemblance
alone is insufficient. Ratios are not inferred from loosely related concepts.
One source cash-flow presentation places equity issuance in investing activities;
that investing subtotal is quarantined rather than silently corrected.

Manual intake verification: 29 documents, 27 content-identity matches,
152 accepted current/reference facts across 10 issuers; 19 issuers remain
without accepted manual facts. All 29 retain some requested-field gaps.
Two rebuilds produced identical artifact bytes. The focused suite passed
52 tests; the full regression suite passed 683 tests. JavaScript syntax,
local HTTP smoke checks and Git whitespace checks passed. Accepted snapshot
hashes and protected protocol/recovery evidence remained unchanged.

### NSE manual supplement

The cumulative local intake also retains the nine leaf files from
`nse_remaining.zip` (including nested IPO archives). Original archives and their
hashes are preserved in `manual_inputs`; no acquisition occurred. General IPO
guides and the index-price CSV are not company financial statements. The two
identity-matched annual reports added 44 review facts, but no newly accepted
financial facts: reporting-basis evidence remains unresolved and Ortel's auditor
explicitly disclaims an opinion. The previous 152 accepted facts remain intact.
Prospectus filenames do not establish issuer identity. No PIT clocks are inferred.

`supplement_archive(pack, inputs)` builds a deterministic cumulative archive;
repeating the same supplement retains earlier records without duplicating files.
Validation stops before publication if a previously accepted normalized fact would
be lost or conflicted. NSE exact-ISIN records retain their canonical exchange;
a supporting dual-listing BSE code is not incorrectly compared to an NSE ticker.

The separate ESDS PDF was initially readable (138 pages, image-only in the first
four inspected pages; SHA-256
`eaa3cc58f740cc5c3e842e5678cdfa68d6eee948ee1459937ac4e3d0c82e97b7`)
but disappeared from its supplied Downloads path before immutable intake. Its
bytes were not cached; it has **not** been ingested or accepted. Restore that
original PDF to continue its identity/OCR/evidence review.

Supplement verification: 56 focused tests and 687 full regression tests passed;
two cumulative rebuilds were byte-identical. All prior accepted recovery facts
and accepted company-fact snapshot content hashes remained unchanged. The accepted
pointer's `accepted_at` differs from the preceding turn's recorded timestamp,
but its snapshot, market fingerprint and financial content are unchanged; this
manual intake did not promote a website snapshot. Index remains empty.

### Last remaining upload

`last_remaining.zip` is preserved in the cumulative recovery store, including
the previously missing ESDS PDF (same recorded SHA-256). Its first auditor page
was rendered and visually inspected: standalone FY ending 31 March 2026.
The PDF is scanned; no text-extracted financial values or filename-based issuer
join is accepted. It remains in document review, not lost or awaiting re-download.

The integrated SEBI 2026-01-31 XML namespace uses explicit INR instance values;
the same existing concept mapping, accounting reconciliation, dimensional,
standalone, audit, duplicate and PIT gates apply. Exact embedded ISIN and legal
entity name support cross-listed NSE identities whose XML context uses a BSE
code. This is not an alias inferred from a filename. TCC's different embedded
ISIN and the unmatched Integrated Proteins filing remain quarantined.
Only directly mapped monetary facts are eligible; no ratio is newly derived.
The three matching filings are SKIL, UNIVAFOODS and BSE-533315. New values remain
current/reference-only, never historical PIT evidence or automatic live promotion.

Completed verification: 55 newly accepted normalized facts, increasing the
cumulative manual recovery layer from 152 to 207 facts across 13 issuers.
Two rebuilds were byte-identical and preserved all prior accepted values.
57 focused tests and 688 full regression tests passed; JavaScript syntax,
accepted snapshot content hashes and Git whitespace checks passed. ESDS and
unresolved identity documents remain quarantined. No staging, commit, push,
stash operation or live/PIT promotion occurred.
