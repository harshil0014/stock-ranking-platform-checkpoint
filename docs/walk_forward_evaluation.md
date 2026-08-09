# Walk-forward outcome evaluation

This milestone reveals outcomes only after the predictions, cohorts, sector taxonomy, and protocol were frozen. It evaluates the Git-frozen blind-prediction bundle with fingerprint `c438c31967e1f2685bbe77d85db6ca44617e024c699dba3749ee3523af6e401d` under protocol `a81278b799e1a61c3684f3b319fb14e2f6f0db6a2bdad1cd79b2ce13fd6f8576` and pre-outcome amendment `7f8c5d40de88077f3b6afcd471d0db4377fab567d2839e719a71ee6b11ae7163`.

## Outcome label

For each frozen eligible company-date, Yahoo history is requested through yfinance at daily frequency with `auto_adjust=False` and `repair=True`. The request begins on the ranking date and ends immediately after the 12-calendar-month target. It retains Close, Adj Close, dividends, splits, and the provider repair indicator where supplied. Provider symbols come directly from the frozen identity-resolution artifacts; successor substitution is prohibited.

The 3-, 6-, and 12-month target is the ranking date plus the stated number of calendar months. The endpoint is the last trading observation on or before that target, never after it. The label is:

```text
future_adjusted_return = endpoint Adj Close / ranking-date Adj Close - 1
```

It is described as an **ADJUSTED-PRICE FUTURE RETURN**, not total shareholder return. Start and endpoint prices, calendar targets, actual endpoint dates, distances, and provider identities remain auditable.

## Frozen comparison

Research V2 uses its frozen score, with higher better. Matched Baseline uses the frozen within-cohort rank with lower rank better. Each comparison uses identical stocks and is calculated within historical official NSE sector and ranking date; raw values are never pooled across sectors.

The primary metric is 12-month sector-date Spearman Rank IC for matched groups with at least three stocks. Spearman is the existing repository correlation applied to pandas average ranks. The primary aggregate is the equal-weight arithmetic mean of sector-level `Research V2 Rank IC - matched Baseline Rank IC`. The structurally available primary sample contains only three observations, all in 2025, so it has **VERY LOW PRIMARY SAMPLE SIZE** and is not statistically conclusive.

Secondary Rank IC uses the same rule at 3 and 6 months. Reported ICIR is unannualized mean sector-date Rank IC divided by its sample standard deviation (`ddof=1`); sector-date observations are not treated as daily observations.

For all frozen sector-date groups with at least two peers, pairwise ordering evaluates every unordered pair. A model-rank tie receives 0.5 credit; an exact realized-return tie is excluded from the denominator. Top-stock excess return subtracts the equal-weight matched-cohort mean from the frozen model's top stock. Top-half-minus-bottom-half uses equal-sized groups and omits the deterministic middle stock in odd cohorts; ties are ordered by frozen rank and ticker. These are ranking diagnostics, not portfolio backtests.

## Reproducibility and limits

Raw outcome caches and evaluation bundles live beneath ignored `data/walk_forward/` paths. A second evaluation is built from the same cached outcome bytes without another provider request; canonical CSV/JSON artifacts and their fingerprints must match byte for byte. The blind bundles are never overwritten.

Interpretation must retain these limits: only four annual ranking dates exist; strict point-in-time filing availability reduced Research V2 coverage; only three primary sector-date observations were structurally available; statistical power is very low; retrospectively acquired Yahoo history inherits adjusted-price semantics; and no transaction costs, liquidity assumptions, or execution model are represented. This evaluates ranking quality, not profitability or investment usefulness.
