from __future__ import annotations

import pandas as pd
import pytest

from stock_ranker.research_v2 import (
    _rank_range_scores,
    _score_eligible,
    get_top_research_v2_by_sector,
)
from stock_ranker.v2_contracts import (
    V2_CONTRIBUTION_COLUMNS,
    V2_METRIC_COLUMNS,
)
from tests.v2_helpers import default_config


def test_rank_range_formula_gives_tied_extremes_100_and_0() -> None:
    values = pd.Series([30.0, 30.0, 20.0, 10.0, 10.0])
    scores = _rank_range_scores(values, higher_is_better=True)
    assert scores.tolist() == pytest.approx([100, 100, 50, 0, 0])


def test_lower_is_better_reverses_direction() -> None:
    values = pd.Series([30.0, 20.0, 10.0])
    scores = _rank_range_scores(values, higher_is_better=False)
    assert scores.tolist() == pytest.approx([0, 50, 100])


def test_all_equal_and_single_stock_receive_50() -> None:
    assert _rank_range_scores(
        pd.Series([7.0, 7.0, 7.0]), higher_is_better=True
    ).tolist() == [50, 50, 50]
    assert _rank_range_scores(
        pd.Series([7.0]), higher_is_better=False
    ).tolist() == [50]


def test_scores_depend_on_rank_not_raw_value_distance() -> None:
    close_values = _rank_range_scores(
        pd.Series([3.0, 2.0, 1.0]), higher_is_better=True
    )
    distant_values = _rank_range_scores(
        pd.Series([1_000_000.0, 2.0, -50_000.0]), higher_is_better=True
    )
    assert close_values.tolist() == distant_values.tolist() == [100, 50, 0]


def _metric_frame() -> pd.DataFrame:
    rows = []
    for ticker, sector, value in (
        ("AAA", "Technology", 30.0),
        ("BBB", "Technology", 20.0),
        ("CCC", "Technology", 10.0),
        ("DDD", "Industrials", 5.0),
    ):
        row: dict[str, object] = {
            "ticker": ticker,
            "company": f"{ticker} Fictional",
            "sector": sector,
            "ranking_date": "2026-06-30",
        }
        row.update({metric: value for metric in V2_METRIC_COLUMNS})
        rows.append(row)
    return pd.DataFrame(rows)


def test_scoring_is_isolated_by_sector_and_contributions_sum_exactly() -> None:
    scored = _score_eligible(_metric_frame(), default_config())
    indexed = scored.set_index("ticker")
    assert indexed.loc["AAA", "return_1y_score"] == 100
    assert indexed.loc["CCC", "return_1y_score"] == 0
    assert indexed.loc["DDD", "return_1y_score"] == 50
    contribution_sum = scored[list(V2_CONTRIBUTION_COLUMNS)].sum(axis=1)
    assert contribution_sum.tolist() == pytest.approx(
        scored["research_v2_score"].tolist()
    )


def test_tied_final_scores_keep_equal_sector_rank_and_cutoff_uses_ticker() -> None:
    frame = _metric_frame()
    frame.loc[frame["ticker"].isin(["AAA", "BBB"]), list(V2_METRIC_COLUMNS)] = 30
    scored = _score_eligible(frame, default_config())
    indexed = scored.set_index("ticker")
    assert indexed.loc["AAA", "research_v2_score"] == indexed.loc[
        "BBB", "research_v2_score"
    ]
    assert indexed.loc["AAA", "sector_rank"] == indexed.loc["BBB", "sector_rank"]
    top = get_top_research_v2_by_sector(scored, 1)
    assert top.loc[top["sector"] == "Technology", "ticker"].item() == "AAA"
