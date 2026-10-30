# Research sources and adaptation notes

The championship uses public research as motivation for candidate features and
objectives. No external implementation is copied into the project.

| Source | Relevant concept | Project adaptation |
|---|---|---|
| [George and Hwang, *The 52-Week High and Momentum Investing* (2004)](https://onlinelibrary.wiley.com/doi/full/10.1111/j.1540-6261.2004.00695.x) | Nearness to a past high may contain information beyond recent return. | Compare point-in-time distance from recorded and trailing 52-week highs. The sign is learned; closeness is not assumed always good. |
| [Maximum Drawdown, Recovery, and Momentum (2021)](https://www.mdpi.com/1911-8074/14/11/542) | Drawdown severity and recovery can describe different states. | Add full-history maximum drawdown, current and maximum underwater duration, and recovery from the worst observed trough. |
| [LightGBM ranking parameters](https://lightgbm.readthedocs.io/en/latest/Parameters.html) | LambdaRank truncation controls emphasis near a desired top-k cutoff. | Compare 25, 30, and 40 truncation settings around the Top-20 decision, with regularized tree settings. |
| [XGBoost learning-to-rank guide](https://xgboost.readthedocs.io/en/release_3.2.0/tutorials/learning_to_rank.html) | Query grouping, NDCG objectives, and pair construction should match the ranking task. | Keep each decision-date/profile as a query and test multiple graded relevance definitions. XGBoost is not an installed dependency in the research environment, so it is a documented future family rather than an unrun result. |
| [CatBoost ranking objectives](https://catboost.ai/docs/en/concepts/loss-functions-ranking) | Pairwise/listwise objectives offer alternative ranking losses. | Considered as an alternative family; not installed in the isolated research environment, so no claim of CatBoost superiority or inferiority is made. |
| [scikit-learn TimeSeriesSplit documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) | Ordered training precedes test, with a gap where needed. | Use the stricter project-specific rule that each 12-month outcome endpoint must be strictly before the scored decision date. Dates, rather than rows, form evaluation blocks. |

The available panel has only six historical training decisions, two 2023
development decisions, and two previously exposed 2025 decisions. All are
retrospective with current-universe survivorship. There is **no genuinely
untouched historical holdout**. A clean prospective comparison requires new
matured outcomes after the registered freeze.
