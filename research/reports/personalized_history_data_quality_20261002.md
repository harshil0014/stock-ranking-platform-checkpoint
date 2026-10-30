# Personalized History Data-Quality Upgrade — 2026-10-02

## Result

The price-history and long-term-growth data layer is materially more complete without changing the frozen 67% Goal / 33% LambdaRank champion or production.

The build is pinned to:

- prediction cutoff: **2026-09-18**
- accepted universe: **4,436 securities**
- accepted company-fact fingerprint: `4064dc5b0a12fc385150a08e23a61f230b0f2acfcee76e394c8e80cee48d741e`
- accepted market state: unchanged
- frozen personalized champion: unchanged
- production deployment: unchanged

## Before / after

| Field | Before | After | Change |
|---|---:|---:|---:|
| No usable price path at all | 62 | **0** | **-62** |
| No defensible adjusted history | 64 | **4** | **-60** |
| Invalid/stale adjusted history | 2 | **0** | **-2** |
| Securities with observed price-history span | 4,372 | **4,436** | +64 |
| Strict 1Y CAGR | 3,823 | **3,827** | +4 |
| Strict 3Y CAGR | 3,417 | **3,421** | +4 |
| Strict 5Y CAGR | 3,126 | **3,129** | +3 |
| Recorded high / days since high | 4,374 | **4,436** | +62 |
| Full-history max drawdown | 4,372 | **4,436** | +64 |
| Observed 1Y realized/downside volatility | 4,358 | **4,404** | +46 |
| Provenance-aware 1Y volatility value | — | **4,436** | complete |
| Long-term growth value | 4,436 | **4,436** | complete |

A price-history span and price-path risk diagnostics are now available for **4,436 / 4,436 (100%)** securities. **4,432** have accepted or validated corporate-action-adjusted histories; the remaining **4** use official raw BSE closes for explicitly labeled risk diagnostics only. A long-term growth input is available for every accepted identity, with provenance distinguishing true observations from estimates.

## Recovery method

The recovery overlay is research-only and does not overwrite accepted state.

- Accepted history cache remains first priority.
- **58** identities receive validated recovery histories where accepted history was absent.
- **2** stale BSE histories are refreshed by a strictly newer validated overlay.
- The BSE recovery uses exact BSE scrip codes and official BSE price-history evidence.
- Recovered BSE histories pass corporate-action checks before promotion.
- Histories that cannot be adjusted defensibly remain quarantined from adjusted-return features rather than being forced into the model.
- For the four residual quarantined identities, official raw BSE closes are retained only for explicitly labeled price-path/risk diagnostics; strict CAGR and adjusted-return fields stay unavailable.

After recovery the source mix is:

- 4,372 accepted history-cache rows
- 58 validated recovery-overlay rows
- 2 validated recovery refreshes
- 4 official BSE raw-risk-only rows

## True 5Y history versus estimated long-term growth

A missing true 5Y CAGR is no longer treated as if it were an observed number.

- **3,129** securities have a real adjusted 5Y CAGR.
- **1,307** securities require an estimated long-term growth proxy.
- Of those estimates:
  - **1,295** use the security's observed history-start CAGR conservatively shrunk toward its sector's observed 5Y median according to available history length.
  - **12** use only a neutral sector/global median because there is too little usable security-specific history.

Every row records:

- `long_term_growth_value`
- `long_term_growth_source`
- `long_term_growth_is_observed`
- `cagr_5y_observed`
- `history_months`

A true 5Y CAGR remains missing when five years of prices do not exist. The estimate is not presented as historical fact.

## Historical-high and risk information added

The enrichment exposes:

- observed price-history span
- strict 1Y / 3Y / 5Y CAGR
- recorded all-history high and date
- days since recorded high
- distance from recorded high
- distance from 52-week high
- full-history maximum drawdown
- current drawdown duration
- maximum drawdown duration
- recovery from the worst trough
- 1Y realized volatility
- 1Y downside volatility

These are derived only from prices available through the frozen cutoff.

## Listing-date provenance

The accepted company snapshot contains official listing dates for **2,575** securities and lacks them for **1,861**, corresponding to the BSE-side metadata gap.

The official BSE `ListofScripData_new` security-list endpoint was checked. It exposes exact security code, issuer/security name, status, group, face value, ISIN, segment and market capitalization, but not listing date.

Therefore the research layer does **not** invent BSE listing dates.

`history_months` is explicitly defined as **observed price-history span**, not listing age. The research field previously named `since_listing_cagr` has been corrected to `history_start_cagr` so future experiments do not overstate what is known.

## Remaining four adjusted-return quarantines

