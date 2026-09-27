# Canonical product consolidation

Date: 2026-09-27

Accepted product base: `2b481da9cdada5281ea6792bfbc431e6c89ae795`

Frozen champion: `d4995807163bef1ec4b297179e6c54a59c71f390`

## Product decision

The primary website has exactly two active ranking modes: Baseline and Personalized. Personalized continues to use whole-share execution, contribution scheduling, residual cash and affordability, accepted corporate actions, Goal scoring, the seven frozen features, sealed LightGBM LambdaRank, and the frozen 67/33 blend.

Research V2 remains available only as explicitly archived research, methodology, validation, and provenance evidence. Rejected regime and ranker challengers are not active product choices.

## Runtime and deployment contract

The external runtime pack remains `research/runtime/personalized-ui-d499580.npz` with SHA-256 `515eac8ffc555a571406a4a41f9d931a016cb6280871a3d89f59846d2692ed0c`.

The container installs LightGBM 4.6.0, SciPy 1.18.1, and `libgomp1`; includes the sealed freeze, runtime audit, accepted corporate-action ledger, and resulting-security terms; and reads the runtime pack from the mounted research volume. An isolated local container returned the exact champion SHA, weights 0.67/0.33, 3,265 personalized results, 1,171 explicit fallbacks, 4,436 visible rows, and retained FRONTSP and KPL as product fallbacks.

External Railway credentials and CLI were unavailable during consolidation. The old `professor-railway-deploy-20260920` branch must remain until the external service is switched to canonical `main` and verified.

## Branch classification before cleanup

- `personalized-ranking-product-20260926`: accepted product source; promoted to canonical `main` and then obsolete.
- `professor-railway-deploy-20260920`: old deployment branch; temporarily retained because the external Railway reference cannot be inspected or changed locally.
- `personalized-investing-20260922`, `product-completeness-recovery-20260908`, `upstox-pit-recovery-20260914`, and `competition-demo-website`: completed ancestors of the accepted product; obsolete after canonicalization.
- `personalized-open-source-regimes-20260926`: rejected challenger; preserved by annotated tag `open-source-regime-challenger-5ed1c43-20260926`.
- `personalized-open-source-rankers-20260926`: rejected challenger with unique historical commits; preserved by a dedicated archival annotated tag before branch deletion.
- `website-gap-recovery-v1`: unpromoted recovery work with unique historical commits; preserved by a dedicated archival annotated tag before branch deletion.
- local Qlib, historical Baseline, Research V2, walk-forward, and open-source research branches: completed ancestors already contained in canonical history.

No protected freeze, prospective shadow artifact, annotated challenger tag, release, or release asset is altered by consolidation.
