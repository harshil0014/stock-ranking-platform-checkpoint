# Personalized ranking product acceptance

Date: 2026-09-27

Branch: `personalized-ranking-product-20260926`

Frozen champion: `d4995807163bef1ec4b297179e6c54a59c71f390`

Champion formula: 67% Goal + 33% sealed LightGBM LambdaRank

## Product boundary

The website now accepts contribution amount, historical lookback, contribution interval, target CAGR, and investment horizon. The submitted profile flows through the existing whole-share execution engine, accepted corporate-action history, Goal scenarios, the seven frozen LambdaRank features, the sealed LightGBM model, and the frozen 67/33 blend.

Supported inputs are:

- contribution amount: INR 1,000 through INR 50,000, including decimals;
- lookback: 12, 36, or 60 months;
- contribution interval: any whole number of days from 7 through 90;
- target CAGR: 10% through 30%, including decimals;
- horizon: 12 months.

The horizon remains fixed at 12 months because the frozen champion was trained and evaluated only for that forward horizon. Unsupported values are rejected explicitly. Values are never clamped or silently substituted.

Exact registered research profiles use their sealed champion rows after the freeze is verified. This is an output-preserving performance path. The independent reproduction check disables that path and recomputes all nine profiles through the website-facing engine.

The complete product universe remains visible. Securities without a personalized row receive an explicit `PRODUCT_FALLBACK` row with baseline or research provenance; they are never presented as personalized output.

## Acceptance evidence

The official acceptance set is `experiments/personalized-product-acceptance/run-03` and its manifest status is `PASS`. The manifest artifact-set SHA-256 is `9f9bb9224c41f87f59cc59654f293a3d3aa49a2b7ac84e5594649b9c0c58926c`.

- Matrix: 162 profiles from 6 amounts, 3 lookbacks, 3 intervals, 3 targets, and the supported 12-month horizon.
- Sensitivity: amount reached execution and ranking; lookback changed cohort or execution and ranking; interval reached execution and ranking; target reached Goal and ranking.
- Frozen reproduction: all nine required profiles passed. Maximum absolute differences ranged from `1.78e-15` to `7.11e-15`, below the `2e-12` tolerance.
- Invalid inputs: all 13 blank, nonnumeric, zero, negative, out-of-domain, fractional-interval, and unsupported-horizon cases were rejected.
- Isolation: deterministic repeat, sequential isolation, and concurrent isolation all passed.
- Latency: runtime pack load 4.981 seconds; matrix median 3.202 seconds, p95 8.724 seconds, maximum 11.216 seconds; cached repeat 0.085 seconds.
- Availability: the default profile returns 4,436 product rows: 3,265 genuine personalized rows and 1,171 explicit fallbacks.

The 14-stock cohort passed identity and product-availability checks. Twelve securities received personalized positions. `BOM:522195` resolved to `FRONTSP` and `BOM:539997` resolved to `KPL`; both remained available as explicit product fallbacks because they were outside the frozen personalized cohort.

The Playwright browser acceptance passed: fields and editable defaults, browser-native invalid-input handling, submission, ranking refresh, profile fingerprint change, deterministic rerun, current-profile stock inspection, page refresh, narrow layout, and zero console or page errors. First full browser result took 9.098 seconds and a cached repeat took 0.337 seconds.

## Data and audit boundary

The 98,546,546-byte runtime pack stays outside Git at `research/runtime/personalized-ui-d499580.npz`. Its SHA-256 is `515eac8ffc555a571406a4a41f9d931a016cb6280871a3d89f59846d2692ed0c`. The versioned audit records 3,790 identities, 14,644,070 observations, 19 explicit source errors, all source hashes, and the build inputs.

The accepted current market snapshot has 4,434 matched securities. The product view has 4,436 prices because it additionally retains two disclosed product fallbacks: `KALYANI` uses an `OFFICIAL_LAST_TRADE_STALE` price from 2026-08-28 and `VASUPRADA` uses an `OFFICIAL_PRIOR_TRADE` price from 2026-09-17. Both counts are therefore valid for different scopes; neither was changed to manufacture test agreement.

The acceptance runner hashes the protected freeze files before and after execution. Every hash remained identical. It does not edit the frozen tag, production branch, prospective predictions, or shadow checkpoint logic.

The final repository test run completed with 927 passed, one expected skip for absent external NSE/NIFTY files, and zero failures in 195.68 seconds.
