"""Deterministic within-sector Baseline V1 ranking."""

from __future__ import annotations

import pandas as pd

from stock_ranker.config import BaselineConfig
from stock_ranker.contracts import OUTPUT_COLUMNS, RANK_COLUMNS


def rank_stocks_by_sector(
    metrics: pd.DataFrame,
    config: BaselineConfig,
) -> pd.DataFrame:
    """Rank metric rows inside their sectors and return canonical output."""

    ranked = metrics.copy()
    sector_group = ranked.groupby("sector", sort=False)
    ranked["yoy_rank"] = sector_group["yoy_growth"].rank(
        ascending=False, method="min"
    )
    ranked["cagr_3y_rank"] = sector_group["cagr_3y"].rank(
        ascending=False, method="min"
    )
    ranked["cagr_5y_rank"] = sector_group["cagr_5y"].rank(
        ascending=False, method="min"
    )
    ranked["recorded_high_recency_rank"] = sector_group[
        "days_since_recorded_high"
    ].rank(ascending=True, method="min")

    # Project-specific Baseline V1 approximation, not a paper-defined formula.
    ranked["baseline_score"] = ranked[list(RANK_COLUMNS)].mean(axis=1)
    ranked["sector_rank"] = ranked.groupby("sector")["baseline_score"].rank(
        ascending=True, method="min"
    )
    ranked["method_version"] = config.method_version

    for column in (*RANK_COLUMNS, "sector_rank"):
        ranked[column] = ranked[column].astype("int64")

    ranked["as_of_date"] = ranked["as_of_date"].dt.strftime("%Y-%m-%d")
    ranked["ath_date"] = ranked["ath_date"].dt.strftime("%Y-%m-%d")

    return (
        ranked.loc[:, list(OUTPUT_COLUMNS)]
        .sort_values(
            ["sector", "baseline_score", "ticker"],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )
