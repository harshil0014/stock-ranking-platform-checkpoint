"""Future portfolio construction and rebalancing boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

import pandas as pd


@dataclass(frozen=True, slots=True)
class RebalanceRequest:
    """Inputs required by a future portfolio constructor."""

    as_of_date: date
    portfolio_value: float


class PortfolioConstructor(Protocol):
    """Interface for future stock selection, weighting, and rebalancing."""

    def construct(
        self,
        ranked_stocks: pd.DataFrame,
        request: RebalanceRequest,
    ) -> pd.DataFrame:
        """Return explicit portfolio constituents and target weights."""
        ...
