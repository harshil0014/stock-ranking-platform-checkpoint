# Locked V13 prospective validation — 2025-09-30 decision

**Verdict: FROZEN CHAMPION RETAINS.** V13 improves several aggregate measures, but the repaired official-price run shows a material weekly drawdown regression and a 12M profile shortfall/return regression. Keep production champion `d499580` frozen. No production, Railway, or website change was made.

## What was tested and when

The V13 policy and coefficients were fixed in [`locked_selection.json`](../../experiments/personalized-v13-20261002/locked_selection.json) (SHA256 `dad3ce68b22a1f744650e501505a3ebc78dc7c4bd39c3247982c4ed84bcac13b`). The 30,305 champion/V13 decision scores were persisted before the outcome was read (SHA256 `5040171dd8a88f9202a89dadba4538537a3571d0eba6bcec0f631634c5a49926`); [`pre_reveal_record.json`](../../experiments/personalized-v13-20261002/prospective-2025-09-30/pre_reveal_record.json) and the pre-reveal audit state that no prospective outcome values were loaded. The 2025-09-30 decision was then simulated once through 2026-09-30. Original reveal record SHA256: `a714c2a994ea64f624aa3dae6e70ef001024ba245fe49d78d75a728bcfef17ca`. Scores and coefficients stayed fixed afterward.

The first reveal exposed a *data coverage* problem: old daily histories missed many September 2026 execution prices. Official NSE/BSE bhavcopies for September 1–18 were acquired **after the first reveal** to repair those dates. This repair used date/identity gaps, not outcome metrics, and retained the first reveal unchanged. Its comparison is explicitly a **post-reveal sensitivity analysis, not a second fresh blind test**. The repaired result is the more complete execution-price assessment and is decisive for risk, but its timing limits any promotion claim.

## One-time reveal, original evidence

| Metric | Champion | V13 | V13 − champion |
|---|---:|---:|---:|
| Coverage | 85.21% | 85.21% | +0.00 pp |
| Rank IC | 0.041345 | 0.040154 | -0.001191 |
| NDCG@20 | 0.502302 | 0.581032 | 0.078730 |
| Pairwise accuracy | 50.84% | 50.69% | -0.15 pp |
| Top-20 target achievement | 30.56% | 35.00% | +4.44 pp |
| Top-20 target shortfall | 13.68% | 12.00% | -1.69 pp |
| Median Top-20 XIRR | -2.65% | -2.28% | +0.38 pp |
| Mean Top-20 asset drawdown | -48.57% | -47.21% | +1.36 pp |

Outcome-available rows: 27,787 / 30,305. The weekly profile had only 33.9% score-and-outcome coverage because 2,416 rows had `MISSING_EXECUTION_PRICE`; its apparent drawdown improvement was therefore unreliable. Both rankers had identical coverage.

## Official-price repair sensitivity (post-reveal)

| Metric | Champion | V13 | V13 − champion |
|---|---:|---:|---:|
| Coverage | 91.63% | 91.63% | +0.00 pp |
| Rank IC | 0.043607 | 0.043064 | -0.000543 |
| NDCG@20 | 0.520304 | 0.604853 | 0.084549 |
| Pairwise accuracy | 50.84% | 50.67% | -0.18 pp |
| Top-20 target achievement | 32.78% | 38.33% | +5.56 pp |
| Top-20 target shortfall | 12.65% | 11.28% | -1.37 pp |
| Median Top-20 XIRR | -0.37% | -0.29% | +0.09 pp |
| Mean Top-20 asset drawdown | -48.07% | -47.86% | +0.21 pp |

Outcome-available rows: 29,884 / 30,305; score-and-outcome coverage 91.63% for both models. The repaired weekly coverage is about 91.6%, with `MISSING_EXECUTION_PRICE` reduced from 2,416 to 10. The repair audit verified 26 official source files and reduced identities with weekly schedule date gaps from 2,139 to 51. It did not change scores or selections.

NDCG@20 rises by +0.0845, Top-20 achievement rises +5.56 pp, and shortfall falls -1.37 pp. Rank IC and pairwise accuracy slip slightly. Aggregate drawdown improves only +0.21 pp. Mean Top-20 XIRR is excluded from selection because extreme stock-level annualizations dominate it; the median moves only +0.09 pp.

## All profile trade-offs (official-price repair)

Positive drawdown delta means a less negative drawdown. Negative shortfall delta is favorable.

