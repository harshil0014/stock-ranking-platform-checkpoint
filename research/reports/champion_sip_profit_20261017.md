# Explicit SIP profit weighting for the active champion

Selected: `sip_risk_confirmed_0.01`. Research activation gate: **DO NOT ACTIVATE**.

## What was tested

The comparator is the currently active original champion plus dual_w0.01. Its component coefficients and high-recency adjustment are preserved exactly. Each candidate adds w × centered within-sector trailing SIP-profit percentile. Tested w: .01, .025, .05, .10, .20. These are additive score coefficients, not a claimed percentage of total nonlinear model importance.

- Plain: direct profit percentile, with larger profit always favored.
- Invested: scale the adjustment by the fraction of the SIP budget actually invested, to reduce low-denominator affordability effects.
- Risk confirmed: also scale by the within-sector inverse downside-volatility percentile.
- Missing profit, missing champion evidence, unknown sector, stale/inactive trading, fewer than five valid peers, or unresolved provider/official discrepancies within the trailing lookback receive zero adjustment. No stock is removed from numerical coverage.

## Profit definition and literature

The signal uses the stored trailing professor-mode gain divided by actual invested cost, excluding unused cash. It is neither XIRR nor forward profit. The project simulator uses its own calendar/trading-day and corporate-action rules, so this is not exact Google Sheets replication.
[Grinblatt and Han (2005)](https://www.sciencedirect.com/science/article/pii/S0304405X05000747) motivates testing gains relative to acquisition cost. Their aggregate capital-gains measure differs from this hypothetical SIP ledger; their findings do not validate these weights or this Indian stock universe. [FINRA performance guidance](https://www.finra.org/sites/default/files/2020-06/Regulatory-Notice-20-21.pdf) distinguishes cash-flow-sensitive IRR from other return measures. The investment-fraction and downside multipliers are engineering hypotheses, not direct paper replications.

## Evaluation

Fifteen configurations predefined before evaluation. Select on 2020–2023, lock one, then evaluate it on 2024–2025. Equal-sector/profile Top3 capped outcomes; weighted utility: 40% rank IC, 25% NDCG, 15% achievement, 10% inverse shortfall, 10% drawdown; directional deltas divided by .01. XIRR is not optimized but is an activation gate. The selected candidate must improve weighted utility and not worsen any of the six aggregate metrics in either period. Common/expanded populations, raw/capped outcomes and Top1/3/5 diagnostics are exported.

| Candidate | Development utility |
|---|---:|
| sip_risk_confirmed_0.01 | -0.012648 |
| sip_invested_0.01 | -0.029758 |
| sip_plain_0.01 | -0.034306 |
| sip_risk_confirmed_0.025 | -0.039782 |
| sip_invested_0.025 | -0.075352 |
| sip_risk_confirmed_0.05 | -0.075676 |
| sip_plain_0.025 | -0.083563 |
| sip_invested_0.05 | -0.103584 |
| sip_plain_0.05 | -0.117190 |
| sip_risk_confirmed_0.1 | -0.175148 |
| sip_invested_0.1 | -0.339430 |
| sip_plain_0.1 | -0.345662 |
| sip_risk_confirmed_0.2 | -0.384312 |
| sip_invested_0.2 | -0.628120 |
| sip_plain_0.2 | -0.671941 |

| Period | Model | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |
|---|---|---:|---:|---:|---:|---:|---:|
| development | current_champion | 34.752% | -25.462% | 58.052% | 0.051615 | 0.590543 | 0.025957 |
| development | sip_risk_confirmed_0.01 | 34.677% | -25.485% | 58.034% | 0.051679 | 0.590276 | 0.025948 |
| recent | current_champion | -0.266% | -31.343% | 22.901% | 0.117771 | 0.637150 | 0.152447 |
| recent | sip_risk_confirmed_0.01 | -0.272% | -31.376% | 22.971% | 0.117905 | 0.637031 | 0.152471 |

Current coverage: 4,436; nonzero selected adjustments: 2,968; changed sector ranks: 851. Stock-order changes are not evidence of increased accuracy.

## Verification and limitations

- Source hashes verified; identical historical query identities and population counts for compared models; current score replay within 1e-12. All current scores finite, bounded corrections, inherited fallback scores unchanged.
- Three tests pass: profit direction/bounds/reliability, abstention, and independence from future dates/outcome columns.
- Source simulation-date audit: 1,516,870 rows checked; zero simulation as-of dates after their decision dates.
- Previously researched historical dates; no fresh out-of-sample validation. Current-survivor universe, retrospective sectors, gross outcomes and incomplete corporate-action certification remain.
- The SIP feature is unavailable for some stocks. The champion remains their fallback; no performance claim is made from invented SIP values.
- Website was not switched by this experiment. A gate pass is research evidence, not proof of future superiority.

## Reproduction

Set PYTHONPATH=src; run `python research/runners/champion_sip_profit_20261017.py`, then `python research/runners/report_champion_sip_profit_20261017.py`. Full scores, query metrics, sector/profile deltas, coverage, protocol and decision are under `experiments/champion-sip-profit-20261017/`.
