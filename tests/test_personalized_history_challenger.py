from pathlib import Path

import numpy as np
import pandas as pd

from research.runners import personalized_history_challenger as challenger


def test_short_history_uses_shrunk_estimate_and_observed_flag(tmp_path, monkeypatch):
    root = tmp_path
    cache = root / "history"
    cache.mkdir()
    repairs = root / "experiments/personalized-data-freeze/build-01"
    repairs.mkdir(parents=True)
    pd.DataFrame(columns=["isin", "snapshot_status", "appended_date", "ticker", "appended_price"]).to_csv(
        repairs / "terminal_repairs.csv", index=False)
    day = "2026-09-18"
    long_dates = pd.date_range("2019-01-01", day, freq="7D")
    short_dates = pd.date_range("2023-01-01", day, freq="7D")
    # End exactly on the decision date; the series contains actual observations only.
    long_dates = long_dates.append(pd.DatetimeIndex([day])) if long_dates[-1] != pd.Timestamp(day) else long_dates
    short_dates = short_dates.append(pd.DatetimeIndex([day])) if short_dates[-1] != pd.Timestamp(day) else short_dates
    for ticker, dates, end_price in (("LONG", long_dates, 150.), ("YOUNG", short_dates, 300.)):
        prices = np.linspace(100., end_price, len(dates))
        pd.DataFrame({"date": dates, "adjusted_close": prices}).to_csv(cache / f"{ticker}.csv", index=False)
    monkeypatch.setattr(challenger, "ROOT", root)
    monkeypatch.setattr(challenger, "HISTORY", cache)
    panel = pd.DataFrame({"isin": ["LONG", "YOUNG"], "decision_date": [day, day]})
    facts = pd.DataFrame({"isin": ["LONG", "YOUNG"], "ticker": ["LONG", "YOUNG"],
                          "derived_research_sector": ["Retailing", "Retailing"]})
    result = challenger.history_features({"current": panel}, facts).set_index("isin")
    assert result.loc["LONG", "cagr_5y_source"] == "OBSERVED"
    young = result.loc["YOUNG"]
    assert young.cagr_5y_source == "ESTIMATED"
    assert young.cagr_5y_observed == 0
    assert np.isfinite(young.cagr_5y)
    assert young.cagr_5y < young.history_start_cagr
    assert young.days_since_recorded_high == 0
    assert young.distance_from_recorded_high == 0
    assert young.full_history_max_drawdown == 0
