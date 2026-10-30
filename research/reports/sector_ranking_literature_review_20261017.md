# Literature review: open-source systems for Indian within-sector stock ranking

Review date: **17 October 2026**. Scope: published methods, available implementations, data requirements, reproducibility and relevance to this project. This is a research review, not a new performance experiment or a promotion of a model.

## 1. Decision summary

**The strongest route is to reuse specific research components around our sector-ranking problem. No reviewed project establishes a ready-made superior replacement for all 4,436 Indian stocks and our personalized SIP goals.**

My recommended order is:

1. **Qlib as a reference implementation and evaluation framework**, with **DoubleEnsemble** the first distinct algorithm to reproduce. It addresses sample weighting and feature selection, has a peer-reviewed paper, and a usable LightGBM implementation.
2. **HIST-style sector relationships, followed by MASTER**, once dated classifications and daily sequence inputs are reliable. These are structurally relevant to comparing companies with peers.
3. **Kronos as a separate pretrained representation/forecast challenger**. It has financial-market pretraining, Indian-market coverage in its paper and an AAAI 2026 publication. Its checkpoint training history must be checked before using our old dates as evidence of generalization.
4. **Point-in-time fundamental ingestion and Alphalens-style sector diagnostics**. These address information and measurement gaps that another architecture alone cannot fix.
5. **DoubleAdapt/TRA later**, after distinguishing genuine changing patterns from data faults and sparse training groups.

These priorities are my engineering judgment from the evidence below. They are not measured probabilities of beating our champion. Full-market numerical coverage, evidence coverage, tradability and predictive accuracy must remain separate quantities.

## 2. Review method and limits

I searched primary research records and official/author repositories across stock learning-to-rank, financial ensembles, temporal adaptation, stock relationship models, foundation models, Indian equity backtest projects, portfolio optimization and financial agents. I followed repository references and inspected selected implementation files rather than relying entirely on search summaries.

Evidence is identified as:

- **P:** peer-reviewed publication verified, with relevant method evidence. This does not certify today's repository or a replication here.
- **R:** research paper/preprint and code, but publication status not independently established in this review.
- **S:** software infrastructure; useful implementation, without a claim of superior stock forecasts.
- **I:** independent project and author-reported experiments; not independently reproduced.

Ten repositories have pinned commit IDs, downloaded READMEs, available root license files and SHA-256 receipts in `research/literature/20261017/repository_manifest.json`. Six selected implementation/data files have separate receipts in `code_manifest.json`. Other projects were reviewed through linked web sources. No downloaded project code was executed. This is a broad, targeted review, not an exhaustive systematic review of every finance paper. Search-engine coverage, unavailable proprietary data and mutable upstream pages limit completeness.

Performance numbers from different papers are deliberately not assembled into a league table: universes, horizons, costs, targets and validation procedures differ. No new training, trading or deployment was initiated for this review.

## 3. Closest systems and methods

