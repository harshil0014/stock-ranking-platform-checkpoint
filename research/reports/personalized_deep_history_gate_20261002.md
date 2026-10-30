# Personalized deep-history source gate — 2026-10-02

## Historical gate verdict (superseded)

The conclusion below was correct for the original checkout state, but is now
**superseded by a real Yahoo reacquisition** at
`experiments/personalized-deep-history-20261002/yahoo-split-ledger-v1/`.
It is retained as a historical audit, not as a final model conclusion. No model
has been promoted from the subsequently reacquired source yet.

The reacquisition contains 3,704 successful raw Yahoo chart responses, 104
explicit failed lookups quarantined from reconstructed rows, and 1,802 observed
split events. Its ledger byte SHA-256 is
`7607aacd11408914368bc71d78f667f5eb15bef56c2e130847f02cc09904e11f`, rather
than the old recorded `0d723a299d346eeffa7160d4108acda8dc609cd7b7e2360f443cdb2cc51c4fcb`.
This is a new acquisition rather than a claimed byte-identical restoration:
every successful raw file was hash-checked against `acquisition_audit.csv`,
and the canonical observed `(isin, date, numerator, denominator)` event set has
1,802 rows and SHA-256
`96156be0548d885ca54dbc075d87e39ad3401ee60f8fb9575a2a0279120591ef`.

This is a data-integrity result, not a negative result for any model. Reusing
the 2025 dates or treating cached split-adjusted closes as dated nominal prices
would make the apparent date expansion invalid.

## What was found

The authoritative v3 enrichment is intact and has 4,436 identities, 4,432
defensible adjusted histories, and four raw-risk-only quarantines. The current
successor research uses ten historical decision dates: six training dates
(2016--2019 annual plus 2022-06/12), two 2023 development dates and two already
exposed 2025 diagnostics. All their profile rows have matured endpoints.

The new reproducible deep-panel runner declares twelve additional matured
decision dates:

| Missing-period additions | Count |
|---|---:|
| 2020-03/09, 2021-03/09, 2022-03/09 | 6 |
| 2023-03/09, 2024-03/09 | 4 |
| 2025-03/06 | 2 |
| Nominal total if the source gate is satisfied | 22 dates (10 + 12) |

It also writes a pairwise 12-month-window overlap table. Semiannual dates have
roughly half their horizon in common, so the nominal 22 is not an independent
22. A final evaluation must report cluster/date-block uncertainty and effective
sample size, not only row-level confidence intervals.

## Source and leakage audit

Permitted local sources are the frozen historical price cache, frozen
whole-share cohorts, the normalized official action ledger, dated terminal
repairs, and the original panel. The new code excludes current sector and
fundamental facts from added rows. It checks that every endpoint is no later
than 2026-09-18 and strictly later than its decision date.

The formerly blocking source was the provider `split_ledger.csv`. The historical cache's
`raw_close` field is documented by the existing executable engine as already
split adjusted. The missing ledger identifies the provider factors necessary to
recover nominal purchase prices before applying official exchange multipliers.
Neither a present-day quote nor an official action list proves how that provider
adjusted a particular cached series. Substituting a derived official-action
bridge is therefore labelled `ESTIMATED_OFFICIAL_ACTION_MATCHED_PROVIDER_FACTOR`
and `provider_split_bridge_is_observed=false`; it is quarantined from champion
comparison and final evaluation.

The real-ledger builder now reads the reacquired ledger directly and rejects any
missing audit, summary hash mismatch, raw-response hash mismatch, or events not
tied to a successful acquisition response. It does not construct or use the
`ESTIMATED_OFFICIAL_ACTION_MATCHED_PROVIDER_FACTOR` bridge. The 104 failed
provider identities are explicitly quarantined because a failed lookup is
unknown split history, not evidence of no splits.

There is also inherited current-survivor membership contamination in the frozen
cohorts. It is retained and must be reported, not corrected by pretending that
delisted names were available.

## Final split and model conclusion

Before reacquisition, no new train/development/untouched split was declared
because it would rest on quarantined nominal execution. The last valid split was:
historical training through 2022-12 endpoint maturity, 2023 development, and
2025 exposed diagnostics; it has no genuinely untouched final historical block.

Accordingly, there are no legitimate champion-versus-challenger aggregate,
profile, regime, missing-history, or NYKAA deltas to add. The last valid such
results remain those in `personalized_successor_20261002.md`: the duration
challenger improved NDCG/drawdown but failed exposed achievement, shortfall and
median-return gates. NYKAA remains diagnostic only (frozen champion rank 1;
the rejected challenger rank 30).

## Reproducible continuation

Use the real ledger and run:

```bash
PYTHONPATH=/tmp/personalized_research_deps python3 \
  research/runners/build_deep_personalized_panel_20261002.py \
  --split-root experiments/personalized-deep-history-20261002/yahoo-split-ledger-v1 \
  --output experiments/personalized-deep-history-20261002/real-panel-v1
```

Then the 22-date panel should be walk-forward fit, with early dates for
training, 2023--2024 development, and the cleanest never-inspected 2025 block
reserved for final evaluation. Do not use the estimated bridge to promote a
model.
