# Open champion comparison and locked historical transfer

Selected experimental candidate: **risk_constrained_high**. User-authorized exploratory selection prioritizes development Top20SIPXIRR and accepts tradeoffs. The two new risk-budgeted policies were compared with the two saved constrained candidates. The winner was locked before its later-period scores were computed.

## Comparison

| Period | Policy | RankIC | IC delta | Professor gain pp | Goal hit gain pp | Top20XIRR gain pp | Top20DD gain pp | Matched dates |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| development | champion | 0.03218 | +0.00000 | +0.00 | +0.00 | +0.00 | +0.00 | 16 |
| development | constrained_high | 0.03448 | +0.00230 | +2.26 | -0.16 | +2.23 | -0.98 | 16 |
| development | constrained_residual | 0.03661 | +0.00443 | +2.18 | -0.09 | +1.55 | -0.80 | 14 |
| development | risk_constrained_high | 0.03425 | +0.00207 | +0.53 | +0.00 | +2.34 | -0.56 | 16 |
| development | risk_constrained_residual | 0.03632 | +0.00414 | +0.51 | -0.26 | +1.94 | -0.86 | 14 |
| transfer | champion | 0.14938 | +0.00000 | +0.00 | +0.00 | +0.00 | +0.00 | 12 |
| transfer | risk_constrained_high | 0.14631 | -0.00308 | +0.82 | +0.23 | -0.78 | -3.61 | 10 |

Development is2020–2023. Transfer is2024–2025, with immature or action-blocked portfolios excluded symmetrically by matched dates. Positive DDgain means less severe drawdown. RankIC is sector/date-averaged Spearman correlation with12monthSIPXIRR. Portfolio gains are mean matched snapshot-cohortXIRR differences, not chainable realized strategy returns. The champion is evaluated on the same feature cohort. Top3 goal support is jointly complete across this round’s candidates and can differ from prior reports.

## What changed

Risk-constrained variants add a decision-time downside252sum bound to the existing five professor-factor bounds. The selected sectorTop3 must match or improve all five professor percentile sums and, for new variants, have no greater historical downside-volatility sum than champion. This is a new optimization constraint. It does not guarantee future drawdown. No predictive model was retrained and no weight grid was searched. The old two candidates reuse their saved rankings. All candidate outcomes are recomputed together only to ensure a common comparison.

The old zero-goal-loss and fixedIC nomination cutoffs are no longer selection gates in this user-authorized round. They were not retroactively changed in old reports. The candidate is selected by the preference declared in the new protocol and all tradeoffs remain visible.

## Concentration and uncertainty

- **development**, 16 matched dates. Mean gain +2.34pp, median +1.66pp, winsorized +1.71pp. Worst leave-one-date-out +0.18pp. Worst leave-one-security-out -0.35pp. Descriptive365day-block95%interval [-4.77,+7.82]pp. Security-deletion audit covered 214 securities. Best date was 2023-03-31.
- **transfer**, 10 matched dates. Mean gain -0.78pp, median +1.04pp, winsorized +0.53pp. Worst leave-one-date-out -2.18pp. Worst leave-one-security-out -2.74pp. Descriptive365day-block95%interval [-5.00,+3.43]pp. Security-deletion audit covered 145 securities. Best date was 2025-08-31.

Single-stock terminal wealth was recovered from corrected SIP labels and verified to reproduce every matched portfolioXIRR to1e-8. Removing a security retains its allocation as0%cash in both models with no replacement and no recovery of originally blocked observations. Contribution shares in JSON refer to net sums and can exceed100%when other contributions offset gains. They are not probabilities or additive XIRR stock attribution.

## Interpretation and verification

Later dates were already used in older project research. This transfer check is a locked-model historical diagnostic, not an independent or prospective holdout. Selection and parameters were not changed after transfer. Publication must report losses as well as gains. The six-year historical sample, overlapping cohorts, survivor identities, retrospective sectors and five-year factor eligibility limit generalization. Younger listings such as Nykaa remain outside this factor-complete pilot. Results cannot establish superiority over proprietary market software without their matched dated predictions.

Nine local tests passed, including exact small-case optimization, factor preservation, optional risk-budget enforcement, tie handling, missing-data rejection and feature prefix invariance. The selection lock pins code and development evidence hashes. One worker/thread,WindowsCPU12.5%cap and4sactive/2srest were used. The website and prospective-ledger streams retain their existing configuration.
