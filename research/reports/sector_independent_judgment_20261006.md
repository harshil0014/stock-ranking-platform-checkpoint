# Current model versus Sir: every-sector judgment

## My verdict

**I modestly prefer the current model for producing sector shortlists. I do not find a clean, robust winner across every sector.** Sir's formula remains competitive and sometimes produces the stronger shortlist. Neither has demonstrated greater future-return accuracy in this exercise.

This is my explicit, reproducible fundamental-quality judgment, applied to every project stock. It is not a claim that I personally researched 4,436 annual reports, know each company's fair value, or possess an independent oracle of future stock returns. A mechanical rubric operationalizes the judgment; the stock and sector explanations expose its reasoning and limitations.

The comparison is complete for the frozen **3 October 2026** snapshot and the **₹7,500 / 36-month / 30-day** profile. This report was finalized on 6 October. No model was retrained, replaced, or deployed.

## Coverage: all stocks remain visible

| Population | Count |
|---|---:|
| Project stocks accounted for | 4,436 |
| Sector groups, including Unclassified | 59 |
| Stocks scored by current model | 1,746 |
| Stocks with computable Sir-formula results using local prices | 4,293 |
| Stocks with sufficient fundamental evidence for the rubric | 4,316 |
| Stocks scored by both methods and the rubric | 1,725 |
| Sectors with at least five comparable stocks | 47 |
| Groups without a defensible comparative verdict | 12 |

All 4,436 rows are in the stock export, including unavailable scores. The 12 groups with insufficient comparison evidence are not assigned artificial winners. The all-stock export includes judge ranks, both competing ranks, common-universe ranks, individual fundamental inputs, component scores, data coverage and reasons for concern.

**Yes, Sir's workbook contains a much larger reference universe.** Its cached ATH and industry/CAGR tables contain **5,441 distinct exchange codes** in total. These are codes, not necessarily distinct companies. We matched 4,387 codes to project identities by exact primary listing identifiers. All 5,441 codes are retained in a separate workbook-universe export; unmatched and secondary listings remain explicitly unjudged. The workbook applies the SIP rank to its 14 selected slots, not automatically to that entire reference list.

## How I judged the stocks

Before calculating the comparison, the runner saved a fixed protocol. The primary rubric gives equal weight to five within-sector components:

1. **Profitability:** three-year ROE and ROCE.
2. **Durable growth:** three-year sales and profit growth.
3. **Financial risk:** debt/equity and promoter pledging.
4. **Cash generation:** operating cash flow relative to positive profit.
5. **Valuation:** positive earnings yield, with loss-making companies assigned zero earnings yield.

