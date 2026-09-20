# Common research platform foundation

This additive layer lets Baseline V1, Research V2, OpenSourceAP predictors,
isolated Qlib models, and future models consume one evidence contract. It does
not change any accepted score, ranking, model default, or dataset.

## Safety boundary

Each numeric observation is stored in long form with security/date identity,
feature name, value, source, evidence fingerprint, availability timestamp, and
an availability status. `pit_verified` means the source clock is independently
valid for that observation. `current_only` means the value may support a
present-day exploration but cannot enter historical training or evaluation.

The common validator applies the existing 15:30 IST decision cutoff separately
to every feature. It rejects missing timezone offsets, post-cutoff evidence,
duplicate natural keys, nonfinite values, and any current-only observation in a
historical mode. Model requirements can also declare maximum evidence age.
Missing inputs produce an eligibility record; they are never imputed.

## Model boundary

The execution registry describes capabilities without importing Qlib,
LightGBM, or Torch. An adapter receives only a validated model-specific matrix
and must return `canonical_signals_v1`. Native deterministic functions,
precomputed outputs, and isolated subprocess models can implement the same
small adapter boundary.

The initial registry records:

- accepted Baseline V1 and Research V2 as verified native methods;
- OpenSourceAP Mom12m with an adapter ready, not evaluated on Indian equities;
- Qlib Linear and LightGBM as synthetic-reproduced isolated models;
- Qlib TRA as synthetic-reproduced and sequence-specific;
- DoubleEnsemble with its existing compatibility blocker visible.

OpenSourceAP Mom12m is based on Chen and Zimmermann's open-source
cross-sectional asset-pricing project and its upstream implementation compounds
calendar-aware monthly returns from t-1 through t-11. That formula is recorded
in the adapter. The upstream code zero-fills missing returns; this platform
conservatively emits no signal unless all eleven lagged calendar months exist.
For complete histories the formula is identical. This milestone does not run
the adapter over the full Indian universe, download its US dataset, or silently
transfer US empirical evidence to Indian equities.

## Evaluation and verification

Existing canonical IC/Rank-IC evaluation and evaluation-protocol fingerprints
remain authoritative. The new consensus verifier requires identical ordered
date/security cohorts and one configuration fingerprint per model. It reports
pairwise rank correlation and an outcome-blind average percentile-rank signal.
It reads no labels and explicitly records that no winner was selected.

Consensus is a diagnostic, not a recommendation, portfolio, product default,
or claim of improvement. Scientific comparison still requires the existing
frozen label dataset and common evaluation-protocol fingerprint. Failed and
blocked models remain visible rather than being dropped.

## Integration sequence

1. Map an accepted source into per-feature evidence without changing it.
2. Validate current or historical mode and obtain an eligibility report.
3. Select the registered model specification and build its complete-case matrix.
4. Execute through a native adapter or an isolated environment.
5. Convert output to canonical signals and evaluate under one frozen protocol.
6. Compare evaluations and optionally run outcome-blind consensus verification.

Expensive full-market fitting, model tuning, winner selection, website-default
changes, and real-market claims are outside this milestone.

`load_accepted_current_evidence` is the first production bridge. It resolves
the hash-validated accepted company-fact snapshot and exposes existing Product
Baseline inputs, accepted V2 fundamentals, market capitalization, ROE, and
operating cash flow under explicit field names. Every row is `current_only`.
Thus these rich present-day values are available for model exploration but are
mechanically rejected by historical training and evaluation modes.

## Model-selection boundary

`marketdata/runners/evaluate_exploratory_models.py` benchmarks the fixed
OpenSourceAP Mom12m definition and fixed equal-weight rank ensembles on the
already revealed frozen four-date cohort. Its output is supplementary and
cannot select a winner or change the product default. Four annual dates and
sixteen sector-date cells are not an adequate independent selection sample;
promotion requires a new prospectively frozen validation window.

