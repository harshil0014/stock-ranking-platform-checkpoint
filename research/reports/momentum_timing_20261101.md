# One-shot test: momentum selection plus reversal timing

**Decision: KILLED by the preregistered yearly-sign rule.** Pooled net returns and
incremental edges survive both cost stresses and removal of the least-liquid
quintile, but the timing overlay fails in 2021 and the plain dip rule fails in
2023. Exposed-period performance was not evaluated. No second threshold search,
new model family, production change, or ledger change followed this failure.

## What was fixed in advance

Start with the global top quartile of the unchanged **20% professor-factor lens**,
selected before joining the NSE source panel. That lens is still 80% champion plus
five 4% factor blocks, not majority weighting of Sir's factors. Compare selected
stocks at least 10% below their highest recorded adjusted closing price with
selected non-dip stocks. Within dips, the timing overlay takes the highest-scored
quartile from the previous price/volume Ridge head. No threshold optimization.

Three annual expanding fits, 2021–23, alpha=10, the same eight globally normalized
features and original training support. Labels must mature before January 1 of the
prediction year. Saved coefficients reproduce the original head's full-support
12-date IC exactly (maximum difference 6.9 e-17); no new comparison
model was selected. This is a test of combining an existing selection lens and
head, not a new head search.

Actual next-open entries, exit at the 21st observed session close including entry
session, fractional-return proxy. Buy and sell each incur 75 bp or 100 bp. These are
**21-session net cohort returns**, not XIRR, annualized returns, a live portfolio,
or a simulation of the workbook's staggered 10–40% ladder and cash allocations.

Liquidity uses prior 20 sessions' average provider Close × Volume, strictly before
the signal date. Quintiles are defined on the full mapped NSE source support
before preference selection. The ex-bottom-quintile analysis retains the original
dip and overlay memberships; it does not refill slots from other stocks.

## Pooled result across all 12 development dates

All returns are percent; the final two columns are percentage-point differences.
Dates are equally weighted; stocks within each group/date are equally weighted.

| liquidity_scope | cost_bps | dip_net | non_dip_net | overlay_net | dip_minus_non_dip | overlay_minus_dip |
| --- | --- | --- | --- | --- | --- | --- |
| all | 75 | 2.243 | 1.781 | 3.177 | 0.462 | 0.934 |
| all | 100 | 1.733 | 1.273 | 2.663 | 0.460 | 0.929 |
| exclude_bottom_quintile | 75 | 1.916 | 1.620 | 3.030 | 0.295 | 1.114 |
| exclude_bottom_quintile | 100 | 1.407 | 1.114 | 2.516 | 0.294 | 1.108 |


At 100 bp per side, the full-cohort non-dip mean is 1.273%, plain dip 1.733%, and
dip-plus-overlay 2.663%. The overlay adds 0.929 pp versus the plain dip rule in the
pooled average. Removing the least-liquid fifth leaves an overlay increment of
1.108 pp. **Cost or lowest-quintile dependence is not what kills this result.**

With the same holding horizon and proportional costs, return differences between
groups mainly scale with the fee factor. We therefore also required absolute net
dip and overlay returns to beat cash; merely preserving a relative edge after
cost would be too weak.

## The yearly rule kills it

At 100 bp per side, percent returns and percentage-point differences:

| liquidity_scope | cost_bps | year | dip_net | non_dip_net | overlay_net | dip_minus_non_dip | overlay_minus_dip |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all | 100 | 2021 | 2.304 | 0.585 | 0.523 | 1.719 | -1.781 |
| all | 100 | 2022 | 0.664 | 0.035 | 1.958 | 0.630 | 1.294 |
| all | 100 | 2023 | 2.232 | 3.201 | 5.507 | -0.970 | 3.276 |
| exclude_bottom_quintile | 100 | 2021 | 1.911 | 0.372 | 0.668 | 1.539 | -1.243 |
| exclude_bottom_quintile | 100 | 2022 | 0.533 | -0.137 | 1.871 | 0.670 | 1.338 |
| exclude_bottom_quintile | 100 | 2023 | 1.779 | 3.106 | 5.008 | -1.327 | 3.230 |


