# Frozen delivery implementation detail, before fitting

All 44 historical decision dates in the existing price-feature panel, 2016–2025.
Use the last RELIANCE.NS observed exchange session strictly before each date for
official delivery and same-session bhavcopy ISIN identity joins. This is a
conservative one-session lag proxy; archive publication vintages remain unknown.
NSE EQ only; no BSE coverage claim. Current-survivor identities remain a limit.

Control: return21/63/126/252, volatility252, downside252, log(1+traded quantity),
log(1+turnover). Challenger adds delivery percentage and its interaction with
return21. Each feature becomes its same-date global percentile minus0.5. Targets
are actual next-open to the 21st observed session close, 25bp each side. No
missing selected open substitution. Annual expanding-window Ridge alpha10;
training labels must end strictly before January1 of prediction year, minimum
three prior dates. No intercept-derived date information enters ranking. No
hyperparameter, source-date, or feature search. Minimum500 complete stocks per
evaluated date. Development2020–23 must have8dates, exposed2024–25 at least4.

Compare mean per-date cross-sectional Spearman IC on identical stock rows; show
champion on the same rows as a diagnostic of the changed target. First inspect
development only; if it fails the floor0.0101349 or paired365day95% centered
block-bootstrap hurdle, kill the challenger without opening exposed performance.
One candidate, 2000 fixed-seed bootstrap repetitions. Acquisition coverage is
reported independently from whether a candidate wins. No production promotion.
