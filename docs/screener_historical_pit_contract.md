# Screener Historical Standalone + Official Filing Clock

Status: implemented workbook, bounded public-page, and fail-closed official-XBRL
candidate contracts; **not yet sufficient for a large historical evaluation**.

## Canonical contract

Contract identifier: `screener_historical_standalone_official_clock_v1`.

- Financial values come from a hash-pinned Screener company workbook explicitly exported in **standalone** mode.
- ISIN is the primary identity key. A workbook is rejected unless a sidecar manifest supplies an exact valid ISIN, ticker, expected workbook company, SHA-256, observation timestamp, and standalone-basis attestation.
- The workbook itself is not treated as proof of identity or basis: its standard `Data Sheet` contains a company name but no ISIN or basis field.
- The official NSE/BSE filing record supplies only the earliest verified public dissemination timestamp for the same ISIN and financial period. It never supplies, edits, or substitutes a financial value.
- Values enter a ranking only after that official timestamp and only when `period_end <= ranking_date`.
- Current and prior PAT are Screener's reported annual standalone `Net profit` values in INR crore.
- ROCE follows the formula embedded in Screener's standard workbook, verified cell-by-cell before parsing:

```text
(current PBT + current interest) * 2
-------------------------------------------------------------
prior (equity capital + reserves + borrowings)
+ current (equity capital + reserves + borrowings)
```

- Debt-to-equity is `Borrowings / (Equity Share Capital + Reserves)` from the same standalone workbook and period.
- Research V2 continues to calculate profit growth from current/prior PAT and keeps its existing negative-leverage, zero-prior-PAT, ranking, weighting, and no-imputation rules unchanged.
- Screener ratios are a consistent canonical methodology. They are **not** represented as issuer-specific statutory ROCE or debt-ratio definitions.

### Scalable public-statement route

Screener's visible `/company/<NSE symbol>/` page is the standalone view. It
publishes the same annual P&L and balance-sheet lines used by the standard
workbook, but amounts are rounded for display. The scalable parser therefore:

- accepts an ISIN only from the supplied Premium bulk export and separately
  requires the page's NSE link to equal that exact ticker;
- requires an explicit standalone label, or the parent-only standalone URL
  with no consolidated alternative;
- derives the same workbook ROCE and D/E formulas from the displayed lines;
- propagates each displayed value's rounding quantum through interval bounds;
- rejects a period when ROCE uncertainty exceeds 1 percentage point or D/E
  uncertainty exceeds 0.02; and
- caches the raw HTML, observation time, URL, bytes, and SHA-256 before parsing.

This route never claims workbook-level precision. It is a separately labelled
Screener observation with conservative numerical bounds.

The older `nse_audited_standalone_fundamentals_v1` records and all frozen research outputs remain unchanged. This is a separately versioned prospective data layer.

## Calibration result

The 14 supplied historical company workbooks were checked against the existing audited standalone gold set:

- 14/14 exact ISIN and ticker identities matched.
- 14/14 FY2026 current and prior PAT pairs matched the audited standalone statements within the workbook's two-decimal crore precision.
- 0 wrong PAT values were accepted.
- Screener ROCE and D/E differences from statutory ratios remain visible diagnostics, not calibration failures, because the methods intentionally differ.
- The two 5,442-row Screener Premium bulk CSVs match all 14 calibration ISINs, but have no explicit historical period or reporting-basis column. They remain current/default-basis secondary evidence and cannot replace standalone historical workbooks.
- Across 122 overlapping annual observations in the 14-company pack, deriving
  the workbook formula from Screener's rounded public display produced mean
  absolute differences of 0.00074 for ROCE and 0.00136 for D/E; 95th-percentile
  differences were 0.00150 and 0.00291. PAT differed by at most ₹0.50 crore.
  Fragile small-equity observations caused the larger tail and are precisely
  the cases removed by the interval gate.

Screener states that screen exports are Premium CSV downloads and that it does not provide an API: <https://support.screener.in/article/28-export-screen-results>. Screener also states that screens normally choose consolidated figures and may fall back to standalone, which is why default-basis bulk rows are not admitted here: <https://support.screener.in/article/41-standalone-or-consolidated>. Company pages can be toggled between standalone and consolidated and company Excel exports provide structured history: <https://www.screener.in/features/>.

## Calibration-pack PIT coverage

Using only verified official exchange timestamps already cached in the repository, the 14-workbook pack supplies this many complete, numerically eligible PIT records:

| Ranking date | Screener records | Existing frozen records | Non-frozen union |
|---|---:|---:|---:|
| 2022-08-05 | 0 | 8 | 8 |
| 2023-08-07 | 1 | 4 | 5 |
| 2024-08-07 | 6 | 8 | 14 |
| 2025-08-07 | 10 | 16 | 26 |
| 2026-08-21 | 12 | n/a | calibration only |

