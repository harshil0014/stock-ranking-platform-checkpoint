# Local market-data refresh

The localhost website exposes **Refresh Market Data** for a controlled background
run of the existing `marketdata/runners/refresh_company_data.py` pipeline.  A
page request never fetches market data: the button returns immediately, the UI
polls `GET /api/live/refresh-status`, and the existing accepted snapshot remains
the last-known-good state until a complete replacement has been validated.

The runner records its user-facing state and terminal output under the ignored
`data/live_market/` directory.  It checks the current accepted market state,
refreshes the permitted exchange and secondary sources, updates bounded BSE
history with date-level deduplication, then rebuilds company facts.  Provider
failures are reported explicitly; they cannot overwrite an accepted state.  A
second refresh request is rejected while a process is active.

This control changes no scoring formula, research protocol, or frozen
historical evidence.  It is a local maintenance action, not a promise of
intraday or real-time data.
