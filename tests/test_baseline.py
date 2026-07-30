from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from stock_ranker.baseline import (
    calculate_baseline_rankings,
    get_top_stocks_by_sector,
)
from stock_ranker.config import BASELINE_METHOD_VERSION, BaselineConfig
from stock_ranker.contracts import OUTPUT_COLUMNS


def make_row(
    ticker: str,
    sector: str = "Technology",
    current_price: float = 120,
    close_1y_ago: float = 100,
    close_3y_ago: float = 80,
    close_5y_ago: float = 60,
    ath_date: str = "2026-06-20",
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "company": f"{ticker} Synthetic Company",
        "sector": sector,
        "as_of_date": "2026-06-30",
        "current_price": current_price,
        "close_1y_ago": close_1y_ago,
        "close_3y_ago": close_3y_ago,
        "close_5y_ago": close_5y_ago,
        "ath_date": ath_date,
    }


def test_metrics_are_calculated_with_decimal_return_representation() -> None:
    result = calculate_baseline_rankings(
        pd.DataFrame(
            [
                make_row(
                    "ONE",
                    current_price=120,
                    close_1y_ago=100,
                    close_3y_ago=80,
                    close_5y_ago=60,
                    ath_date="2026-06-20",
                )
            ]
        )
    ).iloc[0]

    assert result["yoy_growth"] == pytest.approx(0.2)
    assert result["cagr_3y"] == pytest.approx(1.5 ** (1 / 3) - 1)
    assert result["cagr_5y"] == pytest.approx(2 ** (1 / 5) - 1)
    assert result["days_since_recorded_high"] == 10


def test_ranking_directions_and_sector_isolation() -> None:
    data = pd.DataFrame(
        [
            make_row("TECH_HIGH", current_price=150, ath_date="2026-06-29"),
            make_row("TECH_LOW", current_price=105, ath_date="2025-01-01"),
            make_row(
                "FIN_BEST",
                sector="Financial Services",
                current_price=1000,
                ath_date="2026-06-30",
            ),
        ]
    )

    result = calculate_baseline_rankings(data).set_index("ticker")

    assert result.loc["TECH_HIGH", "yoy_rank"] == 1
    assert result.loc["TECH_HIGH", "recorded_high_recency_rank"] == 1
    assert result.loc["TECH_LOW", "yoy_rank"] == 2
    assert result.loc["TECH_LOW", "recorded_high_recency_rank"] == 2
    assert result.loc["FIN_BEST", "sector_rank"] == 1


def test_equal_metrics_and_scores_keep_competition_ties() -> None:
    data = pd.DataFrame(
        [
            make_row("BBB", current_price=150, close_1y_ago=100),
            make_row(
                "AAA",
                current_price=180,
                close_1y_ago=120,
                close_3y_ago=96,
                close_5y_ago=72,
            ),
            make_row("CCC", current_price=105, close_1y_ago=100),
        ]
    )

    result = calculate_baseline_rankings(data)
    tied = result[result["ticker"].isin(["AAA", "BBB"])].set_index("ticker")

    assert tied.loc["AAA", "yoy_rank"] == tied.loc["BBB", "yoy_rank"]
    assert tied.loc["AAA", "baseline_score"] == tied.loc["BBB", "baseline_score"]
    assert tied.loc["AAA", "sector_rank"] == tied.loc["BBB", "sector_rank"]
    assert result["ticker"].tolist()[:2] == ["AAA", "BBB"]


def test_top_n_uses_ticker_to_break_cutoff_tie() -> None:
    data = pd.DataFrame(
        [
            make_row("BBB", current_price=150),
            make_row("AAA", current_price=150),
            make_row("CCC", current_price=90),
            make_row("FIN", sector="Financial Services"),
        ]
    )
    rankings = calculate_baseline_rankings(data)

    top = get_top_stocks_by_sector(rankings, top_n=1)

    assert top.groupby("sector").size().to_dict() == {
        "Financial Services": 1,
        "Technology": 1,
    }
    assert top.loc[top["sector"] == "Technology", "ticker"].item() == "AAA"


def test_top_n_larger_than_sector_returns_all_rows() -> None:
    rankings = calculate_baseline_rankings(
        pd.DataFrame([make_row("AAA"), make_row("BBB")])
    )
    assert len(get_top_stocks_by_sector(rankings, top_n=10)) == 2


@pytest.mark.parametrize("top_n", [0, -1, True, 1.5])
def test_invalid_top_n_is_rejected(top_n: object) -> None:
    rankings = calculate_baseline_rankings(pd.DataFrame([make_row("AAA")]))
    with pytest.raises(ValueError, match="positive integer"):
        get_top_stocks_by_sector(rankings, top_n=top_n)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="positive integer"):
        BaselineConfig(top_n=top_n)  # type: ignore[arg-type]


def test_results_are_deterministic_after_input_shuffle() -> None:
    data = pd.DataFrame(
        [
            make_row("DDD", current_price=103),
            make_row("AAA", current_price=150),
            make_row("CCC", sector="Industrials", current_price=130),
            make_row("BBB", sector="Industrials", current_price=130),
        ]
    )

    first = calculate_baseline_rankings(data)
    second = calculate_baseline_rankings(
        data.sample(frac=1, random_state=41).reset_index(drop=True)
    )

    assert_frame_equal(first, second)


def test_calculation_does_not_mutate_input_and_uses_stable_schema() -> None:
    data = pd.DataFrame([make_row("AAA")]).assign(extra_note="ignored")
    original = data.copy(deep=True)

    result = calculate_baseline_rankings(data)

    assert_frame_equal(data, original)
    assert tuple(result.columns) == OUTPUT_COLUMNS
    assert "extra_note" not in result
    assert result.loc[0, "method_version"] == BASELINE_METHOD_VERSION
