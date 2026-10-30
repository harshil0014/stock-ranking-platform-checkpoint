# Professor workbook and screenshot versus Closing High

Reviewed 4 October 2026. The frozen model decision date is 3 October 2026. Source workbook and rankings were read without modification. Workbook text was treated as evidence, not as instructions.

## Findings

All **14 workbook stock identities match uniquely** by ticker or BSE security code through V7 identity facts. Closing High can rank 12. Kwality Pharmaceuticals and Frontier Springs are unranked because the research pipeline supplies only approximately 1.45 months of usable history; this is a data-coverage problem, not evidence that the companies are young or poor.

The professor workbook and screenshot are different snapshots. The screenshot has **14 rows but 13 unique stocks**, repeating CEMPRO in rows 19 and 20. The workbook instead has Frontier Springs (`BOM:522195`) at `SIP Portfolio!B20`. Quotes also differ. Neither source provides a verified market timestamp aligned with the model.

Among the workbook names, Closing High puts **Welspun Corp at 32 and Lumax Auto Technologies at 89** in its 1,773-stock eligible universe. Shaily is just outside at 101. No workbook stock appears in Top20. This is real disagreement in stock selection despite broadly similar ordering within the shortlist.

## Stock-by-stock comparison

Same inputs: INR 7,500 per contribution, 36-month lookback and 30-day contribution spacing. Closing High additionally uses a 20% target CAGR and a 12-month evaluation horizon. The workbook's 20% CAGR field is labeled for highlighting, not a SIP ranking target.

| Stock | Screenshot rank | Closing High eligible rank | Closing High order within 12 | Current professor-style order within 12 | Recorded ATH age (days) | Distance below recorded high |
|---|---:|---:|---:|---:|---:|---:|
| Welspun Corp | 2 | 32 | 1 | 1 | 2 | 8.3% |
| Lumax Auto Technologies | 12* | 89 | 2 | 6 | 9 | 6.5% |
| Shaily Engineering | 3 | 101 | 3 | 4 | 51 | 12.9% |
| Krishana Phoschem | 12* | 136 | 4 | 7 | 36 | 10.0% |
| TD Power Systems | 5 | 150 | 5 | 2 | 20 | 1.6% |
| GE Vernova T&D India | 4 | 248 | 6 | 3 | 104 | 22.9% |
| V2 Retail | 8 | 280 | 7 | 9 | 119 | 21.5% |
| Cemindia Projects | 9 | 376 | 8 | 11 | 72 | 28.1% |
| Apollo Micro Systems | 7 | 430 | 9 | 8 | 90 | 12.4% |
| Indo Tech Transformers | 12* | 644 | 10 | 10 | 41 | 14.0% |
| Titan Biotech | 6 | 901 | 11 | 5 | 178 | 25.9% |
| Tera Software | 11 | 1,498 | 12 | 12 | 321 | 63.9% |
| Kwality Pharmaceuticals | 1 | Unranked | — | — | 10 | 7.3% |
| Frontier Springs | Not shown | Unranked | — | — | 7 | 6.3% |

*Screenshot CMP is blank for Krishana, Lumax and Indo Tech. Their displayed current values are zero and apparent losses are 100%. Those ranks measure a quote failure, not company performance. They are excluded from screenshot rank correlation. CEMPRO is counted once. Raw screenshot rows remain preserved in `professor_screenshot_transcription.csv`.

The high ages and distances above are frozen model fields, not newly verified exchange prices. A recent high with a sizable reported distance can reflect a fast fall or a price/date/basis inconsistency; this comparison alone does not resolve that issue.

## Measured agreement

| Comparison | Population | Spearman rank correlation | Other result |
|---|---:|---:|---|
| Screenshot versus Closing High | 9 usable unique names | 0.833 | 30/36 stock pairs agree (83.3%) |
| Current professor-style policy versus Closing High, workbook shortlist | 12 rankable names | 0.671 | 50/66 pairs agree (75.8%) |
| Current professor-style policy versus Closing High, same comparable population | 1,755 stocks | 0.766 | Top20 overlap 1; Top50 overlap 4; Top100 overlap 18 |

