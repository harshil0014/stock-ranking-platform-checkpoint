from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from stock_ranker.v2_config import ResearchV2Config, ResearchV2Weights


def test_default_weights_total_exactly_100() -> None:
    weights = ResearchV2Weights()
    assert sum(weights.as_dict().values()) == Decimal("100")
    assert weights.annualized_volatility_1y == Decimal("12.5")


def test_weights_accept_exact_configurable_values() -> None:
    weights = ResearchV2Weights(
        return_1y=20,
        cagr_3y=10,
        cagr_5y=10,
        days_since_recorded_high=5,
        annualized_volatility_1y=10,
        max_drawdown_3y=10,
        roce=15,
        debt_to_equity=5,
        profit_growth_yoy=15,
    )
    assert weights.return_1y == Decimal("20")


@pytest.mark.parametrize(
    "weights",
    [
        {"return_1y": 11},
        {"return_1y": -1, "cagr_3y": 21},
        {"return_1y": "not-a-number"},
    ],
)
def test_invalid_weights_are_rejected(weights: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="Weight|weights"):
        ResearchV2Weights(**weights)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"top_n": 0},
        {"annualization_periods": 0},
        {"anchor_tolerance_days": -1},
    ],
)
def test_invalid_v2_configuration_is_rejected(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        ResearchV2Config(ranking_date=date(2026, 6, 30), **kwargs)
