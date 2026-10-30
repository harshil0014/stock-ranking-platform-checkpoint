# Sir's exact SIP formula: isolated experiment

## What was replicated

The ranking displayed in **SIP Portfolio!N7:N20** in the supplied **Copy of OK Strategy - Master Sheet v4.3 (1).xlsx**. The screenshot shows this same ranking formula in the formula bar. This experiment has no V17, baseline, champion, learned model, closing-high weights, momentum weights, risk penalties, eligibility screen, or tuning step. Existing application code and previous experiments were not replaced.

**Rank = descending RANK of (current value − actual invested amount) / actual invested amount.**

The 10-, 5- and 3-year CAGR columns and the 20% highlight setting do not enter this rank. There is no XIRR or annualization in it. Other workbook tabs contain other calculations; this report does not relabel those as the SIP ranking formula.

Source workbook SHA256: `be2ab62fb41abd4769b5f5d8de7f3df04edc6cfa336bb0d2c5906fc6da2e980b`.

## Verification results

| Check | Result | What it establishes |
|---|---:|---|
| Source formula definitions checked | 82 | Expected schedule, share, investment and ranking formulas match this workbook revision |
| Workbook cached result cells reproduced | 84 / 84 | E, F, G, H, I and N for all 14 stock slots |
| Screenshot ranks reproduced | 14 / 14 | Ranks from the visible invested/current-value totals, including duplicate and missing-quote rows |
| Unit cases | 20 passed | Calendar, rounding, static quantity, missing inputs, errors, ties, duplicate slots and workbook quirks |
| Complete synthetic CSV run | 14 / 14 ranks, returns and share totals | The executable input-to-ledger-to-ranking path works; input files remain intact |
| Uncaptured price receipt | Rejected | An unfilled template cannot pass as observed market data |
| Live Google Finance prices reproduced | **Not verified** | The local XLSX has no usable cached historical close cells |

The screenshot verification uses manually transcribed, rounded rupee totals. It verifies the ordering, not full-precision trade histories or every displayed percentage. The screenshot's final row is a second CEMPRO; the XLSX's final row is BOM:522195. These are different snapshots and are kept separate.

### Reproduced screenshot order

| Rank | Stock |
|---:|---|
| 1 | Kwality Pharmaceuticals |
| 2 | WELCORP |
| 3 | SHAILY |
| 4 | GVT&D |
| 5 | TDPOWERSYS |
| 6 | Titan Biotech |
| 7 | APOLLO |
| 8 | V2RETAIL |
| 9 | CEMPRO, both displayed rows |
| 11 | TERASOFT |
| 12 | KRISHANA, LUMAXTECH, INDOTECH |

The three rank-12 rows have zero displayed current value and −100% profit in the screenshot. That is the formula's treatment of the missing quotes; it is not evidence those companies actually lost 100%.

## Exact calculation chain

### Controls and dates

| Cell | Formula/value | Meaning |
|---|---|---|
| SIP Portfolio!B1 | 7500 | Amount available for each purchase |
| SIP Portfolio!B2 | 36 | Lookback months |
| SIP Portfolio!B3 | 30 | Calendar-day interval |
| StockHistoryData!B1 | Truly blank | Static quantity override is inactive |
| StockHistoryData!B3 | `EOMONTH(TODAY(),-A4)` | Month-end anchor |
| StockHistoryData!A5 | `ROUNDDOWN((TODAY()-B3)/B2,0)` | Number of subsequent schedule rows |
| StockHistoryData!B4 | `SEQUENCE(A5,1,B3+B2,B2)` | Add fixed calendar-day intervals |
| StockHistoryData!C3 | `IF(ISBLANK(B3),"",WORKDAY(B3,1))` | Advance one weekday; no holiday calendar |
| StockHistoryData!D3 | `IF(C3="","",INDEX(GOOGLEFINANCE($E$1,"Close",WORKDAY(C3,-2),1),2))` | First returned historical row, spilling its date and close |

**Row 3 is also a purchase row.** Total requested observations are A5 + 1, not A5. With explicit `TODAY() = 2026-10-05`, the standalone schedule contains 36 observations, from scheduled date 2023-10-31 through 2026-09-15. The first Google Finance request starts 2023-10-30. The final argument `1` requests a one-day history span; it is not an instruction to search indefinitely for the next available trading day. Google's [GOOGLEFINANCE documentation](https://support.google.com/docs/answer/3093281?hl=en) describes that argument and historical array output. [WORKDAY](https://support.google.com/docs/answer/3093059?hl=en) excludes weekends and supplied holidays; this workbook supplies no holidays.

The cached workbook calendar is older: B3 = 45199 (2023-09-30), A5 = 35 and B38 = 46249 (2026-08-15). These values are consistent with multiple possible TODAY dates in September 2026. An unrelated timestamp is not used to invent the precise historical quote time.

### Purchases and ranking

For the first stock, historical close is E, quantity F and cost G. Later stocks use four-column blocks.

```text
F3 = IF(ISBLANK(E3),"",IF(ISBLANK($B$1),ROUNDDOWN($D$1/E3,0),$B$1))
G3 = E3 * F3

SIP Portfolio!E7 = IF(ISBLANK(B7),"",SUM(StockHistoryData!F:F))
SIP Portfolio!F7 = G7 / E7
SIP Portfolio!G7 = SUM(StockHistoryData!G3:G2499)
SIP Portfolio!H7 = D7 * E7
SIP Portfolio!I7 = IFERROR((H7-G7)/G7,"")
SIP Portfolio!N7 = RANK(I7,$I$7:$I$20)
```

