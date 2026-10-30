# Sector Champion: models, research, factors and weights

Prepared 18 October 2026. This is a concise map of the **locally active** `/sector-champion` revision `dual_w0.01_sip_risk_confirmed0.01_20261017`, plus the major models and papers actually reviewed or tested in its research lineage. The score snapshot is 3 October 2026. All 4,436 stocks receive a numerical score; 133 use limited-price-evidence fallback. Historical dates have been repeatedly researched, so the comparisons are not fresh validation.

## Exact scoring architecture

Let `O` be the saved open-model sector percentile, `D` the saved defensive LightGBM sector percentile, and `P` the saved price LightGBM sector percentile. The original champion is `C = .60 O + .15 D + .25 P`. `O = .95 L + .05 × mean(CatBoost_defensive, Ridge_defensive)`, where `L` is the earlier LightGBM `rank_xendcg_balanced_15` challenger. Thus the **expanded coefficients of the original champion** are 57% `L`, 1.5% CatBoost, 1.5% Ridge, 15% defensive LightGBM, and 25% price LightGBM. These are **component score mixing coefficients**, not learned feature importances or performance attributions. Predictions are normalized to sector percentiles before mixing.

The current website adds:

* `H = .01 × (.60 × dual_high_age_percentile + .25 × dual_high_proximity_percentile + .15 × momentum_percentile − .5)`. Dual means an equal blend of 52-week and available-history recorded closing highs. The maximum score movement is ±.005. The .60/.25/.15 weights apply **only to H**.
* `S = .01 × (sector_SIP_profit_percentile − .5) × invested_fraction × inverse_downside_percentile`. The maximum score movement is ±.005. SIP profit is trailing simulated whole-share gain divided by actual money spent, excluding unused cash. It is not XIRR or expected future return.
* Final score `C + H + S`; sort descending **within sector**. `Unclassified` is a display group rather than a verified industry.

Both adjustments abstain if required evidence is missing. High adjustment requires at least 252 observations, 365 history days, 80% active-volume days, recent positive volume and at least five valid peers. SIP also abstains for missing profit, an unresolved relevant corporate action, illiquid/stale evidence or too few peers. They preserve numerical coverage rather than excluding stocks.

### Factor inventory: open and defensive models

The earlier LightGBM, CatBoost, Ridge and defensive LightGBM models use these **14 raw variables**: days since recorded high; distance from recorded high; 52-week-high freshness; one-year downside volatility; 12-to-1 momentum; distance from 52-week high; full-history maximum drawdown; months of price history; three-year CAGR; observed five-year CAGR; high support; strict one-year CAGR; six-month momentum; one-year downside frequency. They also use **14 corresponding within-sector percentile variables**, evidence fraction, active-volume fraction and one-year observation count. This is 31 inputs for the open-model family. The defensive LightGBM additionally receives log amount, lookback months, log SIP interval and target CAGR: **35 inputs**. Its saved tree has **zero splits on those four profile fields**. The open CatBoost and Ridge each get only **1.5%** of the original champion's total component mixture.

The earlier LightGBM challenger learned a balanced training label: 50% sector-relative future SIP return rank, 25% drawdown rank, 25% inverse goal-shortfall rank. The CatBoost/Ridge defensive target and defensive LightGBM target used 25% return, 50% drawdown and 25% inverse shortfall. **Training-label weights do not become direct score weights for a feature.**

### Factor inventory: price LightGBM

Its **31 raw inputs** are:

* Returns: 21-, 63-, 126- and 252-day return; 12-to-1 momentum.
* High behavior: 63-, 126- and 252-day high gap; 252-day high age; fraction of days near a running high; fraction setting a high; breakout strength.
* Trend: 126-day slope; trend fit (`R²`); price-path efficiency.
* Risk/distribution: annualized volatility; downside volatility; drawdown; positive-day fraction; unchanged-day fraction; largest-jump share; fifth-percentile daily loss; return skew.
* Moving averages and change: distance from the 21-, 63-, 126- and 252-day moving averages; acceleration.
* Evidence: number of observations; price staleness; history length.

