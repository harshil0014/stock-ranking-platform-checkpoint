# Professor and competition research demo

## Launch

From the repository root, with the product environment installed:

```powershell
.\.venv\Scripts\python.exe -m stock_ranker.webapp --port 8765
```

Open `http://127.0.0.1:8765/overview`. The server binds only to localhost and normal navigation performs no NSE or Yahoo request.

## Required prepared artifacts

The current rankings require the accepted ignored Baseline and Research V2 bundles under `data/marketdata/`. Historical and validation views require:

- `data/walk_forward/blind_predictions_v1_run_01`
- `data/walk_forward/evaluation_v1_run_01`

The website validates their protocol, amendment, blind, evaluation, per-date manifest, and artifact-inventory identities before presenting them as canonical. If a required artifact is absent or mismatched, the affected view displays a controlled unavailable/integrity state. It never substitutes synthetic values.

## Recommended demonstration sequence

1. **Overview:** distinguish original-paper signals, the Baseline V1 project operationalization, and the Research V2 extension. Point out that the primary historical sample is only three sector-date observations.
2. **Rankings:** switch between current Baseline V1 and Research V2. Filter a sector, search by ticker/company, retain exclusions, and explain that scores are sector-relative.
3. **Stock explanation:** inspect HINDUNILVR. Show all nine accepted factor values, directions, weights, component scores, and contributions. Nothing is recalculated in the browser.
4. **Historical:** select 2022–2025. Emphasize “WHAT THE MODEL KNEW THEN” and the cutoff timestamp. Outcome fields are not included in the prediction table.
5. **Validation:** read the 12-month preregistered result first, including the `n=3` warning and exact sector observations. Then discuss 6- and 3-month secondary Rank IC, pairwise, top-stock excess, and top/bottom diagnostics. These are not a trading backtest.
6. **Provenance:** load HINDUNILVR evidence. Show the NSE audited standalone report identity, dissemination metadata, PDF hash, disclosure pages, issuer formulas, and reported PAT values.
7. **Methodology:** walk through paper → Baseline → V2 → point-in-time reconstruction → frozen predictions → reveal → evaluation → robustness. Show the fixed nine-factor weights and standalone contract.
8. **Status:** show the accepted 324-test robustness milestone, byte-identical reproductions, frozen cohorts, integrity fingerprints, and visible limitations.

## What each view demonstrates

- **Overview:** research question and model boundaries.
- **Rankings / explanation:** explainability and explicit eligibility.
- **Historical:** point-in-time reconstruction and outcome blindness.
- **Validation:** preregistered, horizon-dependent evidence with no promotional conclusion.
- **Provenance:** traceability to source disclosures.
- **Methodology:** distinction between cited signals and project extensions.
- **Status:** deterministic reproduction and fail-closed robustness.

## Known limitations

Only four annual ranking dates and three primary sector-date observations are available. Strict point-in-time filing availability reduced Research V2 coverage. Yahoo adjusted-price history is retrospectively acquired and retains vendor-data risk. The evaluation measures ranking quality, not portfolio profitability; it includes no transaction-cost, liquidity, or execution model. Fixed weights are research choices, not proven optima. The website is a local research presentation surface, not an investment or live-trading application.
