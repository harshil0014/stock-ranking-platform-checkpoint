# Professor-Supplied Acceptance Cohort

This benchmark treats the 99 supplied codes and 14 supplied ranks as external
evaluation evidence. They are not model inputs and are never used to tune a
formula, weight, threshold, sector, horizon, or eligibility rule.

## Identity policy

- `NSE:` codes match only the exact current NSE symbol.
- Prefixless codes require separate official evidence for the exact NSE symbol
  and ISIN. No default exchange and no fuzzy name matching is allowed.
- `BOM:` codes remain BSE identities. A BSE code maps to a current NSE row only
  when verified exchange evidence and the current master establish the same
  ISIN. Otherwise it remains BSE-only.
- A verified identity without an accepted current provider series is reported
  as `LEGITIMATELY UNAVAILABLE`; it is never replaced.

Representative primary evidence includes the official NSE rename circular for
[GVT&D](https://nsearchives.nseindia.com/content/circulars/CML64784.pdf), the
official NSE ISIN circular for
[GOKULAGRO](https://nsearchives.nseindia.com/content/circulars/CML70634.pdf),
official BSE filings for
[Uni Abex](https://www.bseindia.com/xml-data/corpfiling/AttachHis/d99a1e65-1e15-4ce1-a7eb-283e0f978f68.pdf),
[Titan Biotech](https://www.bseindia.com/xml-data/corpfiling/AttachLive/efe05e13-004e-46ae-b933-417044909bf8.pdf),
[Tanfac](https://www.bseindia.com/xml-data/corpfiling/AttachLive/d9736425-9923-4ce9-8129-81e54f03f6dd.pdf),
[Amal](https://www.bseindia.com/xml-data/corpfiling/AttachHis/7b5a4792-30f5-4bcf-b91b-3de46b9df349.pdf),
[G G Automotive](https://www.bseindia.com/xml-data/corpfiling/AttachLive/0d69e86c-8350-435b-900e-93cbeaafb744.pdf),
[Kwality Pharmaceuticals](https://www.bseindia.com/xml-data/corpfiling/AttachHis/d6e5914b-1e9e-459d-b04e-c8f11883b98b.pdf), and
[Tinna Rubber](https://www.bseindia.com/xml-data/corpfiling/AttachLive/42e13197-d328-443e-9daa-745e330dd11b.pdf),
plus the SEBI offer document for
[ADC India](https://www.sebi.gov.in/sebi_data/commondocs/jan-2026/ADC%20India%20Communications%20Limited-DPS_p.pdf).

## Result

- Requested: 99 securities; supplied ranking: 14.
- Exact identity coverage: 99/99.
- Current price coverage at 7 August 2026: 99/99.
- Identity mapping: 85 prefixed NSE, two verified prefixless NSE, four
  ISIN-proven cross-listings, and eight BSE-only securities.
- `RESOLVED`: 99. Delton Cables (`BOM:504240`) is resolved for the current
  price through the official BSE CM-UDiFF BhavCopy Final after Yahoo returned
  no usable series. Its BSE-only status still prevents an accepted NSE-sector
  rank, and raw BSE history is not relabelled as adjusted history.
  `LEGITIMATELY UNAVAILABLE`: 0. `DEFECT REMAINS`: 0.
- Baseline V1 eligible under the unchanged canonical NSE sector contract: 38.
- Research V2 eligible under the unchanged audited-standalone contract: 0.

The supplied ranking is **NOT REPRODUCIBLE FROM AVAILABLE METHODOLOGY**.
It has no disclosed score, sector scope, tie convention, or ranking formula.
Baseline V1 ranks are meaningful only within accepted sectors, so a global
Spearman correlation or global top-k overlap would be invalid. The audit leaves
those fields null and reports six same-sector comparable pairs separately.

Research V2 is **INSUFFICIENT EVIDENCE** for this cohort: current accepted
fundamentals do not make any supplied security eligible. This is not evidence
of model improvement or failure.

The ignored deterministic artifact at
`data/professor_reference/acceptance_current/` contains one row per requested
code, all identity decisions and provenance, price/history coverage, anchors,
raw signals, canonical model statuses/scores/ranks, and the 14-row comparison.

## Reproduction

```powershell
.\.venv\Scripts\stock-ranker.exe professor-acceptance `
  --request data\professor_reference\acceptance_request.json `
  --identity-evidence data\professor_reference\acceptance_identity_evidence.json `
  --bse-snapshot data\professor_reference\bse_bhavcopy_20260807.csv `
  --output-dir data\professor_reference\acceptance_current
```

The website reads and hash-validates that artifact. Search filters never
recompute a scientific rank.
