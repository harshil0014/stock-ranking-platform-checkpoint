# Walk-forward blind prediction reconstruction

This milestone freezes predictor-side artifacts for the preregistered
`walk_forward_validation_protocol_v1`. Its canonical protocol SHA-256 remains
`a81278b799e1a61c3684f3b319fb14e2f6f0db6a2bdad1cd79b2ce13fd6f8576`.
It does not acquire or calculate endpoint prices, future returns, labels, IC,
Rank IC, model comparisons, or any other outcome.

Pre-outcome amendment 001 clarifies that the preregistered `sector-date`
grouping uses the official NSE Indices Sector tier. The verbatim MCWB Industry
is retained separately. The parent protocol and primary metric are unchanged.

## Boundaries

- The only ranking dates are 2022-08-05, 2023-08-07, 2024-08-07, and
  2025-08-07. Yahoo requests end at the day after each ranking date because
  the provider end is exclusive; every returned observation is independently
  required to be on or before its cutoff.
- Historical membership and industry labels come from the hash-pinned official
  July MCWB archives. The July 2023 `DUMMYREL` source row is retained as a
  `SYNTHETIC_CORPORATE_ACTION_PLACEHOLDER`, excluded from investment membership,
  and never replaced by JIOFIN.
- Provider identity is the exact historical NSE symbol plus `.NS`, except for
  reviewed declarative aliases. The current registry contains no aliases and
  expressly prohibits HDFC-to-HDFCBANK and DUMMYREL-to-JIOFIN substitutions.
- The predictor series is the protocol's cutoff-rebased adjusted series:
  `AdjClose(s) / (AdjClose(t) / Close(t))`. It equals raw close at the cutoff
  within an absolute tolerance of `1e-10`.
- Baseline V1 and Research V2 are called through their accepted implementations;
  neither formula, weight, eligibility rule, nor rank rule is reimplemented or
  changed here.

## Fundamental evidence boundary

Only the required fiscal year is considered for each cutoff. An NSE report is
eligible for review only when its exchange dissemination timestamp is proven no
later than the cutoff. Archive presence alone is not treated as historical
availability. The existing pypdf audit generates conservative candidates, but
candidates do not become model inputs without a reviewed declarative mapping
that proves explicit audited standalone ROCE, debt-to-equity, and comparable
current/prior reported profit.

No historical candidate has been accepted into that mapping in this milestone.
Accordingly Research V2 coverage is zero for all four dates, with explicit
exclusions rather than guessed ratios or reporting-basis substitutions. This is
a scientifically valid partial reconstruction, not a Research V2 performance
result.

## Frozen predictor coverage

| Ranking date | Official rows | Investable | Provider resolved | Baseline eligible | Official sectors | Required FY | Pre-cutoff reports | Contract accepted | V2 eligible |
|---|---:|---:|---:|---:|---:|---|---:|---:|---:|
| 2022-08-05 | 50 | 50 | 48 | 46 | 15 | 2021-22 | 0 | 0 | 0 |
| 2023-08-07 | 51 | 50 | 49 | 48 | 15 | 2022-23 | 0 | 0 | 0 |
| 2024-08-07 | 50 | 50 | 48 | 48 | 14 | 2023-24 | 22 | 0 | 0 |
| 2025-08-07 | 50 | 50 | 49 | 47 | 16 | 2024-25 | 42 | 0 | 0 |

The repair audit finds ADANIENT available only with `repair=True` in 2023,
2024, and 2025. Those cases are `REPAIR_AFFECTED`. Their absence under
`repair=False` materially changes four, three, and one sector ranks,
respectively; the primary protocol result remains `repair=True`.

Generated source caches, PDFs, extracted text, and prediction bundles live
under ignored `data/walk_forward/`. Two independent preparations from the same
cache produced 46 byte-identical files each and overall blind prediction
fingerprint
`52455e86ede4681e599c63466c7c4ea345f7684a8004512637f9256abfa34cb0`.
These files contain predictions only and remain blind to all outcomes.
# Official NSE availability rescue

For the 2022 and 2023 snapshots, a final availability audit searched every annual-report candidate whose original NSE Annual Reports archive record lacked a dissemination timestamp. The original null remains preserved. A report is available only when an exact official NSE corporate-announcement attachment has an exchange dissemination timestamp at or before the frozen cutoff and matches the required fiscal year and security identity. Broadcast time, company-site publication, dispatch notices, newspapers, broad announcements, and post-cutoff filings cannot rescue availability.

Rescued reports remain subject to the unchanged `nse_audited_standalone_fundamentals_v1` contract. No ratio is derived, substituted, annualized, or mixed across reporting bases. This rescue uses predictor-side filing evidence only and acquires or calculates no future return, label, IC, Rank IC, or realized comparison.