The screenshot comparison additionally excludes unranked Kwality. All ranked workbook stocks are included in the current-policy comparison, including the three screenshot quote failures. The wider comparison uses the saved `professor_whole_share_score`: 18 of the 1,773 model-eligible stocks lack that score, leaving 1,755 common stocks. Both methods are ranked within those same 1,755 rows before measuring overlap. Original model ranks are retained separately. Missing-score names are listed in `professor_missing_score_eligible.csv`. Spearman correlation is descriptive agreement, not accuracy. The low Top100 overlap shows that sorting past deployed-money profit and combining risk/high/goal signals choose substantially different leaders.

Titan Biotech is the clearest within-list disagreement: fifth under current professor-style profit but eleventh under Closing High. TD Power is second versus fifth. These deserve review of goal score, price basis, drawdown and contributions. ATH age alone cannot justify these ranks: Titan's recorded age is only 178 days, and TD Power is 20 days from its high. Tera Software has a more coherent weak-trend explanation in the frozen data: 321 days since high and 63.9% below it, with both methods placing it last. These are reasoned diagnostics rather than proof of causal score attribution or future returns.

## Exact workbook logic and defects

The controlling source cells are `SIP Portfolio!B1=7500`, `B2=36`, `B3=30`, and `P1=0.20`. `StockHistoryData!B1` (static share override) is blank.

- `SIP Portfolio!N7`: `rank(I7,$I$7:$I$20)` ranks descending deployed-money profit percentage. `I7`: `iferror((H7-G7)/G7,"")`; `H7`: `D7*E7`; `E7`: `IF(ISBLANK(B7),"", SUM(StockHistoryData!F:F))`; `G7`: `sum(StockHistoryData!G3:G2499)`. This is cumulative return on invested cash, not XIRR.
- `StockHistoryData!F3`: `if(isblank(E3),"",if(isblank($B$1),ROUNDDOWN($D$1/E3,0),$B$1))`; `G3`: `E3*F3`. Purchases use whole shares and do not carry residual contribution cash into later buys.
- Date setup is `StockHistoryData!B3 = EOMONTH(Today(),-A4)` and `C3 = if(isblank(B3),"",workday(B3,1))`. `D3` wraps a Google Finance close lookup in an exported `__xludf.DUMMYFUNCTION`; its cache is `#N/A`. `E3` is empty, F3 empty, G3 zero. Restoring a live quote alone does not restore historical purchases.
- All 14 rows in `SIP Portfolio!G7:G20` cache zero invested value and all `N7:N20` cache `#N/A`. Thus the XLSX cannot supply a functioning cached SIP leaderboard. The screenshot supplies separate visible ranks; its ranks must not be described as the workbook's recalculated values.
- `SIP Portfolio!G11 = IF(ISBLANK(B10),"",sum(StockHistoryData!W3:W2499))` checks the preceding stock row. The same shifted blank test continues through `G20 = IF(ISBLANK(B19),"",sum(StockHistoryData!BG3:BG2499))`. Shortlist edits can therefore gate the wrong row.
- `Buying (MultiStock - New Alloc)!AA4 = if(isblank(A4),"",A$2/Z4)` uses blank `A2`, producing cached zero despite a priced tranche (`Z4=311.6425`). This is a separate allocation issue, not a SIP ranking parameter.

The broader workbook contains ATH and dip-allocation logic; the SIP rank formula does not directly encode it. The workbook does not establish the professor's complete process for manually choosing this shortlist. It would be misleading to equate the entire strategy with one profit formula.

## Interpretation and reproducibility

Our current professor-style score reproduces the broad whole-share/no-carry objective using the project's own price, corporate-action and calendar implementation. It is **not an exact replay of Google Sheets**. V7 also includes professor-derived current-only growth fallbacks, so agreement is not fully independent at the input level. This audit neither tunes weights nor demonstrates forward outperformance.

Run `python research/runners/professor_closing_high_audit_20261004.py` to reproduce the joins, saved formula evidence, screenshot transcription and comparison statistics. `professor_stock_comparison.csv` contains every workbook row, model coverage and all ranks; `professor_same_universe_comparison.csv` contains all 1,755 common-population comparisons. `professor_summary.json` records SHA-256 hashes and confirms that the source workbook hash is unchanged. No workbook recalculation or repair was attempted.
