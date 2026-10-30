# Major sector ranking research: live work log

## Objective and constraints

Pursue the complete brief in attachment `512468a9-e12a-4d12-93ce-7e5a42dd1b24/pasted-text-1.txt`: a defensible personalized ranking champion, complementary open-source models, full historical/profile/sector coverage, independent financial review, Sir diagnostic, reproducible comparisons and honest limitations. Preserve existing research and website. No remote deployment. Mean XIRR has zero selection weight. This work log is not a completion claim.

## Completed evidence before the expanded round

- The retained reference is `rank_xendcg_balanced_blend0.25`: 75% previous guarded score and 25% rebuilt LightGBM rank_xendcg balanced sector score. The guarded score itself is 80% open model and 20% profile defensive model. This is an empirical reference, not a universal winner.
- Earlier research includes 37 historical policy comparisons, full-universe professor arithmetic, price/corporate-action audits, sector-specific models, constrained routing, goal-aware models, and current evidence review. The reports and original experiment artifacts remain intact.
- TabPFN teacher/student round: 60 candidates, 15 teachers, 100 students/controls, no broad gate pass. Some small gains depend on the metric and population.
- CatBoost pairwise correction: 12 candidates, 20 fits, no broad gate pass. Recent expanded pair accuracy: champion 55.3024%, uniform small correction 55.3073%, mistake-weighted small correction 55.3063%. This does not support a material universal improvement. Full historical/current replay maximum error 2.22e-16, identical populations verified, 3 tests passed.

## Current hypotheses being executed

1. Independent return, downside and goal models may contain information absent from residual-only corrections. Train them on the full valid guarded prepared history, including pre-2020 rows, with strict outcome endpoint cutoffs.
2. TabM neural internal ensembles may complement trees. Test compact inputs and embedded full features, three simultaneous targets, official open-source implementation.
3. EBM may isolate stable feature effects and limited interactions. Test additive and eight-interaction models, three separate targets.
4. Extra Trees and Ridge provide nonlinear variance-reduction and simple linear controls on the same chronological problem.
5. Weak individual models may help combinations. Evaluate standalone scores, small/full blends, means, medians, nonnegative learned stacking and market-breadth-dependent stacking.

The protocol files are written before outcome evaluation. Independent models use no champion score or stock identity as features. New learned stack coefficients use only matured out-of-time predictions. Training permutations are optimization order, not random train/test splits. TabM uses fixed predeclared epochs, not a random validation split. EBM random validation is disabled.

## Literature and intended scope

| Approach | Primary source | Treatment in this project |
|---|---|---|
| TabM neural ensembling | [ICLR2025 paper and official code](https://github.com/yandex-research/tabm) | Official implementation, adapted to multi-target sector percentiles; not a reproduction of the paper's datasets or tuning budget |
| Explainable boosting / GA2M | [InterpretML and original papers](https://interpret.ml/docs/ebm.html) | Official EBM, additive versus interactions, separate return/risk/goal specialists |
| Tree-versus-neural failure analysis | [NeurIPS2022 benchmark](https://proceedings.neurips.cc/paper_files/paper/2022/hash/0378c7692da36807bdec87ab043cdadc-Abstract-Datasets_and_Benchmarks.html) | Motivation for matched simple/tree controls and avoiding claims that newer architecture automatically wins |
| TabPFN | [Nature paper](https://www.nature.com/articles/s41586-024-08328-6) | Completed direct inference and distillation rounds; retain strongest existing policies as combination inputs |
| Pairwise ranking | [CatBoost objectives](https://catboost.ai/docs/en/concepts/loss-functions-ranking) | Completed pairwise champion correction; weak aggregate change, retain as ensemble input |
| Financial regime adaptation | [Microsoft Qlib](https://github.com/microsoft/qlib) | Investigated framework and temporal routing concepts. Breadth-conditioned stack is a project adaptation, not a reproduction of TRA/DoubleAdapt or their guarantees |
| Quality versus junk | [Authors' paper](https://www.aqr.com/Insights/Research/Working-paper/Quality-minus-Junk) | Current fundamental evidence diagnostic only. Saved current fundamentals cannot be backfilled into historical features |

## Known data limitations that must survive final reporting

- Current snapshot is 2026-10-03, not live prices. 4,436 numerical scores include 4,303 usable price-feature rows and 133 fallbacks.
- All historical evaluation dates are already exposed through prior research. Chronological fitting avoids direct future-label training; it does not undo adaptive reuse of evaluation data.
- Current-universe membership and classifications are retrospective, so survivorship and classification bias remain. Not every inherited price/corporate-action defect is certified fixed.
- Current fundamentals, liquidity and company-evidence coverage are incomplete. No model can legitimately claim complete financial understanding from absent point-in-time data.
- Historical rank metrics and SIP basket-median XIRR diagnostics are not a transaction-cost-complete tradable portfolio backtest.
- Sir is an independent arithmetic diagnostic, not a future-return truth label. The company-evidence rubric is an explicit sensitivity-tested judgment aid, not an objective stock correctness oracle.

## Required completion evidence (still open)

- Completed specialist fits and full serialized replay, learned/fixed combinations, development lock and exposed-date outcomes.
- Complete experiment ledger and contribution/ablation comparisons, including rejected methods and failure explanations.
- Per-profile, per-sector, worst-case, ranking stability and cohort checks.
- Current Top1/3/20/100 within sectors, with financial/evidence explanations and Sir comparisons on matching populations.
- Explicit evidence-backed winner/challenger verdict, architectural formula, references, source hashes and reproducible commands.
- Requirement-by-requirement audit against the original brief; do not equate one completed research round with the full goal.
