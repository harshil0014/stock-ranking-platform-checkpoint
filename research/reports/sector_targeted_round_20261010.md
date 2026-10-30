# Targeted sector-ranking improvement round — 10 October 2026

This follow-up tests two specific responses to the remaining regressions: (1) conservative sector/profile expert selection using only completed feedback; (2) a goal-aware LightGBM target that directly includes achievement and shortfall. All ten variants retain the original benchmark and additionally face the latest rebuilt candidate as a fifth reference.

| Variant | Regressions / 5,832 | Regressions vs latest candidate | Improvements vs latest candidate |
|---|---:|---:|---:|
| conservative_n8_w0.5 | 1188 | 430 | 470 |
| conservative_n4_w0.5 | 1182 | 441 | 641 |
| conservative_n4_w1.0 | 1220 | 481 | 689 |
| conservative_n8_w1.0 | 1239 | 482 | 458 |
| utility_n8_w1.0 | 1624 | 756 | 532 |
| utility_n8_w0.5 | 1596 | 772 | 506 |
| goal_aware_l1_blend0.1 | 2234 | 975 | 315 |
| goal_aware_l1_blend0.25 | 2283 | 927 | 369 |
| goal_aware_l1_blend0.5 | 3828 | 1099 | 195 |
| goal_aware_l1_blend1.0 | 5036 | 1149 | 147 |

**0 of 10 variants satisfy every comparison cell.** No unchanged-score policy is counted as an improvement. The development-selected follow-up is `conservative_n8_w0.5`; selection does not use the recent period.

The new goal target is 50% achieved-target indicator, 25% inverse-shortfall sector percentile, 12.5% return percentile and 12.5% drawdown percentile. Features remain the same 70 price/profile features. Six annual models use only outcomes finishing before the next test year; four weights blend their scores with the previous guarded model.

## Verification

- Replayed all six saved annual goal models against complete historical inputs, with maximum error below 1e-15. Current goal-model scores reproduce exactly and cover all 4,436 stocks.
- Verified identical historical query populations between goal and anchor experiments. All routers use feedback that ended strictly before their decisions.
- Two new router tests passed, covering insufficient-data fallback and rejection of a risk regression. The preceding completed round had 33 distinct passing tests.
- All current rankings still use the 3 October snapshot; 4,303 usable input series and 133 flagged input gaps remain. New objectives do not fill missing data.

## Interpretation

The fixed retrospective gate is a testable ambition. A universal guarantee across future market conditions is not something these experiments can establish. Historical periods were already exposed, outcomes have known adjustment/execution limitations, and repeated testing is not fresh validation.

The existing selected full-coverage research candidate and live UI remain unchanged unless a new policy clears the stated comparison gate. Neither a selective metric nor a reduced universe is used to manufacture a champion.

## Research foundations

[Baseline Bootstrapping, ICML 2019](https://proceedings.mlr.press/v97/laroche19a.html) and [delayed-feedback expert aggregation, PMLR 2020](https://proceedings.mlr.press/v128/korotin20a.html) motivated the routing hypotheses. Their formal guarantees do not apply to this adapted ranking experiment.

Artifacts: `experiments/sector-targeted-round-20261010/`, `experiments/sector-goal-aware-20261010/`, and `experiments/sector-conservative-router-20261010/`.

## Can every individual decision dominate all references?

A separate hindsight diagnostic checks whether any stock in each matched query can simultaneously attain the best return, drawdown and shortfall among the references’ selected Top-1 stocks. It is never used for training or selection.

| Scope | Period | Queries | No feasible dominating stock |
|---|---|---:|---:|
| common | development | 6457 | 854 (13.23%) |
| common | exposed | 5175 | 505 (9.76%) |
| expanded | development | 7419 | 484 (6.52%) |
| expanded | exposed | 5700 | 201 (3.53%) |

Thus universal dominance at every individual Top-1 decision is infeasible for these cohorts and outcomes. This **does not prove the aggregate promotion gate impossible**, and it inherits the dataset’s limitations. It identifies conflicting objectives rather than just a weak learning algorithm.
