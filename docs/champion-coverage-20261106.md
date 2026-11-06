# Champion coverage integration, 6 November 2026

The local champion product now includes 5,547 accepted NSE/BSE identities: the original 4,436 plus 1,111 additional companies from the authorized Screener export. Current vendor financial observations match 5,544 identities. Three source records without NSE/BSE codes are excluded; three unmatched older identities remain visible. This covers the combined accepted dataset, rather than certifying the complete exchange security masters or active trading status.

The 2,386-stock frozen global correction model retains its exact order and Top-20. The original 4,436 sector scores and ranks are preserved. Of the added stocks, 1,108 receive separate, explicitly unvalidated coverage proxy scores and three remain visible without a score. New proxies follow every existing stock within their sector, including all occupants of tied ranks. Global coverage positions put trained global stocks first, other frozen sector stocks next, current-data proxies next, and rows without usable signals last. Those positions are not comparable predictions from one trained model.

The fallback uses cross-sectional percentiles of the vendor's three-year return (30%), five-year return (30%), price/all-time-high proximity (20%), ROCE (10%) and lower debt/equity (10%). Missing factors contribute a midpoint only to this disclosed proxy, and factor coverage is reported. At least one observed return/proximity factor is required for a score. Days since the high, SIP profit, daily paths and execution results remain unknown when unavailable. High proximity is not high recency. No training or historical performance improvement is claimed.

The API and Inspect view distinguish current financial observations from 6 November from frozen model/execution evidence dated 3 October. Current quotes do not overwrite historical execution prices. Seventeen current exchange-code matches with changed ISINs preserve both identifiers and block claims of verified execution continuity. Prospective-ledger records and holdout eligibility are unchanged.

## Reproducibility

Run the existing Screener importer, then `research/runners/build_champion_coverage_20261106.py` using the repository environment and low-load governor. The builder writes a hash-validated package to `work/champion-coverage-20261106/runtime/`. `STOCK_RANKER_CHAMPION_COVERAGE` can select another authorized local package. A missing package preserves the frozen universe and reports its absence; a present but corrupted package fails integrity validation.

The subscription-derived financial observations and portable private runtime remain outside Git. The public repository contains the importer, builder, service integration and tests. All 378 source metrics are preserved locally; 101 canonical financial fields are attached to the champion product. The new financial columns are not silently fed into a model that was trained without them.

Verification checks unique identities and positions, all current matches, changed-ISIN execution blocks, unchanged original scores/order, new-stock lookup, repeat-request stability, missing-evidence behavior, strict JSON and normal HTTP routing. Browser review covers the all-stock count, lookup, details, filters and pagination. Local checks do not certify external CI or a hosted deployment.
