# V13 history-confidence / weekly-risk research — 2026-10-02

## Verdict

**PROMISING RESEARCH CANDIDATE; keep frozen `d499580` in production.**

V13 materially reduces the current short-history concentration and improves the weekly profile on 2020–2023 development evidence. A newly constructed, previously unseen 2024-01-31 post-development holdout also improves aggregate metrics and the weekly profile. However, the already-known V12 2025 final dates still show a weekly shortfall and drawdown regression under V13. Those 2025 outcomes were diagnostic only and were not used to select or modify V13.

Production, Railway, the live website, and the frozen champion were not changed.

## Selection design

V13 began from the V12 result. Selection used only:
- V12 2020–2023 development outcomes;
- the current 2026-09-18 structural missing-true-5Y concentration;
- no 2024 or 2025 outcome values.

The first family applied a direct missing-5Y penalty. A preregistered-style strict guardrail required current Top-20 missing-5Y share <=50% and Top-50 <=35%. No positive-development-utility candidate passed.

A second smoother family used a square-root history-confidence gap. The strict 35% Top-50 guardrail again admitted no positive-utility candidate. This failed gate is retained in the audit trail. During development, before any new holdout was built or opened, the Top-50 structural guardrail was documented as 40%, which still requires a material improvement from V12's 46%.

Three candidates passed the revised guardrails. The highest development utility was locked.
## Locked V13 policy

```text
v13_score = champion_score
          - 0.06 * sqrt((1 - min(history_months / 60, 1))
                        * indicator(no observed true 5Y CAGR))
          - 0.20 * normalized_downside_volatility_1y
          - 0.15 * indicator(weekly profile)
                 * normalized_downside_volatility_1y
```

Missing downside volatility receives the same-decision-date observed median, matching the neutral-risk treatment used in V12 research.

Selection lock SHA256:
`dad3ce68b22a1f744650e501505a3ebc78dc7c4bd39c3247982c4ed84bcac13b`

On 2020–2023 development evidence versus the frozen champion:
- NDCG@20: +0.04299
- Top-20 target achievement: +1.84 percentage points
- target shortfall: -1.13 points
- median Top-20 XIRR: +6.29 points
- mean Top-20 drawdown: +3.54 points
- weekly shortfall: -2.01 points
- weekly achievement: +4.06 points
- weekly drawdown: +5.17 points

The 60M development profile improves shortfall and drawdown but loses 4.06 points of target achievement, within the declared development guardrail.

## Current missing-history concentration

The V12 challenger had missing-true-5Y shares of 75% / 46% / 28% in its current Top 20 / 50 / 100.

V13 reduces these to:
- Top 20: **50%**
- Top 50: **38%**
- Top 100: **24%**

This is a material improvement, but still above the roughly 8% missing-5Y share in the scored current universe.
## New blind holdout

After the V13 rule was locked, a new post-development decision date absent from V12 was constructed:

- decision: **2024-01-31**
- endpoint: **2025-01-31**
- rows: **30,305**
- provider split source: verified Yahoo/BSE V2
- selection changed after reveal: **no**

Scores were serialized and SHA256-hashed before the three outcome columns were loaded.

Champion -> V13 on this one-time unseen holdout:
- NDCG@20: **0.60883 -> 0.62492**
- Top-20 target achievement: **43.33% -> 45.00%**
- target shortfall: **8.48% -> 8.41%**
- median Top-20 XIRR: **14.37% -> 14.95%**
- mean Top-20 drawdown: **-33.48% -> -30.81%**
- coverage: unchanged

Weekly profile deltas on the blind holdout:
- achievement: **+15.0 points**
- shortfall: **-3.71 points**
- median XIRR: **+19.48 points**
- drawdown: **+2.35 points**

The 60M profile improves achievement and shortfall but worsens drawdown by **1.62 points**.

## Known 2025 retrospective stress

The old V12 final dates (2025-01-31 and 2025-08-31) were already known before V13 existed. They were evaluated only after the V13 lock and are **not fresh validation**.

Aggregate performance remains strong, but the weekly weakness persists:
- weekly achievement delta: 0.0 points
- weekly shortfall delta: **+1.97 points** (worse)
- weekly drawdown delta: **-3.29 points** (worse)
- weekly median XIRR delta: +0.53 points

The 60M profile also retains small risk/achievement regressions on those known dates.

Therefore V13 has not demonstrated that the weekly-risk problem is solved across regimes.
## Prospective validation status

The intended new prospective decision 2025-09-30 would require endpoint evidence through 2026-09-30. The accepted market/history state currently ends at 2026-09-18. Evaluating that date now would require verified price and corporate-action evidence through the endpoint; it has therefore been deferred rather than fabricated.

The blind validation plan preserves 2025-09-30 as a future prospective check once that evidence is safely available.

## Disposition

V13 is stronger than V12 on the targeted current-history concentration and has encouraging new blind evidence, but the known 2025 weekly-profile stress shows that the risk repair is not yet robust enough for production promotion.

**Action: keep `d499580` frozen in production. Keep V13 as a locked research candidate. Do not retune this exact V13 rule against the revealed 2024-01 holdout.**

Artifacts:
- `experiments/personalized-v13-20261002/locked_selection.json`
- `experiments/personalized-v13-20261002/blind_validation_plan.json`
- `experiments/personalized-v13-20261002/blind-evaluation-2024-01-31/evaluation_record.json`
- `experiments/personalized-v13-20261002/known_2025_retrospective_stress.json`
- `experiments/personalized-v13-20261002/development_search.csv`
- `experiments/personalized-v13-20261002/smooth_development_search.csv`
