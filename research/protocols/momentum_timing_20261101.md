# One shot: professor preference selection plus dip timing

Frozen before scoring this experiment. Research only; no production promotion or
changes to the champion, 20% lens, or prospective ledger. The prior 21-session
control IC motivated this hypothesis, so development is exploratory reuse, not
independent validation. Exposed data is also already exposed in the wider project.

Selection: use the existing factor20_fixed scores, with their unchanged 80%
champion /20% five-factor core. Global top quartile of all complete-factor eligible
NSE/BSE identities per date, deterministic score-descending/ISIN-ascending order;
take ceil(n/4). Then join the existing official NSE delivery/ISIN panel; do not
re-rank after the join. This pilot therefore covers NSE EQ only, not BSE.

Dip: latest adjusted close on/before D divided by highest recorded adjusted close
available through D, minus1, <=-0.10. This is a recorded closing-high proxy, not an
intraday ATH or a complete IPO-to-date certificate. No upper40% dip restriction.

Timing: reconstruct only the prior fixed price/volume control, Ridge(alpha10),
same eight globally normalized features and original training support. Expanding
annual training with label end strictly before January1, >=3training dates. Within
the selected dip stocks, retain the top score quartile (ceil(n/4), same tie rule).
No alternative thresholds, weighting, features, tuning or retesting after failure.

Execution: actual next observed open strictly after D; sell at21st observed session
close including entry session. Maximum7day entry/holding gaps. Block unresolved
official/provider action windows in(D,exit]. Equal-weight stock returns, equal-weight
matched dates; fixed21-session holding, not a deployed SIP ladder simulation.

Cost stresses:75and100bp per buy and sell. Compare dip vs non-dip and overlay vs
all dip on identical dates. Also require positive absolute dip and overlay net
returns versus cash. Equal-cost fixed-horizon return differences only scale with
cost, so a positive incremental difference alone cannot pass the friction test.

Liquidity: prior20observed sessions strictly before D, average provider Close ×
Volume; complete positive price/finite nonnegative volume, no >7day gaps. Quintiles
are computed before the top-quartile selection on the mapped NSE source support.
Freeze all memberships, then repeat comparisons excluding the lowest quintile.
This is a provider turnover proxy, not certified historical executable capacity.

Development2021–23: minimum20dip and20non-dip,5overlay stocks/date; minimum8matched
dates and2/year. Ex-lowest-quintile: min10/10/3stocks,8dates and2/year. Insufficient
support is INCONCLUSIVE, not a pass. Kill if either incremental edge is <=0 overall
or in any development year, at either cost, on full or ex-lowest-quintile support;
also kill if absolute dip or overlay net return <=0. Report365day block-bootstrap
95% intervals (2000repetitions, seed20261101); three years are weak evidence.

If development fails, stop without exposed performance. If and only if it passes,
run the same locked test once on2024–25 (>=4dates total,2/year), report diagnostic
results with the same sign/cost/liquidity checks. No fresh-holdout or causality claim.
Keep selected security identities local; publish aggregate evidence, hashes and
all support failures. CPUcap12.5%, one compute thread/worker,4s active/2s rest.