These four have official raw BSE price evidence, but their corporate-action history cannot currently be adjusted defensibly under the frozen rules. Their raw closes are therefore used only for diagnostic price-path/risk metrics, with `RAW_RISK_ONLY` provenance; they remain quarantined from strict CAGR and adjusted-return features:

| Security | Reason for quarantine |
|---|---|
| BSE-505685 | dividend actions with insufficient pre-ex-date raw close evidence |
| BSE-534920 | rights action with insufficient pre-ex-date raw close evidence |
| BSE-543765 | dividend action with insufficient pre-ex-date raw close evidence |
| BSE-544257 | dividend action with insufficient pre-ex-date raw close evidence |

They are deliberately not promoted. This is a quality-control decision, not an unnoticed missing-data failure.

## NYKAA diagnostic

NYKAA now has an explicit history-aware record:

- history start: **2021-11-10**
- history end: **2026-09-18**
- observed history: **58.25 months**
- strict 3Y CAGR: **30.57%**
- true 5Y CAGR: **unavailable**
- estimated long-term growth proxy: **-2.03%**
- proxy source: **ESTIMATED_HISTORY_SECTOR_SHRUNK**
- recorded adjusted high: **₹415.52 on 2021-12-01**
- days since recorded high: **1,752**
- distance from recorded high: **-20.06%**
- full-history max drawdown: **-72.09%**
- 1Y realized volatility: **27.74%**
- 1Y downside volatility: **16.93%**

This means future challengers can see the old crash and history age rather than only the 36-month recovery window.

## Data-only champion repair experiment

A separate leakage-aware research audit kept the original seven-feature architecture, the champion LightGBM hyperparameters and the **67% Goal / 33% ranker** structure. The only intervention was replacing unavailable 5Y CAGR inputs with the provenance-aware long-term proxy.

| Metric | 2023 champion → repaired | Exposed 2025 champion → repaired |
|---|---:|---:|
| Coverage | 80.24% → 80.24% | 82.97% → 82.97% |
| Rank IC | 0.02757 → 0.01023 | 0.15467 → 0.15986 |
| NDCG@20 | 0.50117 → 0.52046 | 0.62682 → 0.64611 |
| Pairwise accuracy | 51.94% → 51.01% | 54.87% → 54.68% |
| Top-20 target achievement | 58.33% → 60.00% | **39.72% → 32.78%** |
| Top-20 target shortfall | 6.03% → 5.74% | 12.90% → 12.79% |
| Median Top-20 XIRR | 33.91% → 42.69% | **4.66% → -0.45%** |
| Mean Top-20 drawdown | -34.56% → -27.54% | -42.58% → -37.00% |

The repaired-data model greatly reduces the current short-history concentration:

- champion Top 20 without true 5Y: **90%**
- repaired/retrained Top 20 without true 5Y: **10%**
- NYKAA global rank: **1 → 18**
- NYKAA Retailing rank: **1 → 1**

However, the exposed profile slices are not robust enough for promotion. In particular:

- 30% target: **-17.5 pp** Top-20 achievement and **+2.99 pp** shortfall
- 10% target: **-20.0 pp** achievement and **+1.57 pp** shortfall
- 60M lookback: **-17.5 pp** achievement and **+0.96 pp** shortfall
- base ₹7,500 profile: **-12.5 pp** achievement and **+1.39 pp** shortfall

Feeding the repaired input into the exact already-fitted frozen tree, without retraining, reduces Top-20 short-history concentration to **15%** but still leaves NYKAA #1. That is also not a justified production patch because the tree was trained with native missing-value routing.

**Conclusion:** the enriched information layer is retained for future training/research, but the production champion remains unchanged. Better data alone does not make a safe drop-in replacement.

Full audit:
`experiments/history-enrichment-20261002/data-repaired-champion-v3/summary.json`.

## Reproducibility

Primary build:

```cmd
.venv\Scripts\python.exe research\runners\build_personalized_history_data_quality.py --output experiments\history-enrichment-20261002\final-data-quality-v3
```

Data-only model audit:

```cmd
.venv\Scripts\python.exe research\runners\personalized_data_repair_audit.py --output experiments\history-enrichment-20261002\data-repaired-champion-v3
```

Primary artifacts:

- `src/stock_ranker/history_enrichment.py`
- `research/runners/build_personalized_history_data_quality.py`
- `research/runners/personalized_data_repair_audit.py`
- `experiments/history-enrichment-20261002/final-data-quality-v3/`
- `experiments/history-enrichment-20261002/data-repaired-champion-v3/`

## Production boundary

This work is **research/data enrichment only**.

No production serving code was switched to the repaired ranking, the frozen 67/33 champion was not overwritten, and Railway was not redeployed.
