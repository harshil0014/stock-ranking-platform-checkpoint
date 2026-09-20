# Complete-universe ranking and imputation layer — 20 September 2026

## Result

The accepted ordinary-equity universe is now complete in a separate,
provenance-preserving product layer:

| Check | Result |
|---|---:|
| Accepted identities | 4,436 |
| Completed identities | 4,436 |
| Ranked identities | 4,436 |
| Assigned sectors | 4,436 |
| Product sectors | 58 |
| Originally unranked, now resolved | 449 |
| Originally unclassified, now resolved | 131 |
| Originally blank source cells | 402,069 |
| Blank cells in completed artifact | **0** |
| Rank consistency errors | **0** |
| Duplicate ticker or ISIN identities | **0** |

The accepted observed snapshot remains unchanged with fingerprint
`4064dc5b0a12fc385150a08e23a61f230b0f2acfcee76e394c8e80cee48d741e`.
The completion layer never writes estimates back into that snapshot.

## Estimate provenance

`completed_company_facts.csv` is the no-blank presentation/model view.
`field_estimate_codes.csv` supplies a cell-level code for every original field:

- `0`: observed;
- `1`: sector median or mode;
- `2`: universe median or mode;
- `3`: explicit low-confidence fallback;
- `4`: internal proxy field;
- `5`: conflict reconstruction;
- `6`: exact internal taxonomy mapping;
- `7`: name/taxonomy inference;
- `8`: complete-universe derived model field.

The codebook records the confidence attached to each method. Consequently, a
filled value cannot silently masquerade as an observation. The immutable
accepted snapshot remains available underneath for the original missing state.

## Classification completion

Observed current-product sectors are retained. Missing sectors are resolved in
this order:

1. exact mappings learned from accepted internal taxonomy fields;
2. conservative company-name/domain rules and internal name-token peer models;
3. an explicitly very-low-confidence `Diversified` fallback when no narrower
   internal evidence exists.

All 131 formerly unclassified identities are included in
`resolved_exclusions_audit.csv` with their sector method, confidence, rank and
review disposition.

## Complete ranking architecture

Every company receives a single full-sector rank. The outcome-blind model uses:

- price/history signal: 55%;
- validated current price-ensemble signal: 20%;
- sector-relative quality, growth and risk: 20%;
- valuation: 5%.

Missing inputs are filled hierarchically from internal sector peers and then
the whole accepted universe. The raw score is shrunk toward the neutral sector
midpoint according to the fraction and quality of observed inputs. This makes
weak evidence less extreme instead of excluding the company or pretending the
estimate is precise. Ranks are unique, contiguous and deterministic inside
each completed sector.

Financial sectors continue to exclude conventional industrial ROCE and
debt/equity from the quality aggregate. The 68 return-basis conflicts use the
accepted exact-identity return reference where available, otherwise an
explicitly coded peer estimate; the conflicting source history remains intact.

## Website behavior

The default Complete Universe view now shows all 4,436 accepted securities as
ranked. Company pages read the completed presentation values and expose an
`Estimate Provenance` section listing every estimated field, method and
confidence. Strict Research V2 remains separate and retains its point-in-time
eligibility rules; completion estimates do not enter frozen historical tests.

## Authoritative artifacts

The authoritative build is
`data/analysis/complete_universe_20260918_run_05/`:

- `completed_company_facts.csv`;
- `field_estimate_codes.csv`;
- `estimate_codebook.json`;
- `complete_rankings.csv`;
- `resolved_exclusions_audit.csv`;
- `field_completion_summary.csv`;
- `summary.json` and `manifest.json`.

Build fingerprint:
`b965968004c7fdfa661c126a937b801aa5c5ae8ee705629d8d640821a1764fc8`.

Run 05 is a byte-identical rebuild of run 04, establishing deterministic
reproduction. The final comparison against the previously frozen independent
Codex judgments is stored in
`data/analysis/completed_universe_frozen_audit_20260920_run_01/`. It contains
one row for every one of the 4,436 identities and reports **95.0158%** pairwise
agreement across all 213,345 pairs for which an independent ordering existed
before completion. The 449 originally unrankable identities are individually
reviewed but deliberately excluded from that agreement denominator; no
post-hoc judgment was invented for them.

No network access, third-party ranking, new benchmark, or future outcome was
used to construct this layer.
