# Official BSE historical-price acquisition

This isolated Windows utility downloads official BSE daily-price CSVs for the exact six-digit codes already present in `Downloads\BSE_2025_2026`. It does not change ranking inputs or accepted product snapshots.

The utility uses one visible Microsoft Edge worker. BSE currently rejects a headless browser. It selects the official Equity T+1 and Daily form controls, captures the footer CSV request, and reads the response through the same Playwright browser session. The CSV endpoint never replaces the Stock Prices tab.

Progress is written after every attempt to `Downloads\BSE_History\bse_history_progress.json` and `bse_history_progress.csv`. Successful and `NO_RECORD` tasks are skipped on restart. A task receives at most three attempts.

Setup is isolated from the product environment:

```bat
py -3.13 -m venv .venv-bse
.venv-bse\Scripts\python.exe -m pip install -r marketdata\environment\requirements-bse-history-playwright.txt
```

Full start or resume command:

```bat
.venv-bse\Scripts\python.exe marketdata\runners\download_bse_history_playwright.py --mode full
```

Keep the visible Edge window open. The utility validates that responses are delimited data rather than HTML and rejects codes or dates inconsistent with the requested task.
