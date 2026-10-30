# Current model versus the retained project history

Audit date: 2026-10-04. Product branch inspected: `main`.

**Objective correction, 2026-10-05:** The user clarified that the primary use is ranking stocks within each sector. The global Top 20 results below are secondary diagnostics and do not determine the best model for that purpose. Sector-level evaluation must be the primary selection criterion. See `../sector-priority-audit-20261005/REPORT.md` for the corrected scope and initial within-sector diagnostic.

## Verdict

**No. The current model is not demonstrably better in all aspects than every previous model.** It has substantial improvements over Original Personalized, V17, and several successors on common-stock return and risk diagnostics. There are also direct, measurable regressions. Some earlier families cannot be compared fairly using the retained score files, so superiority over those families remains unestablished.

This audit changes no production scoring, weights, eligibility rules, or UI.

## What was checked

- Inventoried 284 retained CSV evidence artifacts and 787 distinct model/configuration identifiers. Identifiers include trial settings, repeated builds and component names; **these are not 787 independent fitted models**.
- Recomputed seven metrics for **33 earlier score policies**, across up to **44 dates and nine profiles**, producing **7,884 paired date/profile comparisons**.
- Recovered six archived CatBoost, XGBoost and regime blend policies from Git rather than ignoring rejected models.
- Examined the lineage from Baseline V1, Research V2 and early factor models through current Closing High. The coverage table below distinguishes direct comparisons, native evidence and unevaluated adapters.
- Verified unique query keys, finite metrics, minimum common-stock counts, metric differences and aggregate arithmetic. Source SHA-256 hashes are saved in `verification.json`.

**46 of 81 opponent/period comparisons** have all seven aggregate metrics nonworse. The other **35 do not**. None of the 81 comparisons is nonworse on every metric for every constituent date/profile. These counts describe this retained comparison set; they are not probabilities of future success.

## Decisive counterexamples

| Opponent and period | Current score | Earlier score | Finding |
|---|---:|---:|---|
| Closing High confirmation, 2020–2023, basket-median XIRR | 21.46% | 21.80% | Current loses 0.34 percentage points |
| Closing High confirmation, 2024–2025, basket-median XIRR | −0.52% | −0.41% | Current loses 0.11 percentage points |
| V14, 2024–2025, mean constituent drawdown | −28.47% | −25.56% | Current drawdown is worse by 2.91 percentage points |
| V14, 2024–2025, mean target shortfall | 10.19% | 9.58% | Current shortfall is worse |
| V17, 2020–2023, rank IC | −0.04079 | −0.03988 | Current is slightly worse |
| V17, 2020–2023, pairwise accuracy | 48.52% | 48.66% | Current is slightly worse |
| Archived HMM blend, shared 2020–2023 dates, basket-median XIRR | 20.58% | 26.04% | Earlier blend wins on this smaller sample |

The archived comparison has four development dates and nine profiles, not the full 16 development dates. Its 20.58% current return must not be compared directly with the 21.46% current return in the full-period rows. The archived model's earlier rejection also does not mean it loses every metric.

The tiny IC and pairwise differences are not evidence of statistical significance. They do refute literal numerical dominance. The larger V14 drawdown difference and return differences also establish practical tradeoffs.

## Where the current score improves

These rows use matching screened stocks, dates, profiles and outcome labels within each comparison. Values are equal-weight averages of date/profile Top 20 basket-median XIRRs.

| Score policy | 2016–2019 | 2020–2023 | 2024–2025 |
|---|---:|---:|---:|
| Current recovery-aware Closing High score | 5.53% | 21.46% | −0.52% |
| Original Personalized policy | −2.25% | 16.18% | −8.64% |
| V17 | −2.11% | 15.77% | −4.45% |
| V17 refined | −1.03% | 15.07% | −2.68% |
| Closing High priority, 20% explicit high weight | 1.49% | 17.95% | −2.03% |
| Closing High confirmation, before recovery correction | 5.36% | 21.80% | −0.41% |

Against the 20% Closing High priority policy, all seven period averages improve or tie in each period. Against V17, return, mean constituent drawdown, achievement, shortfall and NDCG improve in all three periods, but development IC and pairwise accuracy regress. Individual dates and profiles still lose. Earlier quoted “V17” figures of −1.03%, 15.07%, −2.68% correspond to the **refined V17 score** in these retained files; this report keeps original V17 and refined V17 separate.

The current model's recovery credit fixes a specific ranking behavior: an old ATH becomes less punitive when the price has nearly recovered. That correction is not a universal performance improvement over its immediate predecessor.

## Coverage from Baseline onward

