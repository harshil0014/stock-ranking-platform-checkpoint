# Walk-forward validation protocol v1

## Registration status

This document preregisters the outcome-blind evaluation of unchanged Baseline
V1 and Research V2 rankings on four historical NIFTY 50 snapshots. No stock
prices, filings, rankings, future returns, or model outcomes were acquired or
calculated while freezing this protocol.

- Protocol identifier: `walk_forward_validation_protocol_v1`
- Version: `1`
- Status: `preregistered_outcome_blind`
- Machine-readable specification: `experiments/walk_forward/protocol_v1.json`
- Canonical protocol SHA-256:
  `a81278b799e1a61c3684f3b319fb14e2f6f0db6a2bdad1cd79b2ce13fd6f8576`

The fingerprint is SHA-256 over the parsed JSON value serialized as UTF-8 with
lexicographically sorted object keys, no insignificant whitespace, and JSON
separators `,` and `:`. The hash is recorded here rather than embedded in the
hashed object.

## Frozen ranking dates

| Target date | Actual ranking date | Information cutoff |
| --- | --- | --- |
| 2022-08-07 | 2022-08-05 | 15:30:00 Asia/Kolkata |
| 2023-08-07 | 2023-08-07 | 15:30:00 Asia/Kolkata |
| 2024-08-07 | 2024-08-07 | 15:30:00 Asia/Kolkata |
| 2025-08-07 | 2025-08-07 | 15:30:00 Asia/Kolkata |

These dates cannot be changed after observing outcomes.

## Historical universes

Membership and historical sector/industry classifications come from the
official NSE Indices July *Market Capitalisation, Weightage, Beta* monthly
reports. The current 2026 universe must never be projected backward.

| Report | Expected ZIP SHA-256 | Expected NIFTY 50 CSV SHA-256 |
| --- | --- | --- |
| `mcwb_jul22.zip` | `af2bb20cc901eaaa4694f102dc4cd62517397092660bf000b4f03029764e291a` | `85032a234edeb1adb8fbc1bf233b04151a03467961b64c852cb3bd1b53befd65` |
| `mcwb_jul23.zip` | `ce8a335221f222def0ee68b5d2aa6e2cdf500ec171e9c3d100df01a8a4545ac4` | `aa6ecd85791511aef647a546dfaf7db9b956f10c60ae331885e5855e657debbf` |
| `mcwb_jul24.zip` | `5a89a9e0fd709a1b310f03be4b8a4bc8f36c6982a4e83a8746c88af084b700ba` | `b8bb21128768ee8beb74d5fc9072818900e81a8aa7a11787c9990c72baf694b6` |
| `mcwb_jul25.zip` | `0244f8ac658343e07c045eb390f6ac6e42cefc45540a5badcefefdcd284201f4` | `2f4b9ae31c1f840bf15a8f452c77a0d2fc21fc409d2cee03e0851694d903eafd` |

Expected investable membership is 50 on each date. The July 2023 source's
synthetic corporate-action placeholder `DUMMYREL` remains in source provenance
but is excluded from investable ranking membership because it was not yet a
normally listed and tradable security.

## Predictor prices and features

The accepted donor remains daily Yahoo history through `yfinance` in the
isolated market-data environment, with `auto_adjust=False`, `repair=True`, and
actions preserved. Acquisition must request no predictor observation later
than the historical cutoff. `Close`, `Adj Close`, `Dividends`, `Stock Splits`,
and `Repaired?` indicators are retained.

For predictor dates `s <= t`, the engineering normalization is:

```text
pit_adjusted_price(s | t) = AdjClose(s) / (AdjClose(t) / Close(t))
```

This removes a common post-cutoff adjustment scale while preserving relative
corporate-action-adjusted history through the cutoff. It is not a new ranking
algorithm. Every price feature uses only rows through the cutoff. Existing
Baseline V1 and Research V2 formulas, anchors, tolerance rules, history rules,
directions, weights, ties, and eligibility behavior remain immutable.
Insufficient history causes explicit exclusion and is never imputed.

