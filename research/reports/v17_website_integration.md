# Personalized V17 website integration

Implemented in the original Python website on branch `main`.

## Open

Run from the repository in PowerShell:

```powershell
$env:PYTHONPATH='src'
python -m stock_ranker.webapp --port 8765 --no-auto-refresh
```

Visit http://127.0.0.1:8765/personalized-v17 or select **Personalized V17** in the main navigation, ranking mode dropdowns, or personalized form. Baseline and the original d499580 Personalized option retain their own routes and scoring.

## Included

- Same amount, lookback, SIP interval, target CAGR and investment-horizon inputs as Personalized.
- V17 **refined** scoring, including the separate 12-, 36- and 60-month architectures.
- Global ranks across the eligible full V7 universe, sector positions, ticker/company/ISIN/exchange-code search and stock inspection.
- Stock details show ATH distance, days since ATH, underwater duration, evidence confidence, historical XIRR, target attainment and execution/cash statistics.
- All 4,436 identities remain visible. Default profile: 3,293 ranked and 1,143 explicitly unavailable. Missing sector classifications display as Unclassified without changing model scores.
- Mode changes discard stale results and invalidate in-flight responses from the previously selected model.
- Saved research profiles use exact published scores. Other valid profiles recalculate whole-share execution and goal windows, then apply the frozen models with the original empirical-CDF anchors. No training occurs in the website.

## Runtime package

`research/runtime/personalized-v17` contains copied model files, research snapshots, V7 company metadata, a safe NumPy history pack and a SHA-256 manifest checked on service initialization. It is local runtime data and is excluded from Git by the existing repository policy. Copy this entire package with the application when preparing another environment, or rebuild it where the original research evidence exists:

```powershell
python research/runners/build_v17_website_runtime.py
```

`STOCK_RANKER_V17_RUNTIME` can override the package path. The website never imports the research runners or overwrites research artifacts. The packaging runner redirects its evidence receipt into the new package directory.

The data snapshot is **3 October 2026**, with the research action check through **4 October 2026**. Market Refresh does not silently update this model's evidence. Custom inputs recalculate against this dated snapshot. In local verification, uncached full-universe custom execution took about 29 seconds; repeated profile requests are cached. A missing or altered package produces an explicit unavailable response instead of substituting the original model.

## Verification

`python -m pytest tests/test_personalized_v17_product.py tests/test_personalized_product.py -q -p no:cacheprovider`

Result: **22 passed**. Checks include all nine saved profiles, all model routes, score reproduction below 1e-9 absolute error, full execution replay of the default profile, custom inputs, cache behavior, identity resolution, unavailable rows, sector/global consistency and separate HTTP routing.

Headless Edge browser checks verified direct V17 navigation, running the default plan, MWL at global #1, NYKAA at global #4, stock details, mode switching, back navigation and a 390px mobile layout. No JavaScript errors. Screenshots are in `research/runtime/v17-website-desktop.png` and `research/runtime/v17-website-mobile.png`.

This change adds a selectable website model; it does not replace d499580, retrain V17, or publish a remote deployment.
