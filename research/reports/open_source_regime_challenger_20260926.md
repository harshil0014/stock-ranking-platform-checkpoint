# Open-source regime challenger — 2026-09-26

## Decision

Retain the immutable **67% Goal + 33% LightGBM LambdaRank** control from
`personalized-challenger-d499580-20260926`. None of the preregistered regime
challengers improved mean top-20 goal shortfall on the exact frozen common
cohort. No result is promoted to production or to the frozen prospective test.

## Fixed experiment

- Calibration: 2010-01-04 through 2015-12-31, 1,465 NIFTY 50 trading days.
- Online inference: 2016-01-04 through 2026-09-18, 2,640 trading days.
- Evaluation: six annual validation dates, nine investor profiles, 54 query
  blocks, and an average 2,475.7 executable securities per block.
- Ranker, labels, maturity purge, stock features and 67/33 blend stayed fixed.
- Every blend was computed after applying the original frozen common cohort.
- Row-level reconstructed control predictions matched the saved control within
  `1.11e-16`; aggregate goal shortfall reproduced `0.07627221047547908`.

## Upstream systems

| System | Exact implementation | Published basis | Use |
|---|---|---|---|
| Jump model | `jumpmodels==0.1.1`, `jumpmodels.jump.JumpModel` | Nystrup et al., *Expert Systems with Applications* (2020), DOI `10.1016/j.eswa.2020.113307`; package maintained by the research authors | Discrete two-state model, penalty 50, author example's nine features and upstream online decoder |
| Volatility baseline | `scikit-learn==1.9.0`, `GaussianMixture` | Dempster, Laird and Rubin (1977), DOI `10.1111/j.2517-6161.1977.tb01600.x` | Two-component mixture on calibration-standardized 20-day log downside deviation |
| HMM benchmark | `hmmlearn==0.3.3`, `GaussianHMM` | Rabiner (1989), DOI `10.1109/5.18626` | Two-state diagonal Gaussian HMM on the same nine market features |
| Drift signal | `river==0.22.0`, `ADWIN` | Bifet and Gavaldà (2007), DOI `10.1137/1.9781611972771.42` | Sequential absolute-return change signal combined with JumpModel |
| Portfolio layer | `skfolio==1.4.0`, `EqualWeighted` and `InverseVolatility` | skfolio paper, arXiv `2507.04176` | API compatibility confirmed; excluded from the tournament because it changes the frozen independent-stock SIP estimand and lacks a shared-budget, whole-share, corporate-action-consistent panel |

No statistical estimator was recreated locally. The custom work comprises 568
nonblank, noncomment lines: 244 adapter/evaluation lines, 309 deterministic
runner lines, and 15 verifier lines. Only nine feature formulas were transcribed
from the upstream author's example; the upstream package performs JumpModel
fitting and online decoding.

## Results

All rows below have 100% coverage on the common cohort. Precision and recall use
the realized top 20 as the relevant set, so their values are equal.

| Candidate | P@20 / R@20 | NDCG@20 | Pairwise | Rank IC | Goal attainment | Goal shortfall | Mean XIRR | Mean drawdown | Turnover |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Frozen control | 0.01019 | 0.46774 | 0.50008 | -0.00289 | 0.43611 | **0.07627** | 0.45788 | -0.31618 | 0.92556 |
| JumpModel | 0.00926 | **0.47672** | 0.49864 | **-0.00161** | 0.42130 | 0.08062 | 0.44256 | -0.32627 | 0.93333 |
| Gaussian volatility | 0.00833 | 0.45886 | **0.50079** | -0.00164 | 0.40741 | 0.08919 | 0.88960 | -0.33166 | 0.91778 |
| Gaussian HMM | 0.00370 | 0.46967 | 0.49874 | -0.00768 | **0.43981** | 0.09398 | 0.34601 | -0.35058 | 0.91444 |
| JumpModel + ADWIN | 0.00833 | 0.45802 | 0.49987 | -0.00527 | 0.42963 | 0.08992 | 0.40422 | -0.35032 | 0.93889 |

JumpModel changed every ranker prediction, had 144 tree split uses, and raised
NDCG@20 by 0.00898 and Rank IC by 0.00128. It still increased goal shortfall by
0.00435, lowered goal attainment by 0.01481, and improved shortfall in only 21
of 54 query blocks. Its date-average shortfall was better on three of six dates,
but its profile-average was better for only one of nine profiles. It therefore
contains conditional ranking information without adding investor utility under
the fixed architecture.

HMM increased shortfall by 0.01771. The volatility baseline increased it by
0.01292. Adding River to JumpModel increased it by 0.01365 versus the control
and by 0.00930 versus JumpModel alone. ADWIN issued no discrete drift detections
under its published default threshold; its running estimates were still exposed
to LambdaRank, but they added no independent value.

The volatility candidate's high mean XIRR and terminal wealth came with worse
median XIRR, goal shortfall, goal attainment and drawdown. The mean was driven by
skewed winners and did not satisfy the preregistered investor objective.

## Causal and reproducibility audit

- Preprocessing and every estimator were fit only on the fixed 2010–2015
  calibration interval.
- JumpModel used upstream `predict_online`; HMM used only the last posterior of
  each sequence truncated at the decision date; mixture inference was per day;
  ADWIN received one chronological update stream.
- Removing all observations after 2022-06-30 and rebuilding produced identical
  earlier snapshots within `1e-12`.
- Every stock-label endpoint was strictly earlier than its evaluation date.
- Market observations were never later than their decision dates.
- Corporate-action, whole-share, residual-cash, evidence and blocker columns
  came unchanged from build-04. No unavailable row was imputed into the cohort.
- Compact results, top selections, model hashes, package versions, input hashes,
  state snapshots and leakage evidence are covered by a SHA-256 manifest.

## Research conclusion

The strongest scientifically defensible combination is still the frozen
control. The next experiment should test the same frozen JumpModel feature on a
larger set of genuinely prospective decision dates after the shadow outcomes
mature. Six retrospective dates provide too little regime diversity to estimate
stable conditional interactions, and changing penalties or blend weights now
would turn this result into outcome-driven tuning.
