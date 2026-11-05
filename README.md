# Stock Ranking Platform

Local NSE/BSE stock-ranking website and its frozen champion. Research preferences do not replace the deployed champion.

6 November2026. User-authorized **Global Top-20 Champion** is now shown on the sector-champion page for the tested base SIP profile. Its frozen October3snapshot covers2,386stocks in48sectors. [Later-period results and deployment scope](research/reports/rank_correction_transfer_20261106.md) report a+0.91ppTop20SIPXIRR gain versus the normalized research benchmark and a-1.63ppdifference versus the raw-global-score control. Existing sector ranks continue to use the sector model. Current daily input provenance remains incomplete.

[Rank-error correction research](research/reports/champion_rank_correction_20261105.md) improves development globalTop20SIPXIRR while preserving professor-sectorTop3 membership. Concentration,raw-champion and randomized-tie controls are reported. The separate [locked historical transfer test](research/reports/champion_open_search_20261105.md) records a loss for the earlier risk-constrained candidate. These results remain research evidence.

Latest search, 5 November 2026: [new residual-history challengers](research/reports/residual_challengers_20261105.md). The residual-momentum overlay improved development IC in four years and matched Top20 returns, but fell short of the preregistered accuracy and professor-alignment requirements. [Search history](research/registry/research_search_history_20261105.md) records prior families to exclude from future reruns.

[Constrained Top3 selection](research/reports/constrained_ranking_20261105.md) subsequently protected all five professor-factor averages while improving development IC and Top20 SIP returns. Small goal-hit losses missed the strict nomination rule. [Commercial comparison access review](research/reports/commercial_benchmark_access_20261105.md) covers Trendlyne, Tickertape, MarketsMojo and Stockopedia, with matched score-history access still required for a numerical head-to-head claim.

## Run locally

```powershell
.\.venv\Scripts\python.exe -m stock_ranker.webapp --port 8765
```

Open http://127.0.0.1:8765. Existing data, model packages and local configuration are required; large runtime assets are not all stored in Git. See [runtime and product documentation](docs/).

## Active code

- `src/stock_ranker/`: website, ranking services and data contracts.
- `src/stock_research/`: shared research and validation utilities used by supported commands.
- `tests/`: application tests and retained research checks.
- `research/runtime/`: frozen model packages and manifests. Do not substitute experimental weights.
- `research/runners/prospective_ledger_20261031.py`: append-only daily observations, published to a separate branch.

Some retained folders under `experiments/` supply runtime inputs, regression fixtures or reproducibility dependencies. Their directory name does not mean the associated model is deployed.

## Retained preference experiment

[20% high-recency tilt](research/reports/high_recency_tilt_20261101.md) achieved stronger alignment with days since the recorded high, with weaker predictive accuracy. [User decision](research/reports/high_recency_tilt_disposition_20261101.md): retain it as a successful preference experiment only; do not implement it on the website. Its October 3 snapshot is stale and its inherited five-year eligibility excludes some stocks, including Nykaa.

The earlier [20% professor-factor lens](research/reports/professor_preference_model_20261031.md) is also research-only. Neither is a validated investment improvement.

## Prospective ledger

[Prospective records](https://github.com/harshil0014/stock-ranking-platform-checkpoint/tree/prospective-ledger) preserve timestamps, hashes and source coverage. The frozen October 3 scores remain ineligible for a fresh holdout until a complete daily input pipeline is verified. Never rewrite the ledger or backfill forecasts.

## Historical research

Obsolete standalone experiments and reports were removed from the active checkout. The complete pre-cleanup source and tracked evidence remain at [research-archive-before-cleanup-20261101](https://github.com/harshil0014/stock-ranking-platform-checkpoint/tree/research-archive-before-cleanup-20261101). This archive includes failed trials; their removal is housekeeping, not evidence that all tested models succeeded.

[Cleanup record](docs/codebase_cleanup_20261101.md) lists scope and verification. The cumulative research-attempt ledger is retained for research accountability; historical paths can be resolved against the archive tag.

## Local validation

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m pytest -q
```

For CPU-heavy local checks, use the existing low-load governor: one worker/thread, 12.5% CPU cap, four seconds active and two seconds rest. Do not launch concurrent research queues.
