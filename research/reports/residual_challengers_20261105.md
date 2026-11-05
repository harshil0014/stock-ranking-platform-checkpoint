# Residual-history champion search, 5 November 2026

Development nomination: **none**. Three new feature policies were evaluated. The existing champion remains the reference.

## Novelty audit

The saved archive contains 146 report/protocol paths. Archived runner code revealed earlier monotonic tree models, so the initially proposed monotonic family was dropped before fitting. Raw recency, trend smoothness, factor-weight sweeps, recovery, generic momentum and prior model tournaments were also excluded. Earlier reports explicitly state that their sector percentiles were not regression residual momentum. This supports novelty relative to saved evidence, with uncertainty for uncatalogued manual trials.

The persistent incomplete registry now has 306 documented attempts. This round adds three policies, with no model fitting or hyperparameter search. The local scoped multiplicity calculation covers these three policies only and cannot repair earlier adaptive reuse.

## Method and professor alignment

Weekly log returns are regressed on an intercept plus leave-one-out market and sector reference returns over156weeks. Momentum uses the48residual weeks ending4weeks before the snapshot, normalized by residual volatility. The second feature measures time since the maximum cumulative residual over48weeks. These features test stock-specific behavior after common movements are removed. Reference baskets and sectors come from the current-survivor historical cohort. They are not certified point-in-time investable market factors.

- residual_momentum20 uses80%champion and20%residual-momentum percentile.
- professor_residual50 uses30%champion,50%equal five-block professor core and20%residual momentum.
- residual_high20 uses80%champion and20%residual-path high-recency percentile.

Only professor_residual50 guarantees50%explicit professor score mass. The other policies must preserve measured professor and raw-high alignment to pass. The workbook does not prescribe these coefficients. Inputs inherit five-year complete-factor eligibility, so younger listings are outside this pilot. The champion and all challengers use exactly the same reduced feature cohorts, with sector normalization before label filtering.

## Matched development results

| Policy | IC | IC delta | Professor alignment gain pp | Raw high alignment gain pp | Goal hit delta pp | Top20 XIRR delta pp | Top20 DD delta pp | Changed Top3 % | Portfolio dates |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| champion | 0.03218 | +0.00000 | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 | 0.0 | 16 |
| professor_residual50 | -0.03137 | -0.06355 | +14.16 | +8.60 | -3.85 | -1.97 | -3.38 | 85.8 | 14 |
| residual_high20 | 0.03544 | +0.00326 | -1.37 | -2.41 | +0.19 | +2.58 | -1.02 | 52.4 | 16 |
| residual_momentum20 | 0.03679 | +0.00461 | -0.91 | -1.54 | +0.83 | +2.64 | -0.92 | 52.0 | 14 |

Positive DD delta means less severe drawdown. RankIC is date-balanced mean sector Spearman correlation with corrected12monthSIPXIRR, not market-index alpha. GlobalTop20 compares within-sector normalized scores across sectors. Joint complete sectorTop3 queries are common across policies, portfolio pair date support can differ. Actual adjusted next-open buys,100bp per side, fractional units, price-only outcomes and unresolved-action blocks remain the existing execution proxy. See blocked/failure and annual CSVs. The reference champion IC differs slightly from earlier reports because this round uses the smaller common residual-feature cohort.

The fixed incremental IC floor is0.010134924. This round’s95%familywise365day-block bootstrap hurdle is0.04925. Both are required, alongside IC gain in3of4years, nonworsening professor/high alignment and goal hit, positive portfolio return gain robust to10%winsorization and every leave-one-date-out deletion, drawdown worsening<=2pp and adequate support.

## Individual decisions

- **residual_momentum20**. Positive IC years 4/4. Winsorized portfolio delta +2.88pp, worst leave-one-date-out +1.32pp. Failed requirements: ic_floor, ic_familywise, professor_alignment, raw_high_alignment.
- **professor_residual50**. Positive IC years 1/4. Winsorized portfolio delta -1.93pp, worst leave-one-date-out -3.71pp. Failed requirements: ic_floor, ic_familywise, annual_ic, goal, xirr, winsor, lodo, drawdown.
- **residual_high20**. Positive IC years 3/4. Winsorized portfolio delta +2.55pp, worst leave-one-date-out +0.44pp. Failed requirements: ic_floor, ic_familywise, professor_alignment, raw_high_alignment.

## Verification and limits

Four residual-feature tests passed. They check prefix invariance, self-exclusion, missing-history handling and a known idiosyncratic trend. 26,391 stock-date rows across16 development dates were scored. Input, protocol and archive-code hashes are retained. The prior registry IDs remain present. Exposed2024–2025 was not evaluated. The data were already used for many development decisions, and sixteen overlapping cohorts do not supply independent validation. No current/live ranking or website/runtime change is produced. The October3runtime remains stale for the prospective holdout.

## Literature and implementation review

Scite returned paper metadata, full-text excerpts and citation context. No editorial-notice fields appeared in the returned records, so absence of notices is not independent certification. GitHub inspection found a homework reproduction usingFF5andChina data, whose README warns of possible mistakes. No implementation was copied or executed. Continuity/Frog-in-the-Pan work was excluded from this pilot because earlier project proxies already target that idea.

References

- Blitz, D. C., Huij, J., & Martens, M. (2011). Residual momentum. *Journal of Empirical Finance,18*(3),506–521. https://doi.org/10.1016/j.jempfin.2011.01.003. Primary inspiration for regressing out common returns. Our market/sector weekly adaptation differs from the paper’s Fama–French factors.
- Da, Z., Gurun, U. G., & Warachka, M. (2014). Frog in the pan: Continuous information and momentum. *Review of Financial Studies,27*(7),2171–2218. https://doi.org/10.1093/rfs/hhu003. Reviewed and excluded as substantially overlapping prior continuity tests.
- Jansen, M., Swinkels, L., & Zhou, W. (2021). Anomalies in the China A-share market. Working paper. https://doi.org/10.2139/ssrn.3810114. Scite full-text reports residual-momentum tests in China, supporting cross-market investigation but not Indian performance.
- Singh, S., Walia, N., & Bekiros, S. D. (2022). Risk-managed time-series momentum: An emerging economy experience. *Journal of Economics, Finance and Administrative Science,27*(54),328–343. https://doi.org/10.1108/JEFAS-08-2021-0159. Indian-market context, not validation of this estimator.
- dexin-peng. (2022). Residual momentum toy reproduction. https://github.com/dexin-peng/Blitz-et-al.-2011-Residual-Momentum-toy-reproduce. Reference lead only.
