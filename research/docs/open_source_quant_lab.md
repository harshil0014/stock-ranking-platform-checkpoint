# Open-Source Quant Lab

This layer independently checks or consumes frozen project outputs. It does not define, modify, or replace Baseline V1, Research V2, the preregistered protocol, or frozen outcomes.

## Verified secondary checks

Alphalens Reloaded 0.4.6 reproduces grouped sector/date Spearman IC at the existing 3-, 6-, and 12-month horizons. The project adapter performs exact ticker and sector mapping; Alphalens supplies the IC and descriptive quantile routines. All 18 valid grouped comparisons match the frozen evaluator. Quantile results are descriptive because cohorts are small, and turnover is deferred because only four sparse annual observations exist.

Empyrical Reloaded 0.5.12 independently checks all 34 accepted current Research V2 rows. Annualized volatility and maximum drawdown use equivalent definitions and all 68 comparisons pass at `1e-12`. Its annual-return convention annualizes observed daily periods, whereas the project 1-year return uses exact calendar anchors, so those 34 comparisons are recorded as explained definition differences—not failures.

The preregistered 12-month sector-date evaluation remains primary. These checks are secondary diagnostics and are not evidence of portfolio profitability or model superiority.

## Downstream boundary

skfolio 0.20.1 is installed and provenance-verified, but no portfolio experiment was run. Current data does not preregister top-K selection, rebalancing, transaction costs, a benchmark, or a formation-time covariance policy. QuantStats 0.0.81 is therefore deferred because no scientifically defensible portfolio return stream exists.

Qlib 0.9.7 remains a separate synthetic benchmark environment: Linear, LightGBM, and TRA were reproduced on frozen synthetic protocols; DoubleEnsemble has a recorded compatibility/scientific blocker. Synthetic Qlib results are not compared with real historical Baseline/V2 evidence as one experiment.

## Contribution boundary

Upstream projects provide factor analysis, risk metrics, portfolio optimizers, portfolio analytics, and ML model implementations. This project provides Indian NSE point-in-time reconstruction, data contracts, exact identity mapping, ranking integration, provenance, eligibility, comparison protocols, audit harnesses, and the local website. No upstream algorithm is claimed as project invention.
