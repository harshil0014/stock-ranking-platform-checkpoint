from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from stock_ranker.research_v2 import ResearchV2Inputs, calculate_research_v2
from stock_ranker.v2_config import ResearchV2Config
from stock_research.contracts import validate_labels


def _prices() -> pd.DataFrame:
    dates = pd.date_range("2016-01-01", "2024-05-21", freq="D")
    values = 100 + pd.Series(range(len(dates)), dtype=float) / 100
    return pd.DataFrame({"ticker": "AAA", "date": dates.strftime("%Y-%m-%d"), "adjusted_close": values})


def _universe() -> pd.DataFrame:
    return pd.DataFrame([{"ticker": "AAA", "company": "Alpha", "sector": "Industrials"}])


def _fundamentals() -> pd.DataFrame:
    return pd.DataFrame([
        {"ticker": "AAA", "period_end": "2023-03-31", "available_date": "2023-05-20", "roce": .10, "debt_to_equity": .30, "profit_growth_yoy": .05},
        {"ticker": "AAA", "period_end": "2024-03-31", "available_date": "2024-05-20", "roce": .20, "debt_to_equity": .20, "profit_growth_yoy": .15},
    ])


def _calculate(ranking_date: date, fundamentals: pd.DataFrame | None = None, prices: pd.DataFrame | None = None):
    return calculate_research_v2(
        ResearchV2Inputs(_universe(), prices if prices is not None else _prices(), fundamentals if fundamentals is not None else _fundamentals()),
        ResearchV2Config(ranking_date=ranking_date),
    )


def test_newer_period_is_unavailable_until_its_public_availability_date() -> None:
    before = _calculate(date(2024, 4, 30)).rankings.iloc[0]
    on_date = _calculate(date(2024, 5, 20)).rankings.iloc[0]
    assert before["roce"] == pytest.approx(.10)
    assert before["debt_to_equity"] == pytest.approx(.30)
    assert on_date["roce"] == pytest.approx(.20)
    assert on_date["debt_to_equity"] == pytest.approx(.20)


def test_controlled_timeline_selects_older_available_then_newer_available() -> None:
    fundamentals = pd.DataFrame([
        {"ticker": "AAA", "period_end": "2021-12-31", "available_date": "2022-02-15", "roce": .11, "debt_to_equity": .40, "profit_growth_yoy": .06},
        {"ticker": "AAA", "period_end": "2022-03-31", "available_date": "2022-07-10", "roce": .22, "debt_to_equity": .20, "profit_growth_yoy": .12},
    ])
    assert _calculate(date(2022, 6, 30), fundamentals).rankings.iloc[0]["roce"] == pytest.approx(.11)
    assert _calculate(date(2022, 7, 11), fundamentals).rankings.iloc[0]["roce"] == pytest.approx(.22)


def test_missing_availability_is_rejected_in_strict_contract() -> None:
    fundamentals = _fundamentals()
    fundamentals.loc[1, "available_date"] = None
    with pytest.raises(ValueError, match="available_date must not contain missing"):
        _calculate(date(2024, 5, 20), fundamentals)


def test_future_price_never_enters_formation_metrics() -> None:
    prices = _prices()
    control = _calculate(date(2024, 4, 30), prices=prices).rankings.iloc[0]
    prices.loc[prices["date"].eq("2024-05-01"), "adjusted_close"] = 1_000_000
    audited = _calculate(date(2024, 4, 30), prices=prices).rankings.iloc[0]
    for column in ("return_1y", "cagr_3y", "cagr_5y", "days_since_recorded_high", "annualized_volatility_1y", "max_drawdown_3y"):
        assert audited[column] == pytest.approx(control[column], abs=1e-15)


def test_future_outcome_label_remains_valid_only_as_evaluation_data() -> None:
    labels = pd.DataFrame([{
        "as_of_date": "2024-04-30", "ticker": "AAA",
        "label_end_date": "2025-04-30", "forward_return": .12,
        "label_name": "forward_12m_return",
    }])
    validated = validate_labels(labels)
    assert validated.iloc[0]["forward_return"] == pytest.approx(.12)
    assert validated.iloc[0]["label_end_date"] == "2025-04-30"


def test_selection_is_deterministic_after_input_shuffle() -> None:
    first = _calculate(date(2024, 4, 30)).rankings
    shuffled = _fundamentals().sample(frac=1, random_state=9).reset_index(drop=True)
    second = _calculate(date(2024, 4, 30), shuffled).rankings
    pd.testing.assert_frame_equal(first, second)
