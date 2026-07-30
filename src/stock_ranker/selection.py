"""Deterministic top-N selection from canonical sector rankings."""

from __future__ import annotations

import pandas as pd

from stock_ranker.contracts import OUTPUT_COLUMNS


def select_top_stocks_by_sector(
    rankings: pd.DataFrame,
    top_n: int,
) -> pd.DataFrame:
    """Return exactly the first ``top_n`` ordered rows per sector."""

    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0:
        raise ValueError("top_n must be a positive integer")

    missing = set(OUTPUT_COLUMNS).difference(rankings.columns)
    if missing:
        raise ValueError(
            "Rankings are missing required columns: "
            + ", ".join(sorted(missing))
        )

    ordered = rankings.sort_values(
        ["sector", "baseline_score", "ticker"],
        kind="mergesort",
    )
    return (
        ordered.groupby("sector", sort=False, group_keys=False)
        .head(top_n)
        .reset_index(drop=True)
    )
