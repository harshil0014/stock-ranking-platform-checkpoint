from __future__ import annotations

import pandas as pd

from stock_ranker.baseline import (
    calculate_baseline_rankings,
    get_top_stocks_by_sector,
)
from stock_ranker.exporting import export_rankings


def test_export_creates_both_canonical_output_files(tmp_path) -> None:
    data = pd.DataFrame(
        [
            {
                "ticker": "SYN001",
                "company": "Synthetic One",
                "sector": "Technology",
                "as_of_date": "2026-06-30",
                "current_price": 120,
                "close_1y_ago": 100,
                "close_3y_ago": 80,
                "close_5y_ago": 60,
                "ath_date": "2026-06-20",
            }
        ]
    )
    full = calculate_baseline_rankings(data)
    top = get_top_stocks_by_sector(full, 1)

    result = export_rankings(full, top, tmp_path / "nested", 1)

    assert result.full_rankings_path.name == "full_rankings.csv"
    assert result.top_rankings_path.name == "top_1_rankings.csv"
    assert result.full_rankings_path.is_file()
    assert result.top_rankings_path.is_file()
    assert pd.read_csv(result.full_rankings_path)["ticker"].tolist() == [
        "SYN001"
    ]
