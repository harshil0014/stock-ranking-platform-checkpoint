"""Canonical Baseline V1 input and output column contracts."""

REQUIRED_COLUMNS = (
    "ticker",
    "company",
    "sector",
    "as_of_date",
    "current_price",
    "close_1y_ago",
    "close_3y_ago",
    "close_5y_ago",
    "ath_date",
)

IDENTITY_COLUMNS = ("ticker", "company", "sector")
DATE_COLUMNS = ("as_of_date", "ath_date")
PRICE_COLUMNS = (
    "current_price",
    "close_1y_ago",
    "close_3y_ago",
    "close_5y_ago",
)
METRIC_COLUMNS = (
    "yoy_growth",
    "cagr_3y",
    "cagr_5y",
    "days_since_recorded_high",
)
RANK_COLUMNS = (
    "yoy_rank",
    "cagr_3y_rank",
    "cagr_5y_rank",
    "recorded_high_recency_rank",
)
OUTPUT_COLUMNS = (
    *REQUIRED_COLUMNS,
    *METRIC_COLUMNS,
    *RANK_COLUMNS,
    "baseline_score",
    "sector_rank",
    "method_version",
)
