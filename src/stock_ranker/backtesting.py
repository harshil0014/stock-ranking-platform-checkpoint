"""Future backtesting and benchmark-evaluation boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

import pandas as pd


@dataclass(frozen=True, slots=True)
class BacktestRequest:
    """Minimum inputs for a future point-in-time backtest."""

    start_date: date
    end_date: date
    benchmark_id: str


class BacktestEngine(Protocol):
    """Interface for future portfolio and benchmark evaluation."""

    def run(
        self,
        allocations: pd.DataFrame,
        prices: pd.DataFrame,
        benchmark_prices: pd.DataFrame,
        request: BacktestRequest,
    ) -> pd.DataFrame:
        """Return explicit performance and benchmark results."""
        ...
