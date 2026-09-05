# Professor OK Strategy v4.3 audit

This benchmark treats the professor-supplied workbook as external evidence. It does not change Baseline V1, Research V2, eligibility, sectors, weights, frozen outcomes, or accepted research fingerprints.

## What is reproducible

The workbook contains 19 worksheets and a large formula-driven portfolio model. Its only explicit stock-ranking formulas are `SIP Portfolio!N7:N20`: Excel `RANK` applied to cached SIP profit/loss in `I7:I20`, descending. The cached SIP assumptions are ₹7,500 per contribution, 36 months, and 30-day spacing. The workbook date is 21 August 2026.

For the supplied 14-stock ranking, the explicit workbook SIP rank has 6 exact positions, Spearman correlation `0.8373626373626375`, pairwise agreement `0.8681318681318682`, and top-five overlap `0.8`. Cached 10-year, 5-year, and 3-year CAGR fields were also tested independently. None explains the supplied ordering better than the explicit SIP rank, and none is represented in the workbook as that ordering's formula.

Verdict: **PARTIAL MATCH**. The smallest missing professor input is the exact rule, overrides, and as-of snapshot used to transform the workbook SIP rank into the supplied 14-stock order. The platform does not guess that rule.

## Relationship to the platform

Baseline V1 uses YoY return, three- and five-year CAGR, and recorded/study-period-high recency, ranked within each canonical sector. It is a defensible operationalization of related price signals, but it is not the workbook's global SIP profit/loss ranking. Global correlation between the supplied list and sector ranks would therefore be misleading.

Research V2 remains a separate nine-factor extension. The supplied 99-security acceptance artifact currently has no eligible Research V2 rows, so its comparative verdict is **INSUFFICIENT EVIDENCE**. No outcome, formula, or weight was tuned.

## Screener evidence boundary

Screener states that it has no API. Its terms limit copying and automated reuse, and its automated data may contain errors. The platform therefore does not scrape Screener. It accepts an optional professor/user-supplied CSV export only when it contains exact NSE/BSE codes and an explicit source date. Matching is by exact security code; name-based or fuzzy substitution is prohibited. Screener industry remains separate evidence and never silently replaces the canonical project sector.

No Screener export was supplied for this audit, so Screener-wide classification coverage is not claimed. Representative public-page review confirmed SHAILY as BSE `501423`, NSE `SHAILY`, within Screener's Plastic Products taxonomy, with links to exchange filings.

## SHAILY continuity finding

Official company annual-report evidence states that SHAILY began NSE trading on 4 April 2022 while retaining its BSE identity. An NSE circular records a 2023 face-value subdivision and current ISIN `INE151G01028`. This proves issuer/security lineage but is insufficient to concatenate raw BSE and NSE prices. A defensible cross-exchange five-year history still needs the pre-listing BSE series, old/new ISIN bridge, corporate-action adjustment validation, and a common adjustment basis. The current `INSUFFICIENT_5Y_HISTORY` result is retained.

## Outputs and required input

`stock-ranker professor-strategy` writes deterministic comparison, SIP ranking, diagnostics, summary, and manifest files. Every workbook field includes cell provenance. The website reads only the hash-validated artifact and shows `Professor Reference → Workbook SIP → Baseline V1 → Research V2`.

Final user/professor input still required:

1. The precise 14-stock ordering rule, including overrides and snapshot date.
2. For cohort-wide Screener taxonomy, a legally obtained CSV export plus export date and redistribution permission.
3. For SHAILY continuity, authoritative adjusted BSE history or adjustment-factor evidence for the pre-NSE period.
