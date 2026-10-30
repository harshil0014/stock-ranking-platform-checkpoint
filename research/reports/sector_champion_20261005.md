# Sector-tuned Closing High champion

Date: 5 October 2026. Branch: `main`. Price/data snapshot: 3 October 2026.

## Delivered change

The Closing High model now ranks stocks for comparison **within their own sector**. Global ranking performance had no role in this selection. The existing `/closing-high` UI groups results by sector, displays eligible sector positions and hides the global-rank column and global position in stock details. Scores should not be compared across sectors.

Selected weights:

| Component | Weight | Definition |
|---|---:|---|
| Closing-high strength | 50% | 25% existing continuous high component plus 25% its percentile among eligible sector peers |
| V17 refined | 25% | Percentile among eligible sector peers |
| Downside risk | 20% | Inverse downside-volatility percentile among eligible sector peers |
| Momentum | 5% | 12–1-month return percentile among eligible sector peers |

The continuous high component retains the existing age/recovery, proximity and rolling-high terms. NYKAA's recorded ATH age remains 1,765 days. Groups with fewer than five eligible stocks, and unclassified groups, retain the prior reviewed score. Trading screens, SME lot exclusions, recovered BSE histories, corporate-action treatment and financial review flags remain in place. Baseline, Original Personalized and Personalized V17 keep their own scoring.

## Search and selection

Tested **48 prespecified sector blends** using 30/40/50% high weight, 10/20% downside weight, 5/10% momentum, optional 10% historical goal attainment, and either absolute high strength or a half-absolute/half-sector-relative high component. The remaining weight belongs to sector-relative V17. Historical goal attainment was tested but receives zero weight in the selected candidate.

Selection used only 2020–2023 sector results in this round. A candidate had to improve or tie five aggregate Top 3 metrics, keep each profile's return/drawdown loss within one percentage point and shortfall increase within half a percentage point, and have nonnegative utility in at least 55% of sectors. Utility is `ΔXIRR + 0.5Δdrawdown + 0.5Δachievement − Δshortfall + 0.2ΔNDCG`.

**23 candidates passed**. The selected candidate had the highest declared utility and nonnegative development utility in **60.8% of sectors**. Its definition was locked before this round's early/recent diagnostics; no weights were changed after those diagnostics or sensitivity checks. This is not a claim that every sector improves.

## Primary result: within-sector Top 3

All nine investor profiles, 44 dates, 17,478 matched sector/date/profile comparisons. For each model, metrics are averaged over available dates within each sector/profile and then sector/profile cells equally. Each paired query uses identical stocks and outcome labels. Only classified groups with at least five comparable stocks are evaluated. The periods contain 48, 51 and 52 evaluated sectors respectively.

| Period | Previous median-XIRR average | Sector-tuned | Previous mean constituent drawdown | Sector-tuned |
|---|---:|---:|---:|---:|
| 2016–2019 | 3.65% | 3.08% | −37.28% | −35.90% |
| 2020–2023 | 33.58% | 35.05% | −28.21% | −27.03% |
| 2024–2025 | −0.23% | 0.31% | −34.02% | −33.28% |

All five aggregate metrics improve in 2020–2023 and 2024–2025. Early-period return falls by 0.57 percentage points and achievement falls by 0.26 percentage points; early drawdown, shortfall and NDCG improve. These are averages of constituent Top 3 statistics, **not portfolio XIRRs or portfolio maximum drawdowns**. They differ from the preceding single-profile sector audit because this study includes all nine profiles.

### Profile and shortlist-size checks

- Every profile has better average drawdown, shortfall and NDCG in every period.
- Some profile returns decline: worst profile return changes are −0.89 percentage points in development, −1.60 in early history and −1.59 in recent history.
- Top 5 sensitivity improves all five aggregate metrics in each period. Median-XIRR averages move from 0.91% to 2.05% in early history, 32.82% to 33.52% in development, and −1.85% to −1.26% in recent history.
- **Top 1 is mixed:** return decreases in each period, including 52.58% to 49.31% in development, while drawdown, shortfall and NDCG improve. Early/recent Top 1 achievement also declines. The selected objective is a sector shortlist, not maximizing the realized return of the single first-ranked stock.

