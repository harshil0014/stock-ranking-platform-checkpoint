# Completed sector-ranking research — 10 October 2026

**Selected research candidate: `rank_xendcg_balanced_blend0.25`.** This continuation completed 32 model/blend candidates from 48 annual fits, plus one fixed price-activity follow-up. The selected candidate was compared with 37 recoverable earlier policies, including the baseline, professor formula and prior sector champion. All nine profiles were included.

Its score is **75% previous guarded score + 25% new `rank_xendcg_balanced` sector-percentile score**. This is a blended candidate. Its older component can retain older data defects; rebuilding the new component does not certify the inherited features.

## Coverage

The export ranks **all 4,436 stocks** in **59 sector/classification groups**. **4303** have usable rebuilt price inputs; **133** have explicitly marked missing or unresolved inputs. It uses the **3 October 2026 snapshot**, not live 10 October prices. A fallback score does not certify input completeness or tradability.

## Matched comparison with the previous guarded model

Equal-sector, equal-profile Top-3 SIP metrics; returns capped to [−100%, +100%] before the per-sector calculations. These are ranking diagnostics, not a realizable portfolio backtest.

| Scope | Period | Model | XIRR | Drawdown | Achievement | Shortfall | NDCG | Rank IC |
|---|---|---|---:|---:|---:|---:|---:|---:|
| common | development | Previous | 31.04% | -25.22% | 56.20% | 5.37% | 0.6051 | 0.0174 |
| common | development | New | 31.20% | -24.95% | 56.33% | 5.30% | 0.6115 | 0.0252 |
| common | exposed | Previous | 0.22% | -31.06% | 23.04% | 11.79% | 0.6498 | 0.1494 |
| common | exposed | New | 0.59% | -30.56% | 23.12% | 11.56% | 0.6542 | 0.1551 |
| expanded | development | Previous | 33.82% | -25.72% | 57.26% | 5.23% | 0.5829 | 0.0184 |
| expanded | development | New | 34.75% | -25.43% | 58.03% | 5.16% | 0.5909 | 0.0262 |
| expanded | exposed | Previous | -0.98% | -31.85% | 22.89% | 12.00% | 0.6331 | 0.1417 |
| expanded | exposed | New | -0.22% | -31.31% | 22.93% | 11.76% | 0.6371 | 0.1521 |

## Whole-sector ordering accuracy

Pair accuracy awards one point for correctly ordering two stocks by their later XIRR, zero for reversing them and half for ties. It is measured on identical outcome-covered sector peers. It is not the probability that a stock makes money.

| Scope | Period | Model | Pair accuracy |
|---|---|---|---:|
| common | development | guarded_previous | 50.49% |
| common | development | rebuilt_selected | 50.85% |
| common | development | sector_incumbent | 49.48% |
| common | exposed | guarded_previous | 55.18% |
| common | exposed | rebuilt_selected | 55.36% |
| common | exposed | sector_incumbent | 54.69% |
| expanded | development | guarded_previous | 50.59% |
| expanded | development | rebuilt_selected | 51.02% |
| expanded | exposed | guarded_previous | 55.05% |
| expanded | exposed | rebuilt_selected | 55.30% |

Sector-resampling uncertainty and the fraction of sectors improved are saved in `experiments/sector-accuracy-20261010/paired_sector_accuracy_differences.csv`. These describe the already-exposed sample; they do not correct repeated research selection.

## Professor, baseline and company-evidence checks

Recent-period capped Top-3 outcomes below use matching populations separately for each opponent. The professor comparator replays the project whole-share policy; it is not a claim that the screenshot supplies independent outcomes for every stock.

| Earlier policy | New XIRR | Earlier XIRR | New rank IC | Earlier rank IC |
|---|---:|---:|---:|---:|
| Baseline four-factor formula replay | 1.24% | -2.87% | 0.1635 | 0.0769 |
| Professor whole-share project policy | -0.14% | -7.19% | 0.1459 | 0.0428 |
| Production sector champion | 0.59% | -0.77% | 0.1551 | 0.1326 |
| V17 | -0.25% | 3.79% | 0.1462 | 0.0734 |