IDEA and TRF retain negative Screener D/E and are ineligible under unchanged V2 numeric rules. Other missing rows are caused by the absence of a verified pre-cutoff exchange dissemination timestamp, not by silent backdating.

These counts do not justify a large same-cohort historical evaluation. No outcome evaluation was run.

## Scaling workflow

1. Use exact `(ISIN, NSE symbol)` identities from the supplied Premium bulk
   export and select only issuers with a verified official clock and conventional
   ROCE applicability.
2. Run `acquire_screener_public_history.py`. The deliberately conservative
   default is at most **5** uncached pages per invocation, at least **15 seconds**
   between requests, and a circuit breaker after the first failure. Cache hits
   are free. A zero request budget performs a completely offline rebuild.
3. Re-run the command on a schedule. It deterministically advances the immutable
   cache without manual company downloads. Raw pages remain the evidence layer.
4. Parse cached pages offline, apply uncertainty gates, and join annual periods
   to exact official NSE/BSE dissemination records by `(ISIN, period_end)`.
5. Retain the 14 high-precision workbooks as calibration controls. Future
   Premium workbooks can still be added for rejected precision edge cases.
6. Review deterministic rejects: identity/basis/hash drift, missing clock,
   future filing, unsafe display precision, negative D/E, or zero prior PAT.
7. Build evaluation cohorts only after several hundred securities pass at each
   preregistered date.

Screener exposes no supported API; its documented machine-use path is Premium
CSV export, whose screen basis is automatically selected rather than guaranteed
standalone. Custom bulk screens therefore cannot satisfy this contract. Public
company pages are permitted by `robots.txt`, but must be fetched slowly and
cached. A live scale attempt correctly stopped after the site began resetting
connections; it did not rotate identities, evade the control, or mark failures
as missing data. The bounded scheduled cache is the defensible no-manual route.

## Reproducibility and scientific boundary

The build writes canonical UTF-8/Unix-newline CSVs plus normalized and selected SHA-256 fingerprints. It is resumable by adding immutable manifest records and deterministic because no network access occurs during parsing or cohort construction. Existing Baseline V1, Research V2, classification precedence, live rankings, and frozen walk-forward evidence are not mutated.

Current exports can contain later corrections or restatements. The contract therefore preserves `source_observed_at` and the workbook hash. The official filing clock proves when the period's filing became public; it does not prove that a later Screener snapshot is a byte-for-byte vintage of the first filing. This residual vintage risk must remain visible and should be tested with archived exports or exact filing comparisons on a stratified sample before the large evaluation is approved.

## Route decision, 2026-09-01

`audit_screener_acquisition_routes.py` compared all three proposed paths using
only cached evidence; it made no Screener request.

| Route | Exact result | Decision |
|---|---|---|
| Supported company Excel | 14 precise calibrated issuers and 124 annual periods | Retain as the gold/calibration and precision-edge-case route; it still needs one export per company. |
| Slow resumable public standalone page | 30 cached exact-identity pages parsed, with 0 cache-parse failures; combined with the workbooks, PIT counts are 5 / 6 / 16 / 24 / 29 for 2022–2026 | **Selected scalable route.** It eliminates manual company downloads, preserves raw-page hashes, and advances only through the bounded cache. |
| Official XBRL + Screener formula | 5,848 relevant facts were found for 611 target identities, but 0 complete two-period candidates passed | Not promotable from the present backbone. Keep as a future official-data bridge only after historical comparative facts and vendor-line reconciliation exist. |

All 14 supplied Excel files contain zero OOXML external links, connections, or
query tables. Screener's reusable custom workbook feature controls the exported
layout/formulas, but the downloaded files are static results rather than a
refreshable bulk data connection. Screen CSV export supports many companies but
uses Screener's automatic consolidated/standalone selection, so it cannot prove
the standalone basis required by this contract.

The XBRL result is not a formula problem. On the 14-company calibration set,
the current official facts matched the workbook at its precision for PBT 9/14,
interest 11/14, PAT 13/14, equity capital 13/14, reserves 12/14, and borrowings
only 2/14. No company had a complete prior annual capital/PAT fact set in the
current 1.58-million-fact snapshot. Screener's normalized `Borrowings` commonly
includes amounts not represented by the two top-level XBRL borrowing concepts,
while its ROCE requires both current and prior capital. Substituting, estimating,
or silently changing that vendor normalization would violate the fixed contract.

The official clock provides a real upper-bound capacity of 41 / 50 / 240 / 434 /
541 conventional-ROCE issuers for 2022–2026 (611 unique identities). Those are
targets, not achieved cohorts. The large evaluation remains blocked until the
selected cache contains several hundred complete records at the relevant dates.
Without changing the frozen experiment, a prospective ticker-union audit moves
its 2022–2025 cohorts from 8 / 4 / 8 / 16 to 13 / 10 / 24 / 40. There is no
overlap in this initial cache sample, so the additions are 5 / 6 / 16 / 24.
These are readiness counts only; no outcomes were recomputed or inspected.