Detailed losing sectors and profiles remain in the exports. No claim of universal dominance is made.

## Research used

- [AQR: Building a Better Equity Market Neutral Strategy](https://www.aqr.com/-/media/AQR/Documents/Insights/White-Papers/Building-a-Better-Equity-Market-Neutral-Strategy.pdf) distinguishes within-industry stock selection from industry allocation. This motivated making sector peer groups the normalization and evaluation units.
- [George and Hwang: The 52-Week High and Momentum Investing](https://www.bauer.uh.edu/tgeorge/papers/gh4-paper.pdf) studies the information in proximity to a 52-week high. This supports testing closing-high strength, but does not establish our ATH-age formula or a 50% weight.
- [Hong, Jordan and Liu: Industry Information and the 52-Week High Effect](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1787378) examines industry-related high effects. It is a reason to distinguish industry exposure from within-industry ordering, not proof that neutralization always improves returns.
- [Blitz, Huij and Martens: Residual Momentum](https://www.sciencedirect.com/science/article/pii/S0927539811000041) examines stock-specific momentum. Our within-sector percentile is **not regression residual momentum**; we have not claimed to replicate that method.

## Validation boundaries

Sector assignments come from current sealed `product_sector`, not reconstructed point-in-time membership. Price features end at each decision date, but current-universe survivorship and retrospectively adjusted data remain limitations. All periods have prior research exposure. No independent statistical-significance or fresh holdout claim is justified.

Historical incumbent scores are the prior recovery-score artifacts. Their eligibility does not replay the entire present SME gate or all newly recovered BSE histories. Current serving verification checks those operational rules, but does not convert this score-policy study into a complete historical execution test. No new fundamental weights were inferred from today's financial statements and backfilled into past dates.

The sector-tuned blend is a selected research champion for the declared shortlist objective. It is not proven superior to Baseline, strict Research V2, or every historical project model on a common point-in-time sector cohort. A prospective frozen-sector evaluation remains the appropriate next source of independent evidence.

## Verification

Eight targeted tests passed. Desktop and mobile browser checks confirmed sector filtering, sector rank 1 first, hidden global rank and no JavaScript errors. The live local API returns `closing_high_sector`, `WITHIN_SECTOR` and 1,747 eligible stocks for the default profile. Independent serving checks reproduce each of the nine profile scores and sector ranks without changing eligibility. A custom ?8,250 profile is checked separately.

## Artifacts and reproduction

Under `experiments/sector-tuning-20261005/`:

- `protocol.json`, `trials.csv`, `selection_lock.json`: all candidates, gates and locked choice.
- `summary.csv`, `profile_summary.csv`, `*_sector_profile_metrics.csv`: aggregate and granular tradeoffs.
- `top1_top5_sensitivity.csv`: shortlist-size checks.
- `current_sector_rankings.csv.gz`, `current_sector_top3.csv`: serving exports for all nine profiles.
- `serving_verification.json`: independent arithmetic and rank checks.
- `browser_verification.json`, `sector_desktop.png`, `sector_mobile.png`: browser checks.

Shared formula: `src/stock_ranker/sector_scoring.py`. Serving adapter: `src/stock_ranker/personalized_peak_product.py`. The frozen selection is included in the runtime manifest as `sector_selection.json`.

```powershell
python research/runners/sector_tuning_20261005.py prepare
python research/runners/sector_tuning_20261005.py search
python research/runners/sector_tuning_20261005.py final
python research/runners/sector_tuning_20261005.py sensitivity
python research/runners/finalize_sector_tuning_20261005.py verify
python research/runners/finalize_sector_tuning_20261005.py browser
```
