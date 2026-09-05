# Larger-evaluation readiness boundary

The platform now has a strict, source-neutral point-in-time liquidity contract
for official daily exchange observations: exact ticker/ISIN/exchange identity,
trade date, real availability date, close, volume, traded value, trade count,
and source. It can produce trailing observation counts, average volume, median
traded value, average trade count, and zero-trade days at a ranking cutoff while
excluding evidence not yet available at that cutoff.

This is deliberately **not** a transaction-cost or portfolio model. It does not
estimate slippage, impact, fees, turnover, holdings, returns, or capacity. Those
assumptions must be preregistered before inspecting a broader evaluation and
must distinguish statutory charges from empirical market impact. A partial
20-day history remains `PARTIAL_WINDOW`; it is never padded or imputed.

The historical annual-report readiness matrix in
[`pit_fundamental_scale.md`](pit_fundamental_scale.md) shows where larger
point-in-time cohorts can be built from explicit exchange timestamps and where
an exact official announcement rescue is still required. This preparation does
not recalculate or overwrite the four-date frozen walk-forward experiment.
