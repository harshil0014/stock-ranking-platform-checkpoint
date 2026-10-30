# Expanded full-coverage sector ranking research — 8 October 2026

## Decision

Completed 275 new candidates, 72 pooled annual fits and 18 additional annual global/sector expert sets. Strict clean-dominance passes: **0**. Production has not been replaced.

The strict gate checks Top-1, Top-3 and Top-5; 2020–2023 and 2024–2025; common and expanded populations; raw and capped XIRR; five metrics; and both the production champion and the previously frozen full-coverage challenger. There are 240 directional comparisons per candidate. These are overlapping diagnostics, not 240 independent statistical tests.

## Methods

- CatBoost YetiRank, XGBoost NDCG, Extra Trees and ridge regression; each learns return, balanced or defensive within-sector relevance.
- Four score options per trained model: standalone and 25%, 50%, 75% blends with the frozen full-coverage challenger; two equal-family ensembles.
- Follow-up: 198 equal two-model combinations, each contributing 5%, 10% or 20% beside the frozen challenger. This was adaptive after viewing first-round results.
- Sector-specific experiment: 27 partially pooled ridge candidates, with equal date-sector training weights, at least 120 rows/four dates per local model, and 25%/50%/75% local shrinkage weights. Eighteen annual global/sector model sets trained separately.
- Existing price/high/downside/momentum features plus trading continuity and annual observation count. No current fundamentals enter historical training.
- Each test year is predicted using training outcomes ending strictly before that year. All dates have already been researched, so model selection is retrospective, not a fresh holdout.
- Aggregate metrics weight sectors equally after averaging their decision dates. Common scope compares identical stocks; expanded scope allows the new model to choose outside the production eligibility screen.

## Candidate comparison

| Candidate | Regressing cells / 240 | Worst directional difference | Strict pass |
|---|---:|---:|---|
| pair__catboost_defensive__ridge_defensive__0.05 | 24 | -0.149932 | False |
| pair__catboost_balanced__ridge_defensive__0.05 | 25 | -0.149892 | False |
| pair__catboost_defensive__ridge_balanced__0.05 | 26 | -0.146408 | False |
| pair__xgboost_balanced__xgboost_defensive__0.2 | 27 | -0.143893 | False |
| pair__catboost_defensive__extra_trees_balanced__0.05 | 28 | -0.147995 | False |
| pair__ridge_balanced__ridge_defensive__0.05 | 29 | -0.151242 | False |
| pair__xgboost_balanced__extra_trees_return__0.05 | 29 | -0.153314 | False |
| pair__xgboost_defensive__extra_trees_return__0.05 | 31 | -0.149883 | False |
| pair__extra_trees_defensive__ridge_defensive__0.05 | 31 | -0.151168 | False |
| pair__xgboost_balanced__ridge_defensive__0.2 | 32 | -0.141676 | False |
| pair__catboost_defensive__extra_trees_return__0.05 | 32 | -0.150024 | False |
| pair__extra_trees_return__extra_trees_defensive__0.05 | 32 | -0.150290 | False |

Ranking this table by fewer regressions is a diagnostic choice, not evidence that its first row is a deployable champion. XIRR tails can dominate the worst difference. All candidate results remain in the trial ledger.

## Coverage and limits

The frozen challenger supplies 4,436 finite scores versus 1,746 production scores at the base profile. Seventeen stocks have no usable price evidence and receive an explicitly neutral tied prior. Full coverage is not equivalent to reliable price data, trade eligibility, or predictive accuracy. Current sector labels and a surviving universe are used retrospectively. Corporate-action and extreme-return concerns remain. Prior full-coverage checks showed profile and Top-1 regressions. A clean new production champion cannot be declared solely from a favorable Top-3 average.

## Source-level data warning

The largest historical label is Sejal Glass (INE955I01044), decision date 2021-03-31, future XIRR 9,086.008636 (908,600.86%). Its [2021–22 annual report](https://sejalglass.co.in/document/Annual%20Report%202021-2022.pdf) documents consolidation from 33,550,000 existing shares to 100,000 shares, record date 10 May 2021, and trading resumption on 13 December 2021. This is a concrete corporate-action concern, not proof that the cached label has been correctly or incorrectly adjusted. Reconcile holdings and cash flows before relying on this outcome. Capping returns is sensitivity analysis, not a repair.

## Research sources

- [CatBoost, NeurIPS 2018](https://proceedings.neurips.cc/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html)
- [XGBoost, KDD 2016](https://doi.org/10.1145/2939672.2939785)
- [Extremely randomized trees, Machine Learning 2006](https://doi.org/10.1007/s10994-006-6226-1)

Peer review supports the algorithmic methods, not the profitability of this application.

## Reproduction

Run `python research/runners/full_coverage_open_models_20261008.py`, then `python research/runners/audit_open_models_20261008.py`. Isolated dependency versions: CatBoost 1.2.10 and XGBoost 3.4.1. Data and model artifacts are under `experiments/full-coverage-open-models-20261008/`; previous challenger artifacts remain intact.

The verification file independently recomputes all strict gates, checks all 72 training cutoffs and the 18 local-expert cutoffs, and hashes protocol/results. Existing coverage, formula and independent-rubric regression suite: 34 tests passed in this run. One additional batched-evaluator equivalence test passed (35 total); a real-data comparison also matched 702 reference rows.

The frozen full-coverage challenger itself regresses in nine of the 120 comparable metric cells against production. A new candidate with fewer regressions among the new algorithms is not automatically better than that existing challenger.

## Frozen new research candidate

Name: `pair__catboost_defensive__ridge_defensive__0.05`. Status: `RESEARCH_CANDIDATE_WITH_REGRESSIONS`. Full current export: 4436 stocks, snapshot 2026-10-03. Nine-profile regressions: 465 / 2160 cells. These are diagnostics on reused dates, not independent validation.

The full rankings and all-profile deltas are saved alongside the experiment. The scoring CLI reproduces the frozen package without training.

Base profile, common universe, Top-3; equal-sector/date basket-median XIRR:

| Period | Return treatment | Production | Frozen challenger | New candidate |
|---|---|---:|---:|---:|
| development | raw | 34.57% | 34.31% | 35.27% |
| development | capped | 31.08% | 31.11% | 31.51% |
| exposed | raw | 0.39% | 3.70% | 4.21% |
| exposed | capped | -0.01% | 1.00% | 1.51% |

At the base profile's Top-3 cutoff, the new candidate has 0 regressions across 80 comparisons against the two prior models. This narrower result must not be generalized to Top-1, Top-5 or every profile.
