# Stock Ranking Platform

Local NSE/BSE stock-ranking website and its frozen champion. Research preferences do not replace the deployed champion.

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
