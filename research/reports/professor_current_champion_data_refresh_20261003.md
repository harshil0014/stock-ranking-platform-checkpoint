# Frozen champion on the fuller current company data

## Result

The sealed `d499580` LightGBM LambdaRank model and the exact **67% Goal / 33% ranker-percentile** blend were rerun research-only for the **2026-09-18 decision**. The original 30,467 frozen profile/security rows, execution outcomes, Goal scores, risk features, and model were held fixed. Only previously missing 3Y and 5Y model-feature cells backed by the trusted professor current-data overlay were filled. The original frozen predictions and blend reproduced to better than `1.2e-16` before any fill was applied.

This is a **data sensitivity result, not a new trained model**. It does not use any future outcome, alter weights, or change production.

## Rank changes

The trusted current overlay contains 467 new 1Y growth values, 487 new 3Y values, and 543 new 5Y values in ordinary current fields. The champion's seven model features include **3Y and 5Y CAGR, but not 1Y CAGR**; the 1Y fills therefore cause zero champion rank changes. In the frozen model cohorts, 305 profile/security rows gained 3Y and 965 gained 5Y; 985 rows (243 distinct stocks) gained at least one of these features. Only 641 of those rows had an available complete champion score. Score coverage stayed exactly unchanged.

Across nine profiles, **24,129 scored rank positions changed**: 641 directly filled rows changed position, and 23,488 other rows shifted indirectly because percentile ranking reordered the same cohort. This count is across overlapping profile rows, not independent stocks. **3,749 distinct stocks** moved in at least one profile. The 60M profile is unchanged because its 18 newly filled rows were not score-eligible.

| Profile | Scored rows | Filled feature rows | Top-20 overlap | Top-50 overlap | Top-100 overlap |
|---|---:|---:|---:|---:|---:|
| ₹1,000 | 3,260 | 104 | 15/20 | 44/50 | 92/100 |
| ₹50,000 | 3,264 | 104 | 15/20 | 43/50 | 94/100 |
| Default ₹7,500 | 3,265 | 104 | 15/20 | 44/50 | 93/100 |
| 12M | 3,747 | 172 | 17/20 | 37/50 | 74/100 |
| 60M | 2,866 | 18 | 20/20 | 50/50 | 100/100 |
| Quarterly | 3,263 | 105 | 15/20 | 43/50 | 93/100 |
| 10% target | 3,265 | 104 | 15/20 | 42/50 | 94/100 |
| 30% target | 3,265 | 104 | 14/20 | 44/50 | 94/100 |
| Weekly | 1,197 | 170 | 18/20 | 47/50 | 97/100 |

The complete new [Top 20](../../experiments/professor-current-fallback-20261003/champion-data-refresh-research-v1/new_top20.csv), [Top 50](../../experiments/professor-current-fallback-20261003/champion-data-refresh-research-v1/new_top50.csv), and [Top 100](../../experiments/professor-current-fallback-20261003/champion-data-refresh-research-v1/new_top100.csv) contain every profile. [Every old/new rank and score](../../experiments/professor-current-fallback-20261003/champion-data-refresh-research-v1/all_profile_rank_comparison.csv.gz), [Top-set entries/exits](../../experiments/professor-current-fallback-20261003/champion-data-refresh-research-v1/top_membership_changes.csv), and [the largest moves](../../experiments/professor-current-fallback-20261003/champion-data-refresh-research-v1/largest_rank_moves.csv) are also retained.

## Default-profile Top 20 and largest moves

The default Top 20 keeps 15 of its former names. New ranks 1–20 are: **NYKAA, SJS, BSE-543373, BSE-543543, BSE-543616, PAYTM, BSE-543953, AVALON, SUPRIYA, YATHARTH, ABSLAMC, BSE-519413, DATAPATTNS, PARAS, PRIVISCL, SHRIRAMFIN, SHRIPISTON, BSE-511185, THYROCARE, AARTIPHARM**. The five entries are PRIVISCL, SHRIRAMFIN, SHRIPISTON, THYROCARE, and AARTIPHARM.

All five default-profile exits gained a previously missing 5Y CAGR: **SHAILY 3→35, PTCIL 7→94, INDOBORAX 13→126, STEELCAS 18→47, CHOICEIN 19→48**. The largest default-profile declines were MEDICO **1,427→2,705**, GOYALALUM **938→2,198**, and ASHOKAMET **1,401→2,532**; each also gained a 5Y value. The largest upward moves were SHIVALIK **2,150→1,990** and VCL **1,611→1,508**. These movements come from the frozen model's response to filled inputs and percentile reordering; there is no professor-source penalty.

The default Top-20 missing-5Y share falls from **18/20 to 14/20**, but remains high. None of the new default Top 20 directly gained a CAGR value; the five newly filled former Top-20 names left it. This is a material sensitivity of the frozen champion to missing 5Y inputs.

## NYKAA diagnostic

NYKAA gained no 3Y or 5Y model input in this overlay. Its 5Y value remains missing, so its rank moves only with peers:

| Profile | Old → new rank |
|---|---:|
| Default, ₹1,000, ₹50,000, quarterly, 10% target, weekly | **1 → 1** |
| 12M | 14 → 12 |
| 30% target | 5 → 4 |
| 60M | Outside the frozen cohort |

NYKAA was not an optimization target. Its persistence at #1 in the default profile despite missing 5Y history is a reason **not to connect this data refresh to the live ranking yet**. The professor values themselves are trusted; the concern is how the unchanged champion responds to newly present 5Y inputs.

## Reproducibility and scope

The frozen model, manifest, and rankings were hash-checked. The research runner required original LambdaRank predictions and the 67/33 blend to match the freeze to machine precision, then changed only blank `cagr_3y`/`cagr_5y` feature cells with exact-match professor values. The [machine summary](../../experiments/professor-current-fallback-20261003/champion-data-refresh-research-v1/summary.json), [independent audit](../../experiments/professor-current-fallback-20261003/champion-data-refresh-research-v1/audit.json), and [SHA256 manifest](../../experiments/professor-current-fallback-20261003/champion-data-refresh-research-v1/manifest.json) record the inputs and outputs. The accepted current snapshot, historical V12/V13 panels, frozen champion, production ranking, website, and Railway were not modified.

**Research decision:** keep the refreshed ranking offline. The new information exposes substantial missing-value sensitivity in the frozen champion, and the default Top 20 still has 70% without a 5Y input.
