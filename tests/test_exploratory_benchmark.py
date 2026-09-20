from pathlib import Path

import pandas as pd
import pytest

from stock_research.exploratory_benchmark import build_exploratory_signals, evaluate_exploratory_signals, strict_mom12m
from stock_research.exploratory_benchmark import expanding_ridge_predictions, strict_price_factors


def _history() -> pd.DataFrame:
    dates = pd.date_range("2021-08-31", "2022-07-31", freq="ME")
    return pd.DataFrame({"date": dates, "adjusted_close": [100 * (1.01 ** index) for index in range(12)]})


def test_strict_mom12m_matches_complete_compound_return() -> None:
    assert strict_mom12m(_history(), "2022-08-05") == pytest.approx(1.01**11 - 1)


def test_strict_mom12m_rejects_missing_month_instead_of_zero_fill() -> None:
    with pytest.raises(ValueError, match="incomplete Mom12m"):
        strict_mom12m(_history().drop(index=4), "2022-08-05")


def test_strict_mom12m_ignores_unused_ancient_bad_observation() -> None:
    history = pd.concat([
        pd.DataFrame({"date": ["1999-01-01"], "adjusted_close": [0]}),
        _history(),
    ], ignore_index=True)
    assert strict_mom12m(history, "2022-08-05") == pytest.approx(1.01**11 - 1)


def test_fixed_signals_and_evaluation_preserve_frozen_keys(tmp_path: Path) -> None:
    members = []
    for index, ticker in enumerate(("AAA", "BBB", "CCC"), 1):
        dates = pd.date_range("2021-08-01", "2022-07-31", freq="B")
        history = pd.DataFrame({
            "date": dates,
            "adjusted_close": 100 * ((1 + index / 10000) ** pd.RangeIndex(len(dates))),
        })
        history.to_csv(tmp_path / f"{ticker}.csv", index=False)
        members.append({"ranking_date": "2022-08-05", "ticker": ticker, "isin": f"ISIN{index}", "sector": "Sector", "baseline_sector_rank": index, "research_v2_sector_rank": 4 - index})
    signals = build_exploratory_signals(pd.DataFrame(members), tmp_path)
    assert signals["baseline_signal"].tolist() == pytest.approx([1, 2 / 3, 1 / 3])
    outcomes = pd.DataFrame([
        {"ranking_date": "2022-08-05", "actual_endpoint_date": "2023-08-04", "ticker": ticker, "isin": f"ISIN{index}", "horizon_months": 12, "future_adjusted_return": float(index)}
        for index, ticker in enumerate(("AAA", "BBB", "CCC"), 1)
    ])
    metrics, summary = evaluate_exploratory_signals(signals, outcomes)
    assert len(metrics) == 1
    assert summary["selection_performed"] is False
    assert summary["product_default_changed"] is False


@pytest.mark.parametrize("invalid", [0, -1, float("nan"), float("inf")])
def test_daily_factor_window_never_bridges_invalid_prices(invalid: float) -> None:
    dates = pd.date_range("2021-08-01", "2022-08-04", freq="B")
    history = pd.DataFrame({"date": dates, "adjusted_close": 100.0})
    history.loc[100, "adjusted_close"] = invalid
    with pytest.raises(ValueError, match="daily window"):
        strict_price_factors(history, "2022-08-05")


def test_daily_factor_duplicate_rejected() -> None:
    history = pd.DataFrame({"date": ["2022-07-01"] * 2, "adjusted_close": [100, 101]})
    with pytest.raises(ValueError, match="duplicate"):
        strict_price_factors(history, "2022-08-05")


def test_ridge_uses_only_matured_complete_sector_targets() -> None:
    rows, outcomes = [], []
    features = ["baseline_signal", "research_v2_signal", "mom12m_signal", "mom6m_signal",
                "reversal1m_signal", "low_volatility_signal", "shallow_drawdown_signal"]
    for year in (2022, 2023, 2024):
        for index in range(3):
            key = {"ranking_date": f"{year}-08-07", "ticker": str(index), "isin": f"I{index}"}
            rows.append({**key, "sector": "S", **{feature: (index + 1) / 3 for feature in features}})
            outcomes.append({**key, "horizon_months": 12, "future_adjusted_return": index / 10,
                             "actual_endpoint_date": f"{year + 1}-08-07"})
    signals, labels = pd.DataFrame(rows), pd.DataFrame(outcomes)
    predictions = expanding_ridge_predictions(signals, labels)
    assert set(predictions.ranking_date) == {"2024-08-07"}
    assert set(predictions.training_dates) == {"2022-08-07"}
    assert set(predictions.training_rows) == {3}
    # Neither same-day-maturing nor test/future outcomes may affect the model.
    labels.loc[labels.ranking_date.ne("2022-08-07"), "future_adjusted_return"] = [99, -20, 5, -8, 100, 0]
    changed = expanding_ridge_predictions(signals, labels)
    pd.testing.assert_series_equal(predictions.expanding_ridge_signal, changed.expanding_ridge_signal)
    # Even one unavailable peer prevents using the whole rank-target group.
    labels.loc[0, "actual_endpoint_date"] = "2024-08-07"
    assert expanding_ridge_predictions(signals, labels).empty
