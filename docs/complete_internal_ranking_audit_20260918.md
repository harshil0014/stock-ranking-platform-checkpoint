# Complete internal ranking audit â€” 18 September 2026

## Final architecture decision

The strongest defensible architecture is a governed hierarchy, not an
unqualified replacement by one model:

1. **Validated Ridge + price-multifactor ensemble** is the strongest current
   challenger where its complete price feature vector exists. Its locked test
   remains materially stronger than Baseline, but its current-survivor and
   current-sector-label limitations remain disclosed.
2. **Baseline V1 evidence tiers** remain the deployable complete-universe
   ordering and fallback: `PRIMARY_5Y`, `REDUCED_3Y`, `REDUCED_1Y`, then
   `RECENCY_ONLY`. Lower-evidence tiers never alter primary ranks.
3. **Strict Research V2** remains the audited-fundamental view where all nine
   point-in-time inputs pass the unchanged contract. It is not imputed across
   the broad universe.

This keeps the empirically strongest challenger visible without presenting a
survivorship-limited retrospective result as prospectively proven. The product
does not force incomplete rows into a stronger-looking model.

The later Complete Universe layer does not alter this frozen observed-evidence
audit. It adds a separately fingerprinted, confidence-adjusted product view in
which all estimates are cell-coded and the original snapshot remains intact;
see `docs/complete_universe_completion_20260920.md`.

The final Complete Universe scores were subsequently compared with this same
pre-frozen judgment file, without adding post-hoc judgments. Agreement is
**95.0158%** across the same 213,345 independently orderable pairs. All 4,436
identities have a final stock-level review row; the 449 identities for which no
order existed before completion are reviewed separately and excluded from the
agreement denominator to preserve independence.

## Exhaustive Codex-vs-system method

The audit used no network access, third-party ranking, future outcome, or new
open-source benchmark. It inspected every row in the accepted company-fact
snapshot and recombined only evidence already inside the project:

- the raw Baseline price/history inputs, independently percentile-normalized;
- the outcome-blind validated price-ensemble signal where available;
- current quality, growth, balance-sheet, pledge, and cash-conversion fields;
- earnings yield as a modest valuation check;
- sector-aware treatment that excludes industrial ROCE and debt/equity from
  financial-company comparisons.

### Independence and freeze protocol

The 85% threshold is a reporting threshold, never a fitting objective. Before
the comparator is allowed to read production scores or ranks, the audit now:

1. builds the independent judgment ordering from evidence-only columns;
2. writes `frozen_codex_judgments.csv` to the fresh audit directory;
3. hashes that file and reads it back from disk;
4. only then compares the immutable judgments with production ranks.

The freeze function does not require or access the production score or rank
columns. The comparator rejects a changed universe, eligibility population,
sector, or evidence-tier scope after the freeze. It also rejects a supplied
candidate model when frozen judgments are being consumed. If agreement is
below 85%, the real result is returned with `agreement_target_met: false`;
the audit does not throw away, suppress, or retune a below-target result.

No system weight, feature, classification, or rank is optimized against the
frozen judgments. Genuine corrections must be justified by the project's
underlying evidence and normal model validation. A new benchmark may only be
frozen as a separately identified audit cycle, never silently overwritten.
The earlier v1 run directories are retained only as historical artifacts and
are superseded for agreement claims by the post-freeze v2 run documented here.

The audit comparison is within `(sector, evidence tier)`, exactly matching the
scope in which a production rank is meaningful. Pairwise agreement gives full
credit to concordant ordering, half credit when only one side is tied, and
compares every possible within-scope stock pair. A stock is a meaningful
disagreement when its independent audit rank moves by more than 20% of its peer
group and the group has at least five members.

## Results

| Check | Result |
|---|---:|
| Accepted ordinary-equity identities audited | 4,436 |
| Ranked identities audited | 3,987 |
| Explicitly unranked identities audited | 449 |
| Product sectors | 58 |
| Sector/tier peer scopes | 194 |
| Within-scope stock pairs compared | 213,345 |
| Pairwise Codex/system agreement | **89.6787%** |
| Required agreement | 85% |
| Meaningful rank displacements investigated | 236 |
| Mechanical score/rank errors remaining | 0 |
| Duplicate ticker or ISIN identities | 0 |
| Universe/count reconciliation | PASS |

All 236 remaining meaningful disagreements are supported model-scope
differences: the production rank is a documented price-history rank, while the
audit may move a company because the validated price ensemble, quality/risk,
or valuation evidence points differently. Those differences do not establish
that the Baseline calculation is wrong, so they were retained and explained
row by row instead of being forced to match the audit.

## Genuine defect corrected

The pass found 68 securities whose ranking history and accepted exact-identity
current reference implied one-year gross returns differing by more than the
wide `[0.80, 1.25]` consistency band. These included clear price-scale and
corporate-action-sensitive discontinuities. Previously, they could remain in a
sector rank even though their price bases were inconsistent.

The corrected rule is conservative:

- it never substitutes the reference return into Baseline;
- it does not guess a split, demerger, or adjustment factor;
- it assigns `ONE_YEAR_RETURN_REFERENCE_CONFLICT` and removes the unsafe row
  from peer ranking until the basis is reconciled;
- it applies equally to official-sector and expanded-product routes.

After correction, the ranked count is 3,987. The 449 unranked reasons reconcile
exactly: 217 insufficient history, 131 unclassified, 68 one-year return basis
conflicts, 31 missing history, one stale current price, and one current-price
mismatch.

## Reproducibility

Two post-freeze v2 audit builds are byte-identical with fingerprint
`5440b5e552e8da796ef10805f457d3b6f0e87bff378cbb01e645e875d0021998`.
Their frozen judgment artifact has SHA-256
`3181228540a8f2d76ab4971341df8ea83a9c6dd7855127304310a22bab7e57be`.
The accepted company-fact fingerprint is
`4064dc5b0a12fc385150a08e23a61f230b0f2acfcee76e394c8e80cee48d741e`;
the accepted market fingerprint remains
`98adc0296bff77fd44fc4c6815692a86033b14763d689791df14752550983eb1`.
The refreshed current ensemble fingerprint is
`1c7cc263bb24fdc9c09f553cc828c09d5069b914d90bd89d6e266e70f66c853e`.

The authoritative row-level evidence is in
`data/analysis/codex_complete_universe_audit_20260918_run_06/`:
`frozen_codex_judgments.csv`, `stock_by_stock_audit.csv`,
`meaningful_disagreements.csv`, `sector_reconciliation.csv`, `summary.json`,
and `manifest.json`.