The corrected deterministic runs (`exploratory_model_benchmark_v3_run_02`
and `exploratory_model_benchmark_v3_run_03`)
covered all 104 frozen company-dates and all 16 valid sector-date cells. Mean
12-month Rank IC was 0.2313 for Mom6m, 0.1438 for one-month reversal, 0.1000
for strict Mom12m, 0.0938 for the fixed Baseline/price-factor blend, -0.0114
for Baseline, and -0.0500 for V2. A fixed expanding ridge model trained only
on fully matured earlier sector/date targets scored 0.0750 across its 12
eligible sector-date cells. Its same-cell mean difference versus Baseline
was 0.0318, versus V2 0.1417, and versus Mom12m 0.0500. These small-sample
differences do not authorize promotion. In particular, ridge's 2024 results
were weak, and its positive aggregate depends heavily on 2025.
These are feasibility results, not independent evidence for promotion: the
outcomes were already revealed and the sample contains only four annual dates.

## Prospective production gate

The outcome-blind `prospective_model_validation_v4_20260915` freeze compares
strict Mom12m and fixed price-factor/Baseline blends with the incumbent
Baseline. It uses the accepted 15 September snapshot and contains 3,917
exact-identity securities across 56 sectors from 4,231 incumbent-eligible
securities. The 314 exclusions apply only to challengers and reflect strict
calendar-month requirements for the price factors. The
freeze hashes every history file, records that no outcome was accessed, and
keeps the product default unchanged. Its primary 12-month result cannot mature
before 15 September 2027.

## Fixed chronological ML result (15 September 2026)

The frozen 193-company-date panel was also passed, without reselecting inputs,
to deterministic LightGBM 4.6.0 and the official Qlib 0.9.7
`DEnsembleModel`. Every training sector outcome had to mature strictly before
the test decision date. An audit found that the first supplementary report had
oriented Baseline's lower-is-better score in the wrong direction. The corrected
v3 runs are byte-identical (fingerprint
`15b0c07c4151e101be40b95fa0435f70528955c60003af9eead451ac640829be`).
LightGBM's mean Rank IC is 0.1447 versus -0.0194 for correctly oriented
Baseline on the same 20 sector-date cells. Official DoubleEnsemble's six cells
produce 0.0538 versus 0.1860 for Baseline. These four previously revealed dates
remain supplementary diagnostics rather than independent selection evidence.

## Broad locked chronological study

The preregistered broad price study uses monthly decisions from August 2020
through August 2025. Development ends in August 2023, validation spans the next
12 months, and the September 2024 through August 2025 interval is opened once
as a locked test. The validation rule selected ridge plus a fixed eight-factor
price multifactor before the test was inspected. Across 36,639 locked-test
company rows, 3,079 issuers and 492 sector-month cells, the selected ensemble
achieved mean Rank IC 0.0933 versus -0.0099 for Baseline. It won 63.0% of cells
and 10 of 12 months. A month-block bootstrap for the mean Rank-IC difference
was [0.0496, 0.1573]; the advantage remained positive at minimum peer counts of
5, 10 and 20. The challenger top-minus-bottom forward spread was 0.1219 versus
-0.0713 for Baseline. These results are materially stronger than the earlier
four-date evidence.

The study nevertheless uses today's surviving ordinary-equity universe and
today's sector labels because complete historical membership/classification is
not available. It therefore cannot justify an unconditional replacement of the
production default. Baseline V1 remains the default; the ensemble is recorded
as a validated prospective candidate. Its current, outcome-blind freeze ranks
3,892 securities across 55 sectors, trains only on endpoints preceding the
15 September 2026 decision, and accesses no outcome for that ranking. The stock
API/UI exposes this candidate with that boundary rather than presenting it as
an investment recommendation or proven production winner.

## Integrity correction and preserved diagnostics

The earlier exploratory ridge implementation used earlier ranking dates
without requiring their outcome endpoints to precede the decision. Its
reported ridge result is invalid and superseded; earlier generated artifacts
remain unmodified for audit. Training now excludes same-day endpoint closes
and requires every peer in a sector/date target to have matured. Tests perturb
unavailable labels and require predictions to remain identical. Prediction
artifacts disclose training dates, row counts and latest training endpoint.

