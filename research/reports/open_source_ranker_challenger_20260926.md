# Official open-source ranker challenger — 2026-09-26

## Decision

**REJECT BOTH CHALLENGERS. KEEP THE FROZEN 67% Goal + 33% LightGBM LambdaRank CONTROL.**

Neither official upstream ranker passed the preregistered strict Pareto admission gate. No ensemble was attempted because neither constituent passed and the preregistered fusion gate therefore found no scientifically justified fusion experiment. Nothing was promoted or tagged.

## Immutable control and comparable experiment

- Frozen control: `personalized-challenger-d499580-20260926`, commit `d4995807163bef1ec4b297179e6c54a59c71f390`.
- Research-only source panel: frozen `personalized-final-tournament/build-04` training and validation artifacts, read only.
- Same exact common cohort, six evaluation dates (2020-06-30 through 2025-06-30), nine profiles, seven established features, labels, queries, 67/33 blend, execution outcomes, corporate-action handling, cash handling, and blocker behavior for all candidates.
- A label was eligible only when its endpoint was strictly earlier than the evaluation decision date.
- No imputation, regime input, manual correction, conditional override, searched ensemble weight, evaluation-driven filtering, or final-block hyperparameter tuning was used.
- The experiment definition and strict gate were preregistered before the official `run-02` results were inspected. Equivalence tolerance was `1e-12`; material thresholds were recorded in the specification.

The frozen score was independently reconstructed with maximum absolute differences of `1.11e-16` per prediction and `9.50e-17` across aggregate metrics. These are floating-point noise. Coverage was `1.0` for all three systems.

## Official upstream systems

| Candidate | Exact implementation | Published/repository basis | Parameters |
|---|---|---|---|
| Control | `lightgbm.LGBMRanker` 4.6.0 | Existing frozen system | Frozen 60-tree LambdaRank configuration |
| CatBoost | `catboost.CatBoostRanker` 1.2.10 | CatBoost NeurIPS 2018; YetiRank published method; official CatBoost ranking documentation | `YetiRankPairwise`, 60 iterations, learning rate 0.05, depth 3, L2 10, CPU, one thread, fixed seed |
| XGBoost | `xgboost.XGBRanker` 3.4.1 | XGBoost KDD 2016; official learning-to-rank documentation | `rank:ndcg`, 60 estimators, learning rate 0.05, depth 3, L2 10, histogram trees, top-k LambdaMART pairs with the official tutorial value 8, one thread, fixed seed |

