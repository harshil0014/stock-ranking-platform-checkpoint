# Independent PIT Accounting Validation

This stage extends current Research V2 coverage without changing its formulas,
weights, eligibility rules, or frozen research artifacts. It is deliberately a
precision-first accounting evidence gate, not a general PDF-to-financials
parser.

## Evidence boundary

- Official NSE annual-report metadata supplies ticker, company, ISIN, source
  URL, PDF hash, and exchange dissemination timestamp.
- The earlier `pypdf` review packets supply page locations only. Accepted
  values are reopened and extracted independently with `pdfplumber 0.11.9` and
  `pdfminer.six 20251230` in `.venv-accounting-audit`.
- A record requires an explicit standalone basis, 2025-26 and 2024-25 values,
  the statement unit for profit, and local issuer definitions for ROCE and
  debt-to-equity. Values are not derived from statement components.
- Net debt/equity, cross-row values belonging to another ratio, blanks,
  dashes, mixed bases, conflicting disclosures, OCR-only evidence, missing
  units, negative leverage, and ambiguous definitions are quarantined.
- Availability is the official exchange dissemination date and is filtered
  before a record can enter a ranking date.

## Calibration and controlled promotion

The final strict calibration made 39 field-level comparisons against the
14-company human-reviewed set: 19 exact candidate matches and zero wrong
selected values. Only one report was complete under the fully automatic gate.
This is strong precision but low recall; it does not justify unattended bulk
promotion.

Seven current-period additions passed the first strict independent gate:
`ADANIGREEN`, `DMART`, `DYNAMATECH`, `FSL`, `INDIAMART`, `OBEROIRLTY`, and
`SONATSOFTW`. The accepted current snapshot therefore contains 41 V2-eligible
stocks (the frozen 34 plus seven PIT-safe additions).

A second blind route re-extracted all 179 quarantined reports with PDFium,
independent of pdfminer/pdfplumber. Its initial pass identified three complete
source-review candidates: ALKEM, IMFA, and VEEDOL. A later full-document,
row-safe pass examined every page while preserving the same acceptance rules.
It completed all 179 reports, produced seven explicit engine disagreements,
left 164 incomplete, and identified eight complete review candidates. The two
full-document runs produced byte-identical record SHA-256
`d27edbbc3ae6e752dc720ded1496d5a2c8d08d48933cef5d5169afc133f16535`.

Rendered official standalone statement and ratio pages independently confirmed
five additional records: GESHIP, IFBAGRO, KEC, QUESS, and WELENT. The review
checked exact values, periods, statement units, issuer ratio definitions,
official dissemination timestamps, ISINs, and PDF hashes. The remaining three
complete parser candidates were not promoted without equivalent source-page
adjudication. These five enter only the current-period extension; the frozen 34
and all historical outcomes remain unchanged. The accepted 2026-08-28 product
state initially contained 48 strict V2 rows. The subsequent terminal adjudication
of all 28 one-field-short records raised the 2026-08-28 current state to 61,
while leaving 12 accounting-ambiguous records quarantined. The market and
company-fact fingerprints
`6c026885ebb150afbd80da5e678a632b521c67ba487e60b69da5c967d2b99fed`
and
`e404627f6438c92128c388bb057f23f8128f085c8b90842fb45e3a619084e05a`.

The audit caught and rejected plausible-looking but scientifically different
net-debt/equity disclosures and a case where an empty debt/equity row could
otherwise consume the following interest-coverage values. This is why packet
completeness alone is never promotion evidence.

## Scaling decision

The extraction runner checkpoints every ticker and can resume after malformed
or pathological PDFs. The strict cached 187-packet pass completed 185 records,
quarantined 179, identified six discovery candidates, and retained two explicit
errors (`JKLAKSHMI` parser failure and `MPHASIS` timeout). Every discovery
candidate was subjected to the broader all-profit-page pass; that pass exposed
a conflicting profit disclosure in `BERGEPAINT`, so discovery status alone did
not cause promotion. The audit is useful for producing a small high-confidence
candidate queue, but automatic promotion to hundreds is not yet supported by
measured recall. Historical official-report metadata shows
substantially better report availability in 2024-2026 than in 2022-2023, but
availability is not accounting completeness. No outcome evaluation or broad
backtest should begin until each historical date has a sufficiently large,
sector-diverse set that independently passes the same gate.

The metadata-only historical readiness audit (which does not calculate any
outcome) found explicit pre-ranking-date NSE dissemination timestamps for 50,
60, 284, 523, and 640 reports at the 2022, 2023, 2024, 2025, and 2026 cutoffs,
respectively. The first two dates remain far too sparse, and older archive ZIP
layouts need a separately validated extraction path.

The second extractor materially improved precision-controlled coverage, but
eight complete candidates and five newly adjudicated promotions from 179
reports are not a path to hundreds by themselves. Twenty-eight reports are one
field short after the full-document pass; they are a bounded queue for targeted
geometry/table extraction. The 164 incomplete layouts and seven engine
disagreements remain quarantined. Historical cohort expansion remains blocked
until the same evidence contract has adequate multi-date and multi-sector
coverage.