- In 2021, the overlay trails plain dip by 1.781 pp; after excluding the least-liquid
  fifth it still trails by 1.243 pp.
- In 2023, plain dip trails non-dip by 0.970 pp; after excluding that fifth it trails
  by 1.327 pp.
- The same two sign failures occur at 75 bp per side. All required sample-size
  checks passed: 12 dates, at least 2 per year in both liquidity scopes. This is a
  demonstrated preregistered failure rather than a missing-data verdict.

The pooled result looks attractive. It still fails the exact rule requested.
Changing the years, dip threshold, overlay fraction, or lens weight now would
create another post-result search, so this candidate ends here.

## Uncertainty and the reversal hypothesis

365-day block-bootstrap 95% intervals at 100 bp, in percentage points:

| liquidity_scope | cost_bps | metric | mean | low95 | high95 | dates |
| --- | --- | --- | --- | --- | --- | --- |
| all | 100 | dip_minus_non_dip | 0.460 | -0.993 | 2.294 | 12 |
| all | 100 | overlay_minus_dip | 0.929 | -1.013 | 2.642 | 12 |
| exclude_bottom_quintile | 100 | dip_minus_non_dip | 0.294 | -1.237 | 2.186 | 12 |
| exclude_bottom_quintile | 100 | overlay_minus_dip | 1.108 | -0.720 | 2.599 | 12 |


There are only three development years and 12 quarterly snapshots. The intervals
are descriptive and do not establish independence, stability or live execution.
This test reuses development dates that motivated the hypothesis.

The short head's standardized percentile-feature coefficients are:

| feature | 2021 | 2022 | 2023 |
| --- | --- | --- | --- |
| downside252 | -0.00725 | 0.033295 | 0.023993 |
| log_quantity | 0.009979 | 0.008998 | 0.02275 |
| log_turnover | -0.015585 | -0.044007 | -0.058133 |
| return126 | -0.022252 | -0.04024 | -0.020005 |
| return21 | -0.036756 | -0.032739 | -0.038644 |
| return252 | -0.019042 | 0.031168 | 0.018652 |
| return63 | -0.029771 | -0.000572 | 0.007967 |
| volatility252 | 0.027435 | -0.006638 | -0.020133 |


The return21 coefficient is negative in all three annual fits, consistent with a
short-term reversal component. Correlated predictors make that an association,
not causal feature attribution. The full-universe IC advantage does not guarantee
timing reliability inside a long-term-winner/dip subset, as 2021 shows.

## Coverage, safeguards and limits

The source join supplies NSE EQ observations only; BSE-exclusive stocks are not
tested by this pilot. The selection cutoff was computed on all eligible lens
identities before the NSE join, so missing source coverage did not redefine the
quartile. Recorded closing highs depend on available provider history and price
adjustment vintages, not a certified exchange intraday ATH from IPO onward.
The mapped provider quote venue is not independently certified as an executable
NSE fill. Provider turnover is a liquidity proxy, not measured spread or capacity.

Current survivors, historical sector labels, and the previous source panel's
outcome-availability conditioning remain limitations. A sparse quarterly entry
study does not measure daily ladder fills, cash drag, circuit-lock fills,
suspensions, taxes, lot sizes or delisting proceeds. Corporate action flags block
unresolved holding windows; that is an exclusion safeguard, not repaired prices.

During pre-outcome review, the first worker was paused during cache preparation
and stopped before any fit or metric. A selection bug was corrected: overlay
membership is frozen before future-price/action failures; unknown future outcomes
block the comparison rather than cause replacement picks. As-of failures
quarantine the date. The original protocol and pause evidence were retained; no
weights, thresholds or scoring years changed. Aggregate coverage, failures,
liquidity counts, source hashes and training-fold receipts are included. Stock
identities and memberships remain local; no public stock-pick list was produced.

One research worker and compute thread, Windows CPU cap 12.5%,4 seconds active and
2 seconds rest, no GPU. **14 local tests and 24 integrity checks passed.**
This is local evidence, not a remote CI claim. The incumbent and prospective
ledger branches remain unchanged. There is no basis here to promote this timing
overlay, and the profitable pooled average does not override its failed gate.
