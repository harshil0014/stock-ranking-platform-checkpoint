# Residual-history challengers, 5 November 2026

Frozen before computing residual features or challenger outcomes. User asks for a new champion that respects the professor framework and excludes repeats.

## Prior-search exclusion

Read 146 archived report/protocol paths and scanned all archived Python runners for residual-momentum and monotonic-model implementations. Monotonic learning, raw recency sweeps, positive Ridge, generic momentum, trend continuity, volatility scaling, peer correlations, recovery, goal/tail heads and ladder variants have already been tried. They are excluded. Archive scan receipts and full search text stay in ignored work. Existing partial variant registry has 303 attempts and is incomplete. No exhaustive claim about absent informal trials.

New hypothesis is regression residual momentum and residual-path high age. Earlier sector reports explicitly distinguish their sector percentiles from regression residual momentum. Inspired by Blitz, Huij and Martens (2011), https://doi.org/10.1016/j.jempfin.2011.01.003. Our adaptation uses leave-one-out equal-weight market and sector returns instead of Fama-French factors. This is a new feature test using existing data, not an exact paper replication. Scite search and GitHub repository inspection support method selection. No third-party code is copied.

## Fixed features

For every development/training feature date through 2023, use 157 weekly price anchors spaced seven calendar days ending at decision date. Each anchor uses the most recent observed positive adjusted close, at most seven days old. Weekly log returns are bounded by observed endpoints, missing values stay missing. Require at least 130 of 156 returns, all last 48 returns, at least five contributing sector stocks at each used return and 20 market stocks. Market and sector means exclude the target stock. Fit stock log returns on an intercept and those two reference returns over the available 156 weeks. The residual momentum signal sums the 48 weeks before the last four weeks, divided by their standard deviation times sqrt(48). Residual high age is negative weeks since the most recent maximum cumulative residual over the last 48 weeks. Any historical feature calculation slices paths at as-of before sampling. These reference baskets use the saved feature-date eligible cohort and retrospective sector classifications. Survivorship and sector availability remain limitations.

Normalize signals and the existing five professor blocks within each date/sector common feature cohort before checking labels. Recompute champion percentile on the same cohort. Minimum five stocks per sector. Base corrected panel uses five-factor eligibility, including full five-year history, so results do not cover younger listings. Do not infer all-4436 coverage.

Three fixed policies, no model training or parameter grid

1. residual_momentum20 = 80% champion percentile + 20% residual-momentum percentile.
2. professor_residual50 = 30% champion + 50% equal five-factor professor core + 20% residual momentum.
3. residual_high20 = 80% champion + 20% residual-path high-recency percentile.

Professor core blocks are annual consistency, CAGR3, CAGR5, raw recorded-high recency and historical SIP profit. Only policy2 guarantees 50% explicit professor score mass. Others test new information as champion overlays and must disclose professor alignment changes. No claim that score coefficients are causal feature importance or professor-prescribed weights.

## Evaluation and lock

Only development 2020-2023, sixteen quarterly snapshots, corrected twelve-month next-open SIP labels,100bp per side. Select stocks before outcomes. Unknown selected outcomes and unresolved actions block matched comparisons. Portfolio replay reuses actual adjusted opens. Compare globalTop20 and sectorTop3, date-balanced rankIC, goal20 attainment, drawdown, five-factor and raw-high alignment, annual results, Top3 membership and support. Existing replay routines imported from archive in ignored work, never restore obsolete folders to active tree.

Candidate must gain >=0.010134924 rankIC over matched champion, improve IC in >=3of4 years, professor core and raw-high Top3 alignment must not worsen, goal hit must not fall, portfolio XIRR must improve with nonnegative 10% winsor mean and all leave-one-date-out means, drawdown worsening <=2pp, at least12 matched Top20 dates and12 supported Top3 dates. Familywise365day block bootstrap2000 draws across three challenger IC differences must also clear95% hurdle. No relaxing limits or adding candidates after results. No exposed-period evaluation this round even if development passes. A passing candidate earns a development nomination only, pending independent testing and input-pipeline certification. Website and prospective streams remain under prior user decision.

## Operational checks

One worker/thread,12.5%WindowsCPUcap,4sactive/2srest,CPUonly. Save input/protocol hashes, source code hashes, feature coverage and a development-only scored checkpoint. Verify prefix invariance, leave-one-out means, idiosyncratic signal behavior, finite outputs and reproducible metrics. Append three attempts before evaluation. Preserve existing prospective records and registry IDs. Publish compact aggregate evidence and report. No public individual-stock picks.