The current company-evidence rubric is a separate diagnostic. Higher is better; it is not a calibrated probability.

| Scope | Model | Top-3 company rubric |
|---|---|---:|
| common | guarded_model_score | 0.5603 |
| common | open_model_score | 0.5576 |
| common | rebuilt_score | 0.5628 |
| common | sector_incumbent | 0.5579 |
| expanded | guarded_model_score | 0.5751 |
| expanded | open_model_score | 0.5762 |
| expanded | rebuilt_score | 0.5755 |

## Tradeoffs and stock-level review

- The selected model has **202 / 1512 Top-3 regressions** and **761 / 4536 total regressions** across the original comparison cells. **0 / 32** candidates pass the full broad gate. Aggregate improvements do not establish universal superiority.
- Recent expanded-universe sector tradeoffs against the previous guarded model include Realty: -7.27 percentage points Top-3 XIRR; IT - Software: -5.99 percentage points Top-3 XIRR; Printing & Publication: -5.00 percentage points Top-3 XIRR. Complete per-sector and per-profile differences are saved alongside the rankings.
- Against the 37 earlier policies, **0** are nonworse in every recorded cell. All per-policy and per-profile results are retained. Missing or non-comparable archived studies are not declared beaten.
- A separate candidate was selected solely for development-period whole-sector rank correlation. Its export and recent-period results are in the accuracy report; that alternative criterion does not replace the original promotion gate.
- Every current stock received structural checks. Among 176 sector Top-3 entries, 15 have short price histories and 3 have more than half zero daily changes. All flags are retained in the compact ranking export.
- The KALYANI review exposed a nearly flat price series ranking first in a sector. A fixed activity-tier experiment moved such stocks down but reduced recent ordering accuracy. It is documented separately and has not silently overridden the selected model.
- The existing company-evidence rubric is joined to all current ranks. This is reused evidence, not 4,436 fresh company investigations or an independent future-return oracle.

## Verification and limitations

- Rebuilt high, momentum, trend and downside features use observations available by each decision date. Unresolved adjustment windows and stale inputs are masked. Training outcomes end before the annual test fold.
- Historical predictions were reproduced from every saved annual model. Current exports reproduce the serialized model and within-sector ranking arithmetic. Source hashes and test results are retained.
- **33 distinct tests passed**, including future-price independence, scale invariance, corporate-action guards, frozen-runtime compatibility, sector isolation, pair-accuracy arithmetic and website custom-profile recomputation.
- All historical periods have already been exposed by previous research. The current identity universe and sector classifications are used retrospectively; this is not a survivor-free historical exchange-membership reconstruction. Corporate-action and execution-history reconstruction remains incomplete; masks do not prove that every surviving outcome is correct.
- The live ranking model has not been switched. The frozen-runtime corporate-action guard bug was fixed and tested. Research results are completed, with the remaining qualification limits stated above.

## Research sources

[ICML 2023 learning-to-rank study](https://proceedings.mlr.press/v202/lyzhin23a.html), [financial cross-sectional ranking research](https://arxiv.org/abs/2012.07149), [LightGBM implementation documentation](https://lightgbm.readthedocs.io/en/latest/Parameters.html), and [CatBoost ranking documentation](https://catboost.ai/docs/en/concepts/loss-functions-ranking?lang=en). These informed the tested objectives; performance claims come from the saved project experiments.

## Deliverables

- Full compact ranking: `experiments/sector-research-final-20261010/all_4436_sector_rankings.csv`
- Completed run manifest: `experiments/sector-research-final-20261010/completion.json`
- All 32 candidate comparisons: `experiments/sector-research-final-20261010/all_32_candidate_trials.csv`
- Accuracy diagnostic: `research/reports/sector_accuracy_20261010.md`
- Activity review: `research/reports/sector_activity_review_20261010.md`
- Earlier-policy audit and company rubric: `experiments/sector-price-rebuild-20261010/`
