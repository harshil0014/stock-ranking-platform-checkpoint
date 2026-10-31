# Champion versus market alternatives

Indian NSE/BSE research only. The serving model and app are unchanged. Read the completed report and literature review under `research/reports/` for conclusions and limits; machine-readable scorecards retain every compared policy.

## Interpretation

- `full/sector_summary.csv`: individual-stock ranking metrics, equal date then sector/profile queries. `global_summary.csv` is a different cross-sectional question.
- `sequence/`: the same stock population for every comparator, bounded by the original outcome-independent512-issuer OHLCV sample. Six original MIT network implementations are adaptations trained from scratch, with same-input Ridge/LightGBM controls; overseas paper results are not reproduced.
- `development_lock.json` records selection before exposed metric computation. `familywise_bounds.csv` uses paired query differences aggregated by date. Undefined constant-score IC is missing; per-model metric support is retained. A block longer than available history is unavailable rather than zero uncertainty.
- Goal attainment, selected-stock median XIRR and mean selected-asset drawdown are not combined-portfolio results. Cross-asset tails are not time-series portfolio CVaR. NDCG uses future-XIRR percentile as linear relevance gain and log2 discounts.
- `portfolio_paired_comparisons.csv`: complete-feature selections, actual fractional SIP cashflows and daily path risk; paired valid dates and counts. Base7500, fixed forward12-month globalTop20 or sectorTop3/equal-sector capital. Current survivors/provider adjusted prices limit all results. A missing selected path or unresolved corporate action blocks the whole observation.
- Official NSE gross TRI histories are theoretical investment comparators. BSE500 is price-only, explicitly not TRI. Live-history-only and prelaunch-backfilled results are separated. Costs of0/10/25/50bps per buy and final sale are scenarios, not calibrated tax/market-impact estimates or actual fund NAVs.
- Calibration is fixed prequential logistic calibration from earlier out-of-time scores with mature outcomes only, compared with matched past climatology. The first dates without sufficient mature calibration support are missing. Rankings are not probabilities.
- Stability and personalization use the complete feature cohort, without removing stocks based on future label availability. Snapshot churn is not daily champion validation. Market regimes use trailing252-session Nifty500 TRI returns with fixed minus/plus10% thresholds. Liquidity uses past traded-value thirds; trading activity uses past zero-return-day fraction. These are proxies, not PIT market capitalization or impact-capacity certification.
- `fit_registry.csv`, `runtime_summary.csv`, source-code receipts, environments and acquisition hashes support auditing. Shared-machine wall time is not a normalized speed benchmark. Three seeds are used for stochastic families; deterministic fits are not falsely counted three times.

## Reproduction

This is an evidence checkpoint, not a self-contained redistributable raw-market database. The full original SIP panel, price features, original saved champion/overlay histories and recovered OHLCV batches must be present at their documented paths. Large panels, checkpoints and vendor datasets remain local. Acquisition runners download public official index/factor inputs when those endpoints are available; historical provider responses may be revised. Hashes identify the actual source snapshots.

Use the recorded `tabular_environment.json` and `sequence_environment.json` versions. The tabular runner can import CatBoost/XGBoost from the existing local dependency directory or a normally installed environment. The neural runner requires PyTorch and preferably CUDA. Pinned author class files and both MIT licences are bundled under `research/literature/20261031/code`; they retain original bytes, including upstream whitespace.

From the repository root, using the appropriate Python environment:

1. Run `champion_market_common_20261031.py` to construct source and guarded-label panels.
2. Run `market_index_acquisition_20261031.py`, `champion_market_external_data_20261031.py` and `champion_market_indices_20261031.py` for official indices and actual forward index SIP cashflows.
3. Run `champion_market_tabular_20261031.py ALGORITHM` for every algorithm in the protocol. Fit receipts make completed annual objectives resumable. Local `.external_job_lease` markers are orchestration state and should not be copied into a new run.
4. Run `champion_market_sequence_20261031.py ARCHITECTURE` for gru, alstm, transformer, gats, hist and master in the PyTorch environment. Run `champion_market_sequence_controls_20261031.py` for matched inputs.
5. Run `champion_market_inference_20261031.py` after all tabular fits. It replays saved models on the full feature cohort and checks original valid-row prediction agreement within float32 tolerance.
6. Run `champion_market_evaluate_20261031.py full` and `sequence`, then `champion_market_review_20261031.py` for both tiers. Do not tune against the already exposed period.
7. Run `champion_market_portfolio_20261031.py`, `champion_market_validate_20261031.py`, `champion_market_publish_20261031.py` and `champion_market_plots_20261031.py`. Plots use the separate local plotting dependencies if needed.
8. Run the date-stamped research tests. External CI and production E2E are not claimed by these local research checks.

All runner paths above are under `research/runners/`. The original JSON preregistration and its implementation supplement are under `research/protocols/`. Large raw per-row prediction/query files can be regenerated from the local caches; aggregate results and exact source/audit hashes are the public review surface.

Commercial platforms without reconstructable historical scores remain untested. Current scores or unrelated advertised backtest CAGRs must never be backcast into this tournament. No surviving-stock retrospective result establishes superiority over every Indian ranker.
