# Same-cohort Baseline V1 vs Research V2

## Decision

The comparison machinery is **GO**. It proves that both models use the same
point-in-time-safe security cohort, sector labels, and 12-month outcome row.
The observed result is directionally more favorable to Research V2, but the
sample is far too small to establish model superiority, persistent alpha, or
market outperformance.

Generated evidence is stored under the ignored directory
`data/walk_forward/same_cohort_comparison_v1/`. Its deterministic comparison
fingerprint is
`ef85504249936320c4132b1017e6072c1352e04371bcc31565d178be01d8d30f`.

## Frozen protocol

- Protocol: `same_cohort_baseline_v1_vs_research_v2_v1`.
- Ranking dates: 2022-08-05, 2023-08-07, 2024-08-07, and 2025-08-07.
- Cohort rule: the accepted Research V2 point-in-time eligibility result is
  frozen first; Baseline V1 is recalculated only on those identities.
- Identity: exact official ISIN. Tickers remain display metadata. All 23
  distinct securities resolved one-to-one; no fuzzy mapping was used.
- Sector: the same accepted historical NSE Indices Sector-tier label is passed
  to both models. Cross-sectional calculations use only the frozen comparison
  cohort.
- Outcome: the existing frozen `ADJUSTED-PRICE FUTURE RETURN`, using the exact
  ranking-date adjusted close and the last adjusted close on or before the
  12-calendar-month target. It is calculated once and joined to both models.
- Missing outcome: exclude that identity from both performance sides. The
  accepted run had zero such exclusions.
- Selection: retain the existing sector-relative top-stock convention and also
  report top-`min(3,N)` per sector. Scores are never compared across models.

The blind-prediction fingerprint remains
`c438c31967e1f2685bbe77d85db6ca44617e024c699dba3749ee3523af6e401d`;
the preregistered protocol remains
`a81278b799e1a61c3684f3b319fb14e2f6f0db6a2bdad1cd79b2ce13fd6f8576`;
and the sector-taxonomy amendment remains
`7f8c5d40de88077f3b6afcd471d0db4377fab567d2839e719a71ee6b11ae7163`.

## Actual model map

Baseline V1 consumes the ranking-date price, price anchors one, three, and five
years earlier, and the latest recorded/study-period high date. It calculates
one-year return, three- and five-year CAGR, and days since that high. Within
each sector it competition-ranks each metric in its documented direction and
uses their equal-weight mean rank as `baseline_score`. The comparison calls the
unchanged `calculate_baseline_rankings` path on the restricted cohort.

Research V2 consumes adjusted daily price history available through the
ranking date and the latest eligible audited standalone fundamental record for
which both `period_end` and `available_date` are on or before that date. It
requires the three price anchors, at least two trailing returns, ROCE,
debt-to-equity, and YoY profit growth. Its nine factors are one-year return,
three- and five-year CAGR, recorded-high recency, one-year annualized
volatility, three-year maximum drawdown, ROCE, debt-to-equity, and profit
growth. It applies the unchanged within-sector average-rank-range component
scores and accepted weights of 10, 10, 10, 5, 12.5, 12.5, 15, 10, and 15
percent.

The price-only versus nine-factor construction, factor directions,
normalization, and weights are intentional model differences. Fundamental
availability and opportunity-set size are not model differences in this test:
they are removed by freezing the strict V2 cohort first.

## Cohorts and agreement

| Ranking date | Cohort | Baseline/V2 input equality | Model-rank Spearman | Kendall tau-b | Mean absolute rank difference |
|---|---:|---|---:|---:|---:|
| 2022-08-05 | 8 | exact | 1.000000 | 1.000000 | 0.0000 |
| 2023-08-07 | 4 | exact | 1.000000 | 1.000000 | 0.0000 |
| 2024-08-07 | 8 | exact | 1.000000 | 1.000000 | 0.0000 |
| 2025-08-07 | 16 | exact | 0.645434 | 0.616553 | 0.3125 |

The date-level correlations pool sector-relative ranks and are descriptive.
The generated `sector_metrics.csv` is authoritative for sector-specific
interpretation. In total there are 36 date-security observations, all with one
shared valid outcome.

## Selection and outcomes

The top-one-per-sector selection was identical in 2022, 2023, and 2024. In
2025 it overlapped on 9 of 10 selections (Jaccard 0.818182). Top-`min(3,N)` was
identical on every date; most eligible sectors were so small that this selected
the entire sector.

| Date | Baseline top-one mean | V2 top-one mean | Baseline median | V2 median |
|---|---:|---:|---:|---:|
| 2022-08-05 | 8.7936% | 8.7936% | 13.9786% | 13.9786% |
| 2023-08-07 | 54.9432% | 54.9432% | 44.0132% | 44.0132% |
| 2024-08-07 | 3.3513% | 3.3513% | 3.3239% | 3.3239% |
| 2025-08-07 | 5.7412% | 7.4279% | 6.9382% | 6.9533% |

Under the existing primary 12-month sector-date evaluator, only three sectors
have at least three peers. Research V2 mean Rank IC is `0.0`; matched Baseline
mean Rank IC is `-0.04465819873852043`. Research V2 is higher once and tied
twice. Pairwise accuracy is `0.5384615384615384` versus `0.5`; mean top-stock
excess return is `0.02600583322281222` versus `-0.024191270104655188`; and mean
top-half-minus-bottom-half return is `0.016941199566721687` versus
`-0.009483250844733957`. These are descriptive unit-fraction returns, not a
trading backtest.

## Integrity and limitations

Formation inputs are rejected if they contain future-return or endpoint
columns. Baseline ranks are regenerated through the accepted implementation
and checked against the previously frozen matched ranks. ISIN sets, sectors,
outcomes, and row uniqueness are validated before evaluation. Two offline runs
produced byte-identical artifacts.

The cohorts are only 8, 4, 8, and 16, with many singleton sectors and only
three valid primary sector-date Rank IC observations. Accordingly the evidence
suggests a modest V2 directional advantage on this frozen sample but provides
**insufficient evidence** that Research V2 is generally better. The next
scientific step is broader strict point-in-time fundamental coverage followed
by a separately preregistered larger evaluation—not tuning either model on
these outcomes.
