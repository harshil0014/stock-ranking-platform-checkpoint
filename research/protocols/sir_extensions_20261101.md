# Fixed extensions and concentration audit, before scoring

Parent326a0643. Exploratory reuse of development; earlier failures mean not
confirmed under their gates, not general refutation. Exposed2024–25 is unopened
for every test here. No production or prospective-ledger changes.

Audit first: reproduce the tail75 versus champion globalTop20 portfolio XIRR
delta on the exact14matched2020–23dates. Date-level median,10%per-tail winsorized
mean (floor(n*.1) observations per tail), every leave-one-date-out mean. Individual
stock attribution uses additive TERMINAL WEALTH differences, not additive XIRRs.
From the corrected single-stock XIRR and original deposit schedule reconstruct
terminal wealth, verify weighted-stock totals reproduce both portfolio XIRRs.
Report best-date share of net sum of XIRR deltas; best-stock share of net terminal
wealth difference. Net shares can exceed100%when other contributions are negative.
Replace each security's allocations with idle cash in both strategies, no refill,
and report worst leave-one-security-out mean XIRR increment. Positive median,
winsorized, all date-out and all stock-out means are a concentration screen only.

Count shots: persistent main-branch registry records scoped named configurations
from preserved trial/policy registries plus this round before performance. Fold
fits/seeds are not independent strategies. Cross-round aliases and repeated tests
are conservatively retained as evaluation attempts. Report documented count, known
overlap, omissions, and incomplete older history; never call it exhaustive. Nominal
centered365day block-bootstrap p-values use2000draws,seed20261101. Multiply p by the
documented attempt count (Bonferroni capped1), explicitly a correction within an
incomplete documented history, not a certified global significance level.

1. Goal profiles: frozen tail75 order versus saved profile-specific champion order
on the same feature universe, globalTop20 chosen BEFORE outcome filtering. Any
unknown selected outcome blocks the date for both. Primary corrected12month,
100bp-per-side labels apply only to target10/base7500/target30, which share amount,
schedule and lookback. High-target pass requires mean target30hit increment>0 in
at least2of2021/22/23, >=2valid dates/year, positive pooled increment. target10
direction diagnostic;2020context. Saved nine-profile XIRRs are an explicitly
legacy-same-close cross-profile transfer diagnostic only; do not silently reuse
base7500corrected labels as weekly/quarterly or whole-share amount outcomes.
No new rank personalization is proven merely by changing the goal threshold.

2. Dose response: original equal-weight five-block arithmetic core, global
feature-cohort deciles per date with deterministic ISIN ties BEFORE labels. Show
new corrected12monthSIP XIRR and cashflow-adjusted stock drawdown by decile. Fixed
contrast only: deciles6–9 versus10 AND versus1–5, with drawdown no worse than10.
Require both return contrasts positive and drawdown condition in>=2of2021/22/23,
positive pooled contrasts;2020context. No best-band search after plotting. Count
the two fixed contrasts, and disclose that wider shape inspection is exploratory.

3. Gate: CAGR3>=10%,CAGR5>=10%, recorded closing high within365days. Keep champion
order inside passers. Full-universe diagnostic puts passers ahead of nonpassers
without changing either internal order (pass=.5+.5champion_percentile,fail=.5champion).
This tests gate-first IC on the SAME universe; conditional order inside the gate
is identical by construction. Actual investments use globalTop20passers, >=20
eligible names/date. Compare corrected100bp portfolios, no missing-name refill.
Pass: mean full-universe IC loss<=.01 and matched globalTop20portfolio drawdown
strictly improves, >=8matched dates. Report sectorTop3stock drawdown separately.

4. User-approved proxy, NOT a daily-reset ladder: frozen split-adjusted recorded
ATH at entry; close triggers at-10/-15/-20/-25/-30/-35/-40%, allotments
10/5/20/10/30/15/10%of principal, each once. Already-below levels queue at entry,
all orders execute at strictly following observed open, costs100bp per side.
No stop-loss/reset; unspent cash retained. Capital90000available upfront atD for
both policies; comparator deploys12equal real-calendar-month installments, first
at the open afterD. Horizon12calendar months. Cash earns0%or a fixed4%annual
scenario, compounded by actual days;4%is NOT an observed historical liquid-fund
return. Price-only provider Open/Close proxy, fractional units; dividends/tax
omitted symmetrically. Gated champion Top20as in#3, same stocks/dates/capital for
both. Actions not ALIGNED_MULTIPLIER in(D,end] block both whole portfolios; gaps
>7days or zero-volume execution are unknown, never cash/no-fill successes.
Remove the lowest ADV20quintile without replacing names; its weight remains cash
in BOTH policies. ADV20uses prior20observed sessions strictly beforeD, quintiles
on full feature universe. Budget-level XIRR includes all original capital. Report
deployment, no-fill share and >=5tranches-filled-and-ending-below-cost share.
Pass: positive ladder-minus-SIP mean overall and in EACH2020/21/22/23year for
both cash scenarios and liquidity scopes, >=2valid dates/year; positive10%date
winsorized and every leave-one-date-out mean; portfolio drawdown not worse.

5. ATH break count: count STRICT new recorded lifetime closing highs in the last
365calendar days, excluding the first history observation, tolerance1e-10. Use
only split-adjusted provider closes throughD; no lifetime-high lookup from later
dates. Old high_hits is a different rolling-window record fraction and is already
in the price head. Fixed Ridge alpha10baseline: five professor percentiles,
downside252/volatility252/return21, recorded-high proximity/recency, old high_hits.
Each extra raw feature becomes same-date/sector percentile. Add only ATHcount
percentile. Annual2020–23expanding fits, labels mature beforeJanuary1,>=2dates,
100rows. Target log1p(corrected SIP XIRR clipped[-.95,3]). Common support. Require
mean IC increment>max(.01013492400721767, paired365day95%centered noise hurdle)
and positive increment in at least2of2021/22/23. Documented-shot correction also
reported; no independent predictive-win claim from a nominal pass.

No threshold, band, cost, year, or feature search. Twelve-month proxy observations
overlap; current-survivor identities, retrospective sectors, price vintages and
missing terminal proceeds remain limitations. One worker/compute thread,CPUcap
12.5%,4seconds active/2seconds rest,no GPU,20minute stage watchdogs. Preserve
checkpoints, source hashes, errors, and untouched exposed summaries. Raw stock
selections remain local; publish aggregate evidence and reviewed plots only.