| Family or stage | Evidence covered | Current-versus-earlier conclusion |
|---|---|---|
| Baseline V1 | Deterministic within-sector ranks; strict same-cohort four-date benchmark | No matched SIP head-to-head. Cannot claim beaten. Its sector-relative scores cannot simply be sorted globally. |
| Research V2 | Nine-factor, point-in-time fundamental and sector audit; same strict cohort | No matched current score on its historical cohort. Current financial review flags do not reproduce its historical fundamental evidence. |
| Exploratory factor V1–V3 | Momentum 12m/6m, low volatility, shallow drawdown, reversal, factor blends, expanding ridge; native metrics retained | Different dates, sectors and 12-month price-return outcome. Native evidence only. |
| Broad chronological price ML and V5 price ensemble | ExtraTrees, LightGBM regression, LambdaRank, ridge, momentum, price multifactor and selected ridge/price ensemble | Their sector-level locked test has no matching current-model score file. Superiority unestablished. |
| Complete-universe ranking and evidence tiers | Primary 5Y, reduced 3Y/1Y, recency-only and completed composite/ensemble | Coverage and confidence policies, not interchangeable with Baseline V1. Current-only evidence does not prove investment performance. |
| Prospective validation V1–V4 | Frozen future-facing rankings and protocols | Outcomes not accessed in their saved summaries. No performance win inferred. |
| Greenblatt India | Current ROIC/earnings-yield screen | Different eligible universe; no comparable historical test. |
| Early fractional Personalized and global tournament | Prototype professor, goal, XIRR, existing, ML, ablations and blend trials | Different execution economics/data revisions. Inventoried; native evidence only. |
| Executable and official-action tournament policies | 13 score columns carried in the V12 deep panel: carry/no-carry, professor whole-share, goal, target frequency, existing, existing blend, three ridge variants, cluster, histogram boosting, LambdaRank | Direct paired rescoring wherever retained scores exist. Some learned columns have only four shared dates. |
| Original Personalized champion | Retained `champion_score` on all 44 current benchmark dates | Direct paired comparison. Return improves; not universal seven-metric dominance. |
| Fixed ensemble searches | Including 25 fixed two/three/four-component blends | Trial identifiers and native metrics retained; not every losing trial has comparable row-level scores. No claim all individually beaten. |
| Archived open-source rankers | CatBoost YetiRankPairwise and XGBoost rank-NDCG finalized blends | Direct paired comparison on six shared dates. Mixed results. |
| Archived regime challengers | Jump, volatility, HMM, Jump+ADWIN finalized blends | Direct paired comparison on six shared dates. Mixed results. |
| History challenger and hybrid grids | 60 history settings and 40 hybrid settings | Native tournament evidence; discarded trials do not all retain per-stock predictions. |
| Championship and successor searches | Qualifiers/finalists, successor V1/V2/V3 grids and blends | Catalogued native trial evidence; not all trial predictions available for direct replay. |
| Deep championship V1 | Development and retained 2024/2025 scores | Direct paired comparison. Mixed metrics. |
| V9/V10/V11 history panels | Panel/data-depth revisions | Not separate ranking policies merely because the panel version changed. |
| V12 | Deep championship V3 selected policy | Direct paired comparison on retained shared dates. |
| V13 | Smooth history-confidence/downside policy | Formula replay on 44 shared dates; its special blind/prospective dates are outside this comparison. |
| V14, V15, V16 | Selected saved scores | Direct comparisons; V14 retains a drawdown and shortfall advantage. |
| V17 and refined V17 | Separate original and repair score columns | Direct comparison on 44 dates. |
| V18 and V17/V18 search trials | V18 selected rejected candidate plus catalogued ML/control trial families | V18 direct; losing trials inventoried without universal dominance claim. |
| ATH diagnostic and peak context | Selected diagnostic scores | Direct comparisons on 44 dates. |
| Peak/activity and confirmation searches | Selected 20% priority and 30% confirmation scores; retained losing grid labels | Selected policies direct; all losing grid variants are not individually replayed. |
| Current reviewed Closing High | Recovery-aware 30% high-weight score plus current application safeguards | Historical score correction evaluated. Entire deployed pipeline has not received a matched historical replay. |
| Qlib adapters | Linear, LightGBM and TRA synthetic reproductions; DoubleEnsemble blocked | Infrastructure/synthetic evidence is not a tested Indian-stock ranking model. |
| Alphalens, Empyrical, QuantStats, skfolio integrations | Metrics/portfolio tooling and deferred integrations | Not additional stock score policies to declare defeated. |

The inventory is a documented search of retained project artifacts and relevant Git archives. It cannot establish that every transient, deleted, unrecorded or uncommitted experiment ever run has been recovered. The 787-label registry is a provenance index, not a claim that every label has a fresh performance comparison.

## “All aspects” beyond average return

