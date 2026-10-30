# Personalized Ranking Championship — 2026-10-01

## Verdict

**FROZEN CHAMPION RETAINS TITLE — no challenger is sufficiently robust.**

The frozen `d499580` 67% Goal / 33% LambdaRank model remains the production
champion. The strongest direct history-aware model improves 2023 target
shortfall and future drawdown but reverses both gains on the exposed 2025 dates.
The strongest conservative blend improves 2023 ordering and shortfall by less,
but retains most of the current missing-history concentration and still worsens
2025 shortfall. No production serving code, accepted state, freeze, or
deployment was modified.

## Evidence boundary and tournament design

The historical executable panel has six nominal training decisions
(2016-12-31, 2017-12-31, 2018-12-31, 2019-12-31, 2022-06-30,
2022-12-31), two 2023 development decisions, and two 2025 decisions already
exposed in prior research. A row enters a fit only if its 12-month outcome
endpoint is **strictly earlier** than the scored decision date. Each
decision-date/profile is a ranking query. There is **no genuinely untouched
historical holdout**. Historical panels are retrospective and retain
current-universe survivorship; source publication timing cannot be proven for
every old observation. The 2025 results are diagnostic only and did not choose
models or parameters in this championship.

The frozen current score is reproduced from its sealed rows to maximum absolute
error `2.22e-16`. Its current Goal and execution values are used exactly for
challenger current inference. Historical comparisons use the original
chronological champion-policy predictions on 2023/2025 dates; the 2019/2022
qualification baseline is a maturity-purged reconstruction of the same 67/33
architecture. The original 2023/2025 predictions and the exact current seal
are distinct artifacts, and are never represented as one model fit.

The championship has four stages:

1. **Broad qualification:** 30 candidates across eight feature recipes, three
   ordinal relevance definitions, and ridge/histogram-boosting alternatives on
   2019/2022 dates. Six top-utility candidates and one high-position family
   advanced. The [leaderboard](../../experiments/personalized-championship/v1/round1_leaderboard.csv)
   and [elimination reasons](../../experiments/personalized-championship/v1/round1_eliminations.json)
   preserve every entry.
2. **Development:** 78 parameter/weight settings tested on 2023 dates, with
   Goal weights 60%, 63%, 67%, 70%, 73%, and 75%. A Pareto flag and profile
   guardrails are recorded in the [Round-2 leaderboard](../../experiments/personalized-championship/v1/round2_leaderboard.csv).
   Only one direct candidate satisfied the stated development profile gate.
3. **Robustness:** three distinct direct contenders received one exposed 2025
   diagnostic, plus date, profile, sector (minimum 20 comparable securities),
   turnover, extreme-return, and current missing-history audits. A separate
   conservative family tested 60 blends of the old and new ranker percentiles
   with Goal centered near 67%; finalist blends were then checked on 2025.
4. **Championship:** the frozen policy is compared against every finalist on
   the same date/profile rows. The sealed current ranking supplies the
   missing-history and named-security audit; it has no matured future outcome.

The mean-XIRR observations include extreme retrospective corporate-action
outcomes. Selection used ordinal labels or rank-percentile regression targets,
and the comparison reports median and winsorized mean XIRR separately. No
candidate was advanced because of a gigantic arithmetic mean.

## Features and research basis

The price history features use observed adjusted closes through each decision
date: distance and days from the recorded high, trailing 52-week-high distance,
full-history maximum drawdown, current and longest underwater duration,
recovery from the worst recorded trough, one-year volatility and downside
volatility, and history length. They accompany the original executable XIRR,
Goal, 3Y CAGR, whole-share affordability/cash, and drawdown inputs. The
general history feature computation and since-listing/sector-shrunk estimated
5Y CAGR are in `personalized_history_challenger.py`; observed prices are never
backfilled before listing. Estimates retain the explicit `ESTIMATED` source
flag, `history_months`, and `since_listing_cagr`. Current 2026 terminal prices
come only from the frozen official repair observations where necessary.

