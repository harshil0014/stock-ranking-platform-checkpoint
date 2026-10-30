# Closing High: implemented audit corrections

Implemented on branch `main`, 4 October 2026. Model revision: `closing_high_reviewed`, snapshot 3 October 2026, scoring terminal quote generally 1 October. The existing Closing High UI and API use the reviewed model. Original Personalized and V17 remain separate.

## Changes delivered

### 1. Near-recovery treatment without erasing ATH age

The explicit closing-high allocation remains **30%**: 15% age/recovery, 9% proximity and 6% annual-high recency. The remaining allocations are 50% refined V17, 10% momentum and 10% downside confirmation.

The age contribution now approaches its new-high value continuously as the remaining price gap closes:

```
freshness = exp(-max(age_days, 0) / 1095.75)
depth = clip(-distance_from_high, 0, 1)
recovery_credit = exp(-(depth / 0.05)^2)
reviewed_age = freshness + (1 - freshness) * recovery_credit
```

The 5% transition band was fixed before this round's historical evaluation; it was not searched for the best return. Actual recorded high ages remain unchanged. Deep drawdowns receive almost no credit. The explicit age term no longer creates the large jump on crossing a very old high. V17 and the other inputs can still introduce their own nonlinear behavior.

### 2. History recovery and corporate-action correction

Downloaded separate BSE series for four companies, matched them to existing identities and checked overlapping prices against NSE. Median close differences were 0.08%–0.23%; 95th-percentile differences were below 1.33%. No unchecked cross-exchange splice was used.

| Company | Previously usable months | Now usable months | Retained history and action handling |
|---|---:|---:|---|
| Kwality Pharmaceuticals | 1.45 | 104.97 | BSE from January 2018, after its older bonus |
| Frontier Springs | 1.45 | 320.92 | BSE from January 2000; March 2026 bonus explicitly modeled |
| PTC Industries | 39.75 | 50.23 | BSE from July 2022, after the rights event |
| Steelcast | 58.25 | 80.99 | BSE from January 2020; verified August 2025 split retained |

Frontier's **2:1 bonus became ex-bonus on 13 March 2026**, as recorded in [BSE notice 20260310-46](https://www.bseindia.com/markets/MarketInfo/DispNewNoticesCirculars.aspx?page=20260310-46). The older company announcement had a different proposed date; the rebuild uses the exchange notice. Pre-event nominal purchase prices and post-event share counts now use the correct factor of three. The downloaded notice and its hash are retained.

PTC's earlier rights issue requires subscription mechanics, as described in its [FY2023 financial results](https://www.ptcil.com/PDF/Investors/financial-results/2022-23/Q4-Financial-Results-2022-23.pdf). The accepted series starts after that event. Earlier histories were downloaded but are not silently certified for execution. A 60-month request cannot manufacture unavailable pre-event evidence.

All nine saved profiles were rebuilt using the corrected history book and frozen V17 models. Custom profiles use the same corrected book. The original V17 runtime inputs and model files remain separate from the reviewed history overlay.

### 3. Execution evidence affects availability

BSE M/MT and NSE SM/ST securities with unverified lot sizes no longer receive a Closing High rank. All 357 such identities remain searchable; **28 were previously eligible** under the default activity screen. Two newly recovered companies become eligible, giving **1,747 ranked companies**, versus 1,773 before.

