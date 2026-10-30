# Sector price-activity review — 10 October 2026

The all-stock structural review identified KALYANI at sector rank 1 in the rebuilt candidate, with **99.6% zero daily price changes** across 252 observations. Its inherited volume-active fraction is also about 0.4%. The inherited `HIGH` evidence label does not certify tradability; the export therefore distinguishes anchor evidence from rebuilt input status and provides separate review flags.

The issuer's [2024–2025 annual report](https://www.kalyanicommercials.com/files/annual-reports/KC_AR_2024-25.pdf) describes commercial-vehicle and petroleum-dealership activities. This supports the business classification; it does not establish trading liquidity.

## Fixed follow-up experiment

Before measuring the follow-up, the rule was fixed: with at least 63 observations and more than 80% zero changes, subtract one from the original score. This preserves coverage and ordering within each tier while moving flagged stocks below unflagged stocks. No threshold search was performed. This is a price-activity proxy, not a verified execution model.

- All 4,436 current stocks remain ranked; 13 receive the activity flag.
- Against the parent candidate, 224 metric cells improve and 362 regress out of 1,296; the rest are unchanged within numerical tolerance.
- On the expanded universe in 2024–2025, capped Top-3 XIRR changes from −0.22% to −0.54%, and whole-sector rank IC from 0.1521 to 0.1187.
- On the production-common universe in that period, the aggregate Top-3 results are unchanged.

The rule is retained as an explicitly separate experiment. It has not been accepted as an accuracy improvement or applied to the live ranking. The all-stock export retains the diagnostic flags, so a high score cannot hide the observed flat-price problem.

The data show a conflict between execution plausibility and the current historical outcome objective: a nearly constant quoted price may score better than a falling, actively changing stock. This does not establish that the quoted flat-price return could have been earned. A clean investable ranking still requires reliable historical trading eligibility and execution evidence; zero price changes alone do not prove that a stock was untradeable.

## Artifacts

- `experiments/sector-activity-guard-20261010/protocol.json`
- `experiments/sector-activity-guard-20261010/summary.csv`
- `experiments/sector-activity-guard-20261010/directional_deltas.csv`
- `experiments/sector-activity-guard-20261010/current_all_stock_rankings.csv`
- `experiments/sector-price-rebuild-20261010/all_stock_structural_review.csv`

These are exposed historical research results, not fresh validation. The stock-specific observation generated the hypothesis and is disclosed as such.
