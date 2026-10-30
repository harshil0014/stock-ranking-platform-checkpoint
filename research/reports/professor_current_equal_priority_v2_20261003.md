# Trusted professor Excel fallback in current growth fields

The professor workbook is now treated as an **equal-priority fallback for blank current-data growth fields**. The revised research-only overlay fills `product_baseline_yoy_growth`, `product_baseline_cagr_3y`, and `product_baseline_cagr_5y` directly where the accepted snapshot had no value. `PROFESSOR_EXCEL` remains a source audit label only; there is no source-based discount, penalty, or ranking weight.

| Current field | Missing before | Missing after | Newly filled |
|---|---:|---:|---:|
| 1Y growth | 769 | 302 | 467 |
| 3Y CAGR | 1,156 | 669 | 487 |
| 5Y CAGR | 1,433 | 890 | 543 |

These **1,497 direct fills** affect **625 distinct stocks**. The underlying workbook match covers **4,393 distinct stocks**; the full two-stage overlay has **24,697 professor-sourced filled cells** across the reference and direct fields. The original 1,033 unmatched and seven ambiguous source rows remain excluded. No pre-existing nonblank field was overwritten.

The [revised current-data file](../../experiments/professor-current-fallback-20261003/equal-priority-v2/current_company_facts_equal_priority.csv.gz) has 4,436 company rows. [Direct-fill provenance](../../experiments/professor-current-fallback-20261003/equal-priority-v2/direct_filled_cells.csv) gives every ISIN, target field, value, source workbook table and cell, exchange-code match, workbook hash, and `PROFESSOR_EXCEL` source label. The [coverage table](../../experiments/professor-current-fallback-20261003/equal-priority-v2/coverage_before_after.csv) and [independent audit](../../experiments/professor-current-fallback-20261003/equal-priority-v2/audit.json) verify the counts and raw-cell preservation. The [first-stage report](professor_current_fallback_20261003.md) documents the full workbook match and the ATH, industry, 7Y, and 10Y reference values.

There were **zero** blank accepted `recorded_high`, `recorded_high_date`, `latest_price`, or `market_cap` cells with a matching professor value, so those direct fields required no fill. The workbook's ATH values remain available in the current overlay's professor ATH columns. The 110 blank `product_sector` values with professor industries were left blank because their existing `UNCLASSIFIED` status could not be overwritten under the requested fill-only rule.

This overlay has **not** been connected to the website or used to recompute product baseline scores, ranks, eligibility, or model weights. The accepted 2026-09-18 company-fact snapshot, production pointer, Railway configuration, and historical V12/V13 point-in-time rows remain unchanged. The workbook file was last modified 2026-09-02; this date and the exact source cells remain visible in provenance.
