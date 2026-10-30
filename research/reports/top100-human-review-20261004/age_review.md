# Closing-high age and history review — 4 October 2026

Scope: the frozen 3 October 2026 `base7500` rankings, 1,773 eligible companies. This is an explanation and diagnostic review, not a new model selection, new backtest, independent price certification, or forecast. The production weights and website were not changed. The runner reproduces all eligible scores within 1e-12 before attribution. Data source SHA256 and summary counts are in `age_summary.json`.

## Judgment

The recent-strength preference is clearly working, but the lifetime-age term is strong enough to suppress near-complete recoveries from old peaks. The Top100 contains **zero** companies whose recorded closing high is at least a year old; median ATH age is 28 days and the oldest is APLAPOLLO at 232 days. Removing only the explicit lifetime-age term changes 13 Top100 constituents. This is concrete evidence of a material age preference; it does not establish that removing it improves future returns.

Dr. Lal PathLabs is the clearest human-review challenge: rank207 despite being only 1.09% below its adjusted closing high, making its annual closing high on the latest quote date, and receiving downside-risk confirmation at the 98.1st percentile. NYKAA is a different case: its 21.80% remaining drawdown is meaningful, though its recent trend and downside confirmation are strong. Treating both largely through elapsed time obscures that distinction.

## Exact attribution

The delivered score is:

`0.50*V17_refined + 0.15*exp(-ATH_age/1095.75) + 0.09*(1+ATH_distance) + 0.06*rolling_high_freshness + 0.10*momentum_percentile + 0.10*downside_confirmation`.

Thus the 30% closing-high weight comprises 15% lifetime-age, 9% proximity and 6% annual-high recency. V17 already contains high/drawdown signals, so the total model sensitivity to old highs is greater than the isolated term measured here. No V17 features or percentiles were recomputed in this diagnostic.

| Company | Current rank | ATH age | Below ATH | Annual-high age | Remove direct age, rerank everyone | Change only its age to 365 days | Change only its age to 30 days |
|---|---:|---:|---:|---:|---:|---:|---:|
| NYKAA | 172 | 1,765 | 21.80% | 33 | 7 | 40 | 7 |
| LALPATHLAB | 207 | 1,842 | 1.09% | 2 | 12 | 53 | 13 |
| NAZARA | 231 | 1,816 | 3.89% | 3 | 29 | 75 | 27 |
| ONEPOINT | 201 | 818 | 1.89% | 2 | 67 | 123 | 58 |
| PAYTM | 30 | 13 | 10.48% | 15 | 35 | 78 | 31 |
| DIVISLAB | 5 | 8 | 3.90% | 10 | 6 | 39 | 6 |
| IPCALAB | 7 | 13 | 3.30% | 15 | 9 | 49 | 10 |
| ASIANPAINT | 560 | 1,165 | 29.84% | 302 | 455 | 424 | 329 |
| HDFCBANK | 529 | 428 | 27.62% | 310 | 599 | 519 | 415 |

“Remove direct age” subtracts the 0.15 exponential contribution for every company and reranks on the remaining 0.85 weight; renormalizing by 0.85 would produce identical ranks. “Change only its age” keeps every other company's original score fixed, and changes only the named company's explicit 0.15 contribution. These are different questions and should not be compared as if they were alternative full models.

NYKAA gets only 0.02996 out of the possible 0.15 age points; changing its age to30 adds0.11599 while leaving its actual 21.80% depth and all other inputs fixed. LALPATHLAB gets0.02793; changing its age to30 adds0.11802. Its present age term therefore dominates its otherwise strong confirmation. ASIANPAINT and HDFCBANK remain far outside Top100 even with hypothetical30-day highs, demonstrating that age is not a universal explanation for low ranks. HINDUNILVR is unranked because a resulting-security corporate action valuation is unresolved, not because of old-high punishment.

Two whole-universe alternatives illustrate the horizon issue without selecting a new weight. Replacing lifetime age by annual-high age inside the **same** exponential retains89 of100 constituents and brings eight companies with lifetime peaks older than two years into Top100; NYKAA/LALPATHLAB/NAZARA rank7/10/26. Replacing the direct term by the existing annual freshness function retains87 of100 and ranks those names7/8/20. These are attribution probes, not validated proposals. They also double-count rolling freshness with the existing6% term.

There is a threshold effect worth testing prospectively: a company just below a five-year-old ATH receives about0.03 age points, but exceeding that high resets age and produces about0.15 points. For LALPATHLAB, the isolated reset is about0.1221 score points for crossing a remaining1.09% closing-price gap (about1.10% appreciation). An arbitrarily small crossing near that threshold can trigger the same age reset. This is a discontinuity in the economic treatment of almost identical prices, even though age decays smoothly between new highs. An age-depth interaction or a transition band around the old high is a justified **future hypothesis**, not a reason to insert an untested new weight today.