It also receives **31 corresponding within-sector percentile variables**, sector median 126-day return, sector positive-return breadth, stock momentum relative to sector, evidence fraction, and four profile fields. Total: **70 inputs**. The saved model has **zero splits on amount, lookback, interval and target**. The selected `rank_xendcg_balanced` learning objective concentrated on sector-relative rank, with a target of 50% return, 25% drawdown and 25% inverse shortfall. The website's SIP overlay makes amount, interval and lookback capable of changing final rank; target CAGR affects goal calculations.

## Open-source methods in the active score

| Method | Active contribution | What we took from it | Boundary |
|---|---|---|---|
| [LightGBM](https://proceedings.neurips.cc/paper_files/paper/2017/hash/6449f44a102fde848669bdd9eb6b76fa-Abstract.html) and its [ranking objectives](https://lightgbm.readthedocs.io/en/latest/Parameters.html) | 57% earlier ranker + 15% defensive ranker + 25% price ranker = 97% of the original champion's mixture | Efficient boosted trees and direct within-sector learning to rank | Trained on our data; no pre-trained stock oracle. |
| [CatBoost](https://proceedings.neurips.cc/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html), [YetiRank](https://proceedings.mlr.press/v14/gulin11a.html) | 1.5% of original mixture | A distinct ranking algorithm as a small complement | Original CatBoost paper explains the library, not our Indian performance. |
| [Ridge regression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html) | 1.5% of original mixture | Regularized linear control alongside trees | Simple statistical model, not a pre-trained financial model. |

The percentages above total 100% **before** H and S. The high and SIP adjustments are additive score units, so interpreting them as percentage shares of a nonlinear model would be false.

## Papers that directly shaped the active design

| Source | Short takeaway | What we actually did |
|---|---|---|
| [Poh et al., cross-sectional learning to rank](https://arxiv.org/abs/2012.07149) | Compare stocks as a ranking problem. | Train/evaluate stock ordering inside sector/date groups. Our SIP targets are project adaptations. |
| [Lyzhin et al., ICML 2023](https://proceedings.mlr.press/v202/lyzhin23a.html) | Ranking loss choice matters. | Compare ranking objectives; retain LightGBM `rank_xendcg` price and baseline heads. |
| [George and Hwang, 52-week high](https://doi.org/10.1111/j.1540-6261.2004.00695.x) | Proximity to a rolling high can matter for momentum. | Include high gaps/proximity. The paper does not prescribe our coefficients. |
| [Bhootra and Hur, timing of 52-week high](https://doi.org/10.1016/j.jbankfin.2013.05.025) | The age of a rolling high can matter. | Test and retain a small high-recency adjustment by user choice. It does not justify a universal lifetime-ATH penalty. |
| [Moskowitz and Grinblatt, industry momentum](https://www.aqr.com/insights/research/journal-article/do-industries-explain-momentum) | Sector context matters in momentum. | Rank within sectors and add sector median return/breadth context to the price model. |
| [Gu, Kelly and Xiu, asset pricing ML](https://doi.org/10.1093/rfs/hhaa009) | Nonlinear interactions and characteristics such as momentum/liquidity/volatility warrant testing. | Compare tree and simple linear controls. Their US findings are not claimed as Indian evidence. |
| [Grinblatt and Han, capital gains](https://doi.org/10.1016/j.jfineco.2004.10.006) | Investor gains relative to acquisition cost can affect behavior. | Test a trailing SIP-profit percentile. Our hypothetical ledger is different from the paper's aggregate measure. |

## Other models and ideas we tested, studied or rejected

These **do not contribute to the current website score** unless their idea is separately noted above. The project reports contain results and limitations; a paper is a hypothesis source, not proof of this model's accuracy.

| Method/source | What we learned or tried | Status here |
|---|---|---|
| [XGBoost learning to rank](https://xgboost.readthedocs.io/en/stable/tutorials/learning_to_rank.html), [KDD paper](https://doi.org/10.1145/2939672.2939785) | Another boosted-tree ranking control, with grouped NDCG training. | Tested as a standalone/blend candidate; not active. |
| [Extra Trees](https://doi.org/10.1007/s10994-006-6226-1) | A randomized-tree control against boosted rankers. | Tested; not active. |
| [TabPFN](https://www.nature.com/articles/s41586-024-08328-6), [official code](https://github.com/PriorLabs/TabPFN) | Small-data tabular prior and teacher/student ideas. | Direct and hybrid experiments; no broad gate pass; not active. |
| [TabM](https://github.com/yandex-research/tabm) | Compact neural ensemble specialist. | Tested in specialist rounds; not active. |
| [Explainable Boosting Machine](https://interpret.ml/docs/ebm.html) | Additive and limited-interaction specialist, easier to inspect. | Tested; not active. |
| [Microsoft Qlib](https://github.com/microsoft/qlib), [DoubleEnsemble](https://doi.org/10.1109/ICDM50108.2020.00087) | Research pipeline, temporal evaluation, training-sample weighting and feature selection. | Framework/code studied and research experiments run; no Qlib or DoubleEnsemble component in active score. |
| [TRA](https://arxiv.org/abs/2106.12950), [DoubleAdapt](https://arxiv.org/abs/2306.09862) | Adapt to changing market regimes. | Reviewed; label maturity and historical leakage remain hurdles; not active. |
| [HIST](https://arxiv.org/abs/2110.13716), [MASTER](https://arxiv.org/abs/2312.15235), [FinGAT](https://arxiv.org/abs/2106.10159) | Learn relationships among stocks and sectors. | Reviewed; small peer-context adaptations tested. No graph/attention network in active score. |
| [Kronos](https://ojs.aaai.org/index.php/AAAI/article/view/39730), [Chronos](https://arxiv.org/abs/2403.07815), [TimesFM](https://arxiv.org/abs/2310.10688) | Pre-trained time-series representation/forecast ideas. | Reviewed as possible challengers; not active. A checkpoint may contain information from dates later than a historical test. |
| [Da, Gurun and Warachka, Frog in the Pan](https://doi.org/10.1093/rfs/hhu003) | Smooth progress may differ from one large jump. | Tested continuity proxies such as trend efficiency and jump share; not an extra active overlay. |
| [Daniel and Moskowitz, momentum crashes](https://doi.org/10.1016/j.jfineco.2015.12.002) | Momentum can carry downside risk. | Tested downside/volatility complements; risk variables already exist inside active learned heads. |
| [Safe Policy Improvement](https://proceedings.mlr.press/v97/laroche19a.html), [expert aggregation](https://proceedings.mlr.press/v128/korotin20a.html) | Be cautious when routing between models with weak evidence or delayed outcomes. | Tested routing/stacking ideas; not active. No formal safety guarantee applies. |
| [Super Learner](https://biostats.bepress.com/ucbbiostat/paper222/) | Combine out-of-time predictions instead of selecting a single learner. | Tested learned stacking; retained the simpler fixed mixture above. |
| [Open Source Asset Pricing](https://www.openassetpricing.com/) | Catalog published cross-sectional factors with definitions. | Reviewed as a signal reference; its US data/code do not supply Indian historical features. |
| [Quality Minus Junk](https://www.aqr.com/Insights/Research/Working-paper/Quality-minus-Junk) | Quality screens may help identify risky momentum. | Current-fundamental diagnostic only; undated present-day fundamentals were not inserted into historical training. |

The broader [literature survey](../../research/reports/sector_ranking_literature_review_20261017.md) also covers Indian open-source projects (`trading_tool`, `auto-portfolio-management`, `Nifty-Quant`), Alphalens, Zipline, LEAN, portfolio optimizers, FinRL and financial language agents. Those supplied audit, universe or portfolio-workflow ideas. **None is an active ranking component.** They have no numerical weight in this champion.

## Reproduction and interpretation

The active package and hashes are in `research/runtime/sector-champion-recency/manifest.json`. The actual feature lists and training labels are in `research/runners/full_coverage_challenger_20261008.py`, `research/runners/full_coverage_open_models_20261008.py`, `research/runners/profile_aware_sector_20261008.py` and `research/runners/sector_price_rebuild_20261010.py`. Runtime combination and guard rules are in `src/stock_ranker/sector_champion_product.py` and `src/stock_ranker/sip_profit_signal.py`.

The fixed current snapshot is **not a current-market valuation**. Most inputs are price/history-derived; the model does not have a complete point-in-time Indian fundamental, news or valuation record for every stock. None of the cited papers fixes our score coefficients or validates this exact stock universe.
