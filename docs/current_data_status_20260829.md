# Authoritative current data status — 2026-08-30 audit

This table is the authoritative interpretation of the accepted current-data
state after the 2026-08-28 exchange snapshot. Counts from older documents are
historical observations, not interchangeable definitions.

| Measure | Current count | Exact definition |
|---|---:|---|
| Current exchange-snapshot universe | 5,096 | 2,559 official NSE-master identities plus 2,537 BSE securities observed in the accepted BSE trade snapshot |
| Current prices | 5,095 | Accepted price observation in the 2026-08-28 snapshot |
| Officially sector-classified | 750 | Exact NSE Indices classification only |
| Product-classified | 4,291 | Official classification plus exact-identity secondary classification; never represented as official |
| Strict live Baseline eligible | 571 | Accepted Baseline rules in the official-sector live cohort |
| Product Baseline eligible | 728 | The strict 571 plus 157 exact-identity secondary-classified rows under Product Classification v1 |
| Strict current Research V2 eligible | 61 | Frozen accepted records plus independently reviewed current additions that also pass current price/history gates |
| Frozen real Research V2 cohort | 34 | Immutable 2026-08-07 standalone-contract research bundle; not a current coverage count |
| Company-fact rows | 5,096 | One row per current exchange-snapshot identity |

Accepted current market fingerprint:
`6c026885ebb150afbd80da5e678a632b521c67ba487e60b69da5c967d2b99fed`.
Accepted company-fact fingerprint:
`e404627f6438c92128c388bb057f23f8128f085c8b90842fb45e3a619084e05a`.
Two cached company-fact builds produced the same fingerprint.

## 5,167 versus 5,096 identities

The 5,167 count belongs to the accepted 2026-08-21 exchange snapshot. Exact
`(primary_exchange, exchange_security_id, ISIN)` reconciliation against the
2026-08-28 state gives 4,757 common identities, 410 prior-only identities, and
339 current-only identities, a net change of -71. Of the prior-only identities,
407 are BSE daily trade records and three are NSE-master rows; of the
current-only identities, 330 are BSE daily trade records and nine are
NSE-master rows.

This is a dynamic snapshot-cohort difference, dominated by whether a BSE
security appears in that day's accepted trade file; it is not evidence that
410 issuers delisted. No prior accepted snapshot or evidence was deleted. More
importantly for scientific behavior, none of the 410 prior-only rows was
Baseline-eligible or Research-V2-eligible. The Baseline sets have 499 common
rows, zero lost rows, and 72 newly eligible rows between the two accepted
dates. A future stable all-listings BSE master should be treated as a separate
identity-spine improvement rather than silently relabelling this daily cohort.

## 44 versus 43 pre-expansion V2 rows

The 44 count belongs to the accepted 2026-08-21 current view. The pre-expansion
2026-08-28 rebuild has 43 because VEEDOL has no adjusted close within seven
calendar days before the new current anchor. Its deterministic reason is
`STALE_CURRENT_PRICE_ANCHOR`. No fundamental record was removed and no
eligibility tolerance changed.

Five independently reviewed official NSE annual-report additions—GESHIP,
IFBAGRO, KEC, QUESS, and WELENT—then increased the same 2026-08-28 view from 43
to 48. A subsequent adjudication resolved all 28 one-field-short records:
14 additional reports were promoted, ONGC and OBEROIRLTY were already accepted,
and 12 received accounting-specific quarantine reasons. Thirteen of those 14
new records pass the current price/history gates, taking live eligibility to
61; GULFOILLUB remains `STALE_CURRENT_PRICE_ANCHOR`. AIAENG remains quarantined
because its current D/E cell is a dash, not an explicit numeric zero. Each accepted record preserves exact ISIN, standalone basis, period, official
dissemination date, PDF hash, statement unit, PAT comparison, and issuer ratio
definitions. Screener values played no acceptance role.

## 1,237 product Baseline versus strict-live Baseline

On 2026-08-21, 1,237 was the expanded Product Classification v1 cohort and 499
was the strict official-sector live cohort. All 499 strict rows were in the
product cohort; the 738 additional product rows comprised 669 exact-identity
secondary classifications and 69 official classifications. They were two
cohort definitions, not a temporal fall from 1,237 to 499.

At the current 2026-08-28 state, the corresponding counts are 728 product and
571 strict. All 571 strict rows remain in the product cohort; the 157
product-only rows all use explicitly labelled exact-identity secondary
classification. Baseline formulas, ranking, price-continuity thresholds, and
sector isolation are unchanged.

## Frozen and secondary-evidence boundaries

- The frozen real Research V2 bundle remains
  `2a66a124ba83db489656ab6af5f73a609d3a7c75b5fb540e9bd7d9383b27b25b`;
  its rankings remain
  `81d896dd8011a4aae9c54b83af029f82e05ac48032f06c3e03d7c336e0ca0f1d`.
- The two Screener Premium exports remain current secondary reference evidence
  only. Their canonical reference fingerprint is
  `5303eec99dd7a12851087b39e1ea30b54d80de72d1dc507da0326c16cf7e58ee`.
  They cannot establish period, standalone basis, filing availability, issuer
  ratio definition, or historical PIT eligibility.
- The full-document PDFium audit processed all 179 quarantined reports twice
  with identical record SHA-256
  `d27edbbc3ae6e752dc720ded1496d5a2c8d08d48933cef5d5169afc133f16535`:
  eight complete review candidates, seven engine disagreements, and 164
  incomplete records. Unreviewed, conflicting, and incomplete values remain
  quarantined.

## Readiness verdict

Current-period coverage is improved and internally consistent, but historical
PIT coverage is not ready for a large multi-date evaluation. Explicit official
pre-cutoff annual-report metadata covers only 50 and 60 reports at the 2022 and
2023 cutoffs, versus 284, 523, and 640 at the 2024, 2025, and 2026 cutoffs.
Availability is only the first gate; every accounting record must still pass
the unchanged evidence contract. The milestone is therefore **PARTIAL**:
current coverage advanced with zero knowingly wrong accepted values, while the
hundreds-scale and early-history goals remain open.
