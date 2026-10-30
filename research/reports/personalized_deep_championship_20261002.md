# Deep historical walk-forward championship — 2026-10-02

## Verdict: FROZEN CHAMPION RETAINS TITLE

The locked research finalist is promising on the clean 2024 holdout, but does not meet the broad-robustness promotion rule. Its 60M lookback loses 12.2 percentage points of median Top-20 XIRR on the holdout. The exposed 2025 12M lookback loses 21.9 points of median XIRR, increases target shortfall by 2.1 points, and worsens drawdown by 4.3 points. The development record has large losses on 2020-03-31 and 2022-06-30. No production or frozen-champion artifact was changed.

## Evidence and integrity

The authoritative deep panel expands **10 to 20 decision dates** and **304,670 to 601,730 matured observations**, an increase of **10 dates and 297,060 observations**. The 12-month horizons overlap: the panel reports 47 overlapping date pairs out of 190 and a 0.353 mean adjacent overlap fraction. These rows are not independent trials. The frozen global cohorts retain current-survivor bias.

The deep-panel build uses dated executable price and official-action histories, the observed reacquired Yahoo split ledger, and its raw-response integrity audit. Its canonical split identity has 1,802 events; 3,704 responses succeeded and **104 failed lookups remain quarantined**. Ledger SHA-256 is `7607aacd11408914368bc71d78f667f5eb15bef56c2e130847f02cc09904e11f`; audit SHA-256 is `4e278149a170443ab1921aa448ea8f06e6165a4b37d198939fc22aa60a8dcbda`. All panel endpoints are after their decisions and no later than 2026-09-18. The panel's added rows have no current fundamentals or sectors.

Historical research features are recomputed from adjusted paths cut at each decision date. Current company facts map ISIN to a history file only; all historical sector anchors are replaced with a contemporaneous global observed-5Y median. The historical feature set includes history span, observed/estimated growth provenance, days and distance from high, full-history drawdown, underwater duration, recovery, and volatility. The original panel CAGR is retained separately for the frozen-policy baseline. The authoritative v3 enrichment is used only for current diagnostic inference. Its four `RAW_RISK_ONLY` identities never become adjusted-growth observations. The prepared cache seals 2024 and 2025 outcome columns until the selection lock exists. The `prepare_audit.json` records 64,206 observed security-date feature records, 94,234 estimated-growth panel rows, and 45,660 no-valid-history panel rows.

For each scored date, training admits an outcome only when its 12-month endpoint is **strictly earlier**. Selection used only the twelve declared 2020–2023 development dates. The two 2024 dates were scored once after [locked_selection.json](../../experiments/personalized-deep-championship-20261002/v1/locked_selection.json) was written; the 2025 dates were exposed diagnostics only. The lock contains hashes of the protocol, panel, and 90-setting development table. The one-time [evaluation_record.json](../../experiments/personalized-deep-championship-20261002/v1/evaluation_record.json) references that lock. Extreme mean XIRR is reported but has zero selection weight.

## Tournament and aggregate metrics

Five feature recipes (age, duration, high plus duration, full risk, and full risk without Goal as a tree feature) were fit chronologically with four-grade utility relevance and a regularized 80-tree LambdaRank. Three Goal weights, three champion/new blend shares, and two missing-history penalties made **90 development settings**. This extends the earlier 87-setting successor research; the deeper dates materially changed the conclusion. The development-selected finalist uses `no_goal_risk|utility4|top20`, 60% Goal within the new component, 35% new component, and zero explicit age penalty. The challenger still uses 65% of the frozen champion score. The selected development utility improvement is only 0.00348.

| Metric | Development champion → challenger | Clean 2024 champion → challenger | Exposed 2025 champion → challenger |
|---|---:|---:|---:|
| Coverage | 79.82% → 79.82% | 87.13% → 87.13% | 90.54% → 90.54% |
| Rank IC | -0.0215 → -0.0198 | 0.0762 → 0.0900 | 0.1450 → 0.1550 |
| NDCG@20 | 0.4894 → 0.4828 | 0.5234 → 0.6067 | 0.6322 → 0.6897 |
| Pairwise accuracy | 49.39% → 49.44% | 52.60% → 53.13% | 54.11% → 54.67% |
| Top-20 target achievement | 54.21% → 55.00% | 29.17% → 34.44% | 29.44% → 40.56% |
| Top-20 target shortfall | 8.31% → 7.78% | 16.60% → 14.26% | 14.88% → 13.02% |
| Median Top-20 XIRR | 31.78% → 29.90% | -11.68% → -3.34% | -6.41% → 2.48% |
| Mean Top-20 asset drawdown | -37.10% → -36.95% | -45.70% → -41.73% | -47.01% → -46.71% |

The clean holdout improves all listed utility metrics at unchanged coverage. On 2024-03-31, however, target achievement falls 1.1 points even as shortfall improves 4.2 points. On 2024-09-30 achievement improves 11.7 points. Both dates improve NDCG, Rank IC, pairwise accuracy, shortfall, median XIRR, and mean drawdown. The exposed dates likewise improve aggregate utility; they did not influence selection.

## Profile regressions

All values below are challenger minus champion, in percentage points, averaged over dates in the partition. Positive achievement, median XIRR, and drawdown are favorable; negative shortfall is favorable. The 36M, 20% target, and ₹7,500 monthly profile is `base7500`.

