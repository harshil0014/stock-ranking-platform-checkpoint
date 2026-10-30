# Specialist ensemble findings — interim, not a final champion declaration

Completion addendum: the neural continuation, matched controls, transport audits and final handoff are now complete. The authoritative consolidated verdict is `major_research_final_20261011.md`; the interim text below is retained as the historical checkpoint, not a live pending-task list.

The completed six-family specialist round does not justify replacing the retained research reference. All42annual/current model sets reproduce; all13development-selected finalists fail the recorded broad comparison gate. The four neural continuation budgets are pending and this report does not close the full user goal.

## Architecture actually tested

Independent return, downside and goal heads use official EBM (additive/eight-interaction), ExtraTrees, Ridge, and compact/embedded TabM. Compact models have15inputs, full models70; all use the original annual endpoint cutoffs and valid history. The neural models use the official TabM package with k4 internal members, two64-wide blocks and12fixed epochs. Their multi-target adaptation is not a literal reproduction of the paper's benchmark. Current fit uses1,115,140rows, starting with2016decisions, with endpoints through2026-08-31 before the2026-10-03snapshot.

The112policies include individual heads, fixed return/risk/goal combinations, means/medians, reference blends and nonnegative temporal stacks. Stacks learn on already-matured out-of-time component predictions. The breadth-conditioned version splits at training-median sector breadth and shrinks regional weights toward global coefficients. All raw weights, dates and reference residual mass are in `learned_component_weights.csv`; these are not universal factor percentages.

The retained reference is75%previous guarded score plus25%rebuilt LightGBM rank_xendcg balanced score. The guarded score is80%open-model score plus20%profile-defensive score. Its existing defects/limits remain; retention is not certification of financial superiority.

## Matched primary results

Expanded universe, capped outcomes, sectorTop3, equal sectors/profiles. XIRR below is the established basket-median diagnostic, not a transaction-cost-complete portfolio return. MeanXIRR had zero selection weight.

| Period/model | XIRR | Drawdown | Achievement | Shortfall | NDCG | RankIC |
|---|---:|---:|---:|---:|---:|---:|
| Development reference |34.7466%|-25.4339%|58.0350%|5.1579%|.590933|.026168|
| Development breadth stack |36.1620%|-27.6195%|57.8777%|5.2965%|.601325|.036800|
| Exposed reference |-0.2222%|-31.3087%|22.9269%|11.7564%|.637099|.152114|
| Exposed breadth stack |-0.4972%|-31.0990%|22.6357%|11.6433%|.637992|.153148|

The stack improves943/1296cells but regresses347; larger counts do not compensate automatically for worse achievement/returns or risk in important periods. All gates use overlapping diagnostics, not1296independent tests. Expanded exposed pair accuracy is55.3374% for the stack versus55.3024%reference. RecentTop3 retention is68.37896% versus71.04908%reference, and rank stability .822917 versus.843043. The saved primary financial rubric falls from.569721 to.568335. Its current sectorTop3 union contains51flagged entries among176; Kalyani Commercials remainsNo1 in its sector. Bank flags describe missing bank-specific analysis, not a generic debt-based rejection.

ExtraTrees improves exposed whole-sector pair accuracy to55.5243% but its selected blend regresses onTop3returns, risk, achievement, shortfall andNDCG. EmbeddedTabM standalone retains only42.37% of exposedTop3names versus71.05%reference and has53.10%pair accuracy. That is evidence against its standalone deployment, not against every ensemble use.

## Actual component-removal evidence

Holding the learned stack fixed, each component's removed weight returns to the reference. No reoptimization occurs. Positive/removal-improved cells mean the removed component was harmful in that cell; this is fitted-architecture reliance, not causal importance or the best possible retrained model.

| Removed component | Improved cells | Regressed cells | Ties |
|---|---:|---:|---:|
| AdditiveEBM |737|535|24|
| InteractionEBM |820|454|22|
| ExtraTrees |726|550|20|
| Ridge |560|712|24|
| CompactTabM |870|336|90|
| EmbeddedTabM |578|712|6|
| TabPFNstudent |173|201|922|
| Alllegacycontrols |386|202|708|
| Riskheads |649|635|12|
| Goalheads |377|487|432|

This supports the user's hypothesis that a weak standalone model can help a combination: embeddedTabM has poor standalone recent ordering but its removal harms712cells. CompactTabM's nonzero learned weight does not establish usefulness. These are exposed-data diagnostics; selecting a new removal policy from all periods would add another layer of adaptive reuse.

## Global ranking and score calibration

Sector percentile scores erase the reference's cross-sector score scale. Directly sorting them globally can severely worsenTop1/3results even where within-sector metrics improve. Separate globalTop1/3/20/100audits now cover797,443historical rows, all9profiles and current4436stocks for both execution and specialist rounds.

An adaptive outcome-free quantile-mapping follow-up maps each candidate's within-sector rank to that sector's reference score distribution. It retains sector score levels without introducing company-specific penalties. It is an empirical calibration adaptation, not an established financial profitability result. Candidate ties use average ranks and interpolation, so exact marginal-mass preservation is not claimed when tie patterns differ. Original and transported results remain separate. Final selection and stock reasoning must inspect both; neither can be declared superior from one aggregate.

## Verification and limits

- All42specialist model sets passed replay, source identity and cutoff checks; maximum native error4.44e-16. Ridgefloat32decimal serialization was verified at original dtype; currentfloat64error stays below the original1e-12tolerance.
- The separate execution round passed28model replays after a preserved, provenance-recorded current activity-input repair. No historical outputs or selection changed. Its lower-quartile model is not calibrated:44.18% of2025activity-model outcomes fell below its predicted25thpercentile.
- Current exact ranks require losslessCSVfloat parsing. Eight focused tests passed, including dtype/rank serialization, temporal training, dated activity, stack constraints, stability equivalence and calibration independence from future labels.
- Date-block and leave-one-year-out diagnostics are descriptive. Overlapping horizons, few market periods and extensive prior selection prevent fresh-validation claims.
- Current snapshot is3October2026. Retrospective universe/sector membership, incomplete historical fundamentals, unresolved corporate-action/price concerns and approximate activity/execution data remain. The financial rubric is a sensitivity-tested diagnostic, not a truth oracle.
- Website hashes match the initial checkpoint. No deployment or production replacement occurred.

## Reproducible evidence

Main artifacts: `experiments/sector-specialist-ensemble-20261011/` including `protocol.json`, `combination_protocol.json`, `locked_finalists.json`, `finalist_trials.csv`, `sector_profile_metrics.csv`, `worst_query_regressions.csv`, `pair_accuracy.csv`, `rank_stability_summary.csv`, `financial_comparison.csv`, `all_stock_explanations.csv`, sectorTop1/3/20/100exports, `serialized_replay.csv`, `stack_ablation/`, `supplemental_global/`, and `supplemental_global_transport/`. The cross-study ledger retains source-specific populations/gates; do not add unlike trial cells into a fabricated common denominator.

Primary algorithm/research sources: [TabM official repository](https://github.com/yandex-research/tabm), [InterpretML EBM](https://interpret.ml/docs/ebm.html), [TabPFN official repository](https://github.com/PriorLabs/TabPFN), [quantile transformation documentation](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.QuantileTransformer.html), [backtest overfitting research](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf). Published algorithm results are not evidence of Indian-stock profitability; performance statements above come from this project's saved experiments.

Remaining: complete registered24/48epoch neural continuation and matched12epoch controls; independently audit its serialized models and current financial outputs; synthesize global/sector/profile results and review actual selections; refresh the ledger/provenance and audit every original deliverable. No final champion promotion is established.
