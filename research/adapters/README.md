# Adapter boundary

Adapter implementations live in `src/stock_research/adapters.py` so they are
available through the installed lightweight package.

- Research V2 is identified as `research_v2_baseline`, never as ML.
- Qlib predictions are converted without importing Qlib.
- CSV and pandas Series/DataFrames are supported.
- Pickle is rejected unless the caller explicitly accepts unsafe trusted input.
- Instrument mapping is mandatory; dropped unmapped instruments require an
  explicit opt-in and a report.