| Aspect | Assessment |
|---|---|
| Returns and ranking quality | Many gains, explicit losses above; no dominance. |
| Downside risk | Mean constituent drawdown improves against several predecessors but loses to V14. This is **not portfolio maximum drawdown**. |
| Investor profiles | Per-profile deltas are exported. Aggregate wins conceal losing dates and profiles. |
| Coverage and execution | Current default ranks 1,747 of 4,436 identities, with SME exclusions when lot information is unavailable. The older completed-universe system ranked all 4,436 under evidence tiers. Better execution controls come with reduced coverage. |
| Data/history quality | Recovered BSE histories and corporate-action corrections are useful, but their full historical model effect is not measured here. |
| Old highs and short histories | Recovery credit removes a hard old-high penalty near recovery; history confidence remains important. Neither feature guarantees better outcomes for every stock. |
| Fundamentals | Current financial review flags are informational. No full point-in-time fundamental replay proves superiority over Research V2. |
| Sector concentration | Current Top 100 still contains 20 healthcare names in the prior reviewed audit. Concentration is not solved merely by higher average metrics. |
| Simplicity, interpretability and runtime | Baseline is simpler. No common hardware/runtime benchmark was performed, so no speed or operational dominance claim. |
| Transaction costs, liquidity and investability | Current screens help, but this comparison is not a common all-model net-of-cost portfolio simulation with historical spreads, market impact and SME lots. |
| Generalization | Repeatedly exposed historical periods; no new untouched outcome validation in this audit. |

## Method and limits

1. Join retained predictions by ISIN, decision date and profile. Use the same available stocks for both opponents within each query, requiring at least 20 stocks with both scores and all three outcome labels.
2. Use one outcome source: V17-refinement's retained V12-derived `future_xirr`, `future_shortfall` and `future_drawdown`. Older scores are rescored against those common labels, not refitted. This is not an exact reproduction of each older study's original outcome/data version.
3. Apply the existing `ranking_metrics`: Top 20 median constituent XIRR, mean constituent drawdown, target achievement, mean shortfall, NDCG@20, Spearman rank IC, and deterministic sampled pairwise accuracy (up to 400 stocks). Score ties use ISIN order for Top 20; pairwise ties earn half credit.
4. Average metrics equally across date/profile queries within 2016–2019, 2020–2023 and 2024–2025. Lower shortfall is better; higher is better for the other six metrics, including negative drawdown values closer to zero. Numeric nonworseness uses tolerance 1e-12, not a significance test.
5. Common populations vary by opponent. Missing scores are excluded, not imputed as poor performance. The source manifest and query table expose sample sizes. Partial-coverage learned scores are not full-period evidence.
6. The current historical proxy is the saved **recovery score** from `closing-high-recovery-20261004`. It isolates the recovery correction on the prior activity-screened history. It does **not** backfill the full current SME eligibility gate, newly recovered BSE histories or current financial review flags. Consequently even favorable rows do not prove the entire current deployed model is superior.
7. Dates/profiles overlap and histories were used repeatedly for research. No independent-sample significance, fresh lockbox result, or future performance guarantee is claimed.

## Files and reproduction

- `paired_comparison_tables.md`: all 81 readable opponent/period comparisons.
- `common_population_summary.csv`: all seven aggregate metrics, differences and counts of losing queries.
- `paired_date_profile_metrics.csv`: all 7,884 query-level comparisons.
- `profile_deltas.csv`: profile-specific period differences.
- `comparison_sources.json`: exact opponent score columns and files.
- `model_label_registry.csv` and `all_retained_labels.csv`: configuration identifiers and provenance.
- `artifact_inventory.csv` and `native_study_metrics.json`: retained evidence and noncomparable native results.
- `verification.json`: arithmetic checks and source hashes.

Run from the repository root in this order:

```powershell
python research/runners/all_models_audit_20261004.py inventory
python research/runners/all_models_audit_20261004.py catalog
python research/runners/all_models_audit_20261004.py compare
python research/runners/all_models_audit_20261004.py extended
python research/runners/all_models_audit_20261004.py v13
python research/runners/all_models_audit_20261004.py finalize
```

`compare` resets the comparison outputs; run each append stage once. Archived inputs are retained in this report directory under `archived/`, recovered from tag `archived-open-source-rankers-5428ba0-20260927` (`experiments/open-source-ranker-challenger/run-02/common_predictions.csv.gz` and `experiments/open-source-regime-challenger/run-01/common_predictions.csv.gz`).

## Decision

Describe the current model as **a stronger candidate on several important historical metrics, with explicit tradeoffs and incomplete end-to-end validation**. Do not label it “better than every model in all aspects.” Before promotion on that claim, the remaining work is a common historical replay of the deployed pipeline and early model families, with a frozen objective, costs/eligibility assumptions, profile guardrails and new prospective validation. Repeatedly tuning on these same dates would not close that evidence gap.
