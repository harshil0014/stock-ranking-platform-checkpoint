"""Baseline V1 price-growth and recorded-high-recency metrics."""

from __future__ import annotations

import pandas as pd


def calculate_baseline_metrics(validated: pd.DataFrame) -> pd.DataFrame:
    """Calculate metrics from an already validated canonical input frame."""

    metrics = validated.copy()
    metrics["yoy_growth"] = (
        metrics["current_price"] / metrics["close_1y_ago"] - 1
    )
    metrics["cagr_3y"] = (
        metrics["current_price"] / metrics["close_3y_ago"]
    ) ** (1 / 3) - 1
    metrics["cagr_5y"] = (
        metrics["current_price"] / metrics["close_5y_ago"]
    ) ** (1 / 5) - 1
    metrics["days_since_recorded_high"] = (
        metrics["as_of_date"] - metrics["ath_date"]
    ).dt.days
    return metrics
