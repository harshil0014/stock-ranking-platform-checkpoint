# Professor-factor frontier: three larger departures

Three fixed candidates assign **75% of their score to the five measured professor
factor blocks**, against the champion, the 20% lens and a plain linear 75% control.
Locked preference candidate: **none**. No automatic production
promotion, fresh prospective holdout, or investment-superiority claim is made.

## What actually changed

- **balanced75:** geometric five-factor core. One very weak block cannot be fully
  compensated by four strong ones. Equal log elasticities; this is a joint 75%
  nonlinear score component, not literal 15% linear weight per factor.
- **outrank75:** sector peers vote across five factors. A stock must beat a peer
  in at least three blocks; a deficit larger than 0.40 in any block vetoes that win.
  Wins minus losses become a sector percentile. 75% joint factor-voting component,
  with 25% champion. This is a project-specific voting rule, not a replicated paper.
- **tail75:** 75% arithmetic factor core, 25% upper-quantile learned SIP forecast.
  The small LightGBM head has 100 trees, 7 leaves, depth 3, quantile 0.80 and one thread,
  with no tuning. Five factor percentiles plus three price/risk inputs; annual
  training uses only corrected outcomes matured before January 1. Its target is
  log1p(annual SIP XIRR clipped[-.95,3]), not calibrated goal probability or a
  prediction of doubling returns. [LightGBM's quantile objective and alpha parameter](https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html).

The five blocks remain annual-return consistency, 3Y CAGR, 5Y CAGR, recorded closing
high recency, and historical whole-share SIP profit. This is a preference derived
from the workbook, not weights prescribed by Sir's paper. Fundamental/earnings
fields have not been invented. All source features remain price/SIP oriented.
Nominal score mass is not independent influence, predictive accuracy, or profit.

## New outcome basis and explicit larger risk budget

The earlier training labels could start at the signal close. This batch generated
new per-stock 12-month SIP outcomes:7500 every 30 calendar days, cash until the first
observed open strictly after each deposit date, actual Open×AdjClose/Close,
100 bp per buy and terminal sale, fractional shares, terminal last close at/before
the known horizon with maximum 7-day gaps. Unresolved provider/official action
windows and missing prices remain unknown. Old labels and old tables are intact.
The learned tail head trains on these corrected labels, not the old cashflows.

This intentionally allows a wider preference/risk tradeoff than the old 20% lens:
alignment gain at least 5 percentile points, IC loss at most 0.02, Top-3 goal-hit loss
at most 3 pp, average selected-stock drawdown at most 5 pp worse, and at least 25%of
sector Top-3 sets changed. Actual global Top-20 portfolio XIRR must be no more than 3 pp
lower and drawdown no more than 5 pp worse, on at least 8 matched dates. These are
fixed retrospective research budgets, not a risk policy chosen by the professor.
At least 8 dates must each have 20 complete matched sector queries. No missing
selected-stock replacement. Highest alignment among passers, fixed name tie break.

## Development: preference and stock outcome comparison

2020–23; equal sector then date weighting. Alignment, hit rate, drawdown, changed
fraction and overlap are percent. IC and IC_delta are correlations. Alignment
compares the same input factors being weighted and is mechanically circular;
it measures preference fit, not an independent financial win.

| model | alignment | rank_ic | top3_goal_hit | top3_stock_dd | changed | overlap | IC_delta |
| --- | --- | --- | --- | --- | --- | --- | --- |
| balanced75 | 83.162 | -0.04143 | 52.234 | -31.263 | 88.437 | 44.212 | -0.07248 |
| champion | 65.264 | 0.03105 | 56.199 | -25.916 | 0.000 | 100.000 | 0.00000 |
| lens20 | 69.707 | 0.02251 | 55.766 | -26.370 | 31.933 | 87.212 | -0.00853 |
| linear75 | 83.145 | -0.04436 | 52.040 | -31.358 | 88.307 | 44.598 | -0.07541 |
| outrank75 | 82.533 | -0.05118 | 52.611 | -30.991 | 91.912 | 42.792 | -0.08223 |
| tail75 | 82.594 | -0.06973 | 48.508 | -35.883 | 96.353 | 25.196 | -0.10077 |


Top-3 sets are chosen before outcome filtering. If any model's selected stock has
an unknown label, the sector/date's Top-3 outcome statistics are unavailable for
every model. IC uses common valid stocks, at least 5 per sector. Alignment and
overlap use the full as-of feature cohort, independently of future labels.
The plain linear 75% control shows whether nonlinear or learned complexity earns
anything beyond simply increasing the factor share. It is a reference, not an
extra candidate selected after results.

## Actual portfolio cashflows versus champion

100 bp per side. XIRR and drawdown differences below are model minus champion,
in percentage points, on identical valid dates. Negative drawdown delta means
worse loss. GlobalTop-20 and equal-sector Top-3 hold selection/weights fixed for the
12-month cohort and use the same monthly next-open contributions. These overlapping
cohort means are not a chainable strategy CAGR or a live SIP ladder simulation.

| model | policy | matched_dates | xirr_delta | drawdown_delta |
| --- | --- | --- | --- | --- |
| champion | global_top20 | 16 | 0.000 | 0.000 |
| champion | sector_top3 | 10 | 0.000 | 0.000 |
| lens20 | global_top20 | 15 | -2.260 | -1.123 |
| lens20 | sector_top3 | 9 | -2.763 | -0.644 |
| linear75 | global_top20 | 13 | -11.846 | -5.671 |
| linear75 | sector_top3 | 5 | -7.075 | -5.216 |
| balanced75 | global_top20 | 13 | -12.186 | -5.779 |
| balanced75 | sector_top3 | 7 | -7.294 | -4.838 |
| outrank75 | global_top20 | 15 | -3.295 | -1.759 |
| outrank75 | sector_top3 | 7 | -6.485 | -4.280 |
| tail75 | global_top20 | 14 | 7.688 | -6.531 |
| tail75 | sector_top3 | 2 | -3.101 | -5.947 |


The notable risky tradeoff is **tail75**: global Top-20 mean XIRR exceeds the champion
by **7.688 pp** on **14 matched dates**,
but average portfolio drawdown is **6.531 pp worse**.
Its sector Top-3 goal-hit rate is **48.508%**, versus
**56.199%** for champion, and broad rank IC is
**-0.06973**. This can be a different right-tail/risk exposure,
not a general ranking improvement. No volatility-matched tail control was in this
experiment, so the Top-20 gain is not established as stock-selection alpha. The
sector Top-3 portfolio comparison has only two matched dates and cannot support a
performance claim. No public top picks or changed model result from this finding.

Only global Top-20 is in the frozen pass gate; sector Top-3 is a reported diagnostic.
Portfolio failures block complete observations; they do not remove stocks and
redistribute their weight. Missingness can bias the surviving observations.

## Frozen budget decision

| model | pass_preference_budget | failed_checks |
| --- | --- | --- |
| balanced75 | False | ic_budget, goal_budget, stock_drawdown_budget, portfolio_xirr_budget, portfolio_drawdown_budget |
| outrank75 | False | ic_budget, goal_budget, stock_drawdown_budget, portfolio_xirr_budget |
| tail75 | False | ic_budget, goal_budget, stock_drawdown_budget, portfolio_drawdown_budget |


Passing this budget, if any candidate does, means only a candidate for preference
research. It does not establish improved investment performance. A permitted IC
loss can even produce negative IC; positive IC and a familywise hurdle are
separately required for a predictive-win claim.

365 day centered block-bootstrap 95% intervals for development IC differences,
with a max-statistic hurdle over the three new challengers,2000 fixed-seed draws:

| model | ic_delta | low95 | high95 | familywise_ic_hurdle | clears_predictive_hurdle |
| --- | --- | --- | --- | --- | --- |
| balanced75 | -0.07248 | -0.13793 | -0.01493 | 0.09310 | False |
| outrank75 | -0.08223 | -0.15425 | -0.01823 | 0.09310 | False |
| tail75 | -0.10077 | -0.20560 | -0.00599 | 0.09310 | False |


## How different are the rankings?

Mean within-sector/date Spearman correlation with champion, equal dates:

| period | model | rho |
| --- | --- | --- |
| development | balanced75 | 0.56505 |
| development | champion | 1.00000 |
| development | lens20 | 0.98916 |
| development | linear75 | 0.56201 |
| development | outrank75 | 0.48110 |
| development | tail75 | 0.15006 |


Changed sets and average membership overlap are reported above. A 75%factor
component still shares information with the champion; this is not 75%new signal.

## Locked exposed diagnostic

Not evaluated: no candidate passed the registered development preference/risk budget.

## Coverage, verification, and limitations

Corrected label cache: **73,122 stock-date rows**, **72,809 valid**,
**313 unknown**, across 44 dates.
Pre 2020 mature dates train the tail head;2020–23 is development. All policies use
the same complete factor/price-input population. The model covers mapped NSE/BSE
identities with data, but provider quote venue and historical executions are not
independently certified. It does not constitute full NSE/BSE coverage.

The code fixes score architectures before looking, checkpoints labels per date,
pins protocol/input/model hashes, preserves unknowns, and locks development
selection before any exposed result. **14 local tests and 16 integrity checks
passed.** Full scored memberships and trained models remain local; compact
aggregate outcomes, coverage, overlaps, failures and chronology receipts are
versioned. Local checks do not imply external CI or an investment audit passed.

Current-survivor identities, retrospective sector labels, provider adjustment
vintages, sparse overlapping horizons, and reused development periods remain
material limits. Archived factor input vintages and corporate-action knowledge
are not newly certified. The historical SIP-profit input still follows the
workbook's invested-capital convention; new outcome cashflows include all
scheduled deposits and idle cash. The two quantities are not interchangeable.
No circuit, suspension, market impact, tax or nominal whole-share execution
simulation is claimed. Guarding unresolved corporate actions is not repairing
their historical prices. There is still no fresh complete daily champion input
pipeline eligible to start the 12-month holdout.

One research worker and compute thread, Windows CPU cap 12.5%, 4 seconds active and
2 seconds rest, no GPU, 20-minute worker watchdog. The champion, UI, both prospective
ledger branches, and daily ledger automation are unchanged. No stock-pick list,
real-money position, or regulatory performance claim was published.
