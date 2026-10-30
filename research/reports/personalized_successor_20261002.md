# Personalized successor championship — 2026-10-02

## Decision

**Retain the frozen 67% Goal / 33% LambdaRank production champion.** The strongest new challenger selected on 2023 development data repairs the short-history concentration and improves NDCG, target shortfall, and drawdown there. It fails important exposed 2025 profile slices: aggregate target achievement falls 6.39 percentage points, target shortfall rises 0.23 points, median Top-20 XIRR falls 11.46 points, and turnover rises. This challenger is a research artifact, not safe to replace V1. No production or frozen-champion file was changed.

The existing retrospective data cannot establish a stronger production champion. It has two 2023 development decisions, two 2025 decisions already exposed in earlier research, current-universe survivorship, and no untouched historical holdout. Current 2026-09-18 rankings have no matured future outcome. This is an evidence limit, not proof that a better model is impossible.

## Provenance and research protocol

Current inference reads the authoritative `final-data-quality-v3/history_enrichment.csv.gz` directly. The runner verifies all 4,436 identities and that the four `RAW_RISK_ONLY` histories have neither strict adjusted 5Y CAGR nor an observed-growth designation. The 1,307 estimated long-term growth inputs remain labeled estimates. Raw BSE risk-only closes supply risk diagnostics only, never adjusted returns. The historical feature archive is computed from adjusted prices available by each historical decision date, including the validated recovery overlay. Its old `since_listing_cagr` name is corrected to `history_start_cagr`: it measures observed price span, not verified listing age.

The historical archive had used today's sector classification in estimated 5Y growth. The final tournament **replaces that historical estimate** with a shrinkage of observed history-start CAGR toward the contemporaneous global median of observed adjusted 5Y CAGR. Current 2026 inference continues to use the authoritative v3 provenance-aware sector-shrunk estimate. Historical sector labels are used only in a diagnostic sensitivity table. No stock-specific rule or future outcome enters a feature.

Each fit admits a training outcome only when its endpoint strictly precedes the scored decision. Selection uses 2023-06-30 and 2023-12-31. The 2025-03-31 and 2025-06-30 dates are exposed diagnostics and did not select models or parameters. Historical baselines use chronological champion-policy predictions. The current baseline uses the exact sealed champion rows; recomputed 67/33 scores differ by at most `2.22e-16`.

The new tournament fits 20 rankers across five feature recipes, two four-grade relevance labels, and two regularization settings, then tests three Goal weights and 27 restrained blends: **87 development settings**. This follows the earlier 30-candidate / 78-setting / 60-blend championship and the earlier history tournaments. Those prior runs had already exposed 2025, so accumulated search is not independent validation. Extreme retrospective mean XIRR has no selection weight.

## Strongest final challenger

The selected model uses **67% Goal plus 33% ranker**, with the ranker percentile itself **15% frozen LambdaRank and 85% new LambdaRank**. The new model uses the original execution/Goal inputs plus provenance-aware growth, observed history span, history-start CAGR, full-history maximum drawdown, current and maximum underwater duration, and recovery from the worst trough. It uses 80 trees, learning rate 0.04, seven leaves, depth three, minimum child size 120, L2 penalty 15, and truncation level 25. Four-grade relevance combines within-query XIRR and target-shortfall percentiles. Historical-high and volatility recipes were tested but did not beat the duration-focused fit on the development utility and profile gates. The current v3 historical-high fields remain available for future research.

| Metric | 2023 champion | 2023 challenger | Exposed 2025 champion | Exposed 2025 challenger |
|---|---:|---:|---:|---:|
| Coverage | 80.24% | 80.24% | 82.97% | 82.97% |
| Rank IC | 0.02757 | 0.01826 | 0.15467 | 0.15996 |
| NDCG@20 | 0.50117 | 0.54838 | 0.62682 | 0.66376 |
| Pairwise accuracy | 51.94% | 51.28% | 54.87% | 54.84% |
| Top-20 target achievement | 58.33% | 62.78% | 39.72% | 33.33% |
| Top-20 target shortfall | 6.03% | 4.25% | 12.90% | 13.13% |
| Mean Top-20 XIRR | 132.09% | 215.17% | 869.76% | 177.95% |
| Median Top-20 XIRR | 33.91% | 33.84% | 4.66% | -6.80% |
| Mean Top-20 asset drawdown | -34.56% | -27.38% | -42.58% | -37.45% |

The new model improves NDCG and drawdown on both partitions but loses development Rank IC and pairwise accuracy. The exposed aggregate achievement, shortfall, and median-return failures outweigh those gains. Raw mean XIRR is dominated by extreme corporate-action outcomes and does not support promotion. On 2025-03-31 alone, achievement is -11.67 points, shortfall +2.80 points, and median XIRR -25.64 points; 2025-06-30 partly offsets this but does not repair the investor-profile failures.

## All nine profile deltas

Challenger minus champion, averaged over two dates; values are percentage points. Positive achievement and drawdown and negative shortfall are favorable. The full CSV also records Rank IC, NDCG, pairwise accuracy, mean/median XIRR, coverage, and every date separately.

