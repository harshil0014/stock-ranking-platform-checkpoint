"""Baseline V1 metric calculation and within-sector ranking."""

from __future__ import annotations

import pandas as pd

from stock_ranker.config import BaselineConfig
from stock_ranker.metrics import calculate_baseline_metrics
from stock_ranker.ranking import rank_stocks_by_sector
from stock_ranker.selection import select_top_stocks_by_sector
from stock_ranker.validation import validate_baseline_input


def calculate_baseline_rankings(
    data: pd.DataFrame,
    config: BaselineConfig | None = None,
) -> pd.DataFrame:
    """Validate input and calculate deterministic Baseline V1 rankings.

    Growth values are decimal returns: for example, 0.15 means 15 percent.
    The combined score is this project's documented approximation, not a
    final-ranking formula stated by the source research paper.
    """

    settings = config or BaselineConfig()
    validated = validate_baseline_input(data)
    metrics = calculate_baseline_metrics(validated)
    return rank_stocks_by_sector(metrics, settings)


def get_top_stocks_by_sector(
    rankings: pd.DataFrame,
    top_n: int = 5,
) -> pd.DataFrame:
    """Return exactly the first ``top_n`` deterministically ordered rows per sector."""

    return select_top_stocks_by_sector(rankings, top_n)
