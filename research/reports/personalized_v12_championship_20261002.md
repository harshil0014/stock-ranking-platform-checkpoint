# V12 personalized historical-depth championship — 2026-10-02

## Verdict

**PROMISING CHALLENGER. The frozen `d499580` champion stays in production.** The locked challenger improves every aggregate utility metric on the two untouched final decisions and keeps coverage. Its final weekly profile nevertheless worsens target shortfall by **2.61 percentage points** and asset drawdown by **2.65 points**. The current Top 20 remains **75%** without true five-year history against **7.96%** in the scored universe, and NYKAA remains global rank 1. These are material failures of the requested broad, low-regression and missing-history conditions. No deployment, frozen model, Railway setting, website behavior, V9/V10/V11 panel, or accepted production artifact was changed.

## V12 evidence and integrity

V12 is the authoritative panel at `experiments/personalized-deep-history-20261002/real-panel-v12/deep_panel.csv.gz` (SHA256 `c0b2f5f66836c487340237cc1df231e2f3d2835febcb09b84c0adffb1ab57371`). It has **50 decision dates**, **1,516,870 matured profile/security rows**, and **nine investor profiles**, from 2015-01-31 through 2025-08-31. Ten original source dates contribute **304,670 rows**; 40 reconstructed dates contribute **1,212,200 rows**. The original source rows were copied by the V12 consolidator. A separate post-lock comparison verified **all 56 columns of all 304,670 source rows** against V11 within `1e-12` CSV round-trip tolerance. V12 did not rerun collection.

The research-only structural audit verified every V12 output hash, all **40 checkpoint hashes**, no duplicate `(decision_date, profile_name, isin)` keys, exactly nine profiles on every date, valid decision/endpoint order, endpoints no later than 2026-09-18, exact date coverage, and unchanged source-date coverage. It loaded **no sealed outcome columns**. The two sealed dates each have **30,305 structural rows**. Status counts are 1,150,607 available, 317,247 insufficient history, 25,674 unresolved corporate action, 16,208 unresolved fractional entitlement, 3,087 missing execution price, 2,053 stale terminal, and 1,994 invalid history.

The authoritative V12 provider section is `provider_v2_propagation`: `yahoo-split-ledger-v2` has **3,790 successful** of 3,808 identities, **18 failures**, and **1,816 observed split events**. The ledger SHA256 is `eb4d839e4dc8edf21f3b71098bdf5a6ee215d9c99f0c265ec592a1da2e6be452`; the acquisition audit SHA256 is `1a42e7194ef9f80ff5666f5324609c3aef3f30eac9d0adc176262710749faf49`. V12 uses V2 on all 40 reconstructed dates, where identity coverage is typically **3,790 rather than V11's 3,704**; the ten original source dates retain their original 3,808-identity evidence. The inherited older provider fields are now explicitly labeled V11 lineage in V12 metadata. The official action ledger begins 2010-01-15, supporting the January 2015 full-60-month boundary. No older evidence was fabricated.

The panel's 12-month outcome windows overlap: **212 of 1,225 date pairs** share calendar days. The two final windows share **154 days, or 42.08%** of a year. They are two locked decisions, not two independent experiments. Current-universe survivorship and price-only retrospective outcomes remain limitations.

## Protocol, selection, and seal

The V12 protocol assigns 22 pre-2020 dates to early history, 16 dates in 2020–2023 to development, four 2024 dates to post-lock robustness, 2025-01-31 and 2025-08-31 to untouched final evaluation, and six other 2025 dates to post-lock diagnostics. Every scored fold trains only on labels with a **12-month endpoint strictly earlier** than the decision. Current company facts only map ISIN to a historical price-file key; no current sector or fundamental is used as a historical model feature. Historical missing-5Y growth is an explicit estimate shrunk toward a same-date global observed 5Y median. The preparation file left every 2024/2025 outcome blank, and the sealed-date outcome values were not indexed before lock.

The development search qualified **18 ranker configurations / 113 fixed settings** on four spaced 2020–2023 decisions, then evaluated **five distinct model finalists** on all 16 development dates. It also examined 28 fixed history-risk score adjustments and nine age/downside combinations, for **66 all-date development settings**. The search added the score-adjustment family after weak initial ranker results, using development data only. Four-grade XIRR/shortfall labels, XIRR-only relevance, history age, underwater duration, recorded-high position, volatility, no-Goal and no-3Y ablations, regularized LambdaRank, and restrained frozen/new blends were represented. Extreme arithmetic mean XIRR had zero selection weight. The selection rule rewarded aggregate shortfall, achievement, median return, ranking and drawdown while penalizing the worst date and applying profile/date gates.

