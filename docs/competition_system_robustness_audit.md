# Competition system robustness audit

Audit date: 2026-08-09  
Branch and starting commit: `walk-forward-validation` / `0509d78954e3fd35a9ed09f9577e5c2a6f1eb28d`

This is a fail-closed engineering audit performed after outcome reveal. It does not alter the Baseline V1 or Research V2 methods, weights, universes, classifications, identities, accounting adjudications, blind cohorts, labels, or evaluation metrics.

## Coverage matrix

| Property | Existing coverage before this audit | New test needed | Result |
|---|---|---|---|
| Predictor rows after cutoff cannot affect historical features | Yes: V2 future-row immunity; historical Baseline and blind-price cutoff tests | No | Pass |
| One instant after filing cutoff is excluded; boundary is consistent | Yes: real V2 and blind filing selection tests | No | Pass |
| Outcome columns cannot enter blind predictors | Yes: prohibited-field and written-bundle guards | No | Pass |
| Filing availability after cutoff cannot become eligible | Yes: XBRL, annual-report, blind adjudication, and rescue tests | No | Pass |
| Exact historical identity; no HDFC/HDFCBANK or DUMMYREL/JIOFIN substitution | Yes | No | Pass |
| Unknown sector/identity fails rather than using fuzzy substitution | Yes | No | Pass |
| Baseline/V2 order invariance and ties | Yes | No | Pass |
| Rank IC and pairwise ties | Yes | No | Pass |
| Weekend/holiday outcome endpoints never move past target | Partial: endpoint and calendar-target tests | Yes: shuffled calendar with a post-target row | Pass |
| Outcome-price order invariance | No direct guard | Yes | Pass |
| Duplicate outcome observations | No | Yes | Rejected explicitly |
| Mixed provider identity inside one frozen company-date | No | Yes | Rejected explicitly |
| NaN/infinite outcome prices | Endpoint-only validation | Yes | Rejected before labeling |
| Duplicate/missing/non-finite horizon labels | No direct guard | Yes | Rejected before evaluation |
| Historical sector drives thresholds; singleton/two/three-stock behavior | Partial | Yes | Pass |
| Cache prices and request provenance are hash bound | Price hash only | Yes | Both are now required |
| Protocol/blindness metadata checked at evaluation boundary | Blind fingerprint only | Yes | Protocol and outcome-blind flags now required |
| Missing and malformed Baseline/V2 inputs | Yes: schema, numeric, date, natural-key, anchor, and reason-code tests | No | Pass |
| Deterministic artifact export | Yes | No | Pass |
| Frozen source, weight, cohort, structure, and artifact guards | Partial | Yes | Pass |

## Findings and fixes

Two genuine engineering defects were found. Neither changes an accepted calculation or artifact:

1. Outcome labeling could select deterministically only when provider rows happened to have unique company-date keys and one provider identity. Duplicate dates could make selection depend on input order, and mixed provider symbols were not rejected. Label preparation now validates nonblank identities, one provider per company-date cohort, unique dates, and finite positive adjusted prices before calculation.
2. Evaluation verified the cached price hash but did not independently bind the request-provenance file to its cached hash. It now checks that hash and the frozen blind fingerprint before reading outcomes. Evaluation also rejects protocol/outcome-blind metadata drift and corrupt company-date-horizon panels.

No scientifically consequential defect was found. No research-frozen issue was modified or deferred.

## Audit results

- Temporal leakage: pass. Predictor requests remain cutoff-bounded; post-cutoff prices and dissemination are rejected or filtered by the existing contract; prohibited outcome fields cannot enter blind bundles. Evaluation depends on frozen predictions, but prediction preparation imports no evaluation output.
- Identity substitution: pass. Exact frozen provider symbols are required. HDFC cannot map to HDFCBANK, DUMMYREL cannot map to JIOFIN, and unresolved identities are not replaced.
- Sector taxonomy: pass. `historical_sector` controls grouping; `historical_industry` remains provenance. Singletons enter neither pairwise nor Rank IC, two-stock groups enter pairwise only, and three-stock groups enter Rank IC.
- Missing/malformed data: pass. Missing anchors, fundamentals, provider identities, mappings, invalid numerics, reporting-period mismatches, malformed dates, corrupt keys, and negative leverage produce explicit errors, exclusions, or reason codes. No imputation or fuzzy fallback was observed.
- Ties: pass. Baseline competition ranks, V2 rank-range scores, average-rank Spearman, 0.5 pairwise model-tie credit, excluded exact outcome ties, and ticker cutoff ordering are deterministic.
- Endpoints: pass. Each 3/6/12-month endpoint is independently the last observation on or before its calendar target. Post-target rows are not selected. The adjusted-price return formula is unchanged.
- Cache corruption: pass. Missing/truncated files fail through concise runner errors; altered prices, request provenance, protocol, blind fingerprint, outcome-blind status, and artifact inventories are detected.

## Frozen research and reproduction

- Protocol SHA-256: `a81278b799e1a61c3684f3b319fb14e2f6f0db6a2bdad1cd79b2ce13fd6f8576`
- Amendment SHA-256: `7f8c5d40de88077f3b6afcd471d0db4377fab567d2839e719a71ee6b11ae7163`
- Blind fingerprint: `c438c31967e1f2685bbe77d85db6ca44617e024c699dba3749ee3523af6e401d`
- Evaluation fingerprint: `04e29e8a0f641f900e2ef5ca6d6fe5252b75eff9b23a69fba3b6480f373606c1`
- Frozen eligible cohorts: 2022 `8`, 2023 `4`, 2024 `8`, 2025 `16`.
- Structural groups: `3` primary groups with at least three peers; `7` secondary groups with at least two peers.
- Local blind reconstruction: all 46 files byte-identical to the accepted blind bundle.
- Local evaluation reconstruction: all 9 files byte-identical to the accepted evaluation bundle.

## Residual risks and safe claims

Competition-safe claims supported by this audit are deterministic sector-relative ranking, explicit point-in-time cutoffs, exact historical constituent and identity reconstruction, frozen predictions before outcome reveal, explicit missing-data exclusions, and reproducible blind/evaluation fingerprints.

The project still cannot claim statistical conclusiveness, causal model superiority, paper/benchmark reproduction beyond the documented synthetic experiments, real-market generalization beyond the four frozen dates, portfolio profitability, execution feasibility, absence of all vendor-data errors, or investment usefulness. The primary walk-forward sample remains only three sector-date observations; Yahoo adjusted-price history is retrospective; strict filing availability sharply limits V2 coverage; and no transaction-cost, liquidity, or execution model exists.
