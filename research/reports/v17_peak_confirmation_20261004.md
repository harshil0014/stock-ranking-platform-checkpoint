# Closing-high confirmation continuation

Selected development candidate: `downside_h0.3_q0.1`.

Weights: 50.0% V17 refined, 30% closing-high component, 10% 12-1 momentum, 10.0% downside confirmation.

The prior trading-activity screen is unchanged. Models are compared on identical eligible stocks. All 44 historical dates were previously researched, so these are exploratory comparisons rather than blind validation. Mean stock XIRR is not used to select a candidate. Basket median XIRRs below are averaged across decision dates and profiles; drawdown is average asset drawdown, not a cost-adjusted portfolio backtest.

| Period | Model | Basket-median XIRR | Asset drawdown | Achievement | Shortfall | NDCG@20 |
|---|---|---:|---:|---:|---:|---:|
| development | eligible_v17_score | 15.07% | -29.55% | 44.48% | 8.56% | 0.4017 |
| development | new_score | 21.80% | -26.84% | 48.02% | 6.98% | 0.4438 |
| development | priority_score | 17.95% | -29.11% | 45.56% | 8.16% | 0.4247 |
| early | eligible_v17_score | -1.03% | -40.15% | 33.02% | 14.66% | 0.5091 |
| early | new_score | 5.36% | -34.90% | 38.92% | 11.59% | 0.5659 |
| early | priority_score | 1.49% | -38.31% | 35.66% | 13.50% | 0.5360 |
| exposed | eligible_v17_score | -2.68% | -30.77% | 24.72% | 11.29% | 0.5904 |
| exposed | new_score | -0.41% | -28.52% | 26.53% | 10.14% | 0.6209 |
| exposed | priority_score | -2.03% | -30.00% | 25.46% | 10.65% | 0.6097 |

## Profile tradeoffs versus prior priority model

| Profile | Median XIRR change (pp) | Drawdown change (pp) |
|---|---:|---:|
| amount1000 | +4.46 | +2.70 |
| amount50000 | +4.10 | +1.51 |
| base7500 | +3.53 | +2.37 |
| lookback12 | +2.99 | +3.14 |
| lookback60 | +1.71 | +2.33 |
| quarterly | +3.66 | +2.48 |
| target10 | +3.05 | +2.66 |
| target30 | +3.19 | +2.49 |
| weekly | +2.55 | +2.56 |

NYKAA default ranks: V17 refined 4; previous priority 70; new candidate 172. Its recorded age remains 1765 days.

## Current default Top20

| Rank | Company | Ticker | ATH age |
|---:|---|---|---:|
| 1 | Mangalam Worldwide Limited | MWL | 8 |
| 2 | Anand Rathi Wealth Limited | ANANDRATHI | 23 |
| 3 | Shri Venkatesh Refineries Limi | BSE-543373 | 0 |
| 4 | Laurus Labs Limited | LAURUSLABS | 8 |
| 5 | Divi's Laboratories Limited | DIVISLAB | 8 |
| 6 | Khazanchi Jewellers Limited | BSE-543953 | 42 |
| 7 | IPCA Laboratories Limited | IPCALAB | 13 |
| 8 | S.J.S. Enterprises Limited | SJS | 38 |
| 9 | AAYUSH ART AND BULLION LIMITED | BSE-540718 | 7 |
| 10 | Shyam Metalics and Energy Limited | SHYAMMETL | 8 |
| 11 | SPR Auto Technologies Limited | SHRIPISTON | 2 |
| 12 | Steelcast Limited | STEELCAS | 1 |
| 13 | Apollo Hospitals Enterprise Limited | APOLLOHOSP | 8 |
| 14 | Kingfa Science & Technology (India) Limited | KINGFA | 0 |
| 15 | PTC Industries Limited | PTCIL | 27 |
| 16 | Navin Fluorine International Limited | NAVINFLUOR | 22 |
| 17 | Yatharth Hospital & Trauma Care Services Limited | YATHARTH | 8 |
| 18 | R R Kabel Limited | RRKABEL | 31 |
| 19 | The Federal Bank  Limited | FEDERALBNK | 59 |
| 20 | Tamilnad Mercantile Bank Limited | TMB | 28 |

## Research basis

[Da, Gurun and Warachka (2014)](https://academic.oup.com/rfs/article-abstract/27/7/2171/1578455) studies continuous information and momentum. It motivates investigating trend persistence. Our share of closes near the annual high is a related hypothesis, not their information-discreteness measure. [International evidence](https://academic.oup.com/rof/article/29/1/241/7772889) reports support for information discreteness and limited standalone support for 52-week-high anchoring; these signals are not assumed universally profitable.

The data retain current-universe/survivorship and provider-revision limitations. Positive reported volume and traded-value thresholds are eligibility proxies, not guarantees of fills or transaction costs.

## Website integration

The local website now offers **Closing High** at `/closing-high` and opens that mode by default at `/`. It uses the locked formula and the same activity screen for all nine saved profiles. Other valid contribution profiles recalculate the V17 component and the contribution-dependent traded-value threshold against the fixed 3 October 2026 snapshot. The original Personalized and V17 modes remain selectable. This is a local product change, not a remote deployment or live market refresh.

The runtime package includes hashed closing-high features and the selection lock. The default saved profile was compared row by row with the research export: all 4,436 identities, eligible scores and ranks reproduce within 1e-9; NYKAA remains 1,765 days from its ATH and ranks 172. Custom-profile and HTTP route checks passed. All 396 date/profile benchmark comparisons, Top20/50/100 exports, and baseline source hashes were also verified.

Trial ledger, protocol, dated scores, profile deltas and Top20/50/100 exports are in `experiments/v17-peak-confirmation-20261004`.
