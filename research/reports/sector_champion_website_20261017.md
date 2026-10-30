# User-selected recency champion: website integration

## Active choice

The user explicitly selected the original full-coverage champion plus `dual_w0.01`, accepting its slight historical degradation. This is not the later continuity/risk experiment. Research results and rejection decisions remain intact as evidence; adoption is an explicit user preference override.

Formula: `0.75 × (0.8 × open_model + 0.2 × profile_defensive_15) + 0.25 × rank_xendcg_balanced + 0.01 × (0.60 × dual_recency + 0.25 × dual_proximity + 0.15 × momentum − 0.5)`.

The added recency coefficient is 0.006. “60% recency” describes the added signal, not total-model importance. Recorded high means available-history maximum, not independently certified lifetime ATH. Missing/illiquid/short-history inputs retain zero recency adjustment under the tested eligibility rules.

## Website

- New route `/sector-champion`; metadata and ranking endpoints `/api/sector-champion/metadata` and `/api/sector-champion/rank`.
- Sector Champion is the default landing view and appears in the existing model selectors. Previous Closing High, Personalized and Personalized V17 routes remain available.
- Existing amount, lookback, SIP interval, target return and horizon fields and validation domains are preserved. Search, sector filtering and stock detail views use the existing interface.
- Frozen model inputs and saved LightGBM models are packaged under `research/runtime/sector-champion-recency`. Serving does not import research runners or train models. Every package file is SHA256 checked before inference.
- The accepted snapshot is 3 October 2026. All 4,436 stocks have finite scores; 133 have limited-price-evidence fallback scores. Ranking availability is kept separate from execution availability. Equal scores share sector ranks. Unclassified is a display group.

## Important profile behavior

Both saved models accept `log_amount`, `lookback_months`, `log_interval`, and `target_cagr`, but inspection confirms **zero learned splits on all four fields**. Changing these settings does not change this exact champion's stock order. No artificial profile-dependent score change was introduced.

The existing execution engine receives the submitted fields and recalculates SIP execution, affordability, residual cash and goals. The UI explicitly explains this distinction. A 12-month horizon remains the only supported horizon, as before. Custom profiles may take longer to simulate than stored profiles.

## Verification

- Eight focused tests cover exact default scores and sector ranks, field changes preserving the selected model's actual behavior, invalid-profile rejection, and hash failures.
- Default score maximum absolute difference from the approved export: `2.7755575615628914e-16`; all sector ranks exact.
- JavaScript syntax checked with Node.
- `verify_sector_champion_web_20261017.py` passed live HTTP routing, all form field IDs, invalid inputs, default output parity and changed execution when contribution amount changes. Changing ₹7,500 to ₹1,000 changed contributed amounts for 3,387 stocks with comparable execution data; rankings remained exact. Receipt: `research/runtime/sector-champion-recency/http_verification.json`.
- An arbitrary profile (₹12,345, 47-day interval, 23.5% target) also completed with all 4,436 rows and valid JSON.
- Browser visual inspection was unavailable because local browser access is disabled in Work settings.

## Operation and rollback

Local development server: `python -m stock_ranker.webapp --port 8765 --no-auto-refresh` with `PYTHONPATH=src`. Package generation: `python research/runners/package_sector_champion_20261017.py`.

This integration is on the existing `main` checkout; pre-existing modifications were preserved. No remote publication or Git push is implied. Deployments must include the new runtime package as well as the existing personalized/V17 runtime evidence. Runtime files are intentionally outside Git under the repository's existing policy.

Original champion scores are returned as `original_champion_score` for rollback/audit. Previous research artifacts and website model routes have not been overwritten. To restore the prior website landing view, change `routeView`'s default to `closing-high`; the approved experimental champion remains separately addressable.
