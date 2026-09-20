# Screener-preferred retrospective experiment

This is the separately authorized vendor-restatement-risk-accepted experiment,
not a change to strict PIT evidence, production ranks or the frozen V2 study.
The spreadsheet workflow preserves the supplied data and explicit missingness;
no original workbooks are edited. No new financial accounting audit or external
data acquisition is performed.

## Data and selection

Screener is the financial-value source. Existing exact-ISIN official exchange
period clocks determine period admission at 15:30 IST. Actual vendor observation
timestamps remain alongside these clocks. This does **not** establish that a
modern vendor value existed at the historical date. Same-key conflicting vendor
values are quarantined, not selected based on model performance. The latest
public financial period is selected before feature completeness is tested.

The broad clock-linked data contains 71 issuers in 2022, 111 in 2023, 352 in
2024 and 580 in 2025: 1,114 issuer-dates, 580 distinct issuers. This is financial
feature coverage, not a claim of full historical universe or outcome coverage.

The frozen outcome study has 104 issuer-dates. Its complete-case experimental
subset has 96 (22/24/25/25 by date), and 15 sectors/dates with at least three
peers. Eight exclusions are retained in `exclusions.csv`; no accepted cohort
or eligibility output was modified.

## Fixed models

Quality averages within-sector percentile ranks of net margin, closing-equity
ROE, operating-cash-flow/assets and inverse debt/equity. These are separately
named component factors, not replacements for statutory ratios or V2 formulas.
Quality/momentum averages quality with Mom12m. Ridge uses these four raw factors
and Mom12m with fixed alpha=1, training-only standardization and an unpenalized
intercept. It admits only earlier sector/date labels whose entire peer outcome
has matured strictly before the decision date. There is no imputation, tuning,
hyperparameter search or production promotion.

All competitors use the same complete-case securities. Sector Rank IC uses
average-tie Spearman ranks; groups smaller than three are not scored. Ridge has
no first-date training data and is compared with incumbents on identical cells.
Raw predictions and training row counts/endpoints are saved.

## Descriptive results

| Model | Valid sector-dates | Mean Rank IC |
|---|---:|---:|
| Baseline | 15 | 0.054199 |
| V2 | 15 | -0.026667 |
| Mom12m | 15 | -0.060000 |
| Quality | 15 | -0.027187 |
| Quality/momentum | 15 | -0.104113 |
| Ridge | 12 | -0.058333 |

On its 12 common cells, ridge minus Baseline is -0.184416, minus V2 is
-0.041667 and minus Mom12m is approximately zero. Ridge is negative in 2023
and 2024 and positive in 2025. These results do not support replacing the
production default. They are small-sample, previously revealed, restatement-
risk-accepted diagnostics, not unseen performance or a trading backtest.

Run with the existing product interpreter:

```
.venv\Scripts\python.exe marketdata/runners/evaluate_vendor_risk_models.py --output data/analysis/vendor_financial_features_experiment_<fresh-id>
```

Inputs are hashed before and after execution. The experiment contract and
features are saved before loading labels. Artifacts are independent of the
accepted product, with their own source and output fingerprints. Existing
strict PIT admission remains unchanged.

Validation: 19 focused tests and 771 full-suite tests passed. Two independent
runs have identical bytes for all eight artifacts, with fingerprint
`220c6e2066993d979da5c4c91bf85b62dd12629c8f1f17e135ae129c1402a5f6`.
JavaScript syntax and Git whitespace checks passed. The accepted company-fact
and market fingerprints, frozen cohort, blind manifest and outcome hashes were
unchanged. Work remains unstaged and uncommitted; the safety stash is retained.

## Expanded existing-data panel

The 96-row result above was not the maximum panel supported by local evidence:
it began with the already narrowed 104-row V2 study cohort. A subsequent audit
started instead from all 200 frozen, date-specific NIFTY membership slots. It
recovered a 193-row base panel (48/48/48/49 by date) from exact identities and
accepted local price histories. Seven slots remain excluded because their
historical symbols cannot be joined to a single ISIN without guessing and their
price factor is incomplete. Four additional rows lack Baseline inputs but remain
usable by models whose own inputs are valid; model availability no longer
silently inherits Baseline eligibility.

The largest one-feature accounting group has 121 company-dates and 37 issuers;
the full four-feature quality group has 110 company-dates and 34 issuers. Of the
83 base rows missing the full group, 72 have no verified official period clock
and 11 lack same-period workbook components. These are retained as explicit
gaps. Profit growth is derived only from consecutive annual periods within the
same source workbook; cross-workbook values are never mixed. No values are
imputed or zero-filled.

Every candidate is evaluated on its own valid rows, with a separately reported
Baseline result on precisely the same rows. The broader Mom12m result is also
reported on the 193-row panel and on the Baseline-complete intersection. Across
the revealed four dates, Baseline and Mom12m have mean sector-date Rank IC
0.104643 and 0.098926 respectively (28 valid sector-dates); Mom12m is 0.107468
on the exact Baseline intersection. Full quality is -0.007962 versus Baseline
-0.052165 on 17 common sector-dates. Fixed chronological ridge is 0.023299
versus Baseline -0.036177 on 14 common sector-dates. Other quality variants and
the vendor-risk V2 diagnostic do not improve on their common-row Baselines.
These small, previously revealed subsets are descriptive and do not justify a
production promotion.

Two independent expanded builds are byte-identical across all seven artifacts,
with fingerprint
`32cbeb767d2712d95600761c445a9cd61b324ae7c03399f7b4ff3c63872aa7c8`.
The runner is `marketdata/runners/build_expanded_historical_panel.py`; generated
outputs are ignored. The full suite passes 774 tests. Strict PIT admissions,
accepted product state and production model selection remain unchanged.
