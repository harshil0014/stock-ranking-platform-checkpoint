# Professor workbook versus V17 refined

Analysis date: 4 October 2026. Research comparison only. No workbook, model, production or ranking changes.

## Conclusion

There is meaningful agreement in the ordering of comparable professor-list stocks without tuning V17 refined to imitate that list. This is explanatory agreement, not evidence of superior future returns or independent validation. The professor's SIP table ranks a manually entered shortlist; V17 refined ranks the eligible portion of the full 4,436-stock universe.

## Matching user inputs

| Workbook input | Workbook value and location | Existing model equivalent |
|---|---|---|
| Amount per contribution | ₹7,500; SIP Portfolio!B1 | amount=7500 |
| Historical lookback | 36 months; SIP Portfolio!B2 | lookback_months=36 |
| SIP interval | 30 days; SIP Portfolio!B3 | interval_days=30 |
| CAGR highlight | 20%; SIP Portfolio!P1 | No equivalent ranking control: this is a display threshold. Model target_cagr=20% actually influences ranking. |
| Static share quantity override | StockHistoryData!B1, blank | Not supported by the amount-based personalized model; inactive in this workbook. |
| Forward evaluation horizon | No corresponding SIP-table input | Model uses 12 months; separate from 36-month lookback. |
| Selected stock codes | SIP Portfolio!B7:B20 | Matched all 14 to V7 identities; model universe remains unchanged. |

The existing `base7500` research profile already matches amount, lookback and interval. Existing product input validation also supports these values (`src/stock_ranker/personalized_product.py`). “Lookback” means historical data used, not a lock-in period. A 30-day schedule is not necessarily the same calendar day each month. No UI change was needed for these three controls. Static-quantity investing would require a separately specified and tested execution mode, not a renamed amount field.

Other workbook controls belong to different tools: Opportunity!B2:B4 selects stock/start date/dip threshold; Buying (SingleStock)!B2 sets allocation; Buying (MultiStock - New Alloc)!B1 sets allotment and its row 1/3 controls allocate money across ATH dips. These are entry/allocation rules, not the SIP rank formula.

## What actually determines the professor's rank

SIP Portfolio!N7 is `RANK(I7,$I$7:$I$20)`, descending. I7 is `(H7-G7)/G7`; H7 is current price times accumulated shares; G7 is total purchase expenditure. Therefore the visible SIP ranking is **total profit percentage on deployed money**. It is not annualized XIRR and it does not directly blend CAGR, ATH distance, days since ATH or drawdown.

StockHistoryData!F3 purchases `ROUNDDOWN(amount/price,0)` shares unless its static-quantity override is populated. G3 records price times shares. This calculation does not carry unused contribution cash into subsequent purchases. Calendar generation starts from `EOMONTH(TODAY(),-lookback)` and uses WORKDAY/Google Finance lookups. Our existing professor-style score uses our own trading-date and corporate-action implementation, so it is a comparable policy calculation, not an exact reproduction of those Google Sheets lookups.

The broader workbook does contain genuine ATH logic: ATHCutter counts ATH breaks; the multistock buying sheet displays ATH distance and days since ATH and allocates at 10%, 15%, 20%, 25%, 30%, 35% and 40% dips. Opportunity filters drawdown opportunities. These may inform the professor's manual shortlist, but the workbook does not establish how that final shortlist was chosen. Do not describe the entire professor strategy as only profit sorting.

## What V17 refined weights

For this 36-month profile, V17 refined combines V17 with a regime-aware utility model at a weight of `0.10 * evidence_confidence`. V17 combines the frozen champion with equal monotone-utility and ATH-specialist corrections at a total weight of `0.30 * evidence_confidence`.

At full evidence confidence, the final component weights are:

| Component | Score blend weight |
|---|---:|
| Frozen champion score | 63% |
| Monotone utility correction | 13.5% |
| ATH specialist correction | 13.5% |
| Regime utility correction | 10% |

The champion itself blends 67% goal score and 33% learned ranking score. Consequently its direct goal component contributes 42.21% of the full-confidence final blend. **These are model-component weights, not independent economic-factor percentages.** Goal, growth, ATH, recovery and risk also interact inside the learned components. Assigning a fixed percentage to each of those factors would misrepresent the model. Lower evidence confidence shrinks corrections toward the champion; missing five-year history is not a blanket penalty. The 12- and 60-month profiles use different refinement routes; the table above must not be generalized to them.

The refined model incorporates user settings, goal outcomes, growth/returns, ATH distance and age, underwater duration, recovery, drawdown/volatility and evidence confidence. Fundamentals and peer context are subject to available historical evidence; displaying current context does not prove a historically trained contribution. See the frozen model definition for actual feature lists and source restrictions.

## Stock comparison

Current research decision date: 3 October 2026. Global ranks below come from frozen V17 refined `base7500` results, not from a newly fitted model.

