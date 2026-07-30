"""Canonical Research V2 CSV and result schemas."""

UNIVERSE_COLUMNS = ("ticker", "company", "sector")
PRICE_HISTORY_COLUMNS = ("ticker", "date", "adjusted_close")
FUNDAMENTAL_COLUMNS = (
    "ticker",
    "period_end",
    "available_date",
    "roce",
    "debt_to_equity",
    "profit_growth_yoy",
)

V2_METRIC_COLUMNS = (
    "return_1y",
    "cagr_3y",
    "cagr_5y",
    "days_since_recorded_high",
    "annualized_volatility_1y",
    "max_drawdown_3y",
    "roce",
    "debt_to_equity",
    "profit_growth_yoy",
)
V2_SCORE_COLUMNS = tuple(f"{name}_score" for name in V2_METRIC_COLUMNS)
V2_CONTRIBUTION_COLUMNS = tuple(
    f"{name}_contribution" for name in V2_METRIC_COLUMNS
)
V2_OUTPUT_COLUMNS = (
    *UNIVERSE_COLUMNS,
    "ranking_date",
    *V2_METRIC_COLUMNS,
    *V2_SCORE_COLUMNS,
    *V2_CONTRIBUTION_COLUMNS,
    "research_v2_score",
    "sector_rank",
    "eligible",
    "method_version",
)
V2_ELIGIBILITY_COLUMNS = (
    *UNIVERSE_COLUMNS,
    "ranking_date",
    "eligible",
    "reason_code",
    "reason",
)

HIGHER_IS_BETTER_METRICS = (
    "return_1y",
    "cagr_3y",
    "cagr_5y",
    "max_drawdown_3y",
    "roce",
    "profit_growth_yoy",
)
LOWER_IS_BETTER_METRICS = (
    "days_since_recorded_high",
    "annualized_volatility_1y",
    "debt_to_equity",
)