The earlier v2 prospective artifact used a caller-supplied freeze timestamp
preceding its accepted snapshot. It is not valid prospective timing evidence.
The v3 replacement records actual completion time automatically, after source
acceptance and input stability checks. Old artifacts are preserved but rejected
by the current validator. The validator checks the manifest fingerprint,
complete exact inventory, hashes, chronology, identities and coverage counts.
The current API serves only the replacement freeze; production ranks are not
replaced by challenger ranks. Mom6m is an experimental factor, not yet a
registered executable adapter, and is labelled `specified` accordingly.

The current ensemble was refreshed against the accepted 18 September snapshot:
3,713 securities across 58 sectors, accepted-company fingerprint
`4064dc5b0a12fc385150a08e23a61f230b0f2acfcee76e394c8e80cee48d741e`,
and artifact fingerprint
`1c7cc263bb24fdc9c09f553cc828c09d5069b914d90bd89d6e266e70f66c853e`.
It remains an outcome-blind validated challenger; the governed production
hierarchy and complete audit are documented in
`docs/complete_internal_ranking_audit_20260918.md`.

Current adjusted-price caches remain current/reference sources. Their hashes
do not by themselves prove historical corporate-action or delisting coverage.
This freeze is a prospective candidate record, not a fully specified execution,
transaction-cost or automatic production-promotion policy. More retrospective
trials on revealed outcomes cannot manufacture independent validation.

## Workbook feature integration (15 September 2026)

The cumulative accepted workbook index now includes all 4,387 exact-identity
workbook-backed issuers, including historical identities absent from today's
master. This fixes discovery restricted to the newest batch and older manual
manifests; it does not add those historical identities to the live universe.
Raw workbooks and accepted provider artifacts remain unchanged.

`marketdata/runners/export_historical_financial_features.py --output <fresh-directory>`
exports 1,614,328 observations across 45 named features, with workbook SHA-256,
cell, standalone basis, units, financial period and observed timestamp.
The four derived ratios are explicitly component ratios, not substitutions for
statutory ROCE or accepted V2 fields. All 4,387 workbooks passed; no conflicting
financial keys were found. These figures describe reference-data coverage, not
historical training eligibility.

The exporter separately verifies the accepted official backbone inventory and
raw evidence hashes, retaining 48,725 standalone fact-clock rows. There are
2,223 vendor period/vintage rows with a corresponding official fact clock.
This is not proof that the modern vendor number was published at that time:
the reference bridge rejects historical training and retains original-vintage
verification as false. No historical PIT facts or production models are
promoted by this export. Current/reference feature evidence can enter the
common research interface only after its recorded observation timestamp and
with exact-ISIN sector mapping. Historical PIT safeguards remain independent.

Artifacts: `data/analysis/vendor_financial_features_v2_run_01/` and its
independent deterministic rebuild `vendor_financial_features_v2_run_02/`.
The superseded v1 export is retained, not treated as complete coverage.

Both rebuilds have identical bytes for all six output files, with fingerprint
`8efae99c8fb77cb6d73724ea913b126a10cf25418a72fe6e311f97d14dd85880`.
Available raw sections cover 4,387 annual, 4,384 balance-sheet, 4,386 cash-flow
and 4,036 quarterly issuers. Annual observations span 2004–2026; quarterly
observations span September 2015–June 2026. At least one annual field exists
for 4,250 issuers in 2022, 4,329 in 2023, 4,357 in 2024, 4,362 in 2025 and
4,301 in 2026. These are not counts of complete V2 records or PIT cohorts.

Verification: 22 focused tests and 768 full-suite tests passed, including
localhost HTTP/API smoke tests; JavaScript syntax and Git whitespace checks
passed. Accepted company-fact/market fingerprints and protected cohort,
blind-manifest and outcome hashes were unchanged. The accepted production
default is retained; broad retrospective vendor-feature ML is not promoted
without original-vintage evidence and independent chronological validation.

## External method references

- OpenSourceAP code: https://github.com/OpenSourceAP/CrossSection
- Mom12m implementation: https://github.com/OpenSourceAP/CrossSection/blob/master/Signals/pyCode/Predictors/Mom12m.py
- Chen and Zimmermann, *Open Source Cross-Sectional Asset Pricing*, Critical
  Finance Review 11(2), 2022: https://doi.org/10.1561/104.00000112