## PAYTM and NYKAA: dates reconcile

Raw cached adjusted-price histories were reopened independently of the ranking CSV; receipts are in `age_raw_history_receipts.csv`.

- PAYTM history begins18November2021, matching the [company's listing FAQ](https://ir.paytm.com/faqs). The first adjusted close is1,560.80. Its maximum recorded adjusted close is1,849.900024 on18September2026; its last adjusted close is1,656 on1October2026. Its raw intraday high is1,955 on the listing date. Therefore a recent **closing** high and an old **intraday** high can coexist. The13-day lifetime age is internally consistent, not evidence by itself of a corrupt history. The quote is10.48% below that recent closing high, and its all-history drawdown is82.37%, so “recent ATH” does not mean low historical risk.
- NYKAA begins10November2021, matching the [company's FY2021–22 report](https://www.nykaa.com/media/wysiwyg/2021/Investors-Relations/pdfs/annual-report/21-22/integrated-report-2021-22.pdf). Its adjusted closing high is415.516663 on1December2021 and its last adjusted close324.950012 on1October2026. Their age is exactly1,765 days. The13/1,765-day fields measure from the last observation, whereas the annual-high field measures from the3October decision date; using that date gives15/1,767 days. The two-day clock difference is documented and retained, not silently repaired.
- The lifetime calculation uses the first occurrence of equal maximum closes (`argmax`), while the annual-high calculation uses the most recent exact tie. NYKAA has no equal-high ambiguity in this result. A future data contract should standardize the clock and explicitly label tie semantics.
- The inherited `latest_price` column differs from the scoring quote: PAYTM1,849.9 versus terminal1,656; NYKAA332.15 versus324.95; LALPATHLAB1,896.9 versus2,005.10. Human tables and professor comparisons must use the dated terminal/scoring quote, not assume the inherited field is current. This review does not change either field.

The cached price calculations above verify internal reproducibility. Primary company sources confirm listing/history interpretation, not every2026 close; no claim of independent exchange certification of the full cached series is made.

## Short history versus young company

Thirty Top100 names lack true five-year price history. One, JSWINFRA, has35.94 months in the exported history (rank51). The median Top100 history is142.74 months, so the portfolio is not wholly an IPO basket. DIVISLAB/IPCALAB have282.68/368.99 months of data and near-record closes; their ranks5/7 remain6/9 after removing direct age. These are coherent mature-company examples.

Some short histories represent a newer exchange listing rather than a recently created business. STEELCAS is rank12 with58.25 months beginning23November2021. Its [own NSE listing notice](https://www.steelcast.net/pdf/NSE%20_Letter_New_Listing_18112021.pdf) identifies that NSE start and refers to already-listed equity (notice indexed by search; direct fetch timed out). PTCIL is rank15 with39.75 months beginning9June2023; its [FY2023–24 corporate-governance report](https://www.ptcil.com/PDF/Investors/corporate-governance/2023-24-Corporate-Governance-Report.pdf) confirms the NSE listing date and shows BSE prices before that date. Consequently these features are maxima over the available provider/exchange history, not demonstrated all-exchange lifetime records. LLOYDSME and RAMRAT have similarly recent cached starts and deserve the same provenance check before being labeled young companies.

MWL's official listing field says18September2025 while its cached price history starts25July2022; ONEPOINT similarly has an official date in2019 and history in2017. These are flags to distinguish exchange/segment migrations and historical identity, not grounds to delete earlier observations. Do not truncate provider history blindly to a metadata listing date.

A shorter series has had less opportunity to contain a very old peak or a full bear cycle; its maximum possible age is mechanically bounded by observed span. The present missing-history confidence adjustment does not prove this exposure is adequately controlled. First resolve older cross-exchange history with ISIN and corporate actions, then report history completeness separately from trend strength. The counterfactuals do not manufacture missing history.

## Review disposition

Keep the frozen model for comparison. Flag LALPATHLAB, NAZARA and ONEPOINT as near-high recovery cases requiring an explicit explanation of the heavy age deduction; NYKAA as a strong-recent-trend/old-peak case with a still-material drawdown; PAYTM as a recent closing-high but historically deep-drawdown case. Prioritize history coverage for STEELCAS/PTCIL and date/price labels before new weight searches. A useful next experiment would lock an age-depth interaction, control history length, and evaluate on genuinely unseen dates with the same eligible universe. This review cannot certify future performance or establish the best weight.

Artifacts: `age_sensitivity.csv` (all4,436 default-profile rows), `age_summary.json`, `age_history_definitions.csv`, `age_raw_history_receipts.csv`; reproducer: `research/runners/age_review_20261004.py`.