These are my chosen criteria, not a trained replacement ranking model. Neither competing score, past SIP return, ATH age nor momentum enters the rubric. The quality research literature supports examining profitability, growth and safety, but does **not** validate these exact weights or this India snapshot. See [Quality Minus Junk](https://www.aqr.com/-/media/AQR/Documents/Insights/Working-Papers/Quality-Minus-Junk.pdf).

Missing applicable metrics receive neutral component values, with explicit coverage reporting and a minimum coverage threshold. That decision is materially influential, so I also ran a complete-fundamentals comparison. Banks, Finance and Insurance exclude corporate debt and cash-conversion measures. A further sensitivity also excludes these measures for Capital Markets and Fintech. Even this does not substitute for capital adequacy, asset quality, insurer solvency, underwriting quality, or intermediary funding analysis.

This rubric also misses management quality, competitive advantage, accounting quality, capital allocation, pending litigation and reliable forward earnings estimates. It can overvalue apparently cheap cyclicals, misread growth from a small base, and reward ratios distorted by negative equity or exceptional income. Vendor observation dates are exported; observation dates are not proof that cash flow and earnings refer to identical financial periods.

## Results on identical stocks within each sector

Primary sector verdict: compare the mean judgment score of each method's top three on the **same** stocks. Differences within two points out of 100 are practical ties. These points are rubric scores, **not accuracy percentages or expected returns**.

| Result | Current model | Sir's formula |
|---|---:|---:|
| Sectors won | **17** | 12 |
| Average top-three judgment points | **55.81** | 53.09 |
| Average top-one judgment points | **54.85** | 51.20 |
| Average top-ten judgment points | **55.00** | 53.12 |
| Mean full-ranking Spearman agreement with rubric | **0.289** | 0.070 |
| Mean top-three NDCG agreement with rubric | **0.810** | 0.767 |

There are **18 practical ties** and **12 groups with insufficient comparable stocks**. Each comparable sector has equal weight in the aggregate, so large sectors do not dominate. Ranking agreement is agreement with the declared rubric, not market truth. Stable ISIN ordering breaks selection ties; formula ranks themselves retain competition ties.

### Robustness matters

| Check | Current minus Sir, mean top-three points |
|---|---:|
| Primary rubric | +2.72 |
| Greater emphasis on quality | +3.64 |
| Greater emphasis on growth | +1.49 |
| Greater emphasis on valuation | +3.05 |
| Broader financial-sector treatment | +2.87 |
| Require complete fundamental coverage | **+0.45** |
| Remove two largest current-model sector advantages | +1.62 |

**The complete-data result is the main reason I will not call this a decisive win.** Under that restriction, Sir wins **15** sectors, the current model wins **11**, and **21** are practical ties. Changing the comparison population changes the selections. Twelve sector differences also change direction under at least one weight variation, including small differences already classified as practical ties.

A descriptive bootstrap over the 47 sectors gives a primary mean difference interval of about +0.36 to +5.29 points. Sectors are not independent markets, and this is not future-return confidence or inference adjusted for prior research and model selection. The complete-data sensitivity is more useful than presenting that interval as certainty.

## My interpretation of important disagreements

### Telecom services: prefer the current shortlist

On common stocks, current selects **INDUSTOWER, BHARTIARTL and TATACOMM**. Sir selects **HFCL, IDEA and INDUSTOWER**. Current's average rubric advantage is **17.81 points**. In the frozen inputs, HFCL has negative operating cash flow and IDEA is loss-making. TATACOMM also has a leverage concern, so the current shortlist is not unqualified.

This is a substantive weakness of pure historical SIP-profit sorting: a rebound can rank a financially distressed company highly. Vodafone Idea's [January 2026 quarterly filing](https://www.myvi.in/content/dam/microsite/pdfs/Results/FY2025-26/Q3-2026/Q3FY26RESULTS.pdf) separately documents losses and negative net worth. That dated filing corroborates a risk concern; it is not a fresh October financial assessment or a claim the share price cannot rise.

### Realty: prefer the current shortlist under this evidence

Current selects **PHOENIXLTD, ASHIANA and OBEROIRLTY**; Sir selects **CCCL, PVP and PROZONER**. The current shortlist leads by **28.87 points**. The stored inputs show weaker profitability and cash evidence for Sir's selections, including loss and missing-data flags. This supports preferring the current shortlist for further research. Property cash flows and recognition are lumpy, and the sector classifications themselves warrant review before interpreting this as a clean business-to-business comparison.

### Capital Markets: Sir's choices deserve respect

Sir selects **MCX, BSE and ANANDRATHI**; current selects **ANANDRATHI, NUVAMA and PRUDENT**. Sir leads by **15.47 points** under the primary rubric. The frozen inputs show strong profitability and growth for BSE and MCX. The current model's closing-high emphasis does not by itself justify overlooking these qualities.

The primary cash/leverage treatment is imperfect for intermediaries such as NUVAMA. The broader-financial-treatment sensitivity is therefore supplied separately. A generic cash-flow flag is not a sufficient basis for declaring a financial intermediary inferior.

### Other sectors

Current has pronounced advantages under the rubric in Leisure Services, Industrial Products, IT Software and Aerospace & Defense. Sir leads in Finance, Cement, Food Products and Transport Services. The sector report contains the actual selected names, component differences, flags and evidence limits for **every group**, including those without a verdict.

## What was actually run for Sir

The isolated experiment's per-stock share-rounding and actual-invested-profit arithmetic was extended to all 4,436 project identities. No model blend or closing-high weight was added. The adapter uses stored raw closing prices and the first observation inside the explicitly declared one-day request window, with terminal prices no later than the snapshot. Ranking is descending profit divided by actual invested amount within the sector.

This is **Sir's arithmetic with local price inputs**, not a verified live Google Finance replication for 4,436 stocks. Raw-price adjustment conventions, provider coverage and corporate actions can change results. The workbook's positional bugs—such as the final stock depending on the first stock's cost cell—have no natural independent-stock equivalent and are not generalized to arbitrary companies.

There are 36 requested price observations per stock. The window starting **26 January 2024** has no stored close for any stock. Every stock on the common comparison set therefore has **35/36 observations**; neither method gains a relative advantage from differential price coverage on that common set. Outside it, history can be much shorter. Across the full universe, 107 stocks lack history and 36 yield no investment. The ledger exposes every requested and observed date, price, quantity and cost. Missing terminal data are not fabricated into meaningful −100% returns.

The current model intentionally abstains for many stocks. Its coverage is 1,746 versus Sir's 4,293 computable scores. **Better agreement on the common set does not prove better ranking over the entire universe**, because current does not produce a rank for most of it. Native top-three selections and their data coverage are exported separately from the controlled comparison.

## Verification and reproducibility

- **26 tests passed** for formula behavior and benchmark isolation, missing values, financial-sector treatment and date windows.
- Independently reconciled **159,696 scheduled stock observations**, shares, costs, final profit scores and common-sector ranks.
- Checked all 4,436 identities occur exactly once and all 59 groups appear in the sector output.
- Confirmed no selected terminal quote is later than 3 October 2026 and no price lookup searches beyond its declared window.
- Source hashes and the fixed protocol are saved with the outputs.

Run from the project root:

```powershell
python research/runners/sector_independent_judge_20261005.py
python research/runners/verify_sector_independent_judge_20261005.py
python -m pytest tests/test_sector_independent_judge.py tests/test_professor_exact_formula.py -q -p no:cacheprovider
```

## Deliverables

All paths below are relative to `experiments/sector-independent-judge-20261005/`:

- `all_stock_sector_judgments.csv`: all 4,436 project stocks, ranks, judge inputs and flags.
- `every_sector_review.md`: readable judgments for all 59 groups.
- `sector_verdicts.csv`: aggregate evidence for each sector.
- `all_workbook_stock_judgments.csv`: all 5,441 workbook codes, including unmatched entries.
- `workbook_universe_coverage.csv`: exact-code matching evidence and table membership.
- `sir_trade_ledger.csv.gz`: all purchase calculations.
- `complete_fundamentals_sensitivity.csv`, `broader_financial_sector_sensitivity.csv`: alternate evidence treatments.
- `native_top3_coverage.csv`: selections on each method's own population.
- `protocol.json`, `summary.json`, `verification.json`: assumptions, hashes and checks.

**Decision:** retain the current model as the working sector-shortlist method, with Sir's ranking visible as a useful comparison. Do not claim it wins every sector or is more accurate at predicting returns. The complete-fundamentals result argues for investigating individual disagreements and improving data quality before increasing confidence in either ranking.
