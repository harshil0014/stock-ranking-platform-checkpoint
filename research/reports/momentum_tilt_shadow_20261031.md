# Correction and separate momentum-tilt shadow registration

31 October 2026. Production champion unchanged. No retraining.

The earlier recommendation of `sip_invested_0.05` was too strong if read as a performance improvement. Its small historical-factor alignment changes are partly an expected consequence of rewarding historical SIP profit. The candidate was chosen after outcomes were exposed. It is a preference experiment, not a validated replacement or a majority-weight implementation of the professor's full framework.

## How much actually changes?

On the saved 3 October 2026 base7500 inputs, restrict to the same classified, evidence-positive sectors with at least five peers. Select exactly three names per sector, descending score then ISIN for boundary ties:

| Candidate | Comparable sectors | Changed Top-3 sets | Unchanged sets | Shared slots | Mean shared names per sector | Slot overlap |
|---|---:|---:|---:|---:|---:|---:|
| sip_invested_0.05 | 57 | 8 | 49 | 163 / 171 | 2.860 / 3 | 95.32% |
| sip_plain_0.05 | 57 | 9 | 48 | 162 / 171 | 2.842 / 3 | 94.74% |

Each changed sector replaces one name. Invested 0.05 changes Aerospace & Defense, Auto Components, Commercial Services & Supplies, Construction, Fertilizers & Agrochemicals, Healthcare Equipment & Supplies, Pharmaceuticals & Biotechnology, and Retailing. Plain 0.05 additionally changes Industrial Manufacturing.

For completeness, all 59 serving groups, including Unclassified and a small group, have 176 available slots. Invested 0.05 retains 168/176; plain0.05 retains 167/176. These broader display groups are not all valid within-sector evaluation cohorts.

The snapshot is stale and these are deterministic descriptive counts, not uncertainty estimates or forward validation. Some factor-alignment comparisons have only 28 complete sectors. A one-snapshot increase of 0.06 CAGR-percentile points does not establish useful improvement.

## Performance evidence does not justify promotion

Invested 0.05 has lower development IC and attainment and slightly worse selected-stock drawdown. Its exposed global Top-20 mean SIP XIRR is 1.91 percentage points below champion on nine matched valid dates. The sector Top-3 comparison has only three exposed valid dates and is not used as positive justification. Neither the exposed attainment gain nor a factor-alignment change earns a fresh validation claim.

## Action taken

Freeze exactly one preference candidate, `sip_invested_0.05`, under a new [protocol](../protocols/momentum_tilt_shadow_20261031.json) and isolated `prospective-momentum-tilt-v1` append-only branch. Leave the original `prospective-ledger`, its registration, production scoring, and daily automation unchanged. A first observation is a frozen implementation/overlap audit, always ineligible for the fresh holdout. No retrospective forecast is backfilled. Registration is not an active daily forecast pipeline.

Fresh shadow issuance remains blocked: the complete champion daily-input refresh is not verified and current inputs are dated 3 October. The recorder deliberately implements only frozen registration audits; fresh ingestion is not yet implemented. Repeatedly saving old scores would not cure this missing pipeline, so no redundant daily stale-shadow automation was added.

## Prospective decision rule

Before any eligible new outcomes, fix an operational alignment objective: an equal-weight mean of Top3 within-sector percentiles for 1Y price return, 3Y CAGR, supported 5Y CAGR, recorded-high recency, and trailing professor-mode SIP profit. This is our explicit project definition, not weights supplied by the paper. It does not add fundamentals or all five annual returns.

Require at least 2 percentile-point mean alignment improvement, no individual factor loss exceeding 1 point, at least 10% of comparable sectors changing their Top3, and explicit complete-factor coverage. Set maximum losses of 0.01 IC, 2 percentage points selected-stock drawdown, 2 points global Top-20 portfolio drawdown, and 2 points global Top-20 mean SIP XIRR at 25 bps per buy/final sale. Require adequate matched portfolio coverage rather than citing three favourable dates. These are operational preference limits, not a powered proof of statistical noninferiority.

Archive daily eligible forecasts, evaluate fixed monthly primary issues only after 12 monthly issue dates have fully matured over their 12-month outcome horizon, and report paired date-block uncertainty. This is roughly 24 months after the first eligible issue, not 12 months after this stale registration. No automatic promotion. New weights or objectives require a separate registration.

A separate labelled product lens remains a useful direction, but no UI was added that would imply complete verified fundamentals, majority professor-factor weighting or fresh adjusted inputs. Model rank stays unchanged. No claim of verified investment-performance superiority is made.

## Verification

The recorder reproduces the saved candidate formula, validates source hashes, rejects nonfinite/duplicate inputs, records actual observation time separately from source date, never marks its frozen audits eligible, and reuses the tested append-only manifest chain on the isolated branch. Original ledger heads are checked before and after publication. This work changes research files only.
