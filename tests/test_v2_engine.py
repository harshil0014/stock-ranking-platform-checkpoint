from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from stock_ranker.research_v2 import (
    ResearchV2Inputs,
    calculate_research_v2,
)
from tests.v2_helpers import default_config, make_inputs


def test_every_raw_price_metric_uses_documented_formula() -> None:
    inputs = make_inputs((("AAA", "Technology"),))
    result = calculate_research_v2(inputs, default_config())
    row = result.rankings.iloc[0]
    prices = inputs.prices.assign(
        date=pd.to_datetime(inputs.prices["date"]),
        adjusted_close=pd.to_numeric(inputs.prices["adjusted_close"]),
    ).sort_values("date")
    ranking_date = pd.Timestamp("2026-06-30")

    def anchor(years: int) -> float:
        target = ranking_date - pd.DateOffset(years=years)
        return float(prices.loc[prices["date"] <= target, "adjusted_close"].iloc[-1])

    current = float(prices.iloc[-1]["adjusted_close"])
    assert row["return_1y"] == pytest.approx(current / anchor(1) - 1)
    assert row["cagr_3y"] == pytest.approx((current / anchor(3)) ** (1 / 3) - 1)
    assert row["cagr_5y"] == pytest.approx((current / anchor(5)) ** (1 / 5) - 1)

    one_year_date = prices.loc[
        prices["date"] <= ranking_date - pd.DateOffset(years=1), "date"
    ].iloc[-1]
    trailing = prices.loc[prices["date"] >= one_year_date, "adjusted_close"]
    assert row["annualized_volatility_1y"] == pytest.approx(
        trailing.pct_change().dropna().std(ddof=1) * (252**0.5)
    )
    three_year_date = prices.loc[
        prices["date"] <= ranking_date - pd.DateOffset(years=3), "date"
    ].iloc[-1]
    drawdown_prices = prices.loc[
        prices["date"] >= three_year_date, "adjusted_close"
    ]
    expected_drawdown = (drawdown_prices / drawdown_prices.cummax() - 1).min()
    assert row["max_drawdown_3y"] == pytest.approx(expected_drawdown)
    high_date = prices.loc[
        prices["adjusted_close"].eq(prices["adjusted_close"].max()), "date"
    ].max()
    assert row["days_since_recorded_high"] == (ranking_date - high_date).days


def test_latest_available_revision_for_latest_period_is_selected() -> None:
    inputs = make_inputs((("AAA", "Technology"),))
    inputs.fundamentals.loc[0, ["roce", "debt_to_equity", "profit_growth_yoy"]] = [
        0.10,
        0.8,
        0.05,
    ]
    revised_fundamentals = pd.concat(
        [
            inputs.fundamentals,
            pd.DataFrame(
                [
                    {
                        "ticker": "AAA",
                        "period_end": "2025-03-31",
                        "available_date": "2025-09-01",
                        "roce": 0.30,
                        "debt_to_equity": 0.4,
                        "profit_growth_yoy": 0.20,
                    },
                    {
                        "ticker": "AAA",
                        "period_end": "2024-03-31",
                        "available_date": "2026-01-01",
                        "roce": 0.99,
                        "debt_to_equity": 0.01,
                        "profit_growth_yoy": 0.99,
                    },
                ]
            ),
        ],
        ignore_index=True,
    )
    inputs = ResearchV2Inputs(
        inputs.universe, inputs.prices, revised_fundamentals
    )
    row = calculate_research_v2(inputs, default_config()).rankings.iloc[0]
    assert row["roce"] == pytest.approx(0.30)
    assert row["debt_to_equity"] == pytest.approx(0.4)
    assert row["profit_growth_yoy"] == pytest.approx(0.20)


def test_future_valid_and_malformed_numeric_rows_do_not_change_result() -> None:
    inputs = make_inputs()
    before = calculate_research_v2(inputs, default_config())
    future_prices = pd.DataFrame(
        [
            {"ticker": "AAA", "date": "2026-07-01", "adjusted_close": 99999},
            {"ticker": "BBB", "date": "2026-07-02", "adjusted_close": "bad"},
        ]
    )
    future_fundamentals = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "period_end": "2025-03-31",
                "available_date": "2026-07-01",
                "roce": "bad",
                "debt_to_equity": "bad",
                "profit_growth_yoy": "bad",
            }
        ]
    )
    augmented = ResearchV2Inputs(
        inputs.universe,
        pd.concat([inputs.prices, future_prices], ignore_index=True),
        pd.concat(
            [inputs.fundamentals, future_fundamentals], ignore_index=True
        ),
    )
    after = calculate_research_v2(augmented, default_config())
    assert_frame_equal(before.rankings, after.rankings)
    assert_frame_equal(before.eligibility, after.eligibility)


def test_repeated_recorded_high_uses_latest_date() -> None:
    inputs = make_inputs((("AAA", "Technology"),))
    inputs.prices.loc[
        inputs.prices["date"].isin(["2026-06-29", "2026-06-30"]),
        "adjusted_close",
    ] = 999
    result = calculate_research_v2(inputs, default_config())
    assert result.rankings.iloc[0]["days_since_recorded_high"] == 0


