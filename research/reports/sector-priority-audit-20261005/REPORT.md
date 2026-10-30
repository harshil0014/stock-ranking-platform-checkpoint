# Primary objective: rank stocks within their sector

Date: 2026-10-05.

The user's primary objective is to select strong stocks **within each sector**. Global stock ranking is secondary. This means comparing pharmaceutical companies with pharmaceutical companies, banks with banks, and so on; it does not mean ranking sectors against one another.

## Correction to the preceding audit

The preceding global Top 20 audit answers a different question. Its global return, drawdown and concentration comparisons remain valid within their stated scope, but cannot decide which model best ranks sector peers. In particular, a healthcare-heavy global Top 100 is not by itself evidence that within-sector ordering is poor.

The UI already exposes `personalized_sector_rank` and its eligible peer count. However, the current Closing High score combines global percentile features and a globally developed V17 component, then orders eligible stocks within each sector. A sector rank in the UI does not establish sector-specific optimization or validation.

## Primary evaluation contract

- Compare models on identical eligible stocks within the same sector, date and investor profile.
- Evaluate the Top 3 within sectors with at least five comparable stocks. Keep small and unclassified groups visible in coverage, without treating singleton ranks as successful predictions. Top 1 and Top 5 sensitivity checks should accompany a full model selection study.
- Measure Top 3 return, downside, target achievement, shortfall, NDCG, and ordering across sector peers. Global portfolio metrics are secondary.
- Average dates within each sector, then weight sectors equally. Publish each sector's results so aggregate improvement cannot conceal persistent sector-specific losses.
- Treat Baseline V1 and strict Research V2 as primary sector comparators. Preserve their original data requirements; do not substitute a global score or imputed fundamental model and call it Baseline/V2.
- Evaluate all investor profiles, old-high/recovery cases, short-history stocks and execution eligibility within sectors before selecting a replacement.
- Use historical point-in-time sector membership for validated historical claims. Today's product classifications applied backward are a retrospective diagnostic only.
- Test sector-relative feature normalization as a candidate; do not assume that it improves performance or change production weights before comparison. Keep the explicit closing-high component in the candidate design.

## Initial within-sector diagnostic

The accompanying runner compares current recovery-aware Closing High with Original Personalized, V17, refined V17, Closing High priority and Closing High confirmation on the default `base7500` profile across 44 dates. All six scores share exactly the same stock population within each evaluated sector/date.

It uses `product_sector` from the current application's sealed facts, rather than an older enrichment map that mixes broad labels such as Industrials with narrower industry labels. Current product membership is still not historical membership.

### Result: changing the objective changes the comparison

Equal-sector averages of within-sector Top 3 median constituent XIRR:

| Model | 2016–2019 | 2020–2023 | 2024–2025 |
|---|---:|---:|---:|
| Current reviewed Closing High score | 3.51% | 31.92% | −0.76% |
| Original Personalized | 1.08% | 35.73% | −3.67% |
| V17 | 3.11% | 33.57% | −2.52% |
| V17 refined | 3.22% | 33.66% | −2.35% |
| Closing High priority | 2.68% | 34.91% | −1.40% |
| Closing High confirmation | 3.50% | 31.98% | −0.50% |

The three periods include 45, 47 and 49 evaluated sectors respectively. The current score beats V17 on this return measure in the early and recent periods, but **loses in 2020–2023**, whereas the preceding global comparison favored current return in every period. This demonstrates why global performance cannot select the sector-ranking winner. These are constituent XIRR summaries, not an equal-weight portfolio XIRR or investable portfolio return.

Outputs:

- `equal_sector_summary.csv`: date averages within sectors, then equal sector weighting.
- `sector_period_metrics.csv`: each sector's gains and regressions.
- `sector_date_comparisons.csv`: paired observations with Top 3 metrics.
- `sector_coverage.csv`: evaluated, small and unclassified groups.
- `protocol.json`: scope, counts and assumptions.

This is an initial diagnostic, **not** a complete all-model, all-profile sector validation. Baseline and strict Research V2 require their appropriate historical feature cohorts. The historical current score also excludes some recent deployment changes, as documented in the earlier audit. Repeatedly researched outcomes are not a fresh lockbox.

No production weights, sector assignments or UI behavior were changed by this audit.

Reproduce with:

```powershell
python research/runners/sector_priority_audit_20261005.py
```
