# Reproduce V17

Completed experiment: reproduce training in a separate checkout/output root; do not overwrite locks. Python3.13, numpy/pandas/lightgbm and CPU PyTorch.

From repository root, run the research runner with stages in this order:

```text
prepare
round1
round2
robustness
development_diagnostics
historical_behavior
round3
round4
round5
lock_final
final_pass
final_robustness
development_diagnostics
inference_diagnostics
report
audit
```

Example: `python research/runners/personalized_v17_20261003.py round1`. Each search round writes an exclusive protocol before evaluation. Round1 has24 configurations, round2 nine, round3 two, round4 three, round5 one; total39. No exposed/current results select candidates.

For inference only with completed models:

```powershell
python research/runners/personalized_v17_20261003.py score_current_replay
```

This writes reproduced_current_scores.csv.gz using the immutable V15 current V7 replay and the four final trained correction files. It is research inference, not a data acquisition or production deployment command. The input must retain the same per-date/profile universe for percentile normalization. model_definition.json records exact features, formula, and hashes.

Historical annual fitting uses labels with endpoint strictly before the first scored decision date of each year. The lookback60 specialist adds ATH constraints;12/36 use the raw specialist. Monotone regression is pooled across profiles with query-normalized weights. No ISIN, ticker, source, current fundamental, or sector predictor is used. All raw fields and observed confidence come from the frozen dated replay.

Read decision.json/report for caveats. Frozen dependencies V15/V16 must remain available; their runners are read-only imports. Never call their writing stages. Current post-September18 corporate-action completeness remains conditional.
