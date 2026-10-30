# Closing-high-priority research model

The requested stronger closing-high preference is implemented as an explicit 20% score component. This is a fixed preference model; it is not claimed to outperform V17 on every return metric. A separate balanced experimental model provides stronger aggregate historical return results.

## Exact score and eligibility

`score = 0.70 * V17_refined + 0.20 * closing_high_component + 0.10 * momentum_12_1_percentile`

`closing_high_component = 0.50 * exp(-ATH_age_days / 1095.75) + 0.30 * (1 + ATH_distance) + 0.20 * 365 / (365 + age_of_52_week_closing_high)`

Thus lifetime closing-high age has a direct 10% score weight, closeness to the lifetime closing high 6%, and rolling closing-high recency 4%. V17 contributes its existing high-price signals as well. Raising ATH age while holding the remaining inputs fixed cannot improve the new explicit score.

Lifetime ATH fields retain the frozen benchmark definition (age at the last quote and first occurrence for equal highs). The new rolling-high age uses the latest equal adjusted closing high in the preceding 365 days, measured at the decision date. NYKAA has no equal-ATH tie; its 1,765-day stored age is preserved.

The eligible shortlist requires at least 120 observations over the last year, positive reported volume on at least 80% of those observations, both a quote and a positive-volume observation within seven calendar days, and median daily reported traded value of at least 100 times the contribution. This represents an assumed maximum 1% participation in median daily traded value; it does not measure transaction costs or guarantee execution.

Every stock remains in the full export with its unfiltered research rank and explicit eligibility reason. Missing activity evidence is not represented as proven liquidity.

Validation covers 44 historical decision dates and 4,436 current stocks. The default eligible shortlist contains 1,773 scored stocks. New provider features cover 155,607 stock/date observations, 4,081 stocks, and 51 dates including training dates. Features use no quotes after the observation date.

## Historical comparison

Rates are averages of date/profile Top20 basket statistics, not a portfolio CAGR or a transaction-cost-adjusted trading backtest. Drawdown is average asset drawdown; closer to zero is better. The same-universe V17 row applies exactly the new eligibility screen, so the model comparison does not attribute the screen itself to better scoring.

| Period | Model | Top20 median XIRR | Achievement | Shortfall | Asset drawdown | NDCG@20 |
|---|---|---:|---:|---:|---:|---:|
| development | V17 same eligible universe | 15.07% | 44.48% | 8.56% | -29.55% | 0.4017 |
| development | Closing-high priority | 17.95% | 45.56% | 8.16% | -29.11% | 0.4247 |
| development | V17 original universe | 58.63% | 61.18% | 5.74% | -28.35% | 0.5972 |
| early | V17 same eligible universe | -1.03% | 33.02% | 14.66% | -40.15% | 0.5091 |
| early | Closing-high priority | 1.49% | 35.66% | 13.50% | -38.31% | 0.5360 |
| early | V17 original universe | -3.27% | 29.17% | 13.83% | -33.91% | 0.5315 |
| exposed | V17 same eligible universe | -2.68% | 24.72% | 11.29% | -30.77% | 0.5904 |
| exposed | Closing-high priority | -2.03% | 25.46% | 10.65% | -30.00% | 0.6097 |
| exposed | V17 original universe | 53.17% | 56.11% | 9.05% | -40.53% | 0.7190 |

Profile changes against V17 on the same eligible stocks, averaged across the 44 dates:

| Profile | Median XIRR change (pp) | Drawdown change (pp) |
|---|---:|---:|
| amount1000 | +2.06 | +0.51 |
| amount50000 | -0.50 | -0.21 |
| base7500 | +1.72 | +0.81 |
| lookback12 | +8.04 | +3.40 |
| lookback60 | +2.96 | +2.14 |
| quarterly | +1.74 | +0.61 |
| target10 | -0.66 | +0.57 |
| target30 | +3.46 | +1.00 |
| weekly | +0.44 | +0.52 |

## Alternative balanced experimental model

The earlier selected age/momentum model blends 90% V17 refined with 10% learned age-aware ranking plus an explicit age/momentum penalty. It is available in `experiments/v17-peak-context-20261004/current_top20.csv`. Its median-return/drawdown changes against V17 refined are:

| Period | Median XIRR change (pp) | Drawdown change (pp) |
|---|---:|---:|
| development | +1.53 | +1.60 |
| early | +0.15 | +0.59 |
| exposed | +6.60 | +0.09 |