Each purchase spends `quantity × close`. Unspent budget is neither carried forward nor included in the invested denominator. Static quantity, when nonblank, takes precedence over the amount and is not rounded. Zero is an active override. Shares are valued directly at the current quote. There is no extra corporate-action or dividend operation in this formula chain; the provider's price basis is therefore material.

Ranks use unrounded profit fractions. Equal values receive equal ranks with gaps afterward, as documented for [RANK](https://support.google.com/docs/answer/3094098?hl=en). Duplicate stock slots remain separate observations.

### Preserved workbook quirks

1. **Mismatched totals ranges:** shares sum the entire quantity column, while invested cost stops at history row 2499. Existing history formulas extend to row 9991. The experiment preserves this mismatch.
2. **First-row error handling:** F7 does not have IFERROR. F8:F20 return zero when average-price division fails.
3. **Shifted blank guards:** G11 checks B10, G12 checks B11, continuing through G20 checking B19. These guards are preserved, including their behavior if the preceding stock code is blank.
4. **Frontier query dependency:** StockHistoryData!BD3 tests the first stock's cost G3 instead of the calendar C3. Subsequent rows follow that pattern. Receipts are the actual resulting price cells, so this provider/formula dependency is not replaced with a guessed lookup rule.
5. **Missing current quote:** the sheet can value purchased shares at zero and report −100%. The replication preserves that behavior rather than adding a new screening policy.
6. **Google Sheets export wrappers:** the XLSX stores Google Finance calls inside `IFERROR(__xludf.DUMMYFUNCTION(...), fallback)`. These are not functioning Google Finance calls in a normal Python or Excel calculation engine. The audit retains the literal exported formula and cached values.

## Why the cached run has no meaningful stock ranking

The audit scanned 459,608 StockHistoryData cells and found **zero numeric historical close cells** in the 14 price columns. Current-quote fallback values are present, but the history spills are missing. Thus the supplied cache yields zero shares, zero invested/current value, blank profit and `#N/A` rank for all 14 rows. F7 is `#DIV/0!`; other average-price rows are zero.

Those results were reproduced, not replaced with fabricated prices. Matching them establishes cached formula parity but does not establish live market-data parity. Synthetic runs are explicitly labeled and must not be read as recommendations or market rankings.

## Run the experiment

From the project root:

```powershell
python research/runners/professor_exact_formula_20261005.py
python -m pytest tests/test_professor_exact_formula.py -q -p no:cacheprovider
python research/runners/verify_professor_exact_formula_20261005.py
```

The first command reads the supplied workbook without modifying it, writes the audit, reproduces cached results and creates a date-specific input template. It uses only the Python standard library and imports no project ranking code.

Outputs are under `experiments/professor-exact-20261005/`:

- `formula_audit.json`: literal formulas, shared formula definitions, cached cells and workbook hash.
- `cached_replay.csv` and `cached_cell_checks.csv`: all 14 results and 84 comparisons.
- `screenshot_rank_checks.csv`: independent screenshot rank reconciliation.
- `schedule.csv`: every schedule date, worksheet row and Google Finance request date.
- `price_cells_template.csv` and `quotes_template.csv`: explicit data interface.
- `verification.json` and `integration_verification.json`: machine-readable verification results.
- `synthetic_receipt_run/`: fully executed example, explicitly synthetic.

### Run with captured Google Sheets values

Use the same controls, stock slots and TODAY date in the source sheet. Copy its actual historical close output cells and current quotes into **copies** of the templates. Record the returned dates and a source/snapshot reference. Set `captured=yes` for every observed cell, including a genuinely blank result. An unobserved cell must remain `captured=no` and will be rejected. Error-valued close cells can contain literal `#N/A`, `#DIV/0!`, etc. A numeric close needs its returned date.

```powershell
python research/runners/professor_exact_formula_20261005.py --as-of 2026-10-05 --receipts path/to/captured_prices.csv --quotes path/to/captured_quotes.csv --output experiments/professor-exact-captured
```

This writes `receipt_rankings.csv` and `receipt_trade_ledger.csv`. Every slot/date must be supplied; duplicate, missing, uncaptured and mismatched inputs fail explicitly. Input hashes are recorded. CSV receipts establish the calculation inputs, not independent proof that a provider supplied them; provenance remains visible.

The runner does not emulate Google Finance, search ahead through missing prices, infer split factors, or use stale quotes from another date. A different provider can supply experimental cell values, but that would be a different-data run and must be labeled accordingly. Live Google Sheets recalculation has not been performed in this experiment.

## Difference from the project's earlier professor-style simulator

The previous proxy used an end-date-relative start, advanced purchases to available trading dates, imposed history availability rules and applied explicit corporate-action handling. Those choices can be useful for other experiments, but they are not this worksheet's exact formula chain. This experiment uses month-end anchoring, the workbook's date requests, actual cell inputs, its exact denominator and its quirks.

Sir's formula ranks the selected stock slots. Applying it within a sector means supplying that sector's stock cohort and ranking those profit fractions. No global percentile or sector adjustment is inherent in the source formula. This experiment preserves the supplied 14-slot workbook cohort so its replication is directly checkable.
