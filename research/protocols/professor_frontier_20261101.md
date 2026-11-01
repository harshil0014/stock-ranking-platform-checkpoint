# Larger preference frontier: three fixed 75% factor architectures

Frozen before any new labels or candidate performance are inspected. This is a
bounded retrospective preference experiment prompted by the user, not independent
validation. Previous development and exposed periods have already been used.
Production champion and both prospective branches remain unchanged.

Five required blocks: annual-return consistency,3Y CAGR,5Y CAGR, recorded closing
high recency, historical whole-share SIP profit. Use their existing dated sector
percentiles and strict complete-factor eligibility. No neutral imputation. Cohort
requires the dated downside252/volatility252/return21 price inputs for every model,
before target filtering, and >=5 peers. Carry existing factors/normalization intact.

References: champion;20% equal-factor lens;75% arithmetic equal-factor core plus
25% champion. Three challengers, no additional variants:

1. balanced75:75% geometric mean of the five positive percentile blocks,25%
   champion percentile. Equal log elasticities, not literal15% linear weights.
2. outrank75:75% sector peer outranking percentile,25% champion percentile.
   Pair win requires >=3 of5 factors strictly higher and no factor worse by
   >0.40 percentile units. Core is wins minus losses, percentile-normalized within
   sector. Five equal votes, fixed veto; no pair-matrix search.
3. tail75:75% arithmetic equal-factor core plus25% learned forecast percentile
   within sector. LightGBM quantile alpha0.80,100trees,learning_rate0.03,7leaves,
   max_depth3,min_child_samples50,reg_lambda10,random_state20261101,num_threads1,
   deterministic,force_col_wise. Inputs: five factor percentiles plus raw
   downside252,volatility252,return21. Target log1p(next-open12monthSIP XIRR
   clipped[-0.95,3]). Annual expanding fits; label endpoint strictly before
   January1 of prediction year; >=2mature dates and100rows. No tuning or alternate
   tail targets. Core75% is explicit score mass, not causal influence or accuracy.

Generate new stock outcomes using actual provider Open×AdjClose/Close, strict
next-session entry after each30calendar-day contribution,7500contribution,12calendar
months,100bp each buy/terminal sale, idle cash tracked, fractional shares. Existing
corporate-action statuses other than ALIGNED_MULTIPLIER block future holding windows;
missing paths/opens or >7day gaps stay unknown. Do not repair prices by guessing.
New labels differ from legacy same-close outcomes; old outputs remain untouched.
Provider prices, survivor identities and retrospective sectors are not PIT-certified.

Development2020–23 only. Rank IC on the same finite target stocks, >=5/sector.
Top3 selections before outcome availability checks; if any policy's selected name
lacks an outcome, block that sector/date for every policy. Equal sector then date
means. Alignment is mean original five-factor percentiles in selected Top3;
mechanical preference fit is not predictive accuracy. Report changes/overlap.

Also replay actual fixed-selection globalTop20 and equal-sectorTop3 portfolios
at100bp per side, using the same execution engine/guards. No missing selected-stock
replacement. Compare each challenger to champion on matched valid dates.

Wider risk budget fixed now, intentionally more permissive than the old lens gate:
alignment gain>=0.05;IC loss<=0.02;Top3goal-hit loss<=3pp;mean selected-stock drawdown
worsening<=5pp;changed sectorTop3fraction>=0.25. GlobalTop20 matched portfolio
XIRR loss<=3pp and drawdown worsening<=5pp, >=8matched development dates. Other
metrics need >=8dates and >=20matched sectors/date on8dates. Report year splits,
365day block intervals, and familywise centered max-bootstrap hurdle for the
three IC increments (2000 draws); no independent predictive-win claim without
clearing the hurdle and positive IC. Risk-budget pass is only preference candidacy.

Select highest alignment gain among gate passers, deterministic name tie break;
otherwise none. Exposed2024–25 diagnostic only for that locked challenger and
references, once, with no reselection or weight changes. If none pass, do not
evaluate exposed. No daily pipeline/ledger stream or automatic model promotion.
One worker/thread, CPUhardcap12.5%,4sactive/2srest, no GPU. Per-date label checkpoints;
20minute worker watchdog. Local source panels and stock selections remain private;
publish compact aggregate results, protocol/input hashes, failures and tests.

Primary implementation reference:
https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html