The selected policy is simple and stock-agnostic:

```text
challenger_score = frozen_champion_score
                 - 0.05 × (1 - min(observed_history_months / 60, 1))
                          × indicator(no observed adjusted 5Y CAGR)
                 - 0.20 × min(max(one_year_downside_volatility, 0) / 2, 1)
```

Unavailable historical downside volatility receives the same-decision-date observed median, avoiding a missing-risk bonus. Current inference uses the provenance-aware v3 downside-volatility value. This candidate's development robustness-adjusted utility is **+0.00859**. It improves development NDCG by 0.04044, Top-20 achievement by 1.42 points, shortfall by 0.93 points, median XIRR by 6.61 points, and drawdown by 3.39 points; coverage is unchanged. Its worst development date still loses 6.11 points of achievement and 2.01 points of shortfall, which substantially reduces the robustness-adjusted utility.

The selected configuration was written before final outcomes were read. The final selection-lock SHA256 is `b0e7f8e94570fd7dd70a1da6f3a4bfa35c59a30653d283cc1f53489c458d3615`. It fingerprints the V12 panel, protocol, prepared label seal, V12 integrity audit, tournaments, selected coefficients, relevant code, v3 enrichment, and provider ledger. The initial lock is retained. The one-time evaluation record verifies the same lock hash and records no selection change after reveal. Python compilation and **14 focused tests** passed; all 13 files in the frozen champion manifest still match their original sizes and hashes.

## Champion versus locked challenger

Values are means across all date/profile blocks in each partition. Higher is better for IC, NDCG, pairwise accuracy, achievement, XIRR, and drawdown (less negative); lower is better for shortfall. The 2025 final partition was evaluated once after the lock. Previously exposed 2025 dates are separated as diagnostics.

| Metric | 2020–23 champion → challenger | 2024 champion → challenger | Untouched final champion → challenger | Other 2025 champion → challenger |
|---|---:|---:|---:|---:|
| Coverage | 79.29% → 79.29% | 87.57% → 87.57% | **90.30% → 90.30%** | 87.94% → 87.94% |
| Rank IC | -0.02820 → -0.02805 | 0.07872 → 0.08407 | **0.08890 → 0.09268** | 0.12425 → 0.12734 |
| NDCG@20 | 0.52539 → 0.56584 | 0.53130 → 0.59449 | **0.53354 → 0.62410** | 0.59989 → 0.69712 |
| Pairwise accuracy | 49.13% → 49.14% | 53.15% → 53.36% | **53.77% → 53.88%** | 53.89% → 53.96% |
| Top-20 target achievement | 56.18% → 57.60% | 27.78% → 34.72% | **31.39% → 40.56%** | 40.09% → 47.59% |
| Top-20 target shortfall | 8.28% → 7.35% | 14.20% → 12.92% | **14.38% → 12.64%** | 12.81% → 10.36% |
| Mean Top-20 XIRR | 416.50% → 565.51% | 54.11% → 108.38% | **178.67% → 340.17%** | 2402.97% → 3274.38% |
| Median Top-20 XIRR | 35.01% → 41.62% | -8.80% → 0.37% | **-10.10% → 4.02%** | 2.67% → 23.19% |
| Mean Top-20 asset drawdown | -35.40% → -32.00% | -43.98% → -41.25% | **-44.58% → -43.11%** | -44.39% → -41.90% |

Arithmetic mean XIRR is extremely sensitive to retrospective corporate-action outliers and was excluded from selection. The final result is strong in aggregate, but the two final dates differ: on **2025-01-31** NDCG improves 0.49402 → 0.62707, achievement 23.89% → 36.11%, shortfall 18.95% → 14.85%, median XIRR -24.73% → -8.91%, and drawdown -46.03% → -42.22%. On **2025-08-31** NDCG improves 0.57306 → 0.62113, achievement 38.89% → 45.00%, and median XIRR 4.53% → 16.94%, but shortfall worsens **9.81% → 10.42%** and drawdown **-43.13% → -44.00%**.

## Final profile regressions and Pareto limits

The table gives challenger minus champion on the two final decisions, averaged within each investor profile, in percentage points. Positive achievement, median XIRR, and drawdown are favorable; negative shortfall is favorable.