The feature ideas were adapted from the original [52-week high momentum
paper](https://onlinelibrary.wiley.com/doi/full/10.1111/j.1540-6261.2004.00695.x),
[drawdown and recovery research](https://www.mdpi.com/1911-8074/14/11/542),
and [LightGBM's LambdaRank truncation guidance](https://lightgbm.readthedocs.io/en/latest/Parameters.html).
The source-by-source adaptation and unrun XGBoost/CatBoost boundaries are in
[research notes](personalized_championship_sources_20261001.md). Current sector
labels are not reliable historical point-in-time classifications; no sector
label or sector-relative feature was used in finalist fitting. The sector
result table is diagnostic only.

## Feature ablations and qualifying results

At the same 67/33 weight, 60-tree LightGBM setting, and eight-level XIRR
relevance, the 2019/2022 qualification measurements were:

| Ranker feature recipe | NDCG@20 | Top-20 shortfall | Median Top-20 XIRR | Worst date shortfall Δ vs champion |
|---|---:|---:|---:|---:|
| Proxy + age | 0.4703 | 4.83% | 38.11% | +0.07 pp |
| High position + age | 0.4759 | 4.91% | 39.53% | +0.58 pp |
| Drawdown duration/recovery + age | **0.5136** | **3.13%** | **42.80%** | **−1.31 pp** |
| High + drawdown | 0.5079 | 4.11% | 41.88% | +0.37 pp |
| Full risk (including volatility) | 0.5104 | 3.92% | 41.00% | −0.63 pp |
| Full risk, excluding Goal from ranker | 0.4825 | 5.23% | 36.46% | +1.06 pp |
| Full risk, excluding growth | 0.4671 | 6.25% | 35.99% | +1.46 pp |

These are ablations on the qualification dates, not causal feature effects.
The drawdown duration family qualified strongly, but its later behavior was
less stable. The history/high family met the 2023 profile guard with smaller
aggregate gains. Regression-to-rank alternatives qualified well in 2019/2022
but lost 2023 ordering utility, so the architecture stayed near Goal plus
LambdaRank. The [full candidate leaderboard](../../experiments/personalized-championship/v1/round1_leaderboard.csv)
contains all 30 rows.

## Direct-finalist scoreboard

The table shows challenger minus frozen champion. Positive NDCG, achievement,
median XIRR, and drawdown deltas are favorable; negative shortfall is
favorable. All direct finalists preserve measured coverage. Full absolute
values and deltas for all nine metrics are in the [direct-finalist audit](../../experiments/personalized-championship/audit-v1/champion_vs_contenders.csv),
with [profile blocks](../../experiments/personalized-championship/v1/finalist_profile_blocks.csv)
and [date values](../../experiments/personalized-championship/v1/finalist_date_metrics.csv).

| Direct challenger | Period | Rank IC Δ | NDCG@20 Δ | Pairwise Δ | Achievement Δ | Shortfall Δ | Median XIRR Δ | Drawdown Δ |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| High/age, 63% Goal, 8 grades | 2023 | −0.0103 | +0.0240 | −0.60 pp | +3.89 pp | −1.33 pp | +3.92 pp | +9.30 pp |
| Same | Exposed 2025 | **−0.0429** | **−0.0647** | −1.27 pp | −2.78 pp | **+5.59 pp** | −4.42 pp | **−8.45 pp** |
| Drawdown/age, regularized, 63% Goal | 2023 | +0.0126 | +0.0566 | +0.04 pp | +7.50 pp | −1.18 pp | +27.30 pp | **−3.91 pp** |
| Same | Exposed 2025 | −0.0144 | −0.0021 | −0.67 pp | **−8.89 pp** | **+1.36 pp** | −7.17 pp | +0.91 pp |
| Drawdown/age, utility labels, 73% Goal | 2023 | −0.0119 | −0.0057 | −0.75 pp | +1.11 pp | −0.89 pp | −5.39 pp | +6.12 pp |
| Same | Exposed 2025 | +0.0095 | −0.0292 | +0.06 pp | **−10.83 pp** | **+1.71 pp** | −13.82 pp | +3.59 pp |

The development-eligible high/age model improves shortfall and drawdown on
both 2023 dates, but shortfall **rises by 4.83 and 6.34 percentage points** on
the two exposed 2025 dates. Its mean future drawdown worsens by 7.97 and 8.94
points on those dates. These independent date directions are a decisive
stability failure. Its 2025 10% and 30% target profiles have shortfall increases
of 7.82 and 9.76 points, respectively. The other direct finalists do not solve
the aggregate/profile trade-off.

## Conservative ranker blends

The final conservative search combined the old LambdaRank percentile with
10–50% of a new history-aware ranker percentile; Goal remained between 63%
and 73%. Sixty settings were selected on 2023 only. The two most relevant
trade-offs and a distinct high-position blend then received the exposed check.
See the [blend leaderboard](../../experiments/personalized-championship/blends-v2/development_leaderboard.csv),
[before/after table](../../experiments/personalized-championship/blends-v2/champion_vs_blends.csv),
and [profile blocks](../../experiments/personalized-championship/blends-v2/profile_blocks.csv).

| Blend | Period | NDCG@20 | Shortfall | Median XIRR | Drawdown | Current Top-20 short-history share |
|---|---|---:|---:|---:|---:|---:|
| Frozen champion | 2023 | 0.5012 | 6.03% | 33.91% | −34.56% | 90% |
| 70% Goal; 10% new drawdown ranker within 30% ranker | 2023 | 0.5143 | 5.46% | 38.05% | −35.33% | 85% |
| Same | Exposed 2025 | 0.6408 vs 0.6268 | **13.76% vs 12.90%** | 1.86% vs 4.66% | −42.77% vs −42.58% | 85% |
| 67% Goal; 50% new drawdown ranker within 33% ranker | 2023 | 0.5464 | 4.77% | 46.37% | −37.55% | 55% |
| Same | Exposed 2025 | 0.6705 vs 0.6268 | **13.12% vs 12.90%** | −0.08% vs 4.66% | −41.13% vs −42.58% | 55% |
| 70% Goal; 10% new high ranker within 30% ranker | 2023 | 0.5184 | 5.50% | 33.76% | −33.47% | 85% |
| Same | Exposed 2025 | 0.6247 vs 0.6268 | **13.77% vs 12.90%** | 0.87% vs 4.66% | −43.56% vs −42.58% | 85% |

The 70%/10% blend is the smallest-degradation development candidate: Rank IC
improves 0.0008, NDCG improves 0.0132, shortfall falls 0.56 points, and
median XIRR rises 4.14 points. Pairwise accuracy drops only 0.05 points.
However, it worsens future drawdown 0.77 points in 2023, then worsens 2025
shortfall 0.87 points. Its 2025 30% target slice loses 10 points of achievement
and gains 3.65 points of shortfall. At only 10% new ranker influence, 85% of
the current Top 20 still lack true five-year history, so it fails the core
missing-history requirement. Larger blends shift more young listings out but
accumulate larger profile or median-return losses. This is the observed Pareto
trade-off; no blend clears all hard guardrails.

## Coverage, age bias, turnover, sectors, and outliers

Coverage is identical to the champion for every direct finalist and blend on
the comparable historical cohorts. In the current base profile, stocks without
true 5Y history are **7.99% of the scored universe** but 90%/46%/29% of the
champion's Top 20/50/100. The direct high/age finalist reduces those shares to
25%/20%/16%; the regularized drawdown finalist to 5%/8%/16%. The conservative
70%/10% blend leaves them at 85%/46%/27%. These are distinct trade-offs, not
proof of future utility. Full rows are in the [current missing-history audit](../../experiments/personalized-championship/audit-v1/current_missing_history_audit.csv)
and [blend audit](../../experiments/personalized-championship/blends-v2/current_short_history.csv).

The direct high/age finalist's mean Top-20 replacement fraction between the
two 2023 dates is 83.3%, versus 78.9% for the champion; between the exposed
2025 dates it is 65.0%, versus 80.6% for the champion. The regularized
drawdown finalist turns over 96.1% in 2023 and 87.8% in 2025, weakening its
stability claim. The full [turnover table](../../experiments/personalized-championship/audit-v1/turnover.csv)
contains every profile.

Across 38 date/sector blocks with at least 20 comparable securities per
partition, the direct high/age finalist's mean sector Top-5 shortfall delta
is approximately zero in 2023 and **+3.7 points** in exposed 2025; the worst
exposed sector block is **+24.1 points**. Current sector labels may not match
historical classification, so this is a sensitivity check, not a sector
training claim. See [sector slices](../../experiments/personalized-championship/audit-v1/sector_slices.csv).

The 2023 champion Top-20 winsorized mean XIRR (capped at 300%) is 69.6%,
compared with 63.1% for the direct high/age finalist; in exposed 2025 the
same pair is 57.2% versus 38.2%. This contrasts with its impressive raw mean
in 2023 and supports downweighting outlier-driven claims. The full
[extreme-return audit](../../experiments/personalized-championship/audit-v1/extreme_return_and_history.csv)
also records counts above 300% and worst selected drawdowns.

## Named diagnostic and attribution

NYKAA was an audit case only; no security identity appears in any feature,
label, weight, fit, or selection rule. The frozen current ranker receives
`cagr_5y = NaN`; its raw LambdaRank contribution from that missing feature is
**+0.3058**. Across all 260 scored current rows with a missing original 5Y
value, that feature's mean contribution is **+0.2348** (median +0.2274),
versus **−0.0405** for observed-5Y rows. The new features record 58.25 months
of trading, since-listing CAGR −2.07%, an `ESTIMATED` sector-shrunk 5Y proxy
of −2.03%, 1,752 days since the recorded high, −20.06% distance from that
high, and −72.10% full recorded-history maximum drawdown. The high/age
finalist gives its 5Y proxy a −0.0101 raw contribution, days-since-high
−0.0629, and history length +0.0771. Its global rank changes **1 → 114**;
its Retailing rank remains **1 → 1**. The drawdown finalists put it at global
25 and 27, still Retailing 1. Raw tree contributions are not blended-score
contributions.

The Retailing Top 10 for the frozen champion is NYKAA, ETERNAL, V2RETAIL,
CARTRADE, NAUKRI, MEDPLUS, ARVINDFASN, VMART, DMART, TRENT. For the direct
high/age finalist it is NYKAA, ETERNAL, CARTRADE, V2RETAIL, JUSTDIAL,
ARVINDFASN, DMART, NAUKRI, VMART, MEDPLUS. The full
[current audit](../../experiments/personalized-championship/audit-v1/current_missing_history_audit.csv),
[raw finalist scores](../../experiments/personalized-championship/audit-v1/current_2.csv.gz),
and [feature contributions](../../experiments/personalized-championship/audit-v1/contributions_2.json)
make the case inspectable. A rank move for this one security did not influence
the championship verdict.

## Reproducibility, tests, and next evidence

The [protocol](../protocols/personalized_championship_v1.json) fixes dates,
seed, maturity rule, feature families, parameters, and Goal-weight search.
The executable runners are `personalized_championship.py`,
`personalized_championship_audit.py`, and
`personalized_championship_blends.py`. [Input hashes and the frozen-score check](../../experiments/personalized-championship/v1/audit.json)
are sealed in the research output. The existing frozen champion directory was
read but never overwritten. The profile/date/sector/turnover/extreme-return
outputs above are available as CSV. Research code has no production-serving
entry point.

From the repository root, use fresh output directories for reproduction:

```powershell
.venv-qlib\Scripts\python.exe research\runners\personalized_championship.py --audit-ticker NYKAA --output experiments\personalized-championship\repro-v1
.venv-qlib\Scripts\python.exe research\runners\personalized_championship_audit.py --audit-ticker NYKAA --championship experiments\personalized-championship\repro-v1 --output experiments\personalized-championship\repro-audit-v1
.venv-qlib\Scripts\python.exe research\runners\personalized_championship_blends.py --championship experiments\personalized-championship\repro-v1 --output experiments\personalized-championship\repro-blends-v1
```

Relevant tests passed: the new history and maturity tests plus the existing
Personalized engine/product/sector tests. Python compilation passed for the
new research runners. The larger barrier is evidence, not a missing hyperparameter:
only two 2023 development dates are available, the 2025 dates were already
exposed, and the current ranking lacks matured prospective outcomes. A
promotion claim needs new untouched date blocks with complete executable
prices and corporate actions, preferably including distinct market regimes
and more history for recent listings.