def test_negative_leverage_is_ineligible_with_reason() -> None:
    inputs = make_inputs()
    inputs.fundamentals.loc[
        inputs.fundamentals["ticker"].eq("BBB"), "debt_to_equity"
    ] = -0.2
    result = calculate_research_v2(inputs, default_config())
    report = result.eligibility.set_index("ticker")
    assert not bool(report.loc["BBB", "eligible"])
    assert report.loc["BBB", "reason_code"] == "INVALID_DEBT_TO_EQUITY"
    assert "BBB" not in set(result.rankings["ticker"])


def test_zero_eligible_stocks_returns_empty_canonical_rankings() -> None:
    inputs = make_inputs()
    inputs.fundamentals["debt_to_equity"] = -1
    result = calculate_research_v2(inputs, default_config())
    assert result.rankings.empty
    assert len(result.rankings.columns) > 0
    assert not result.eligibility["eligible"].any()


def test_missing_fundamentals_and_insufficient_history_are_reported() -> None:
    inputs = make_inputs()
    fundamentals = inputs.fundamentals.loc[
        ~inputs.fundamentals["ticker"].eq("AAA")
    ]
    prices = inputs.prices.loc[
        ~(
            inputs.prices["ticker"].eq("BBB")
            & (inputs.prices["date"] < "2025-01-01")
        )
    ]
    inputs = ResearchV2Inputs(inputs.universe, prices, fundamentals)
    result = calculate_research_v2(inputs, default_config())
    report = result.eligibility.set_index("ticker")
    assert "NO_AVAILABLE_FUNDAMENTALS" in report.loc["AAA", "reason_code"]
    assert "MISSING_5Y_PRICE_ANCHOR" in report.loc["BBB", "reason_code"]


def test_in_scope_malformed_numeric_value_makes_stock_ineligible() -> None:
    inputs = make_inputs()
    inputs.prices["adjusted_close"] = inputs.prices["adjusted_close"].astype(
        object
    )
    index = inputs.prices.index[inputs.prices["ticker"].eq("AAA")][10]
    inputs.prices.loc[index, "adjusted_close"] = "bad"
    result = calculate_research_v2(inputs, default_config())
    report = result.eligibility.set_index("ticker")
    assert "INVALID_PRICE_VALUE" in report.loc["AAA", "reason_code"]


def test_in_scope_malformed_fundamental_makes_stock_ineligible() -> None:
    inputs = make_inputs()
    inputs.fundamentals["roce"] = inputs.fundamentals["roce"].astype(object)
    inputs.fundamentals.loc[
        inputs.fundamentals["ticker"].eq("AAA"), "roce"
    ] = "bad"
    result = calculate_research_v2(inputs, default_config())
    report = result.eligibility.set_index("ticker")
    assert "INVALID_ROCE" in report.loc["AAA", "reason_code"]


def test_stale_anniversary_anchor_is_reported() -> None:
    inputs = make_inputs((("AAA", "Technology"),))
    prices = inputs.prices.loc[
        ~(
            (inputs.prices["date"] >= "2025-06-20")
            & (inputs.prices["date"] <= "2025-06-30")
        )
    ]
    result = calculate_research_v2(
        ResearchV2Inputs(inputs.universe, prices, inputs.fundamentals),
        default_config(),
    )
    assert "STALE_1Y_PRICE_ANCHOR" in result.eligibility.loc[0, "reason_code"]


@pytest.mark.parametrize("dataset,date_column", [("prices", "date"), ("fundamentals", "available_date")])
def test_malformed_dates_are_fatal(dataset: str, date_column: str) -> None:
    inputs = make_inputs()
    frame = getattr(inputs, dataset)
    frame.loc[0, date_column] = "not-a-date"
    with pytest.raises(ValueError, match="ISO YYYY-MM-DD"):
        calculate_research_v2(inputs, default_config())


@pytest.mark.parametrize("dataset", ["prices", "fundamentals"])
def test_duplicate_natural_key_is_fatal(dataset: str) -> None:
    inputs = make_inputs()
    frame = getattr(inputs, dataset)
    duplicated = pd.concat(
        [frame, frame.iloc[[0]]],
        ignore_index=True,
    )
    inputs = ResearchV2Inputs(
        inputs.universe,
        duplicated if dataset == "prices" else inputs.prices,
        duplicated if dataset == "fundamentals" else inputs.fundamentals,
    )
    with pytest.raises(ValueError, match="duplicate"):
        calculate_research_v2(inputs, default_config())


def test_results_are_deterministic_after_all_inputs_are_shuffled() -> None:
    inputs = make_inputs(
        (
            ("AAA", "Technology"),
            ("BBB", "Technology"),
            ("CCC", "Industrials"),
        )
    )
    first = calculate_research_v2(inputs, default_config())
    shuffled = ResearchV2Inputs(
        inputs.universe.sample(frac=1, random_state=1).reset_index(drop=True),
        inputs.prices.sample(frac=1, random_state=2).reset_index(drop=True),
        inputs.fundamentals.sample(frac=1, random_state=3).reset_index(drop=True),
    )
    second = calculate_research_v2(shuffled, default_config())
    assert_frame_equal(first.rankings, second.rankings)
    assert_frame_equal(first.eligibility, second.eligibility)