| Profile | Achievement Δ | Shortfall Δ | Median XIRR Δ | Drawdown Δ |
|---|---:|---:|---:|---:|
| ₹1,000 amount | +10.0 | -1.82 | +11.91 | +0.15 |
| ₹7,500 base | +12.5 | -3.08 | +9.84 | +2.30 |
| ₹50,000 amount | +5.0 | -0.28 | +1.87 | +0.33 |
| 12M lookback | +20.0 | -6.11 | +53.98 | +9.40 |
| 60M lookback | **-2.5** | **+0.08** | +1.61 | **-0.86** |
| Quarterly interval | +7.5 | -1.43 | +6.99 | +1.42 |
| 10% target | +15.0 | -2.40 | +14.19 | +0.50 |
| 30% target | +15.0 | -3.23 | +17.73 | +2.59 |
| Weekly interval | 0.0 | **+2.61** | +8.95 | **-2.65** |

The weekly shortfall rises **11.28% → 13.89%** and drawdown deepens **-46.45% → -49.09%**. Both final weekly dates individually worsen shortfall (+2.20 and +3.02 points); this is not just an average masking opposite signs. The 60M lookback has smaller but consistent risk/achievement losses. These are the main Pareto costs of the large aggregate gains. The strongest direct high/duration and no-3Y finalist blends failed development gates; a pure downside-volatility adjustment was close but had negative robustness-adjusted utility. The locked two-signal policy was best under the development selection rule. No 2025 result was used to change it.

Top-20 replacement fractions favor the challenger: **69.6% versus 75.7%** across development transitions, **83.1% versus 88.5%** in 2024, **79.4% versus 88.3%** across the two final dates, and **71.2% versus 78.8%** on other 2025 dates. The 2025 date windows overlap, so turnover and outcomes should not be treated as independent replications.

An outcome-defined, post-lock regime audit describes the broad universe's median 12-month base-profile XIRR. All 2024 and 2025 decisions fall in its negative-return bucket; there the challenger improves achievement, shortfall, median XIRR, NDCG, and drawdown. Of the 16 development dates, ten have universe median XIRR above 20%; their aggregate achievement delta is **-0.44 points**, though NDCG, shortfall, median XIRR, and drawdown improve. This is a descriptive sensitivity check, not a selection feature or a prospective market-regime forecast. Adjacent decision horizons overlap.

## History age, current ranking, and sectors

The v3 enrichment gives all **4,436** accepted identities a provenance-aware long-term growth value and recorded-high/full-history risk diagnostics; **3,129** have true adjusted 5Y CAGR, **1,307** an explicit estimate, and four BSE histories remain `RAW_RISK_ONLY` for risk diagnostics. The V12 historical feature preparation records 188,894 profile rows without a usable observed history path; their growth input is labeled `NO_HISTORY` and unavailable risk features receive neutral treatment in the selected score rule. Historical Top-20 missing-true-5Y share is generally near or below the scored-cohort share, but the current sealed champion ranking is unusually concentrated.

In the current base profile, both policies score **3,265** names; **7.96%** of that cohort lacks true 5Y history. The frozen champion's Top 20/50/100 shares are **90% / 46% / 29%**. The challenger reduces them to **75% / 46% / 28%**. This helps but does **not** remove the current missing-history bias. NYKAA is diagnostic only and remains **global rank 1 and Retailing rank 1** for both. Its v3 record contains 58.25 months of observed history, estimated -2.03% long-term growth, a recorded high 1,752 days earlier, and -72.09% full-history maximum drawdown. No identity-specific rule was fitted.

Current-sector labels were used only to inspect current Top-20 composition, never to train historical rows or grade historical sector outcomes. Both current Top 20s span 15 sectors and have at most two names in any one sector. There is no point-in-time historical sector classification in V12, so a historical sector-return claim would be misleading.

## Reproduction and disposition

The structural audit is `real-panel-v12/integrity_audit.json`; the post-lock full source comparison is `real-panel-v12/source_value_audit.json`. The locked championship outputs are in `experiments/personalized-deep-championship-20261002/v3/`: qualification and development leaderboards, the initial and final selection locks, final evaluation record, profile/date rows, outcome-regime and turnover audits, missing-history audit, current scores and sector composition, `audit_summary.json`, machine-readable `decision.json`, and a SHA256 manifest of 56 research files. The protocol is `research/protocols/personalized_deeper_walkforward_v2.json`; the resumable championship entry point is `research/runners/personalized_deeper_championship_v12.py`.

**Action:** retain the frozen production champion. The locked score adjustment is the strongest V12 research challenger, with real aggregate gains and good stability, but it has not met the profile-risk and current missing-history conditions needed for promotion. Its final outcomes must not be used to retune this same candidate. A later promotion attempt needs newly matured, unexposed dates and a development-only solution to the current Top-20 history concentration and weekly-profile risk.
