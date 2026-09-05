# PIT-safe structured-fundamental bridge

## Result

The 28 one-field-short annual-report records are now fully adjudicated: 14
additional records pass, two (`OBEROIRLTY` and frozen-universe `ONGC`) were already accepted, and 12 remain
quarantined with specific accounting reasons. This is a resolution of every
record, not a claim that every record should become eligible.

The attached Screener Premium exports are useful secondary evidence but cannot
be backdated into the 2022–2025 cohorts. They were observed in August 2026 and
contain current values without an audited reporting basis, source filing ID, or
historical availability timestamp. An old financial-period label is not proof
that the present export value was public and unchanged at that old date.

## Scalable admission rule

`pit_structured_fundamentals.py` implements the smallest safe bridge. It joins
structured values to an official exchange filing only on exact
`(ISIN, period_end, reporting_basis)`. A record is admitted through one of two
routes:

1. a contemporaneously archived structured export observed no later than the
   ranking date; or
2. a later structured export whose four values have been deterministically
   matched to the original hash-verified official filing.

The second route avoids manual PDF archaeology: structured values locate the
target rows, while deterministic table/text extraction from the original
attachment supplies a compact value-match evidence hash. It does not treat
Screener as the historical clock. Official exchange dissemination remains the
availability boundary.

## What is needed to scale 2022–2025

The current two CSVs cannot expand historical cohorts because they do not
contain period-specific ROCE, debt-to-equity and PAT series. A future Screener
export must include those historical columns (or company workbooks containing
the history), exact ISIN and an explicit standalone/consolidated basis. Each
period is then joined to the corresponding NSE/BSE filing event and checked
against the original attachment automatically. Rows that fail identity, basis,
period, timestamp or numeric agreement remain quarantined.

| Ranking cutoff | Exact official reports already timed | Historical admissions from the two supplied current exports |
|---|---:|---:|
| 2022-08-05 | 50 | 0 |
| 2023-08-07 | 60 | 0 |
| 2024-08-07 | 284 | 0 |
| 2025-08-07 | 523 | 0 |

The official-report counts are ceilings before accounting validation, not V2
cohort claims. The zero is a useful failure result: the supplied exports were
observed in 2026 and expose only current ROCE, D/E and PAT, so stamping them
with an older exchange filing date would create look-ahead. The scalable next
input is a period-specific Screener history export (or company workbook) whose
values can be bulk-matched to these already timed original filings.

This preserves the accepted formulas and prevents later restatements from
leaking into earlier ranking dates. No backtest is authorized until these
cohorts are materially larger.