| Stock | Screenshot rank | V17 refined global rank | V17 order within the 12 rankable workbook stocks | Current professor-style order within those 12 |
|---|---:|---:|---:|---:|
| Welspun Corp | 2 | 84 | 1 | 1 |
| Shaily Engineering | 3 | 95 | 2 | 4 |
| Lumax Auto Technologies | 12* | 100 | 3 | 6 |
| TD Power Systems | 5 | 257 | 4 | 2 |
| Krishana Phoschem | 12* | 258 | 5 | 7 |
| GE Vernova T&D India | 4 | 270 | 6 | 3 |
| V2 Retail | 8 | 327 | 7 | 9 |
| Apollo Micro Systems | 7 | 680 | 8 | 8 |
| Cemindia Projects | 9 | 733 | 9 | 11 |
| Indo Tech Transformers | 12* | 1,938 | 10 | 10 |
| Titan Biotech | 6 | 2,378 | 11 | 5 |
| Tera Software | 11 | 2,975 | 12 | 12 |
| Kwality Pharmaceuticals | 1 | Unranked | — | — |
| Frontier Springs | Not shown | Unranked | — | — |

*Screenshot CMP is missing for these three stocks, producing zero current value and apparent −100% returns. Those ranks are data failures, not evidence of bad companies. Screenshot repeats Cemindia; the Excel file instead has Frontier Springs in row 20. Company-level statistics count Cemindia once.

### Agreement, with denominators

- **Screenshot versus current V17 refined:** Spearman correlation **0.867**, pairwise agreement **31/36 = 86.1%**, across **9** distinct stocks with usable screenshot CMP and a current model rank. Excluded: three missing-price screenshot stocks and unranked Kwality. This compares different/unknown dates and is descriptive only.
- **Same-current-data professor-style score versus V17 refined:** Spearman correlation **0.741**, pairwise agreement **53/66 = 80.3%**, across **12** rankable workbook stocks. This separates the ranking objectives more cleanly, but does not recreate the exact spreadsheet execution calendar.
- **Full-universe membership:** **0** workbook stocks in current Top20; **0** in Top50; **3** in Top100: Welspun Corp, Shaily and Lumax Auto Technologies. Relative agreement within a shortlist does not imply matching full-market picks.

Titan Biotech is a substantial disagreement: fifth on our current professor-style profit ordering but eleventh among these 12 under V17 refined. Its model-data annualized carry XIRR is about 86.1%, while recorded ATH distance is −25.9% and days since high is 178. These are descriptive inputs, not a proven causal attribution for its lower model rank. Do not invent an explanation solely to defend the model.

Kwality and Frontier Springs have only about 1.45 months of usable history in the current research input and status INSUFFICIENT_HISTORY. This describes pipeline evidence, not company age or quality. Their omitted ranks remain a coverage limitation; no ranks were fabricated.

## Workbook integrity and comparison limits

1. All 14 exported SIP rows have zero cached invested value and #N/A cached rank. Historical Google Finance lookups are #N/A and adjusted-price cells are empty. The Excel file therefore cannot supply a valid live SIP leaderboard without restoring those dependencies. The screenshot is separate evidence.
2. The screenshot and workbook contain different quotes and a different last stock. Neither is an aligned current-market benchmark.
3. SIP invested-value formulas from row 11 onward check the preceding stock-code row for blankness. This can mis-gate results after editing the shortlist.
4. In the multistock sheet, AA4 refers to `A$2/Z4` rather than its displayed sixth-tranche allotment; the exported result is zero despite a nonzero sixth allocation. This is an allocation-sheet issue, not a SIP ranking weight.
5. The workbook's own ATH sheet flags split/bonus adjustment risks. Present-day workbook values must not be copied backward into historical model training.
6. V7 already contains some professor-derived current-only growth fallbacks. Similarity is therefore not fully independent at the input-source level. No professor ranks were used to tune this comparison.
7. This is not a new out-of-sample performance test and it does not change the prior model verdict. Production remains d499580; V17 refined remains research-only.

## What to show the professor

“We use the same ₹7,500, 36-month lookback and 30-day contribution inputs. Your SIP table sorts cumulative profit on invested cash. Our model also uses goal achievement, annualized cash-flow return, ATH behaviour, recovery, risk and evidence confidence. The two methods agree on about 80% of stock pairs in the comparable current shortlist, but they do not choose the same full-market Top20. We show missing-data cases explicitly.”

## Reproducibility

- Runner: `research/runners/compare_professor_v17_refined_20261004.py`
- Detailed stock data: `experiments/professor-v17-refined-comparison-20261004/stock_comparison.csv`
- Metrics, source hashes and limitations: `experiments/professor-v17-refined-comparison-20261004/summary.json`
- Workbook values and formulas: `experiments/professor-v17-refined-comparison-20261004/workbook_formula_evidence.json`
- Frozen architecture: `experiments/v17-refinement-20261004/model_definition.json`

All 14 workbook identities were matched uniquely by exact ticker or BSE security code through V7 facts. No fuzzy company-name matches were used. The source workbook was opened read-only and remains unchanged.