A planned sensitivity audit compares `repair=True` with `repair=False` and
reports every affected company/date. It is not permitted to replace the
preregistered primary result.

## Point-in-time fundamentals

The contract remains **NSE Audited Standalone Fundamentals v1**
(`nse_audited_standalone_fundamentals_v1`). Each ranking date requires only
the immediately preceding March fiscal year:

| Ranking year | Required fiscal year |
| --- | --- |
| 2022 | FY2021-22 |
| 2023 | FY2022-23 |
| 2024 | FY2023-24 |
| 2025 | FY2024-25 |

No older-year fallback is allowed. All three inputs must share the audited
standalone basis: explicit issuer-disclosed ROCE, explicit issuer-disclosed
debt-to-equity, and current/prior audited standalone reported PAT. Derived
ratios, proxies, ROA, ROE, ROEV, ROIC, and cross-basis mixing are forbidden.

Canonical availability requires an NSE exchange dissemination timestamp no
later than the applicable cutoff. Current archive presence does not prove
historical availability. An unprovable timestamp causes explicit
`UNVERIFIED_FILING_AVAILABILITY` exclusion.

## Future-return labels

The primary horizon is 12 calendar months; 3- and 6-month horizons are
secondary robustness checks. Each endpoint is the last trading observation on
or before the calendar target date. The label is:

```text
Yahoo adjusted price at endpoint / Yahoo adjusted price on ranking date - 1
```

Exact endpoint dates, values, symbols, and source settings must be retained.
No label may influence predictors, eligibility, weights, parameters, or model
selection.

## Fair comparison

For each date, full historical Baseline V1 is context only. Research V2 defines
its eligible cohort. Matched Baseline V1 reruns the unchanged Baseline engine
on exactly that cohort within each historical sector. Only Research V2 versus
matched Baseline is a model-performance comparison. Original Baseline rank
must never be compared directly with Research V2 rank as a performance
statistic.

## Preregistered evaluation

The primary outcome is 12-month sector-date Spearman Rank IC for matched
cross-sections containing at least three stocks. Research V2 score is already
higher-is-better. Baseline signal is the negative unchanged Baseline score so
that higher is better. Average ranks handle ties.

The primary aggregate is the equal-weight arithmetic mean across valid
sector-date observations. The primary comparison is the paired mean of:

```text
Research V2 Rank IC - matched Baseline V1 Rank IC
```

Both model means are reported separately. Raw sector-relative scores are never
pooled across sectors.

For 12, 3, and 6 months, secondary reporting includes median Rank IC, sample
standard deviation, unannualized Rank ICIR where defined, pairwise ordering
accuracy, top-ranked-stock excess return against its matched sector cohort,
equal-sized top-half minus bottom-half spread (omitting the middle stock for an
odd cohort), and V2 win/tie/loss counts with tolerance `1e-12`. Pairwise
accuracy needs at least two stocks; Rank IC needs three. Singletons produce no
ranking-quality observation. Top-five overlap is not a performance statistic
when cohort size makes it tautological.

## No tuning after registration

Observed outcomes cannot change model formulas or weights, the accounting
contract, ranking dates, primary horizon or metric, universe or sector rules,
price donor, or excluded-company treatment. Later alternatives must be marked
exploratory and cannot replace the preregistered primary result. If Baseline
wins, that result must be reported.

## Frozen limitations

- Yahoo histories are retrospectively acquired, not vendor-vintage snapshots.
- Yahoo adjusted-price semantics are inherited from earlier accepted work.
- Annual-report archive completeness may reduce Research V2 coverage.
- Missing dissemination timestamps cause exclusion.
- Historical symbol/name changes may cause identity-resolution exclusions.
- Four annual ranking dates provide limited statistical power.
- This is ranking-quality research, not a transaction-cost study, portfolio
  profitability claim, investment-performance claim, or investment advice.