The balanced alternative has profile tradeoffs: its development default-profile median XIRR falls 3.64 percentage points and its 60-month profile falls 3.91 points. It was selected under aggregate rules adopted after the user authorized a broader redesign, not the earlier all-profile gates. Previously observed results are not a fresh holdout.

## Current default Top20

| Rank | Company | Ticker | ATH age (days) | Positive-volume fraction |
|---:|---|---|---:|---:|
| 1 | Shri Venkatesh Refineries Limi | BSE-543373 | 0 | 88.0% |
| 2 | Mangalam Worldwide Limited | MWL | 8 | 98.0% |
| 3 | Anand Rathi Wealth Limited | ANANDRATHI | 23 | 98.0% |
| 4 | S.J.S. Enterprises Limited | SJS | 38 | 98.4% |
| 5 | Steelcast Limited | STEELCAS | 1 | 98.4% |
| 6 | Khazanchi Jewellers Limited | BSE-543953 | 42 | 98.8% |
| 7 | Yatharth Hospital & Trauma Care Services Limited | YATHARTH | 8 | 98.0% |
| 8 | R R Kabel Limited | RRKABEL | 31 | 98.0% |
| 9 | Acutaas Chemicals Limited | ACUTAAS | 90 | 98.0% |
| 10 | Aarti Pharmalabs Limited | AARTIPHARM | 2 | 98.0% |
| 11 | Laurus Labs Limited | LAURUSLABS | 8 | 98.0% |
| 12 | Nuvama Wealth Management Limited | NUVAMA | 69 | 98.0% |
| 13 | Divi's Laboratories Limited | DIVISLAB | 8 | 98.4% |
| 14 | SPR Auto Technologies Limited | SHRIPISTON | 2 | 98.4% |
| 15 | Aditya Birla Sun Life AMC Limited | ABSLAMC | 100 | 98.0% |
| 16 | PTC Industries Limited | PTCIL | 27 | 98.4% |
| 17 | One 97 Communications Limited | PAYTM | 13 | 98.0% |
| 18 | Shyam Metalics and Energy Limited | SHYAMMETL | 8 | 98.0% |
| 19 | Craftsman Automation Limited | CRAFTSMAN | 21 | 98.8% |
| 20 | GHCL Textiles Limited | GHCLTEXTIL | 30 | 98.4% |

## NYKAA and the liquidity diagnostic

NYKAA retains its verified 1,765-day ATH age. Its default V17 rank is 4, its new unfiltered rank is 83, and its eligible shortlist rank is 70. Its rolling 52-week closing high is 33 days old and positive reported volume occurs on 98.0% of observations. Those facts explain why an old lifetime peak and a recent annual peak can coexist.

Datiware (BSE-519413) has positive reported volume on only about 16% of observations and is excluded from the eligible shortlist. Its apparently low volatility is not treated as sufficient evidence of tradability. These are provider observations, not an allegation about the company.

| Hypothetical NYKAA ATH age | Rank with other inputs and companies fixed |
|---:|---:|
| 30 | 6 |
| 365 | 22 |
| 1765 | 70 |
| 3650 | 102 |

## Research evidence and limits

- [Bhootra and Hur (2013)](https://www.sciencedirect.com/science/article/abs/pii/S0378426613002446) studies recency of the 52-week high as a momentum signal. It motivates rolling-high age; it does not establish an optimal ATH penalty here.
- [Raju, Indian 52-week-high study](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4587697) motivates high-price proximity in Indian equities.
- [Lesmond, Ogden and Trzcinka (1999)](https://academic.oup.com/rfs/article-abstract/12/5/1113/1565408) uses zero returns in transaction-cost estimation. It motivates investigating inactive prices; it does not validate the fixed 80% activity screen.
- Development, early history, and 2024-2025 periods have all been exposed during this research. Current-universe mapping and adjusted provider histories carry survivorship/revision limitations. No fresh holdout, causal profitability claim, or execution guarantee is supplied.
- The extra learned activity model and stronger logarithmic age penalties were also tested. Their full trial ledgers are retained; they were not chosen as return improvements. The priority model is an explicit preference design, not a relabeling of those trial results.
- Product website rankings have not been switched. This package supplies reproducible research rankings and a materially stronger closing-high option for review.

## Files

`priority_current_top20.csv`, `priority_current_top50.csv`, `priority_current_top100.csv`: all nine profiles. `default_rankings_readable.csv`: compact default ranking and eligibility reasons. `stock_diagnostics.csv` and `nykaa_age_sensitivity.csv`: company diagnostics. `priority_metrics.csv` and `same_universe_profile_date_comparison.csv`: full dated benchmarks. `priority_protocol.json` fixes the design.