Sources: [CatBoost ranking objectives](https://catboost.ai/docs/en/concepts/loss-functions-ranking), [CatBoost paper](https://proceedings.neurips.cc/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html), [YetiRank paper](https://proceedings.mlr.press/v14/gulin11a.html), [XGBoost learning-to-rank guide](https://xgboost.readthedocs.io/en/stable/tutorials/learning_to_rank.html), [XGBoost paper](https://doi.org/10.1145/2939672.2939785).

The custom work is 495 lines across the minimal estimator adapters, causal tournament runner, and manifest verifier. It supplies grouping, common input/output contracts, audit hashes, evaluation, and verification; ranking is performed entirely by the upstream libraries.

## Aggregate ranking results

| System | Pairwise accuracy | Rank IC | NDCG@5 | NDCG@10 | NDCG@20 | NDCG@50 | P/R@20 | P/R@50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Frozen control | 0.500075 | -0.002886 | 0.417317 | 0.442042 | 0.467743 | 0.479045 | 0.010185 | 0.018519 |
| CatBoost YetiRankPairwise | 0.498100 | -0.007747 | 0.430208 | 0.442964 | 0.457471 | 0.470354 | 0.000926 | 0.010741 |
| XGBoost rank:ndcg | 0.498463 | -0.013666 | 0.414923 | 0.429069 | 0.448524 | 0.474396 | 0.002778 | 0.019259 |

P/R@5 and P/R@10 were zero for every system. They were retained in the admission gate as genuine ties and were not dropped.

## Personalized investor results

| System / K | Goal attainment | Goal shortfall | Mean XIRR | Median XIRR | Terminal wealth | Mean drawdown |
|---|---:|---:|---:|---:|---:|---:|
| Control / 5 | 0.318519 | 0.099309 | 0.215898 | 0.049814 | 188,606 | -0.327618 |
| CatBoost / 5 | 0.385185 | 0.085559 | 0.190022 | 0.088700 | 187,738 | -0.275545 |
| XGBoost / 5 | 0.374074 | 0.100043 | 0.222997 | 0.090268 | 188,935 | -0.363176 |
| Control / 10 | 0.377778 | 0.087816 | 0.370900 | 0.109209 | 205,414 | -0.326731 |
| CatBoost / 10 | 0.403704 | 0.081213 | 0.209091 | 0.116525 | 191,170 | -0.280776 |
| XGBoost / 10 | 0.403704 | 0.093113 | 0.267522 | 0.091562 | 195,329 | -0.356717 |
| Control / 20 | 0.436111 | 0.076272 | 0.457881 | 0.145058 | 207,248 | -0.316177 |
| CatBoost / 20 | 0.411111 | 0.082125 | 0.282681 | 0.123788 | 198,584 | -0.289892 |
| XGBoost / 20 | 0.417593 | 0.089758 | 0.362841 | 0.116330 | 203,933 | -0.356003 |
| Control / 50 | 0.420741 | 0.079554 | 0.585336 | 0.137855 | 212,355 | -0.310856 |
| CatBoost / 50 | 0.412222 | 0.082284 | 0.446112 | 0.124950 | 210,091 | -0.299779 |
| XGBoost / 50 | 0.436667 | 0.086287 | 0.647270 | 0.145366 | 220,124 | -0.347535 |

## Admission and stability audit

- **CatBoost: FAIL.** It materially improved 10 protected metrics, including NDCG@5, goal outcomes at K=5/10, and drawdown at every K, but degraded 22 protected metrics. The losses include pairwise accuracy, Rank IC, P/R@20 and @50, NDCG@20 and @50, goal outcomes at K=20/50, mean XIRR at every K, and terminal wealth at every K.
- **XGBoost: FAIL.** It materially improved 6 protected metrics, including goal attainment at K=5/10/50 and mean XIRR and terminal wealth at K=50, but degraded 23 protected metrics. The losses include pairwise accuracy, Rank IC, NDCG at every K, goal shortfall at every K, several XIRR/wealth measures, and drawdown at every K.
- CatBoost reduced K=20 shortfall on 3 of 6 dates, 1 of 9 profiles, and 24 of 54 date/profile query blocks; 39 of 54 blocks triggered at least one preregistered severe-harm flag.
- XGBoost reduced K=20 shortfall on 1 of 6 dates, 0 of 9 profiles, and 11 of 54 query blocks; 41 of 54 blocks triggered at least one severe-harm flag.
- Every date, profile, query block, and top-K selection is preserved in the compact official artifacts. Aggregate gains therefore cannot conceal the broad deterioration.

## Causal, determinism, and leakage audit

- All training endpoints were strictly earlier than their target decision dates.
- The only estimator inputs were the seven frozen features; `future_*`, regime, Sir-workbook, and outcome-derived fields were excluded.
- Queries were deterministically ordered by decision date, profile, and ISIN.
- Fixed seeds and one-thread execution were used. Adapter tests reproduce identical predictions and semantic model hashes.
- CatBoost hashes only its predictive JSON structure because its serialized metadata contains a wall-clock timestamp. XGBoost hashes the upstream JSON booster bytes.
- The artifact verifier checks every byte size and SHA-256 digest, the artifact-set fingerprint, frozen commit identity, leakage status, and the no-promotion conclusion.
- Production, commit `d499580`, its immutable tag, and prospective shadow artifacts were untouched.

## Reproducibility artifacts

- Protocol: `research/specifications/open_source_ranker_challenger_20260926.json`
- User rules captured verbatim: `research/specifications/open_source_ranker_requirements_20260926.txt`
- Official run: `experiments/open-source-ranker-challenger/run-02/`
- Detailed gate: `pareto_gate.json`
- Every date/profile/query delta: `date_stability.csv`, `profile_stability.csv`, `paired_query_deltas.csv`
- Predictions and top-K selections: `common_predictions.csv.gz`, `topk_selections.csv.gz`, `topk_overlap.csv`
- Causal and model evidence: `leakage_audit.json`, `model_audit.json`, `inputs.json`, `manifest.json`

## Next research step

Do not revise either rejected model after seeing these final blocks. The strongest defensible next experiment is a new preregistered ranker selected and tuned solely on an earlier development/validation period, then judged once on newly matured prospective shadow outcomes that have not yet been used for model design. The frozen control remains champion until a candidate clears the unchanged strict gate.

## Test result

- New ranker integration and leakage tests: **6 passed**.
- Official run verifier: **PASS** (`control`; hashes and immutable boundaries verified).
- Full artifact-complete repository suite: **920 passed, 1 skipped, 1 failed** in 186.79 seconds.
- The sole failure is the pre-existing dirty live-site checkout mismatch `price_ready 4436 != accepted-bundle matched_count 4434` in `test_live_counts_match_the_atomic_accepted_bundle_and_frozen_v2_is_unchanged`. The modified live-site production files were present before this isolated branch was created and were left untouched.