| Profile | 2023 achievement | 2023 shortfall | 2023 drawdown | Exposed 2025 achievement | Exposed 2025 shortfall | Exposed 2025 drawdown |
|---|---:|---:|---:|---:|---:|---:|
| ₹1,000 amount | **-5.0** | -0.29 | +7.38 | +2.5 | -1.30 | **-1.59** |
| ₹7,500 base | +15.0 | -3.63 | +6.97 | **-12.5** | -0.02 | +11.26 |
| ₹50,000 amount | +10.0 | -1.17 | +5.95 | **-2.5** | -2.79 | +9.05 |
| 12M lookback | +12.5 | -3.16 | +10.50 | +15.0 | -6.98 | +0.32 |
| 60M lookback | **-7.5** | **+0.62** | +2.91 | **-20.0** | **+5.77** | +0.88 |
| Quarterly interval | **-2.5** | -1.26 | +8.77 | 0.0 | **+0.15** | +5.36 |
| 10% target | 0.0 | -0.61 | +4.85 | **-15.0** | **+1.82** | +9.12 |
| 30% target | +5.0 | -3.45 | +8.84 | **-20.0** | **+6.34** | +4.66 |
| Weekly interval | +12.5 | -3.08 | +8.39 | **-5.0** | -0.91 | +7.09 |

The 60M, 10% target, and 30% target shortfall regressions disqualify the candidate despite its aggregate ranking gains. The 2023 ₹1,000 and 60M achievement regressions show that even development gains are not uniform. Exposed median XIRR falls 18.91 points for the base profile, 25.37 for 60M, 21.28 for the 10% target, and 33.16 for the 30% target.

## Pareto, stability, and sectors

Three distinct finalists were fixed on 2023 before the exposed diagnostic. Exposed deltas are against the same champion rows.

| Finalist | 2023 shortfall Δ | 2023 drawdown Δ | Exposed NDCG Δ | Exposed achievement Δ | Exposed shortfall Δ | Exposed median XIRR Δ |
|---|---:|---:|---:|---:|---:|---:|
| Duration blend, selected | -1.78 pp | +7.17 pp | +0.0369 | **-6.39 pp** | **+0.23 pp** | **-11.46 pp** |
| High + underwater direct | -1.71 | +3.05 | +0.0135 | **-4.44** | -0.81 | **-4.96** |
| Full risk direct | -0.40 | +5.15 | -0.0198 | **-6.67** | **+0.15** | **-9.60** |

Only three of 87 new settings improve development Rank IC; none simultaneously improves Rank IC, NDCG, shortfall, and drawdown. The chosen model's Top-20 replacement fraction between the two 2023 decisions is **87.8%** versus the champion's **78.9%**; between the exposed 2025 decisions it is **85.0%** versus **80.6%**. It is less stable.

Sector results use current accepted sector labels only as a sensitivity check; historical point-in-time sector membership is unverified. Across 38 date/sector blocks per partition with at least 20 scored names, the challenger’s mean sector Top-5 shortfall delta is +0.12 pp in development and +2.16 pp in exposed diagnostics. The worst exposed block is +16.90 pp. Five-stock sector slices are noisy, but they do not support broad dominance.

## Missing-history concentration and NYKAA

The authoritative v3 layer provides an observed price path for **4,436/4,436**, defensible adjusted history for **4,432**, and explicit raw-risk-only status for four quarantines. True adjusted 5Y CAGR is available for **3,129**; **1,307** have an estimated long-term growth input. All 4,436 have recorded-high and full-history risk diagnostics. Before enrichment, 62 had no usable price path and 64 lacked defensible adjusted history. No prelisting prices or BSE listing dates were fabricated.

Among 3,265 scored current base-profile names, **7.96%** lack true 5Y history. The champion's Top 20/50/100 shares are **90% / 46% / 29%**; the challenger’s are **5% / 10% / 6%**, with identical coverage. This convincingly repairs the frozen tree's known positive missing-5Y shortcut, but historical utility does not validate promotion.

NYKAA is diagnostic only. The v3 record has 58.25 months of observed history, estimated -2.03% long-term growth, a recorded high 1,752 days earlier, -20.06% distance from that high, and -72.09% full-history maximum drawdown. Its current global base-profile rank changes **1 → 30**, while its Retailing rank remains **1 → 1**. No identity-specific rule or selection criterion uses it.

## Reproducibility and action

The research-only runners are `research/runners/personalized_successor_20261002.py` and `research/runners/audit_personalized_successor_20261002.py`. Final outputs are in `experiments/personalized-successor-20261002/v3/`: all 87 settings, three exposed finalist blocks, all profile/date metrics, current scores, fitted current LightGBM, turnover, sector sensitivity, input hashes, and summary. Both runners completed and compiled. The v3 provenance, current coverage, strict label-maturity, and frozen-score-reproduction checks passed.

**Do not replace V1 on this evidence.** The next legitimate promotion decision needs new matured, genuinely unexposed decision-date blocks with verified executable prices and corporate actions, several market regimes, and stable results across target, amount, interval, and lookback profiles.
