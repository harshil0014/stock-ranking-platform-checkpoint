"""Configuration and weights for Research V2."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


RESEARCH_V2_METHOD_VERSION = "research_v2_point_in_time_weighted"


@dataclass(frozen=True, slots=True)
class ResearchV2Weights:
    """Percentage weights for the nine Research V2 components."""

    return_1y: Decimal = Decimal("10")
    cagr_3y: Decimal = Decimal("10")
    cagr_5y: Decimal = Decimal("10")
    days_since_recorded_high: Decimal = Decimal("5")
    annualized_volatility_1y: Decimal = Decimal("12.5")
    max_drawdown_3y: Decimal = Decimal("12.5")
    roce: Decimal = Decimal("15")
    debt_to_equity: Decimal = Decimal("10")
    profit_growth_yoy: Decimal = Decimal("15")

    def __post_init__(self) -> None:
        total = Decimal("0")
        for item in fields(self):
            raw_value = getattr(self, item.name)
            try:
                value = Decimal(str(raw_value))
            except (InvalidOperation, ValueError) as exc:
                raise ValueError(f"Weight {item.name} must be numeric") from exc
            if not value.is_finite() or value < 0:
                raise ValueError(
                    f"Weight {item.name} must be finite and nonnegative"
                )
            object.__setattr__(self, item.name, value)
            total += value
        if total != Decimal("100"):
            raise ValueError(f"Research V2 weights must total exactly 100; got {total}")

    def as_dict(self) -> dict[str, Decimal]:
        return {item.name: getattr(self, item.name) for item in fields(self)}


@dataclass(frozen=True, slots=True)
class ResearchV2Config:
    """Point-in-time calculation settings."""

    ranking_date: date
    top_n: int = 5
    weights: ResearchV2Weights = field(default_factory=ResearchV2Weights)
    annualization_periods: int = 252
    anchor_tolerance_days: int = 7
    method_version: str = RESEARCH_V2_METHOD_VERSION

    def __post_init__(self) -> None:
        if isinstance(self.ranking_date, datetime) or not isinstance(
            self.ranking_date, date
        ):
            raise ValueError("ranking_date must be a date")
        if (
            isinstance(self.top_n, bool)
            or not isinstance(self.top_n, int)
            or self.top_n <= 0
        ):
            raise ValueError("top_n must be a positive integer")
        if (
            isinstance(self.annualization_periods, bool)
            or not isinstance(self.annualization_periods, int)
            or self.annualization_periods <= 0
        ):
            raise ValueError("annualization_periods must be a positive integer")
        if (
            isinstance(self.anchor_tolerance_days, bool)
            or not isinstance(self.anchor_tolerance_days, int)
            or self.anchor_tolerance_days < 0
        ):
            raise ValueError("anchor_tolerance_days must be a nonnegative integer")
        if not self.method_version.strip():
            raise ValueError("method_version must not be blank")
