# Closing High: human review and professor benchmark

Completed 4 October 2026. Default profile: Rs7,500 every 30 days, 36-month lookback, 20% target CAGR. Ranking decision date: 3 October 2026. This review covers every Top100 constituent, old-high counterexamples outside the list, the supplied Excel workbook, and the supplied screenshot.

## My judgment

The ranking is a coherent recent-strength screen. Its exact ordering is not yet a defensible ranking of overall business quality or executable investment opportunities. It successfully recognizes several mature companies making recent highs, but overstates confidence in some small or transformed businesses, omits material execution constraints, and sharply penalizes some almost-complete recoveries from old highs.

I would retain the ranking as a research shortlist and challenge several placements before using it to allocate money. I would not solve the identified problems by adding another arbitrary weight or by forcing agreement with the professor. These are distinct data, execution and scoring-design questions.

All 100 stocks have individual analyst notes in [the complete review](top100_stock_by_stock_review.md), with [a sortable CSV](top100_stock_by_stock_review.csv). Each received a snapshot financial, price-history and trading review. Eleven unusual names received additional primary-source investigation in [company diligence](company_due_diligence.md). This is not a claim that 100 annual reports and auditor notes were independently audited. The analyst judgments are made after observing the ranks, so they are diagnostic judgments rather than a blind test or a validated alternative score.

## The most important stock-level disagreements

| Stock | Rank | My judgment and evidence |
|---|---:|---|
| Mangalam Worldwide | 1 | Reasonable momentum candidate; number one is hard to justify as business quality from the frozen data. Debt/equity 0.79, cash conversion 0.48 and reported promoter pledge 22.85% require scrutiny. It migrated to mainboard in 2025, so excluding it merely as an SME would also be wrong. |
| Shri Venkatesh Refineries | 3 | Recent strength does not settle debt/equity 2.38 and negative operating cash flow. Review working capital, funding and historical trading rules. |
| Aayush Art and Bullion | 9 | The strongest challenge to the low-risk interpretation: only 5.12% measured downside volatility alongside P/E 245.92x, negative operating cash flow and M-series evidence. Confirm business continuity, price formation and executable exit liquidity. A smooth chart cannot supply those answers. |
| PTC Industries | 15 | A capital-investment and future-delivery case: P/E 269.82x, ROCE 8.43% and negative operating cash flow in the frozen fields. Its price history begins with a newer NSE listing, despite older BSE history. The model's history is not a complete economic lifetime. |
| Paytm | 30 | Recent closing-high classification is internally reproducible, but P/E 136.87x and ROCE 4.96% make profitability durability a separate question. An old intraday high and recent adjusted closing high can coexist. |
| Indo Borax | 43 | Snapshot promoter pledge is 100% of promoter holdings. That is a specific financing question even though company debt/equity is zero. The figure is a source observation; confirm current encumbrance terms before acting. |
| Mobavenue AI Tech | 65 | The company's disclosed transformation from education to advertising technology makes its long ticker history a poor proxy for a decade of the present business. Historical prices need an economic-continuity label. |
| Dr Lal PathLabs | 207, outside Top100 | The clearest challenge to the age design: just 1.09% below its old closing high, annual high two days old, but heavily suppressed by a 1,842-day lifetime age. |

The first 100 also contain financially coherent candidates. For example, IPCALAB, ALIVUS, WELCORP, SUNPHARMA and STYLAMIND combine recent strength with positive cash conversion and less demanding snapshot valuations than several higher-ranked names. This supports keeping them under review; it does not establish an exact alternative order or expected return.

