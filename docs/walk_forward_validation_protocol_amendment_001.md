# Walk-forward validation protocol amendment 001

## Registration

- Amendment identifier: `walk_forward_validation_protocol_amendment_001`
- Amendment version: `1`
- Status: `preregistered_pre_outcome_clarification`
- Canonical amendment SHA-256:
  `7f8c5d40de88077f3b6afcd471d0db4377fab567d2839e719a71ee6b11ae7163`
- Parent protocol: `walk_forward_validation_protocol_v1`, version `1`
- Parent protocol SHA-256:
  `a81278b799e1a61c3684f3b319fb14e2f6f0db6a2bdad1cd79b2ce13fd6f8576`

The amendment hash uses the parent protocol's canonicalization: parse the JSON,
serialize it as UTF-8 with lexicographically sorted object keys, no
insignificant whitespace, and separators `,` and `:`, then apply SHA-256. The
hash is recorded here rather than embedded in the hashed object.

This clarification was registered on 2026-08-09 before acquiring or calculating
any endpoint price, future-return label, IC, Rank IC, or other outcome. It does
not rewrite `protocol_v1.json`.

## Predictor-only discovery

The official MCWB files expose a column named `Industry`, not the higher-level
official `Sector` tier. The first blind implementation preserved that value as
`historical_industry` but then passed it to Baseline V1 and Research V2 under
their canonical `sector` field. This produced 27, 29, 28, and 30 Baseline
groups. The issue was discovered solely from predictor-side peer-count
feasibility; no outcome was available or consulted.

NSE Indices defines a four-tier hierarchy: Macro-Economic Sector, Sector,
Industry, and Basic Industry. The preregistered primary aggregation remains
**sector-date Spearman Rank IC**. This amendment clarifies that `sector` means
the official NSE Indices **Sector** tier applicable at the ranking cutoff.

The verbatim MCWB `Industry` remains preserved as source provenance. An exact
declarative crosswalk maps it to `historical_sector` using the official
classification structure. Fuzzy matching, current-company classification,
current-2026 website sectors, and unresolved partial mappings are forbidden.

## Official structures

| Ranking dates | Official NSE Indices structure | SHA-256 |
|---|---|---|
| 2022-08-05 | Industry Classification Structure, April 2022 | `428e90ab2681a62d611362bb1d8a3bbb0d301c2a2ff198c9d1280ec2854ec21c` |
| 2023-08-07, 2024-08-07, 2025-08-07 | Industry Classification Structure, July 2023 | `8ae58cbd10d7dd5184d76cfec6486f91c019026c8de329432b69c54ff7235f8b` |

The July 2023 structure is the latest official structure published on or before
the latter three cutoffs. Exact URLs, document applicability, official sector
codes, official Basic Industry evidence, and the verbatim label crosswalk are
recorded in `marketdata/specifications/walk_forward_nse_sector_mapping.json`.

## Pre-outcome feasibility

Counts use only Baseline-eligible stocks and contain no performance data.
Peer-size distributions are represented as `peer size: number of groups`.

| Date | Raw Industries | Industry distribution | Industry groups >=2 / >=3 | Official Sectors | Sector distribution | Sectors >=2 / >=3 |
|---|---:|---|---:|---:|---|---:|
| 2022-08-05 | 27 | `1:18, 2:4, 3:2, 4:1, 5:2` | 9 / 5 | 15 | `1:5, 2:2, 3:2, 4:2, 5:3, 8:1` | 10 / 8 |
| 2023-08-07 | 29 | `1:19, 2:6, 3:1, 4:1, 5:2` | 10 / 4 | 15 | `1:5, 2:3, 3:1, 4:1, 5:4, 10:1` | 10 / 7 |
| 2024-08-07 | 28 | `1:17, 2:7, 3:1, 4:1, 5:2` | 11 / 4 | 14 | `1:4, 2:3, 3:1, 4:1, 5:4, 11:1` | 10 / 7 |
| 2025-08-07 | 30 | `1:21, 2:5, 3:2, 5:2` | 9 / 4 | 16 | `1:6, 2:4, 3:1, 4:1, 5:3, 11:1` | 10 / 6 |

Every raw Industry used by a Baseline-eligible stock maps to exactly one
official Sector. There are no unresolved mappings.

## Unchanged protocol elements

The primary metric itself is unchanged. Ranking dates, future horizons,
historical constituent membership, price policy, accounting contract,
fundamental policy, Baseline V1 formulas and ranking behavior, and Research V2
formulas, weights, eligibility, and ranking behavior all remain unchanged. No
outcome-dependent decision was made.
