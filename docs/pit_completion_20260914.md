# PIT completeness: accepted-local evidence reconciliation

This pass does not promote additional fundamentals. Product Baseline remains
3,246 eligible and Research V2 remains 63 eligible among 4,572 securities.
The accepted market date is 2026-09-07, with a 15:30 IST research cutoff.

## Integrity correction

`validated_fundamental_candidates` previously compared only the calendar date
of the official NSE dissemination timestamp. A same-day release after 15:30
could consequently enter a candidate. The gate now rejects those releases;
15:30:00 itself is permitted. Its timestamp schema represents exchange-local
IST. Reviewed promoted specifications certify dates only: a same-day record
without certified dissemination time is deferred, not assigned midnight.
Earlier-day records remain available. No source timestamp is inferred from
PDF names, retrieval dates or vendor financial periods.

The 29 existing promoted-addition rows, identities and deferred results at
2026-09-07 were compared with the pre-change loader and are exactly unchanged.
No historical results were regenerated. Future recomputation on a report's
publication day may conservatively exclude it under the corrected boundary.

## Evidence inspected

- Accepted official XBRL backbone: 1,582,209 normalized facts. The complete
  source-concept scan found no `ROCE` or capital-employed concept-name hits.
  This is not proof that disclosure text in every original filing lacks ROCE.
  Debt-equity concepts alone cannot supply the complete audited V2 contract.
- Current manual recovery: 302 accepted current/reference facts, 19 issuers.
  No exact ISIN plus document-SHA256 match to a pre-cutoff official clock in
  the accepted backbone's facts or documents. These facts remain reference-only.
  A clock for a different document or another period is not a substitute.
- Latest independent PDFium review: 179 reports. Twenty-four issuers already
  appear in the accepted additions specification. Subsequent adjudication
  outranks preliminary extraction, including exclusions for net-debt ratios,
  dashes, conflicting profit, missing ratio definitions and ambiguous columns.
  An older parser's complete-record label is not new promotion evidence.

## Current eligibility waterfall

| Reason | Securities |
|---|---:|
| ELIGIBLE | 63 |
| FUNDAMENTALS_UNAVAILABLE | 2,493 |
| BSE_FUNDAMENTAL_CONTRACT_UNAVAILABLE | 1,995 |
| NO_AVAILABLE_FUNDAMENTALS | 15 |
| PRICE_UNAVAILABLE | 5 |
| MISSING_5Y_PRICE_ANCHOR;NO_AVAILABLE_FUNDAMENTALS | 1 |

These are V2 statuses, not company-page financial-number coverage. In
particular, the five V2 price exclusions were not silently filled using the
separate Product Baseline current/reference-price policy.

## Reproducible outputs

Run `.venv\Scripts\python.exe marketdata\runners\audit_pit_completion.py
--output data\diagnostics\<fresh-name>` as one command. It never acquires data
or changes accepted state. It writes issuer-level residuals, manual clock
reconciliation, annual-report reconciliation and a summary with input hashes.
Existing output directories are rejected.

`data/diagnostics/pit_completion_20260914_final_a` and `final_b` contain
byte-identical outputs. Twenty-eight protected input files were unchanged.
The summary SHA256 is
`ee95d17a9cea679cc4bb7320685c9ef6684677f168d83bb820039acf393e1969`.

Verification: 50 focused tests passed; the full suite passed all 724 tests
in 222.26 seconds with caching disabled and a fresh GUID temporary directory.
Post-suite protected hashes and `git diff --check` passed. The Git index
remained empty and the safety stash was retained; no commit or push occurred.

Company fingerprint:
`ad3cd53f6de553132f6413ca72dfab9621024ad2cf885cea992533cc459da80b`.
Market fingerprint:
`6dad2b7d600bdb4458bec10f854cdd69e815298369b703b0eaffeafdfb69e504`.

## Completion boundary

PARTIAL: the cutoff defect is corrected and the inspected local evidence is
reconciled, but coverage has not increased. No claim is made that all external
official archives or every unreviewed PDF page have been exhausted. Additional
coverage requires independently validated compatible accounting disclosure
and a matching official publication clock, not reclassification of current
reference facts or weaker ratio definitions. No Baseline formula, V2 weight,
classification, accepted snapshot, or frozen research result was modified.
