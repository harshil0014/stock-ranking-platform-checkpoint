# Professor Excel fallback for current company facts

## Result

The supplied workbook was used as a **trusted current-only fallback** for the accepted 2026-09-18 company-fact snapshot. The new overlay has 4,436 company rows. It matches **4,393 distinct stocks** and fills **23,200 blank cells** across 4,392 stocks. One matched stock had no eligible blank value. Every filled cell has `PROFESSOR_EXCEL` provenance, an exact workbook sheet/cell address, workbook SHA256, and the identity-match method in `filled_cells.csv`.

The accepted snapshot and pointer remain unchanged. The overlay is an isolated research data candidate; it is not wired into website pages, model rankings, production, Railway, or historical V12/V13 rows.

| Field | Missing before | Missing after | Filled |
|---|---:|---:|---:|
| Professor 1Y CAGR | 4,419 | 332 | 4,087 |
| Professor 3Y CAGR | 4,419 | 732 | 3,687 |
| Professor 5Y CAGR | 4,421 | 992 | 3,429 |
| Professor 7Y CAGR, new field | 4,436 | 1,201 | 3,235 |
| Professor 10Y CAGR | 4,423 | 1,640 | 2,783 |
| Professor reference current price | 4,418 | 4,400 | 18 |
| Professor reference market cap | 4,418 | 4,400 | 18 |
| Professor industry | 4,419 | 44 | 4,375 |
| Professor ATH price, new current-only field | 4,436 | 3,652 | 784 |
| Professor ATH date, new current-only field | 4,436 | 3,652 | 784 |

The exact machine-readable counts are in `coverage_before_after.csv`. The workbook's `CAGR` sheet supplied 40 source rows, including three pairs of identical duplicate entries. On the `ATH` worksheet, the A:E table supplied 796 ATH rows, while the **independent I:O table** supplied 5,424 coded industry and return rows. These two tables were joined independently by code; their physical row alignment was never treated as a stock match. Of 6,260 source rows, 5,220 matched, corresponding to 4,393 unique accepted ISINs. The 1,033 unmatched and seven ambiguous/name-mismatched source rows were skipped and are listed separately. A:E matches used exchange code plus company-name check (weakest accepted similarity 0.80). I:O has no company name, so it was accepted only for a unique exact exchange-code match. No fuzzy-only match was accepted.

## Field and identity boundaries

- Existing nonblank cells are copied verbatim from the accepted company-fact CSV. The independent roundtrip audit compared their raw CSV cell text and passed. Valid zeros were not treated as blank.
- The workbook's `CAGR` and I:O return tables agree on overlapping filled values. Their percentages are stored as decimal fractions in `professor_workbook_cagr_1y`, `_3y`, `_5y`, `_7y`, and `_10y`. They do not replace `product_baseline_*` CAGR fields, which use a separate adjusted-price and ranking contract.
- The workbook's ATH is preserved as `professor_workbook_ath_price` and `professor_workbook_ath_date`. It does not overwrite `recorded_high`, `recorded_high_date`, or days since high, whose adjusted-price basis differs. Where NSE and BSE ATH entries for the same ISIN differed, the entry for the accepted security's primary exchange was chosen. There are no unresolved conflicting field values.
- The workbook file was last modified **2026-09-02 09:52 UTC**. Its reference price and ATH values are therefore labeled as professor workbook evidence, not a live 2026-09-18 exchange close. No volatility, downside-volatility, or maximum-drawdown column was present in the keyed `CAGR`/`ATH` tables; those risk fields remain unfilled.
- The 1Y return table includes 23 source values above 500% and a maximum decimal CAGR of 185.7857. These are retained exactly as professor reference values, with cell provenance, and are not injected into product ranking inputs.
- Source workbook SHA256: `be2ab62fb41abd4769b5f5d8de7f3df04edc6cfa336bb0d2c5906fc6da2e980b`. Accepted company-fact CSV SHA256: `d0436b9f79eda4de11524f22e7be985ae6d3a06c7ef3c72151973498c3f08301`. Accepted state SHA256: `79462a7499ef120f530652b077274c70cec5c6ee1379e9d5c88bef2c6dd412c0`.

## Artifacts

The full updated file is `experiments/professor-current-fallback-20261003/current_company_facts_professor_overlay.csv.gz`. `filled_cells.csv` is the authoritative per-cell provenance and exact workbook-cell ledger. `coverage_before_after.csv`, `unmatched_rows.csv`, `ambiguous_rows.csv`, `conflicting_values.csv`, `summary.json`, `roundtrip_audit.json`, and `manifest.json` provide the count and integrity audit. The reproducible builder is `research/runners/build_professor_current_fallback_20261003.py`; the independent audit is `research/runners/audit_professor_current_fallback_20261003.py`.

The independent audit checked **23,210 workbook cells** (including duplicate-source cells) and all 23,200 filled overlay cells. It confirmed every original nonblank CSV cell was copied verbatim.

**Current state:** 4,392 stocks enriched in the isolated overlay; accepted production facts, website behavior, model weights/rankings, and V12/V13 historical evidence are unchanged.