| Profile | Development achievement / shortfall / median / drawdown | Clean 2024 achievement / shortfall / median / drawdown | Exposed 2025 achievement / shortfall / median / drawdown |
|---|---:|---:|---:|
| ₹1,000 amount | +0.4 / -0.1 / -2.6 / +0.8 | +7.5 / -2.8 / +19.9 / +6.7 | +17.5 / -2.7 / +17.4 / +0.7 |
| ₹50,000 amount | +0.4 / -0.6 / -5.4 / +0.1 | +7.5 / -1.6 / +8.1 / +2.5 | +10.0 / -2.7 / +8.7 / +1.0 |
| Base 36M | +1.3 / -0.8 / -3.5 / -0.3 | +2.5 / -1.2 / +9.0 / +3.9 | +15.0 / -2.5 / +6.0 / +2.7 |
| 12M lookback | -1.2 / +0.3 / -4.7 / -0.7 | +5.0 / -2.3 / +5.3 / -0.5 | **-5.0 / +2.1 / -21.9 / -4.3** |
| 60M lookback | +1.2 / -1.2 / +6.9 / +0.8 | 0.0 / -0.6 / **-12.2** / +1.7 | +20.0 / -4.0 / +19.8 / +3.3 |
| Quarterly interval | -1.7 / -0.3 / -6.1 / 0.0 | +15.0 / -6.1 / +20.0 / +4.5 | 0.0 / +0.8 / +1.3 / -4.2 |
| 10% target | +4.6 / -1.6 / -4.3 / +1.5 | +7.5 / -3.6 / +13.7 / +8.2 | +15.0 / -2.6 / +29.4 / +1.3 |
| 30% target | +1.3 / -0.5 / +2.4 / +0.4 | +2.5 / -2.3 / +4.6 / +2.9 | +17.5 / -4.5 / +13.1 / +2.7 |
| Weekly interval | +0.8 / +0.1 / +0.5 / -1.1 | 0.0 / -0.6 / +6.6 / +5.8 | +10.0 / -0.5 / +6.3 / -0.5 |

All profile/date cells and ranking metrics are in `all_profile_date_slices.csv`. The clean 60M median loss and exposed 12M multi-metric loss disqualify promotion under the declared broad-investor rule. The exposed quarterly shortfall/drawdown losses reinforce that conclusion.

## Date and regime robustness

The development aggregate hides sharp reversals. On **2020-03-31**, achievement is -15.6 points, shortfall +4.8 points, median XIRR -24.9 points, drawdown -2.3 points, and NDCG -0.091. On **2022-06-30**, the corresponding changes are -15.0, +5.0, -23.8, -4.0, and -0.126. These dates are selection dates, not a post-hoc holdout claim. Across four dates each in 2020–21, 2022, and 2023, median XIRR deltas are -1.2, -1.2, and -3.3 points; the 2023 target-achievement delta is -1.2 points. The 2024 and 2025 two-date blocks show +8.3 and +8.9 median points, respectively. All 16 date blocks and 144 date/profile cells are preserved in the CSV, including the mild 2024-03 achievement loss.

## Stability, missing history, and NYKAA

Mean Top-20 replacement fractions between neighboring dates are **92.3% champion vs 91.6% challenger** on development, **92.2% vs 94.4%** on clean 2024, and **90.6% vs 81.7%** on exposed 2025. Adjacent cohorts and changing markets drive much of this turnover; the holdout stability regression remains a concern.

Current base-profile coverage is 3,265 for both scores. True 5Y history is missing in **7.96%** of that scored universe. The frozen champion has **90% / 46% / 29%** missing-5Y shares in its Top 20/50/100; the finalist has **20% / 24% / 21%**. This repairs much of the frozen tree's concentration, but the finalist's current Top 20 remains 2.5 times the universe missing-history share. On the clean 2024 dates, the Top-20 missing share is 0.6% champion versus 5.3% challenger against a 5.6% universe share. On exposed 2025 it is 3.9% versus 12.5% against a 7.1% universe share. These are fairness and robustness diagnostics, not model selection inputs.

NYKAA is diagnostic only. In the current base profile it moves from global rank **1 to 35**, while remaining Retailing rank **1 to 1**. No identity-specific rule was used. The v3 layer records 58.25 observed months, estimated -2.03% long-term growth, 1,752 days since the recorded high, -20.06% distance from that high, and -72.09% full-history drawdown.

## Reproduce and limits

Research-only code: `research/runners/personalized_deep_championship.py` and `research/runners/audit_personalized_deep_championship.py`. Run the former in `prepare`, `development`, then `final` order, followed by the audit. Protocol: `research/protocols/personalized_deep_walkforward_v1.json`. Artifacts: `experiments/personalized-deep-championship-20261002/v1/`, including input/protocol hashes, locked selection, full development tournament, one-time holdout and exposed profiles, scores, turnover, missing-history and current diagnostics. The stages reject duplicate preparation, selection, and holdout evaluation.

The focused protocol, enrichment, and tournament tests passed: **18 passed** with an isolated pytest temporary directory; both runners compile. History construction inherits adjusted-price/provider basis risk and frozen-cohort survivorship. Several decision windows overlap. The 2025 block was exposed before this tournament. These limits and the profile/date regressions prevent a replacement of the frozen 67% Goal / 33% LambdaRank champion.
