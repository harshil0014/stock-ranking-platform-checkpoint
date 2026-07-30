from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_ranker.ingestion import load_stock_csv
from stock_ranker.validation import validate_baseline_input


def valid_data() -> pd.DataFrame:
    return pd.DataFrame(
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


def test_missing_and_misspelled_columns_are_rejected() -> None:
    data = valid_data().rename(columns={"ticker": "symbol"})
    with pytest.raises(ValueError, match="Missing required columns: ticker"):
        validate_baseline_input(data)


@pytest.mark.parametrize("column", ["ticker", "company", "sector"])
def test_blank_identity_values_are_rejected(column: str) -> None:
    data = valid_data()
    data.loc[0, column] = "   "
    with pytest.raises(ValueError, match=column):
        validate_baseline_input(data)


def test_missing_required_values_are_rejected() -> None:
    data = valid_data()
    data.loc[0, "company"] = None
    with pytest.raises(ValueError, match="Missing values.*company"):
        validate_baseline_input(data)


@pytest.mark.parametrize("date_value", ["30/06/2026", "2026-6-30", "not-a-date"])
def test_non_iso_dates_are_rejected(date_value: str) -> None:
    data = valid_data()
    data.loc[0, "as_of_date"] = date_value
    with pytest.raises(ValueError, match="ISO YYYY-MM-DD"):
        validate_baseline_input(data)


def test_impossible_calendar_date_is_rejected() -> None:
    data = valid_data()
    data.loc[0, "as_of_date"] = "2026-02-30"
    with pytest.raises(ValueError, match="invalid calendar date"):
        validate_baseline_input(data)


@pytest.mark.parametrize(
    "value",
    ["not-a-number", np.nan, np.inf, -np.inf, 0, -1],
)
def test_invalid_prices_are_rejected(value: object) -> None:
    data = valid_data()
    data["close_3y_ago"] = data["close_3y_ago"].astype(object)
    data.loc[0, "close_3y_ago"] = value
    with pytest.raises(ValueError, match="close_3y_ago"):
        validate_baseline_input(data)


def test_recorded_high_after_observation_is_rejected() -> None:
    data = valid_data()
    data.loc[0, "ath_date"] = "2026-07-01"
    with pytest.raises(ValueError, match="recorded high date"):
        validate_baseline_input(data)


def test_duplicate_ticker_and_date_is_rejected() -> None:
    data = pd.concat([valid_data(), valid_data()], ignore_index=True)
    with pytest.raises(ValueError, match=r"Duplicate \(ticker, as_of_date\)"):
        validate_baseline_input(data)


def test_same_ticker_on_different_dates_is_allowed() -> None:
    second = valid_data()
    second.loc[0, "as_of_date"] = "2026-07-01"
    data = pd.concat([valid_data(), second], ignore_index=True)
    assert len(validate_baseline_input(data)) == 2


def test_loader_rejects_missing_file(tmp_path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        load_stock_csv(tmp_path / "missing.csv")


def test_loader_reads_and_validates_csv(tmp_path) -> None:
    path = tmp_path / "stocks.csv"
    valid_data().to_csv(path, index=False)

    loaded = load_stock_csv(path)

    assert loaded.loc[0, "ticker"] == "SYN001"
    assert pd.api.types.is_datetime64_any_dtype(loaded["as_of_date"])
