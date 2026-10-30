# SIP-profit champion: agreement check and activation

## User decision

The user accepted the slight historical degradation and requested that the selected `sip_risk_confirmed_0.01` variant be integrated after checking whether it moves toward sir's ranking. The prior research no-degradation gate remains failed; this is an explicit preference override, not a newly discovered performance improvement.

## Does the ranking move toward sir's criterion?

Yes, modestly. Current snapshot, base7500 profile, identical comparable populations within each sector:

| Measure (equal-sector average) | Recency champion | With SIP preference |
|---|---:|---:|
| Spearman rank correlation | 0.463455 | 0.467385 |
| Kendall rank correlation | 0.345259 | 0.348502 |
| Top-three overlap | 23.8994% | 23.8994% |

Across 53 sectors and 3,164 comparable stocks, Spearman agreement improves in 28 sectors, remains unchanged in 25, and deteriorates in none. Correlation increases by 0.00393, about 0.85% relative to its previous value. This is not a 0.85% improvement in investment accuracy or future returns.

The reference is the project's stored professor-mode trailing SIP profit percentage, with unresolved corporate-action windows excluded and at least five comparable stocks per sector. It uses the project's calendar and corporate-action conventions, not newly recalculated Google Sheets cells. The comparison establishes movement toward the criterion, not exact reproduction of the workbook or screenshot. Full-universe correlation cannot be claimed because some stocks lack usable SIP evidence. Sector detail: `experiments/champion-sip-profit-20261017/sir_agreement_by_sector.csv`.

## Activated calculation

`new score = recency champion + 0.01 × (sector SIP-profit percentile − 0.5) × invested budget fraction × inverse downside percentile`

High-recency coefficients are unchanged. Evidence, activity, minimum peer count and corporate-action guards are identical to the experiment. Missing SIP evidence means zero SIP adjustment; numerical coverage remains 4,436. This is the selected downside/affordability-adjusted version, not the plain 20% candidate.

## Website behavior

The same Sector Champion route and user controls are retained. Stored profiles use their own frozen SIP evidence. Custom profiles calculate professor-mode SIP profit from the submitted amount, interval and lookback using the existing history engine. The target-return field controls goal calculations; it does not enter simple SIP profit. Stock details expose trailing SIP profit and its score adjustment. The previous recency champion score is returned for comparison/rollback.

Runtime revision: `dual_w0.01_sip_risk_confirmed0.01_20261017`. The runtime package hash-verifies stored profile evidence and unresolved-event dates. Previous manifest preserved as `manifest_before_sip.json`; restoring that manifest disables the SIP overlay without changing research records.

## Verification

- 13 focused tests pass, including exact reproduction, preserved recency score, profile-dependent SIP changes, guards and integrity checks.
- All 4,436 default-profile scores match the selected experiment within 3.34e-16; all sector ranks match exactly.
- JavaScript syntax passes Node checking.
- Live default/custom-profile API verification passed and is recorded in `research/runtime/sector-champion-recency/sip_http_verification.json`. An arbitrary ₹12,345 / 47-day / 23.5%-target profile returned all 4,436 stocks and changed 3,001 scores through its SIP evidence. Default sector ranks matched exactly.
- Snapshot remains 3 October 2026. Historical performance tradeoffs remain as documented in `champion_sip_profit_20261017.md`.

Local website integration only; no remote publication is claimed. Browser visual inspection remains unavailable because local browser control is disabled in Work settings.