| Profile | NDCG Δ | Achievement Δ | Shortfall Δ | Median XIRR Δ | Drawdown Δ | Top-20 overlap | Missing true 5Y, champion → V13 |
|---|---:|---:|---:|---:|---:|---:|---:|
| amount1000 | +0.1611 | +20.00 pp | -3.30 pp | +4.54 pp | +1.54 pp | 14/20 | 15.00% → 10.00% |
| amount50000 | +0.1466 | +15.00 pp | -4.47 pp | +8.12 pp | -0.54 pp | 14/20 | 5.00% → 5.00% |
| base7500 | +0.1079 | +5.00 pp | -2.56 pp | +0.09 pp | -0.30 pp | 16/20 | 5.00% → 5.00% |
| lookback12 | -0.0232 | -5.00 pp | +1.42 pp | -14.79 pp | +1.22 pp | 8/20 | 5.00% → 0.00% |
| lookback60 | +0.0208 | +0.00 pp | -1.61 pp | +0.00 pp | +2.20 pp | 17/20 | 0.00% → 0.00% |
| quarterly | +0.0844 | +0.00 pp | -0.12 pp | +0.72 pp | +2.56 pp | 14/20 | 10.00% → 5.00% |
| target10 | +0.0705 | +5.00 pp | -2.16 pp | +1.03 pp | -2.85 pp | 14/20 | 5.00% → 5.00% |
| target30 | +0.0667 | +0.00 pp | +0.69 pp | -2.10 pp | +1.59 pp | 15/20 | 5.00% → 5.00% |
| weekly | +0.1262 | +10.00 pp | -0.21 pp | +3.16 pp | -3.49 pp | 14/20 | 5.00% → 5.00% |

The decisive regressions are weekly drawdown **-3.49 pp**, despite weekly achievement +10.00 pp and shortfall -0.21 pp; and 12M achievement **-5.00 pp**, shortfall **+1.42 pp**, median XIRR **-14.79 pp**, and NDCG -0.0232. The 10% target drawdown worsens -2.85 pp; the 30% target shortfall worsens +0.69 pp. These are one decision date with overlapping profiles, not nine independent holdouts.

## History, concentration, and diagnostics

On this 2025-09-30 decision, V13 reduces top-20 missing observed true-5Y CAGR for the small-amount profile from 15% to 10%, 12M from 5% to 0%, and quarterly from 10% to 5%; most other profiles stay at 5% or 0%. The profile table gives every count. The previously frozen *current-universe* diagnostic at 2026-09-18 was V12 vs V13 missing true-5Y share of Top-20 **75% → 50%**, Top-50 **46% → 38%**, and Top-100 **28% → 24%**. These are distinct universes/dates.

Top-20 membership overlap ranges from 8/20 (12M) to 17/20 (60M), so the 12M regression coincides with substantial turnover. NYKAA was diagnostic only: in the 2025-09-30 base profile its score rank moved 1,063 → 1,112 of 3,114 scored; weekly 1,142 → 1,145 of 3,111. It was not used in fitting or selection.

## Evidence and limits

The decision evidence combines a frozen historical panel, the validated adjusted-history overlay, V2 Yahoo split provenance, new Yahoo price responses, official NSE/BSE daily bhavcopies, and official action responses. The original 2,517 official-action rows and 1,816 split rows were preserved; 4 official action rows and 2 Yahoo split events were appended. Three BSE action codes (511664, 511692, 526373) failed with HTTP 403 and were quarantined. The score audit retains observed, estimated, adjusted-history, and `RAW_RISK_ONLY` distinctions. No missing prices or actions were fabricated.

The initial 16 official bhavcopy files support September 21–30; the 26 repair files support September 1–18. September 14 was absent from both official exchange archives and was not fabricated. The first reveal outcome file, repair outcome file, source receipts, overlays, scripts, audits, and decision are individually hashed in [`artifact_manifest.json`](../../experiments/personalized-v13-20261002/prospective-2025-09-30/artifact_manifest.json). The repair's post-reveal timing and the weekly/12M regressions prevent promotion. Existing prior V13 blind and exposed-2025 diagnostics remain separate; no model search or retuning followed this prospective result.

Production HEAD remains `c12dd9b189bc71684bfac52606eb89abd5e383c7`. The [`prospective_decision.json`](../../experiments/personalized-v13-20261002/prospective-2025-09-30/prospective_decision.json) contains exact machine-readable values and promotion blockers.
