# Conservative sector improvement experiment — 10 October 2026

Objective: reduce the remaining sector/profile regressions without replacing the fixed benchmark or using future outcomes to choose a sector expert.

Tested six policies over six existing experts. Four retain the anchor unless each metric has a nonnegative paired lower margin on at least four/eight completed dates; two use a combined-utility criterion. Routing uses same-sector, same-profile, completed observations within five years. The margin is a heuristic, not an independence-based confidence guarantee.

| Candidate | Regressions / 5,832 | Regressions vs anchor | Improvements vs anchor |
|---|---:|---:|---:|
| conservative_n8_w0.5 | 1188 | 430 | 470 |
| conservative_n4_w0.5 | 1182 | 441 | 641 |
| conservative_n4_w1.0 | 1220 | 481 | 689 |
| conservative_n8_w1.0 | 1239 | 482 | 458 |
| utility_n8_w1.0 | 1624 | 756 | 532 |
| utility_n8_w0.5 | 1596 | 772 | 506 |

**0 / 6 policies pass the full gate.** Development-selected policy: `conservative_n8_w0.5`. It has 430 regressions and 470 improvements versus the current research candidate across 1,296 parent comparison cells. This comparison includes all nine profiles, Top1/3/5, common/expanded universes, raw/capped outcomes and six metrics.

## Verification

- 797,443 historical stock/date/profile rows have finite scores for every policy; identities match the earlier experiment.
- Every routing feedback endpoint is strictly earlier than its decision date. All saved sector aggregates reproduce the summary within 1e-12.
- Two tests verify baseline fallback and rejection of a risk regression even when other metrics improve.
- Previously exposed historical dates remain exposed. There is no fresh holdout and no claim of guaranteed market superiority.

## Decision

The existing full-coverage research export remains the reference. A routing policy that regresses against it is not relabeled a universal champion. No live model was replaced. All experiment scores and evidence are retained for inspection.

## Research

[Safe Policy Improvement with Baseline Bootstrapping, ICML 2019](https://proceedings.mlr.press/v97/laroche19a.html) motivates retaining a baseline when evidence is insufficient. [Mixing past predictions, PMLR 2020](https://proceedings.mlr.press/v128/korotin20a.html) motivates delayed-feedback expert aggregation. This experiment is an adaptation of those ideas, not a replication of either algorithm or its guarantee.

A universal future-performance guarantee cannot be established from this finite dataset. The unchanged retrospective all-metric gate is testable, and the exact result above is the acceptance criterion used here.