All quoted P/E, ROCE, pledge and cash-flow fields above come from the frozen Screener-derived facts. They are dated provider observations and can differ in reporting basis. They were not inserted into historical training. Primary corporate disclosures supply additional context: [PTC's FY25 report](https://www.ptcil.com/PDF/Investors/annual-reports/62thAnnualReport.pdf) describes significant investment in Aerolloy; [Laurus' FY26 presentation](https://www.lauruslabs.com/Investors/PDF/Q4/InvPresentation30042026.pdf) describes a large continuing capital-expenditure program. These explain why normalized future earnings need examination; they do not prove that current valuations are justified.

## Is old-high punishment excessive?

It is materially strong, and several recovery cases warrant a redesign test. The 30% explicit closing-high component comprises 15% lifetime age, 9% proximity and 6% annual-high recency. The Top100 has no ATH age of one year or more; median age is 28 days and the oldest is 232 days.

The following diagnostic subtracts only the explicit 15% age term from every eligible stock, holds all other score components and eligibility fixed, and reranks the universe. It does not retrain V17 or establish a better strategy.

| Stock | Current eligible rank | Rank without explicit age | Remaining distance below ATH |
|---|---:|---:|---:|
| NYKAA | 172 | 7 | 21.80% |
| Dr Lal PathLabs | 207 | 12 | 1.09% |
| Nazara | 231 | 29 | 3.89% |
| One Point One Solutions | 201 | 67 | 1.89% |

Only 13 Top100 memberships change, but individual recovery names move dramatically. Dr Lal PathLabs is a stronger overpunishment example than NYKAA because the remaining drawdown is much smaller. Conversely, Asian Paints and HDFC Bank remain far outside Top100 even under a hypothetical recent high; age does not explain every low ranking.

There is an important threshold effect: Dr Lal PathLabs could gain roughly 0.122 score points from the age reset on crossing a remaining 1.09% high-price gap, holding other terms fixed. An economically small change near the old peak can therefore cause a large ranking jump. Test an age-depth interaction or a transition near the previous high in a locked future experiment. Do not infer that removing age altogether has now been validated.

[Full age attribution](age_review.md) and [all-stock sensitivity calculations](age_sensitivity.csv) preserve the verified NYKAA age of 1,765 days. The lifetime clock is measured at the last quote while rolling-high age uses the decision date; this two-day difference is documented. Historical adjusted closing highs are distinct from intraday highs.

## Concentration, valuation, execution and history

| Review finding | Top100 result | Interpretation |
|---|---:|---|
| Pharma/biotech plus healthcare services | 20 names | 20% by count versus 7.1% of the eligible universe. A shared sector shock matters. |
| Auto components | 11 names | 11% versus 4.8% of eligible stocks. |
| Industrial products | 11 names | 11% versus 9.6% of eligible stocks; less disproportionate than pharma. |
| P/E above 60 | 28 of 99 with a P/E | Price strength does not provide valuation protection. The threshold is an attention flag, not an optimized exclusion rule. |
| Negative operating cash flow outside the four financial-sector groups | 11 names | Requires explanation using investment, working capital and reporting basis. Bank/lender leverage and cash flow need different tests. |
| Provider history shorter than five years | 30 names | Includes older companies with newer exchange histories. Do not equate it with company age. |
| BSE M series in frozen facts | 3 names | Aayush, Khazanchi and Trident require verified lot metadata. |

These are constituent counts, not portfolio weights or measured correlations. Sector labels are inherited and can be stale after business changes; [sector detail](sector_concentration.csv) makes that provenance inspectable.

The [NSE trading rules](https://www.nseindia.com/static/products-services/emerge-sme-trading-system) require exchange-defined market lots for SME normal-market orders; the odd-lot facility does not generally allow a retail investor to build a position one share at a time. Positive reported volume alone cannot validate a Rs7,500 purchase. Current exact lots for the three M-series names were not certified in this review. Former SME companies also need historical lot-aware SIP replay, even after mainboard migration. The [NSE migration list](https://www.nseindia.com/static/companies-listing/raising-capital-public-issues-emerge-selecting-a-migration-to-main-board) supports distinguishing MWL and Swaraj's current status from their earlier history.

## Professor workbook and screenshot benchmark

All 14 workbook identities were matched. Twelve have a model rank; Kwality Pharmaceuticals and Frontier Springs have insufficient usable history in this pipeline. This is a coverage defect, not a judgment of those businesses.

| Stock | Screenshot rank | Closing High eligible rank |
|---|---:|---:|
| Welspun Corp | 2 | 32 |
| Lumax Auto Technologies | 12, missing screenshot CMP | 89 |
| Shaily Engineering | 3 | 101 |
| TD Power Systems | 5 | 150 |
| GE Vernova T&D | 4 | 248 |
| Titan Biotech | 6 | 901 |
| Kwality Pharmaceuticals | 1 | Unranked: history coverage |

The screenshot and Excel file are separate snapshots. The screenshot repeats CEMPRO and contains three missing CMP values that produce apparent -100% returns. The Excel file instead ends with Frontier Springs, and its exported historical Google Finance dependencies fail: invested-value caches are zero and all 14 SIP rank caches are #N/A. The screenshot's visible ranks therefore cannot be described as recalculated workbook results.

The SIP table ranks deployed-money cumulative profit percentage using `RANK(I7,$I$7:$I$20)`. It does not rank XIRR. Its 20% CAGR field is a highlighting threshold; the model's 20% target influences scoring. The wider workbook does contain ATH/dip rules, and the professor's manual selection process cannot be reconstructed from the SIP rank formula alone.

| Comparison | Valid population | Result |
|---|---:|---|
| Screenshot versus Closing High order | 9 distinct usable names | Spearman 0.833; 30/36 pairs agree |
| Current professor-style policy versus Closing High within workbook list | 12 names | Spearman 0.671; 50/66 pairs agree |
| Current professor-style policy versus Closing High on identical comparable population | 1,755 names | Spearman 0.766; 18/100 Top100 overlap and 1/20 Top20 overlap |

The manually selected workbook list itself overlaps Closing High Top100 in two stocks: Welspun Corp and Lumax. That is different from the 18-name overlap obtained by comparing both policies on the same 1,755 stocks. Of 1,773 model-eligible names, 18 lack a professor-style score and are excluded from both sides; both rankings are recomputed within the common population. Those missing observations are exported in [the coverage exception list](professor_missing_score_eligible.csv). The policy calculation uses the project's prices/calendar/actions and is not an exact live Google Sheets replay. The professor-derived inputs already present in V7 also prevent a claim of complete input independence. Agreement does not prove prediction accuracy, and disagreement does not prove either approach superior.

Titan Biotech and TD Power are legitimate challenge cases. They rank much better on current deployed-money profit than on Closing High, while neither has a very old ATH. Their ranking explanations need the other score components; blaming ATH age would be incorrect. [Full professor audit](professor_audit.md) gives exact cells, all 14 stocks, exclusions and formula defects; [comparison CSV](professor_stock_comparison.csv) preserves every row.

## Fixes in priority order

1. **Make execution claims depend on dated lot and settlement metadata.** Rebuild historical SIP fills across migration dates and expose unavailable execution evidence. Do not silently turn current SME-volume eligibility into an investable Rs7,500 recommendation.
2. **Repair history completeness and economic continuity.** Link older BSE/NSE history by ISIN and corporate actions, recover Kwality/Frontier coverage, and mark major business transformations. An available-series high should be labeled as such until lifetime coverage is established.
3. **Test the old-peak reset effect.** Use the near-recovery cases above to define an age-depth hypothesis before evaluating it; retain a fixed comparison and genuinely unseen dates for performance claims.
4. **Add a transparent fundamental review layer.** Surface valuation, cash conversion, pledge and capital-return concerns with source dates; apply sector-appropriate financial tests. These review flags should not be confused with validated ranking weights.
5. **Show concentration and price provenance.** Label sector counts and dated scoring prices. The inherited latest_price is often from 18 September while scoring terminal prices are 1 October, so apparently different quotes are not by themselves proof of corruption.

The audit is complete. It provides a reasoned judgment for every Top100 stock, specific outside-list counterexamples, both professor comparisons and reproducible diagnostic calculations. No production weights, website ranking, source workbook or frozen ranking export was changed by this review.
