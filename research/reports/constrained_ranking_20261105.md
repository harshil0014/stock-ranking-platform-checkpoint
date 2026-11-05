# Professor-constrained stock selection, 5 November 2026

Development investment/preference nominees: **none**. Two new constrained selection policies were tested. Exposed outcomes were not evaluated.

## Change in approach

The saved residual objectives rank stocks first. A mixed-integer optimization then chooses exactly three stocks per sector/date, maximizing the objective while requiring each of five professor-factor percentile sums to match or exceed the champion trio. Both the residual-momentum and residual-high objectives are tested once. This is a constrained selection policy, with no blend grid or predictive-model retraining. It explicitly reuses the new residual inputs from the immediately prior pilot rather than claiming they are newly discovered again.

The constraints separately protect annual consistency,CAGR3,CAGR5,raw-high recency and trailing SIPprofit on each sectorTop3 set. They do not prescribe each stock’s weight, raw-day averages, Top1/Top2 alignment or globalTop20 alignment. Selected trios are ordered by the original objective, then the remaining stocks follow that objective. Original sorted score values are reassigned to this ordering with nextafter tie resolution.

## Development comparison, 2020–2023

| Policy | RankIC | IC delta | Professor gain pp | Goal hit gain pp | Top3 stock DD gain pp | Top20 XIRR gain pp | Top20 DD gain pp | Changed Top3 % | Matched Top20 dates |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| champion | 0.03218 | +0.00000 | +0.00 | +0.00 | +0.00 | +0.00 | +0.00 | 0.0 | 16 |
| constrained_high | 0.03448 | +0.00230 | +2.26 | -0.16 | -0.60 | +2.23 | -0.98 | 20.8 | 16 |
| constrained_residual | 0.03661 | +0.00443 | +2.18 | -0.09 | -0.50 | +1.55 | -0.80 | 19.9 | 14 |

Higher DD gain means a less severe drawdown. RankIC is within-sector Spearman correlation with twelve-month SIPXIRR, sector-balanced then date-balanced. GlobalTop20 comparisons are matched by date and cost100bp per buy and final sale, using next adjusted Open and the existing corporate-action exclusions. Snapshot coverage inherits the five-year factor requirement and current-survivor, retrospective-sector limitations. Comparisons are against the same reduced common-cohort champion rather than all4,436current stocks.

## Fixed decisions

- **constrained_residual**. Positive portfolio years 3/4. Winsorized return gain +2.11pp. Worst leave-one-date-out gain +0.21pp. Solver fallback 0.40%. Failed requirements: goal. Clears the prior incremental IC floor: False.
- **constrained_high**. Positive portfolio years 3/4. Winsorized return gain +2.22pp. Worst leave-one-date-out gain +0.11pp. Solver fallback 0.27%. Failed requirements: goal. Clears the prior incremental IC floor: False.

The strict goal-hit requirement is the only failed primary requirement for both policies. The decrease is small in percentage points, but the criterion was not relaxed after results. Their positive IC increments also remain below the prior0.010134924head-family hurdle. These policies can be retained as experimental tradeoff candidates without describing them as validated replacements.
- Descriptive365day-block95%Top20XIRR interval for constrained_residual: [-9.52,+8.65]pp, on 14 matched dates.
- Descriptive365day-block95%Top20XIRR interval for constrained_high: [-6.36,+8.75]pp, on 16 matched dates.

Both intervals include losses. In particular, the constrained-high policy’s annual average Top20XIRR differences are -8.69pp in2020,+2.01pp in2021,+5.18pp in2022and+10.41pp in2023. The three positive years and positive leave-one-date-out results do not establish stability in every market regime.

## Higher-cost diagnostic

After seeing primary results, we fixed an additional200bp-per-side replay of the same selections. This diagnostic does not change the primary gate or add candidate weights.
- constrained_residual: Top20XIRR delta +1.50pp, drawdown delta -0.81pp, 14 matched dates.
- constrained_high: Top20XIRR delta +2.16pp, drawdown delta -1.01pp, 16 matched dates.

This round asks a new investment-selection question. It accepts IC loss up to0.005 in exchange for at least1ppTop20XIRR gain, robust positive gains, at least3positive years, nonworsening goal hit and professor constraints, drawdown cost<=2pp and support. Those rules were fixed before this policy’s results. They differ from the preceding pilot’s IC-superiority question and must not be conflated. No result can turn reused development dates into independent validation.

## Solver and audit

1492 sector/date/policy optimizations were logged. 1487 returned confirmed optimal feasible solutions. Every actual outputTop3 set was independently checked against all five factor bounds. The champion set was a known feasible fallback. Eight tests passed, including exhaustive small-case comparison, preference constraint enforcement, missing-factor rejection, score ties, residual self-exclusion and prefix invariance. Both solver and feature calculations used one compute thread under the Windows12.5%CPUcap and4sactive/2srest governor. NoGPU.

The cumulative incomplete registry now contains 309 documented attempts, with prior IDs preserved. Scan receipts cover409archived source paths and found no prior MILP/linear-programming/constrained-rerank implementation. This is evidence relative to saved history, not proof that every older informal search was catalogued.

## Commercial software comparison

Official pages from Trendlyne,Tickertape,MarketsMojo and Stockopedia were reviewed. A matching historical Indian-stock score export was not obtained. Therefore numerical superiority to these platforms is unmeasured. [The access matrix and exact comparison contract](commercial_benchmark_access_20261105.md) describe the evidence needed. The academic and internal baselines are not substitutes for those proprietary predictions.

## References

- Celis,L.E.,Straszak,D.,&Vishnoi,N.K.(2018). Ranking with fairness constraints. ICALP2018. https://arxiv.org/abs/1704.06840. General constrained-ranking inspiration, adapted here to numerical preference-factor bounds rather than fairness categories.
- SciPy developers. scipy.optimize.milp documentation. https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html. Mixed-integer solver interface, with HiGHS threads fixed to1.
- Blitz,D.C.,Huij,J.,&Martens,M.(2011). Residual momentum. Journal of Empirical Finance,18(3),506–521. https://doi.org/10.1016/j.jempfin.2011.01.003. Residual-feature inspiration from the prior pilot.
