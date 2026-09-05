from __future__ import annotations

import pandas as pd
import pytest

from stock_ranker.liquidity_contract import calculate_point_in_time_liquidity, validate_liquidity_panel


def _panel() -> pd.DataFrame:
    return pd.DataFrame([
        {"ticker": "A", "isin": "INE000A01001", "exchange": "NSE", "trade_date": "2026-01-01", "available_date": "2026-01-01", "close": 10, "volume": 100, "traded_value": 1000, "trade_count": 5, "source": "official bhavcopy"},
        {"ticker": "A", "isin": "INE000A01001", "exchange": "NSE", "trade_date": "2026-01-02", "available_date": "2026-01-02", "close": 11, "volume": 200, "traded_value": 2200, "trade_count": 0, "source": "official bhavcopy"},
        {"ticker": "A", "isin": "INE000A01001", "exchange": "NSE", "trade_date": "2026-01-03", "available_date": "2026-01-04", "close": 12, "volume": 300, "traded_value": 3600, "trade_count": 8, "source": "official bhavcopy"},
    ])


def test_liquidity_cutoff_filters_on_trade_and_real_availability_date() -> None:
    result = calculate_point_in_time_liquidity(_panel(), ["2026-01-03"], window=2)
    row = result.iloc[0]
    assert row["latest_trade_date"] == "2026-01-02"
    assert row["average_daily_volume"] == 150
    assert row["median_daily_traded_value"] == 1600
    assert row["zero_trade_day_count"] == 1
    assert row["liquidity_status"] == "COMPLETE_WINDOW"


def test_liquidity_panel_is_not_mutated_and_rejects_invalid_evidence() -> None:
    original = _panel()
    before = original.copy(deep=True)
    validate_liquidity_panel(original)
    pd.testing.assert_frame_equal(original, before)
    bad = original.copy()
    bad.loc[0, "traded_value"] = -1
    with pytest.raises(ValueError, match="nonnegative"):
        validate_liquidity_panel(bad)


def test_liquidity_contract_does_not_estimate_transaction_costs() -> None:
    result = calculate_point_in_time_liquidity(_panel(), ["2026-01-04"], window=20)
    assert result.iloc[0]["liquidity_status"] == "PARTIAL_WINDOW"
    assert not any("cost" in column for column in result.columns)