| Project/method | Evidence and source | What it supplies | Fit to our task and main limitation |
|---|---|---|---|
| Microsoft Qlib | S/R; [official repository](https://github.com/microsoft/qlib), [benchmark configurations/results](https://github.com/microsoft/qlib/blob/main/examples/benchmarks/README.md) | Data handling, models, rolling research, backtesting, portfolio/execution components | Closest general research platform. Its principal stock benchmarks use Chinese datasets; it does not supply our Indian universe or SIP target. MIT code; official dataset availability is currently restricted according to its README. |
| DoubleEnsemble | P, ICDM 2020; [paper](https://doi.org/10.1109/ICDM50108.2020.00087), [implementation](https://github.com/microsoft/qlib/blob/main/qlib/contrib/model/double_ensemble.py) | Sequential ensemble with training-trajectory sample weighting and shuffled-feature selection | High-priority CPU-friendly challenger. Changes how models learn, unlike merely averaging more predictions. Need sector-balanced weighting and task-specific targets. |
| Cross-sectional learning to rank | P, Journal of Financial Data Science 2021; [Poh, Lim, Zohren and Roberts](https://arxiv.org/abs/2012.07149) | Pairwise/listwise learning for systematic cross-sectional strategies | Direct conceptual match. Our existing ranking objectives already cover this family; another LTR label alone is not a new research direction. Group by date, sector and relevant profile. |
| HIST | R; [paper](https://arxiv.org/abs/2110.13716), [author code](https://github.com/Wentao-Xu/HIST) | Concept-oriented shared information between stocks | Strong conceptual sector fit; published examples target CSI100/300. Indian concepts/relationships need dated provenance. No root license identified in pinned author repository; check the separately licensed Qlib implementation before reuse. |
| MASTER | P, AAAI 2024; [paper](https://arxiv.org/abs/2312.15235), [official code and correction notices](https://github.com/SJTU-DMTai/MASTER) | Intra-stock/inter-stock attention and market-conditioned features | Worth reproducing after a smaller relationship baseline. MIT code; released examples and original proprietary research environment differ. See implementation findings below. |
| Temporal Routing Adaptor (TRA) | P, KDD 2021; [paper](https://arxiv.org/abs/2106.12950), [Qlib integration](https://github.com/microsoft/qlib/blob/main/examples/benchmarks/TRA/README.md) | Multiple prediction patterns and temporal routing | Potential regime specialist. Must use only losses/outcomes available at the decision date. Original reproduction scripts and maintained integration are different paths. |
| DoubleAdapt | P, KDD 2023; [paper](https://arxiv.org/abs/2306.09862), [author API](https://github.com/SJTU-DMTai/DoubleAdapt) | Incremental data and model adaptation | Potentially useful under drift. With long SIP targets, labels become available slowly; short-horizon update logic cannot be copied unchanged. Author API notes a normalized-label IC issue. |
| RD-Agent | R/S; [Microsoft repository](https://github.com/microsoft/RD-Agent), [research paper](https://arxiv.org/abs/2505.15155) | Automated factor/model research workflows | Useful for experiment organization and bounded hypothesis generation. More autonomous trials increase selection bias unless the experiment budget and untouched evaluation are controlled. MIT code. |

### Additional stock-ranking research with direct relevance

These extend the relationship-model shortlist; they are not yet implementations audited in our environment.

| Method | Primary evidence / code | Relevance and replication hurdle |
|---|---|---|
| Relational Stock Ranking (RSR) | [Temporal Relational Ranking paper](https://arxiv.org/abs/1809.09441), [author repository](https://github.com/fulifeng/Temporal_Relational_Stock_Ranking) | Combines temporal stock signals with relationships and ranking. A useful earlier baseline before more elaborate graph models. Reconstruct dated Indian relationships; audit dependencies and reuse terms. |
| STHAN-SR | P, AAAI 2021; [author-hosted paper](https://tylersnetwork.github.io/papers/aaai21-hypergraph_attention_stock_selection.pdf), [author code](https://github.com/midas-research/sthan-sr-aaai) | Hypergraphs represent relationships among groups of stocks, directly supporting a ranking formulation. Sector groups offer a starting hypothesis, but grouping alone is not evidence of incremental prediction. Older Python/PyTorch-Geometric setup needs a separate reproducibility environment. |
| FinGAT | [paper](https://arxiv.org/abs/2106.10159), [author implementation](https://github.com/Roytsai27/Financial-GraphAttention) | Particularly relevant: stock and sector graphs, temporal patterns, and combined ranking/movement tasks. Learned relationships reduce dependence on manually specified links. The released environment is old; fully connected attention warrants memory/scaling checks for 4,436 names. |
| AlphaStock | P, KDD 2019; [conference record](https://www.kdd.org/kdd2019/accepted-papers/view/alphastock-buying-winners-and-selling-losers-in-deep), [paper](https://arxiv.org/abs/1908.02646) | Cross-asset attention with Sharpe-oriented reinforcement learning. Useful architectural precedent; objective and long-short trading assumptions differ from our sector/SIP task. A canonical executable release was not verified in this pass. |

**Priority within this family:** compare a simple peer-aggregate model against one graph method before trying all architectures. FinGAT is a strong conceptual alternative to HIST for stock/sector interaction; STHAN-SR is useful when credible group relationships exist. The paper-driven choice should be determined by our available dated inputs and a fixed replication budget, not the highest headline return.

### Implementation findings that change the recommendation

**DoubleEnsemble:** The inspected code defaults to six submodels and supports switching sample reweighting and feature selection separately. Its loss-curve implementation supports GBM, its loss calculation supports MSE, and its data adapter rejects multi-label targets. It is not a drop-in three-objective ranker. Reproduce the original regression route first, then document sector-percentile targets or separate outcome heads as adaptations. The sample-by-tree loss matrix also creates memory cost. [Pinned source](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/qlib/contrib/model/double_ensemble.py)

**MASTER:** The authors report earlier exported validation/test data inadvertently filtered stocks using training processors, and a later validation-processing mismatch. They provide updated data/code guidance. Reproduction must follow these notices. [Author explanation](https://github.com/SJTU-DMTai/MASTER)

There is also a concrete small-sector adaptation hazard: `drop_extreme` calculates `int(0.025*N)` then slices `[k:-k]`. For fewer than 40 stocks, `k=0`, so the slice is empty. That matters if we change daily full-universe batches into sector batches. Fixing this would be an explicitly documented adaptation, not evidence that the original full-universe experiment is invalid. [Inspected source](https://github.com/SJTU-DMTai/MASTER/blob/de8f58557096abde4216a701b35fc4368158d111/base_model.py)

**DoubleAdapt:** Its author API explicitly tells users to revise the example IC evaluation, which uses normalized rather than raw labels. Pearson IC can change under nonlinear transformations; within-group rank IC may be invariant only for monotonic transformations on the same population. We should recompute all metrics in our common harness. [Author note](https://github.com/SJTU-DMTai/DoubleAdapt)

## 4. Pretrained models and generic tabular components

| Model family | Evidence/source | Candidate role | What remains unproven |
|---|---|---|---|
| Kronos | P, [AAAI 2026 proceedings](https://ojs.aaai.org/index.php/AAAI/article/view/39730); [official code](https://github.com/shiyu-coder/Kronos) | Market sequence features; return or volatility specialist | Superiority on our sector/SIP task, coverage of illiquid names, checkpoint-specific temporal independence |
| Chronos / Chronos-Bolt / Chronos-2 | Original Chronos: P, TMLR 2024; [paper](https://arxiv.org/abs/2403.07815), [official family repository](https://github.com/amazon-science/chronos-forecasting) | Probabilistic forecasts or uncertainty controls | General forecasting scores do not establish stock-selection alpha. Later versions have their own evidence and training corpora. Repository Apache-2.0. |
| TimesFM | Original method: P, ICML 2024; [paper](https://arxiv.org/abs/2310.10688), [Google repository](https://github.com/google-research/timesfm) | General pretrained time-series baseline | Price-level forecast accuracy is not sector-relative return ranking. Pin exact model version and verify checkpoint terms/cutoff. |
| TabPFN | P, [Nature paper](https://www.nature.com/articles/s41586-024-08328-6); [official code](https://github.com/PriorLabs/TabPFN) | Small-data tabular prior, teacher/distillation component | Already investigated in our project. General tabular performance does not establish a new financial winner. Model/version-specific terms apply. |
| TabM | P, ICLR 2025; [official paper/code](https://github.com/yandex-research/tabm) | Efficient neural ensemble trained on our tables | This is an architecture, not pretrained Indian stock expertise. Already present in our specialist research work. |
| Explainable Boosting Machines | S with research lineage; [InterpretML](https://interpret.ml/docs/ebm.html) | Nonlinear additive and limited-interaction specialists | Interpretability is useful; it does not guarantee accurate future rankings. Already included in specialist work. |
| CatBoost / LightGBM rankers | Research-backed libraries; [CatBoost objectives](https://catboost.ai/docs/en/concepts/loss-functions-ranking), [LightGBM objectives](https://lightgbm.readthedocs.io/en/latest/Parameters.html#objective) | Strong common controls and final ranking heads | Extensively explored here already; gains need new information or a distinct learning hypothesis, not a renamed wrapper. |

### Why Kronos deserves a controlled experiment

The paper describes OHLCV/amount pretraining across 45 exchanges and explicitly includes NSE India among in-distribution exchanges. It evaluates return and volatility forecasting as well as other tasks. This makes it more directly relevant than a generic language model. Its results still do not establish Indian within-sector SIP performance. [Paper and appendices](https://arxiv.org/html/2508.02739v1)

The repository provides mini/small/base checkpoints and fine-tuning examples; the listed large model is not released. Start with a small fixed checkpoint and deterministic evaluation of multiple sampled paths, not a large tuning sweep. [Model availability](https://github.com/shiyu-coder/Kronos)

**My proposed acceptance condition:** establish the exact checkpoint's pretraining dates and overlapping Indian securities first. If temporal independence cannot be established, label old-date results as retrospective representation diagnostics and use prospective observations for a clean comparison. A frozen checkpoint can still contain future information relative to a backtest date; freezing it does not remove that information. Also retain actual missing-data masks: an OHLC forecasting interface does not create reliable histories for stocks we lack.

A recent five-US-stock foundation-model comparison reports practical benefits but stops short of universal reliable alpha. It is a preprint with a small universe, useful as counter-evidence rather than a definitive verdict. [Financial return forecasting comparison](https://arxiv.org/abs/2606.27100)

## 5. Indian projects: useful examples, narrower evidence

### rejinreeza/trading_tool

The author reports a filing-date-based NSE XBRL fundamental strategy on 98 companies. In its stated June 2020–March 2025 comparison, fundamental CAGR is 33.34% versus buy-and-hold 34.87%, with greater drawdown for the fundamental strategy. These are author-reported results, not our reproduction. The README also admits survivorship, fill/liquidity and free-data limitations. Its honesty about unsuccessful results makes it useful research context. [Repository](https://github.com/rejinreeza/trading_tool)

The inspected `fundamentals.py` is a **current** Yahoo-fundamentals screen and explicitly disallows historical use. It must not be mistaken for the claimed historical XBRL pipeline; this review did not certify that pipeline end to end. No root reuse license was identified. [Inspected current-screen module](https://github.com/rejinreeza/trading_tool/blob/3e037198d962775b45ffdb5e6d55f771f31385fc/src/trading_tool/fundamentals.py)

### ninad164/auto-portfolio-management

Useful design ideas include cash contributions, monthly selection, dataset provenance and explicit universe modes. The author distinguishes synthetic demos from real-price runs. [Repository](https://github.com/ninad164/auto-portfolio-management)

Its universe code applies start/end membership intervals and checks overlaps. However, the checked snapshot-source manifest contains only its header. Thus, this is useful scaffolding, not verified delivery of a complete historical Indian universe. MIT license. [Membership code](https://github.com/ninad164/auto-portfolio-management/blob/669b17e1e0374701b02a447184fff1a7b40bb250/src/universe_history.py), [manifest](https://github.com/ninad164/auto-portfolio-management/blob/669b17e1e0374701b02a447184fff1a7b40bb250/data/universe_snapshots/sources_manifest.csv)

### raogaurav17/Nifty-Quant

Provides a configurable Nifty50 momentum/low-volatility/AR strategy framework with costs and dated membership changes. GPL-2.0 repository. Its claimed survivorship-free status was not independently certified. [Repository](https://github.com/raogaurav17/Nifty-Quant)

The inspected timeline does contain explicit added/removed events, but the event entries have reasons rather than source-document URLs. That is stronger than a static list but still requires checking each event, identifier history and delisted data. Also, its README reports a larger total return but smaller annual return for momentum than low volatility over the apparently same sample; differing metric definitions or a table error need reconciliation before trusting performance comparisons. [Timeline](https://github.com/raogaurav17/Nifty-Quant/blob/879db8c1a1b532c184280f4b9702b94b41cebc3b/conf/universe/nifty50_timeline.json), [reported results](https://github.com/raogaurav17/Nifty-Quant)

### Other reproducible-looking ranker examples

- [justinliu00/ml-cross-sectional-alpha-ranking](https://github.com/justinliu00/ml-cross-sectional-alpha-ranking): a compact US-equity walk-forward ranking project. Useful experiment organization; limited universe and independently unverified results. README-level review only.
- [matthiola0/ml-cross-sectional](https://github.com/matthiola0/ml-cross-sectional): boosted learning-to-rank with walk-forward validation and price-derived factors. Its adaptation of asset-pricing research is not a reproduction of the original rich fundamental dataset. README-level review only.
- [MayankRathi14/FinGATv2](https://github.com/MayankRathi14/FinGATv2): an independent Indian-market adaptation with graph learning, reinforcement-learning claims and a web interface. This is a particularly close application example, but its advertised directional-accuracy percentage cannot be compared with our pairwise sector-ranking percentage. Publication lineage belongs to the original FinGAT method; the adaptation's claims were not independently validated here. README-level review only.

**Conclusion for India:** none of these examples supplies verified full-market historical data, classifications, execution realism and personalized sector rankings matching our requirements. Reuse data contracts and audit patterns; do not copy their reported returns into our benchmark.

## 6. Factor evidence relevant to closing highs and sectors

| Research | Supported idea | Consequence for our design |
|---|---|---|
| George and Hwang, *The 52-Week High and Momentum Investing*, Journal of Finance 2004 | Nearness to a rolling high has published momentum evidence. [Paper](https://onlinelibrary.wiley.com/doi/full/10.1111/j.1540-6261.2004.00695.x) | Justifies a rolling-high baseline. It does not prescribe our 20%/30% weights or establish a monotonic penalty for all-time-high age. |
| Moskowitz and Grinblatt, *Do Industries Explain Momentum?*, Journal of Finance 1999 | Industry momentum is a meaningful part of stock momentum. [Author-associated summary](https://www.aqr.com/insights/research/journal-article/do-industries-explain-momentum) | Measure stock selection within industries separately from selecting winning industries. A strong global score can miss our objective. |
| Gu, Kelly and Xiu, *Empirical Asset Pricing via Machine Learning*, RFS 2020 | Nonlinear interactions and momentum/liquidity/volatility characteristics matter in their US study. [Published paper](https://doi.org/10.1093/rfs/hhaa009) | Strong rationale for tree/neural controls; their economic results do not transfer automatically to India or price-only inputs. |
| Chen and Zimmermann, Open Source Asset Pricing | Documented implementations of published cross-sectional signals. [Project](https://www.openassetpricing.com/), [code](https://github.com/OpenSourceAP/CrossSection) | Use as a signal-definition and replication catalog. GPL-2.0 code and WRDS-dependent source data are separate issues. A US signal library does not supply Indian data. |

My inference: retain closing-high information, but let rolling recency, distance, recovery, risk and history length have distinguishable roles. A very old ATH can reflect an IPO spike, a genuine deterioration or a recovering company. The literature above does not justify treating all three as the same case. Within-sector ablations should establish whether ATH age adds information beyond rolling-high distance and momentum.

## 7. Infrastructure, portfolio construction and financial agents

| Project | Verified role/source | Recommendation |
|---|---|---|
| Alphalens / Alphalens Reloaded | Factor return, IC and turnover analysis; [original](https://github.com/quantopian/alphalens), [continuation](https://github.com/stefan-jansen/alphalens-reloaded) | High-value independent diagnostic reference. Use sector groups and inspect binning/neutralization; our SIP metrics remain separate. |
| Zipline / Zipline Reloaded | Event-driven backtest engine; [continuation](https://github.com/stefan-jansen/zipline-reloaded) | Potential execution-verification layer. Indian calendars, corporate actions, fills and data ingestion still need adaptation. |
| QuantConnect LEAN | Open trading/research engine; [official code](https://github.com/QuantConnect/Lean) | Useful cost/fill/portfolio architecture. Engine availability is not Indian data entitlement or a pretrained alpha model. |
| PyPortfolioOpt | Portfolio optimization, shrinkage, Black-Litterman, HRP; [code](https://github.com/PyPortfolio/PyPortfolioOpt), [JOSS paper](https://joss.theoj.org/papers/10.21105/joss.03066) | Use after ranking for allocation; it does not itself learn which stock should rank first. MIT repository. |
| Riskfolio-Lib | Broad risk/portfolio optimization; [official code](https://github.com/dcajasn/Riskfolio-Lib) | Candidate for portfolio-level downside controls. Changes allocation, so compare under the same stock signals. |
| skfolio | Portfolio modeling and financial cross-validation; [official code](https://github.com/skfolio/skfolio) | Useful evaluation and allocation API; BSD-3-Clause repository. Not evidence of a superior ranking model. |
| FinRL | Reinforcement-learning trading workflows; [official code](https://github.com/AI4Finance-Foundation/FinRL) | Later priority. A trading policy requires an execution environment and reward design beyond stock ordering. |
| FinRL-X | Modular trading infrastructure; [2026 preprint](https://arxiv.org/abs/2603.21330) | Architectural reference. No exact implementation/performance reproduction in this review. |
| FinGPT | Financial-language-model ecosystem; [official code](https://github.com/AI4Finance-Foundation/FinGPT) | Potential filing/news feature extraction. Timestamped inputs and model knowledge contamination matter in historical use. |
| FinRobot | Financial analysis/report workflows; [official code](https://github.com/AI4Finance-Foundation/FinRobot), [research](https://arxiv.org/abs/2411.08804) | Useful separation of computed financial values and generated explanations. Apache-2.0 repository; data/API/model terms remain separate. It is not a truth oracle for ranking accuracy. |

For personalization, Das, Ostrov, Radhakrishnan and Srivastav formulate dynamic goal-wealth allocation with contributions/withdrawals. This is a closer conceptual match to goal achievement than optimizing rank correlation alone. It assumes a portfolio/opportunity model; it does not provide an all-stock ranker. [Authors' paper](https://srdas.github.io/Papers/DP_Paper.pdf)

My proposed separation is: stock evidence -> within-sector prediction -> profile-specific utility -> allocation/execution -> explanation. A risk optimizer or an LLM can improve its own stage without proving that the ordering itself became more accurate.

## 8. Licensing and reproducibility findings

Pinned code-license checks:

| Repository | Commit prefix | Root license observed |
|---|---|---|
| microsoft/qlib | 543552324638 | MIT |
| SJTU-DMTai/MASTER | de8f58557096 | MIT |
| SJTU-DMTai/DoubleAdapt | e20b6e46ccbd | No root license identified |
| Wentao-Xu/HIST | 149114c47fbd | No root license identified |
| OpenSourceAP/CrossSection | 5c2a1647dafb | GPL-2.0 |
| rejinreeza/trading_tool | 3e037198d962 | No root license identified |
| ninad164/auto-portfolio-management | 669b17e1e037 | MIT |
| raogaurav17/Nifty-Quant | 879db8c1a1b5 | GPL-2.0 |
| shiyu-coder/Kronos | 67b630e67f6a | MIT |
| microsoft/RD-Agent | 484776c211e4 | MIT |

These are repository observations, not a full dependency or legal audit. Public source visibility does not itself establish reuse permission. A repository's code license does not automatically cover pretrained weights, exchange data, third-party API feeds or trademarks. Pin each selected artifact and retain its actual terms before incorporation. No library was installed or integrated in this pass.

## 9. What would constitute convincing evidence here?

The principal methodological warning is repeated selection on historical backtests. Bailey and colleagues formalize backtest overfitting and propose a framework for estimating its probability. Their framework is evidence against equating the best result after many trials with a confirmed improvement. [Published research record](https://escholarship.org/uc/item/4w1110bb)

For this project, I recommend the following **future** evaluation contract:

1. **Population:** identical date/sector/profile populations for all challengers; show both the common evidence subset and full coverage. Keep missing-price/fallback rows visible, without pretending they contain learned stock evidence.
2. **Time:** training labels must be fully realized before fitting. Fundamentals and relationship edges must use publication/availability dates. Keep all same-date related records together; no random row split across duplicated profiles.
3. **Targets:** predeclare within-sector rank IC, pairwise accuracy and top-k relevance; independently report goal achievement, shortfall, drawdown, turnover and costs. Mean XIRR receives no selection weight under our existing requirement.
4. **Sector balance:** equal-sector summaries plus each sector, small sectors and worst-case sectors. Separate a uniform sector-momentum effect from within-sector discrimination.
5. **Dependence:** confidence intervals resample time blocks, accounting for overlapping investment horizons; stock-pair counts are not independent sample counts.
6. **Coverage:** report numerical, usable-price, fundamental, relationship and executable coverage separately. Excluding a difficult population may improve metrics while violating the user's intended scope.
7. **Selection:** log every attempted family and configuration. Our repeatedly used historical dates are exposed research data; new architecture names do not make those dates untouched.
8. **Realism:** include corporate-action verification, identity changes, suspended/delisted stocks where available, cash contributions, whole-share constraints and realistic execution assumptions.
9. **Human review:** blind comparative company evidence reviews with documented reasons and disagreement categories. Sir's arithmetic and an explicit qualitative rubric are complementary diagnostics, not objective future-return labels.
10. **Promotion:** compare against the existing champion and simple controls on matched populations. Report material regressions; if no method dominates all dimensions, present the tradeoff frontier rather than declaring universal superiority.

## 10. Concrete next research sequence

This sequence is a proposal from the review; none of these new experiments was run in this pass.

| Order | Experiment | Matched controls / ablation | Condition to proceed |
|---|---|---|---|
| 0 | Audit dated universe, labels, adjusted prices and filing availability | Existing frozen data manifests | Resolve material provenance gaps or state exactly which remain |
| 1 | DoubleEnsemble on sector-relative targets | Same LightGBM budget; sample weighting only; feature selection only; both | Source-compatible regression reproduction, memory estimate, fixed chronological selection |
| 2 | Sector/concept context | Existing model + peer aggregates; then HIST-style relations | Dated taxonomy/edges; remove relationship inputs to measure incremental value |
| 3 | MASTER | Same sequence inputs with simple MLP/GRU and no inter-stock attention | Corrected preprocessing; safe small-group handling; profile-independent information grouping |
| 4 | Kronos small frozen features/forecasts | Momentum/volatility and generic forecasting control | Checkpoint chronology, terms, cost estimate; no contaminated historical winner claim |
| 5 | DoubleAdapt or TRA | Same backbone with fixed rolling retraining | Mature-label updates; enough sequential observations for routing evidence |
| 6 | Filing-quality and liquidity specialists | Price-only matched model; missingness and stale-report ablations | Point-in-time filings and execution evidence; distinguish banks from industrial accounting ratios |
| 7 | Allocation or goal-policy improvement | Identical stock scores with alternative allocators | Evaluate allocation gains separately from ranking gains |

Given the current CPU-only environment, start with tree-based work and peer aggregates. Benchmark a small neural pilot before scheduling full-universe repeated training. This is a resource prioritization judgment, not a claim that neural methods cannot win.

The local worklog already records TabPFN, ranker, EBM, TabM and ensemble research. Their existence should be acknowledged before calling them new ideas. This review does not infer completion or superiority of previously launched jobs; their authoritative result artifacts must be audited separately. See `research/reports/sector_major_research_worklog_20261011.md`.

## 11. Final assessment

**Best overall reference system:** Qlib.

**Best first distinct algorithm to reproduce:** DoubleEnsemble, with explicit sector adaptations and ablations.

**Best relationship-model direction:** simple dated peer context first, then HIST/MASTER.

**Most relevant pretrained financial challenger found:** Kronos, conditional on checkpoint chronology and input quality.

**Most useful independent tooling:** sector-aware factor diagnostics and a transaction-aware simulator.

**Most important uncovered gap:** reliable point-in-time evidence and genuinely independent evaluation. More sophisticated models can be worth testing, but none of the reviewed literature establishes that these gaps disappear.

The literature review is complete for this scoped pass. It identifies implementable candidates, specific code issues, evidence limits and a bounded reproduction plan. It does not establish a new champion or completion of the broader model-development task.
