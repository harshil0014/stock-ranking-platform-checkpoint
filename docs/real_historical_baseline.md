# Real historical NIFTY 50 Baseline V1

This adapter converts a frozen, validated daily-price bundle into the existing Baseline V1 contract. It does not change any scoring formula and does not implement corporate-action mathematics.

The acquisition environment pins `yfinance==1.5.1` (upstream project: <https://github.com/ranaroussi/yfinance>, Apache-2.0 software licence). Acquisition uses the public `Ticker.history` API with `period="max"`, `interval="1d"`, `auto_adjust=False`, `repair=True`, and `actions=True`. The selected field is the repaired fetch's Yahoo `Adj Close`. It is an upstream-maintained adjusted-price series, includes upstream dividend adjustments, and is therefore not claimed to have the same source-price semantics as the original paper. Yahoo Finance data remains subject to its research/education/personal-use caveat and source terms.

RELIANCE is independently audited against the supplied official NSE raw history and corporate-action file around the 20-Jul-2023 demerger and the 28-Oct-2024 1:1 bonus. The project compares raw Close, Adj Close, auto-adjust-equivalent values, action markers, and repair metadata, but applies no project adjustment.

Anchors are the latest trading observation on or before the as-of/anniversary target, with a maximum seven-calendar-day delay. No future observation or imputation is allowed. The recorded-high date is the latest occurrence of the maximum selected adjusted close in the provider's maximum available history through the as-of date. As elsewhere in this project, this is a recorded/study-period high and is a true all-time high only if the provider history covers the security's complete trading history.

Every current constituent is retained in an eligibility report. Terminal prices are independently checked against the supplied official NSE 07-Aug-2026 snapshot with a fixed ₹0.05 absolute or one-basis-point relative tolerance. Failures are excluded rather than substituted or silently dropped.

The prepared website mode reads only the ignored local bundle. It makes no network call. It uses real historical prices for the current NIFTY 50 universe, so it is not survivorship-bias-free, a walk-forward backtest, an investment recommendation, or evidence of profitability.

Provider maximum history can contain inherited or legacy identity history. Yahoo reports BAJAJFINSV history from 12-Aug-2002, but Bajaj Finserv's first annual report says it was incorporated on 30-Apr-2007 and the NSE admitted security `BAJAJFINSV` (then ISIN `INE918I01018`) to dealings from 26-May-2008. Consequently, the recorded-high search applies a general source-driven boundary: when an authoritative exchange listing date is supplied, observations before that date remain preserved in the donor panel but cannot define the current security's recorded high. Boundaries are data in `marketdata/specifications/nse_security_history_boundaries.csv`, not ticker-specific program logic. Anchor prices and accepted Baseline formulas are unchanged.

Upstream yfinance supplies acquisition, repair, and adjusted-series behavior. This project supplies exact-symbol mapping, normalization, anchors, official-NSE cross-checks, eligibility, caching, fingerprints, and presentation. The accepted Baseline V1 engine supplies the four formulas and sector-relative equal-rank-mean approximation.
