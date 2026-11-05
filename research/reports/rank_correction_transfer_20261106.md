# Exact rank-correction candidate, later-period test

Candidate **error_corrected_professor**, frozen November5algorithm, evaluated on2024–2025. Two annual models were fitted using only outcomes mature before each test year. Model parameters,0.25correction and professor constraints were held fixed.

| Metric | Development2020–2023 | Later2024–2025 |
|---|---:|---:|
| GlobalTop20SIPXIRR gain | +5.44pp | +0.91pp |
| GlobalTop20drawdown gain | +0.60pp | -0.32pp |
| Sector/date rankIC gain | +0.000001 | -0.000047 |
| SectorTop3goalhit gain | +0.00pp | +0.00pp |
| Professor alignment gain | +0.00pp | +0.00pp |
| SectorTop3sets changed | 0% | 0.00% |
| MatchedTop20dates | 16 | 12 |

Positive drawdown gain means a less severe drawdown. These are matched mean snapshot-cohort12monthSIPXIRRs using next adjustedOpen,100bp each side,fractionalshares and existing unresolved-action blocks. They are not chained strategy returns. Later outcomes were used by earlier research and are a historical transfer diagnostic, not fresh confirmation.

## Robustness

Median date gain +2.03pp,winsorized +1.16pp,worst leave-one-date-out +0.12pp,worst leave-one-security-out +0.16pp. Descriptive365day-block95%interval[-1.15,+2.53]pp.
Raw-score global champion control: candidate minus control -1.63pp on10matched dates. This avoids treating sector-normalization tie-breaking as the sole benchmark.
Annual matchedTop20differences: 2024 +0.96pp, 2025 +0.89pp.

Stock deletion replaces that allocation by0%cash in both portfolios without refill. Corrected stock-label terminal wealth was checked to reproduce all portfolioXIRRs to1e-8. Individual stocks are not published.

## Deployment scope

The tested candidate primarily changes cross-sector globalTop20selection. The current website defaults to within-sector champion rankings, with4,436identities and profile-dependent SIP adjustments. This research cohort requires all five professor factors plus residual histories, so it does not cover all those identities. Promoting its name without delivering the tested global selection and honest coverage would misrepresent the model. Current input files are frozen October3,2026, and the daily champion-input pipeline remains unverified. The separate prospective ledger must not be relabeled as forecasts from this candidate.

## Verification

Nine feature/optimizer tests passed. Training maturity,fold-model hashes and every professor constraint were checked. The low-load governor enforced one worker/thread,12.5%CPUcap,4seconds active/2seconds rest. Raw inputs,protocol and scorer hashes are retained. There were no changes to coefficients or features after viewing transfer outcomes.

## Authorized promotion completed

The candidate is installed as the Global Top-20 Champion panel on the existing `/sector-champion` website page. The panel supports the tested base profile only, ₹7,500 every30days,36monthlookback,20%target,12monthhorizon. The October3,2026snapshot supplies2,386eligible stocks across48sectors. Missing five-year or residual history receives no global selection. Original sector ranks and other-profile execution remain available.

The2026annual model uses54,831mature training rows, latest label endpoint2025-12-31. Its champion input matches the production scorer with maximum score difference3.1e-16. All48current sector queries solved optimally with no fallback. The runtime validates CSV and model hashes before serving.

23local tests passed, including realHTTPchampion entry-point integration, full4,436row response, globalTop20identity/rank checks, unsupported-profile behavior, tamper rejection, original sector-model parity and solver/feature checks. The actual browser was opened, base ranking submitted, and all20global selections and snapshot coverage observed in the rendered panel. The local server is at http://127.0.0.1:8765/sector-champion. Public GitHub publication distributes the code and runtime package, not a separately hosted public website.

The global promotion reflects the user's explicit choice to accept experimental tradeoffs. Later-period normalized-benchmark gain is+0.91pp, but the raw-global-score control comparison is-1.63pp on10matched dates. The descriptive95%interval for the normalized-benchmark gain spans-1.15pp to+2.53pp. That is mixed historical evidence, not established broad market superiority. No prospective-ledger branch or protocol was changed.

Rollback can restore the previous website service and assets from commit7b31b683 while retaining the research report. The new package and `global_champion_product.py` can then remain archived or be removed separately.
