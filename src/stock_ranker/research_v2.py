"""Future Research V2 scoring boundaries.

No V2 metrics are implemented in this milestone. Implementations will supply
risk metrics, fundamentals, sector scores, and transparent weighted scores.
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd


class ResearchScoringModel(Protocol):
    """Interface for a future explainable scoring model."""

    @property
    def method_version(self) -> str:
        """Return a stable scoring-method identifier."""
        ...

    def score(self, data: pd.DataFrame) -> pd.DataFrame:
        """Return validated metric and score results."""
        ...