The UI explains the exclusion and suppresses misleading whole-share XIRR, share-count and affordability outputs for these securities. This follows the requirement to trade SME shares in defined lots described by [NSE's market-segment rules](https://www.nseindia.com/static/products-services/emerge-sme-market-segment).

Former SME companies are distinguished from current SME series. MWL, Swaraj and CFF retain their mainboard status and receive historical-lot review flags. No speculative market lot has been invented. Historical lot-aware replay for every migrated company is still unavailable; their displayed simulation and reported-volume evidence are labeled accordingly. This is an explicit product boundary, not a claim that every ranked stock has verified fills.

### 4. Review information in the existing UI

- Financial flags for high P/E, substantial promoter pledge, negative operating cash flow and leverage. Banks, finance, capital markets and fintech are exempt from the generic cash-flow/leverage tests.
- Business-continuity flags for the investigated transformations, and separate labels for available price history versus company age.
- Dated scoring price, financial observation date, source financial values and actual usable history length in Inspect.
- Top100 sector counts on every result, independent of the selected table filter. These are company counts, not an allocation or correlation model.
- The previous confidence label now says **price-field coverage**, matching what the underlying completeness measure actually represents.

Financial review thresholds are transparent attention flags, not newly fitted scoring weights. For example, MWL remains #1 with its financing concerns visible; the change does not invent a validated business-quality score to demote it. Sector classifications inherit the frozen provider snapshot and can still lag major business changes.

## Current default ranking changes

| Stock | Previous rank | Reviewed rank |
|---|---:|---:|
| Dr Lal PathLabs | 207 | **11** |
| Nazara | 231 | **93** |
| One Point One Solutions | 201 | **68** |
| NYKAA | 172 | **172** |
| Kwality Pharmaceuticals | Unavailable | **229** |
| Frontier Springs | Unavailable | **538** |
| PTC Industries | 15 | **15** |
| Steelcast | 12 | **24** |
| Aayush / Khazanchi / Trident Lifeline | 9 / 6 / 77 | Unranked: lot evidence required |

NYKAA retains its 1,765-day recorded high age. Its 21.8% gap gets virtually no near-recovery credit. Dr Lal's 1.09% gap gets substantial credit while its 1,842-day age remains visible. Current Top100 membership overlap is 97/100; the three newly included names replace the three unverified SME names above.

## Historical measurement, including tradeoffs

All 44 decision dates × nine profiles were compared on identical available populations. **This historical comparison isolates the recovery correction**. Current financial flags, current SME classifications and newly downloaded histories were not backfilled into earlier dates. It is not a backtest of the entire revised execution/data overlay.

| Period | Previous basket-median XIRR | Recovery correction | Average asset drawdown: previous → corrected |
|---|---:|---:|---:|
| 2016–2019 | 5.36% | 5.53% | −34.90% → −34.78% |
| 2020–2023 | 21.80% | 21.46% | −26.84% → −26.81% |
| 2024–2025 | −0.41% | −0.52% | −28.52% → −28.47% |

These are means of date/profile basket-median stock XIRRs and average constituent drawdowns, not transaction-cost-adjusted portfolio returns. The correction improves explicit age continuity and aggregate drawdown, but **does not dominate the previous model on returns or every metric**. The largest period/profile return regression is the 60-month profile in 2020–2023 (−2.17 percentage points); weekly drawdown in 2024–2025 worsens by 0.28 percentage points. Every profile's tradeoffs are exported. Previously exposed dates do not constitute fresh validation.

The adoption is a behavioral and data-quality correction requested after the audit, not a declaration of a newly proven best-performing strategy. No favorable period or profile has been hidden.

## Professor comparison after the corrections

The reviewed policy and saved professor-style whole-share policy are reranked on the same **1,729** comparable eligible names. Another 18 ranked names lack a professor-style score. Top100 overlap is **18**, with Spearman correlation **0.7653**. This is descriptive agreement, not prediction accuracy. The earlier workbook/screenshot audit remains applicable; neither cached Excel ranks nor missing screenshot quotes have been treated as a functioning live benchmark.

## Reproduction and outputs

Run these from the project root in order:

```
python research/runners/closing_high_recovery_20261004.py
python research/runners/recover_review_history_20261004.py
python research/runners/build_reviewed_history_20261004.py
python research/runners/build_v17_website_runtime.py
python research/runners/finalize_closing_high_review_20261004.py
```

The history builder requires the retained primary-source Frontier notice in `history-receipts/frontier_bonus_notice.html`; it intentionally refuses to infer the event date from provider prices alone. Network downloads can change over time; the accepted receipt hashes are recorded in `history_build_manifest.json`.

On a clean checkout, first run `build_v17_website_runtime.py` to build the original V17 inference package used by the history builder. Run it again after the reviewed history build to package the verified overlay. Packaging checks the history-build hashes and rejects incomplete or altered overlays.

Artifacts under `experiments/closing-high-recovery-20261004/`:

- `reviewed_top100.csv`: all nine profiles.
- `default_rank_changes.csv`: all 4,436 default-profile identities.
- `professor_common_comparison.csv`: identical-population comparison.
- `paired_historical_metrics.csv` and `profile_tradeoffs.csv`: every period/profile result.
- `history_validation.json`: overlap checks, accepted start dates and action scope.
- `verification.json`: independent score/rank reproduction and population checks.
- `browser_verification.json`, `reviewed-desktop.png`, `reviewed-mobile.png`: rendered UI checks.

The root page and `/closing-high` use the reviewed model. `/personalized` and `/personalized-v17` remain available. Market Refresh does not silently turn this fixed research snapshot into a live model.

## Verification completed

Thirty distinct tests passed across the original Personalized, V17, reviewed Closing High and continuity/evidence checks. This includes saved profiles, custom profiles, routing, cache behavior, SME figure suppression and Frontier's bonus factors. Independent arithmetic reproduces scores and ranks for all nine reviewed profiles. All 396 historical comparison populations match. Desktop and 390px mobile browser checks passed, including search, inspection, financial flags, exclusions, mode switching and a custom Rs8,250 profile. No JavaScript exceptions were observed. `git diff --check` and Python compilation checks passed.
