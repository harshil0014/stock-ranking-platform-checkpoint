# Product Baseline official prior-trade recovery — 14 September 2026

The accepted market snapshot remains 7 September 2026, fingerprint
`6dad2b7d600bdb4458bec10f854cdd69e815298369b703b0eaffeafdfb69e504`.
Its five absent same-day quotes remain absent in the immutable market dataset.
The current product can now show a separately dated official last-trade quote.
No current reference creates historical PIT evidence.

## Evidence and acceptance

`stock_ranker.product_price_reference` reads cached official NSE/BSE bhavcopies.
UDiFF observations require the exact canonical ISIN, ordinary stock type, positive
finite closing price and positive traded volume. NSE full bhavcopies require an
exact symbol/series link to an official ISIN master within seven days of the
observation. Files, master links and SHA-256 hashes remain attached to the quote.
Future observations, unsupported identities, conflicting equal-priority prices,
and observations without trades cannot supply a quote. The newest official trade
is selected; the primary exchange wins when both exchanges traded that day.

A prior trade within the existing seven-day continuity window can supply the
Product Baseline current price when the accepted adjusted-history terminal is
within 2%. Historical anchors retain the market snapshot date. A newly attained
recorded high uses the quote's actual date. Stale quotes remain visible with their
actual date but cannot enable ranking. A known corporate action after the last
trade requires review. Cross-exchange price/history conflicts remain excluded;
the recovery does not replace them with newer Screener observations.

| Security | Official last trade | Price (INR) | Product result |
| --- | --- | ---: | --- |
| ABMINTLLTD | NSE, 2026-09-04 | 55.86 | Eligible |
| KALYANI | NSE, 2026-08-28 | 144.99 | Current price stale |
| PBMPOLY | NSE, 2026-09-04 | 61.00 | Insufficient one-year history |
| RAJVIR | BSE, 2026-08-31 | 7.74 | Conflict with cached NSE terminal 5.32 |
| SONAL | NSE, 2026-09-04 | 88.98 | Insufficient one-year history |

These rows are audit results, not selection rules or hardcoded inputs.

## Isolated rebuild and outcome

`marketdata/runners/rebuild_product_prior_prices.py` starts from the previously
accepted company-fact CSV. It changes only current-product quote fields and
Product Baseline output fields. Existing metric cells are copied verbatim.
Only sectors admitting a newly eligible security are reranked, using the existing
Baseline rank function. Every other accepted cell is compared as a literal
string, preventing floating-point serialization changes from slipping through.

Independent candidates `candidate_prior_prices_c_20260914` and
`candidate_prior_prices_d_20260914` match byte-for-byte. The accepted fingerprint
is `ad3cd53f6de553132f6413ca72dfab9621024ad2cf885cea992533cc459da80b`.
No previously eligible security was lost. Baseline increased from 3,245 to 3,246;
only Basic Materials ranks changed. V2 remains 63. All protected market, research,
classification and non-product financial cells are unchanged.

The full 4,572-company waterfall is:

| Result | Count |
| --- | ---: |
| Eligible | 3,246 |
| Insufficient one-year history | 589 |
| Insufficient three-year history | 428 |
| Insufficient five-year history | 307 |
| Stale verified price | 1 |
| Price/history continuity conflict | 1 |

Official same-day coverage is still 4,567. Current-or-dated-official-reference
coverage is 4,572, including one stale reference. This does not mean that every
company has five years of continuous usable prices.

## Residual evidence

The deterministic audit runner `marketdata/runners/audit_product_baseline_residual.py`
examines the full noneligible cohort and its accepted history files. For every
1/3/5-year target it records the exact target date, preceding available observation,
history hash, and whether the existing seven-day anchor tolerance is satisfied.
It also checks preserved older caches: no additional missing anchor was found.
It examined 278 local official files for the missing-price cases.

Final machine-readable reports:

- `data/company_facts/product_baseline_residual_final_20260914/baseline_residual.csv`
- `data/company_facts/product_baseline_residual_final_20260914/price_evidence.csv`
- `data/company_facts/product_baseline_residual_final_20260914/summary.json`
- `data/company_facts/prior_price_acceptance_20260914/acceptance.json`

Missing anchors are not all proof of a recent IPO. An NSE listing date can be
later than a company's BSE listing, and a cached history start is not proof that
earlier trading never occurred. Some gaps may be recoverable with independently
verified earlier exchange history and corporate-action/identity continuity.
This recovery does not claim that all remaining gaps are permanently impossible.
No price is carried into a missing historical date or inferred from a nearby
observation to make an anchor pass.

The quote overlay is read from the accepted company-fact snapshot during website
navigation, with no provider requests. Market data remains immutable; dated
references show their own exchange/date/status and preserve source hashes.
