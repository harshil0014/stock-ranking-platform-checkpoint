# Screener historical evaluation readiness freeze

Status: **TARGETED DATA FIX REQUIRED**. The final evaluation is not authorized.

This audit was performed without calculating or inspecting a future return,
IC, Rank IC, Kendall correlation, top-bucket result, portfolio result, turnover,
or transaction-cost result.

## Frozen protocol

- Identifier: `screener_historical_same_cohort_evaluation_protocol_v1`
- Version: `1`
- Status: `frozen_pre_outcome_execution_gated`
- Canonical SHA-256: `428a1c50e89bbb8ecce55d34586269f7ea1172791a5d7e26273ca46d71da1c93`
- Machine-readable source:
  `experiments/walk_forward/screener_same_cohort_protocol_v1.json`

The hash is SHA-256 over the parsed JSON serialized as UTF-8 with sorted object
keys and separators `,` and `:`. Baseline V1, Research V2, sector methodology,
ranking dates, outcome definition, ties, eligibility, formulas, and weights are
immutable. The protocol uses official date-specific NIFTY 50 membership and
the official date-applicable NSE Indices Sector tier. A later current-company
population is never projected backward.

## Headline-count reconciliation

The previously reported `49 / 78 / 226 / 247` figures are not historical
comparison cohorts. They are ticker unions between the existing historical
NIFTY-50 Research V2 rows and Screener records selected from a later broad
issuer population. Those unions were useful acquisition-capacity indicators,
but they do not prove ranking-date membership and would introduce survivorship
bias if evaluated as historical universes.

After applying the official historical membership, exact current Screener
ISIN identity, the Screener standalone contract, the corrected 15:30 IST
information cutoff, unchanged price eligibility, and date-only evidence that a
12-month endpoint exists, the defensible same cohorts are:

| Ranking date | Starting prospective count | Official universe | Identity/PIT clean | 12m endpoint available | Final same cohort | Rank-IC-eligible sectors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022-08-05 | 49 | 50 | 0 | 0 | 0 | 0 |
| 2023-08-07 | 78 | 50 | 0 | 0 | 0 | 0 |
| 2024-08-07 | 226 | 50 | 3 | 3 | 3 | 0 |
| 2025-08-07 | 247 | 50 | 3 | 3 | 3 | 0 |

The six clean rows are all sector singletons. Therefore there are zero valid
sector-date Rank IC observations. Running the final evaluation would produce
no scientifically interpretable primary comparison.

## PIT cutoff correction

The prior Screener cohort builder used end-of-calendar-day as its cutoff. The
frozen ranking protocol stops at **15:30 IST**. A filing disseminated after the
market close on the ranking date could therefore enter the old readiness count.
The selector now applies 15:30 IST exactly. This changes only PIT timing; it
does not change a financial value, formula, eligibility rule, or rank.

Rebuilding the 200 accepted workbooks from unchanged normalized data and the
unchanged official clock produces corrected broad Screener readiness counts of
`41 / 74 / 217 / 232` for 2022-2025. A later filing that is not yet public does
not force exclusion when an older period really is the latest PIT-available
filing. Eligibility is applied to that selected latest available period, and
an ineligible latest available period never falls back to an older eligible
period.

The 2024 count falls by two: `INDUSTOWER` and `ONGC` were disseminated after
15:30 IST on the ranking date and had no earlier PIT-available Screener period.
For 2025, six after-cutoff FY2025 filings (`INDUSTOWER`, `IOC`, `KIMS`,
`MPSLTD`, `NTPC`, and `ONGC`) correctly select their older latest-public
periods instead. This preserves the established latest-PIT-available rule; the
older periods remain explicit and are never presented as FY2025 values.

## Exclusions and concentration

The dominant exclusion is `NO_SCREENER_PIT_FUNDAMENTALS` within the official
historical universe: `48 / 48 / 45 / 46` securities by date. Exact current
Screener ISIN identity is unavailable for `2 / 2 / 2 / 1` historical symbols,
including identities that no longer exist as the same current security. No
substitution is permitted.

Outcome readiness was checked using ticker/date columns only from the accepted
Yahoo history cache. Values were not read by the readiness engine. Predictor
files were independently required to end on or before their ranking date.

## Targeted fix, not Batch 5

General checklist collection should stop. The deterministic targeted list has
26 unique issuers selected specifically to reach at least ten securities and
two sectors with at least three peers on every date if every listed fix passes.
It prioritizes already verified official clocks and identifies where historical
official-clock rescue must occur before a workbook is useful. It excludes
financial-sector issuers from the proposed fix because conventional Screener
ROCE/debt leverage is not automatically economically comparable for those
entities.

The primary bottleneck is 2022/2023 official historical dissemination coverage,
not a shortage of arbitrary 2024/2025 company workbooks. No additional manual
download should be requested until the targeted clock/identity rows are
resolved. The target is evidence planning, not automatic admission: every
workbook must still pass exact identity, standalone, hash, latest-filing-first,
numeric, price, and PIT checks.

## Frozen evaluation behavior

When and only when all execution gates pass, the primary metric is 12-month
sector-date Spearman Rank IC on identical Baseline/V2 securities. Baseline is
reranked within the matched cohort. Kendall tau-b, pairwise accuracy, top-ranked
excess, top-half/bottom-half spreads, and top-N overlap are secondary and
descriptive. Ties use the frozen average-rank/competition conventions. Missing
outcomes remove the security from both methods. No cost-adjusted portfolio is
claimed because the experiment has no supported execution or transaction-cost
model.

Four annual dates cannot establish universal superiority or conventional
statistical significance. Results must remain per-date/per-sector first, with
any pooled result clearly labelled descriptive.
