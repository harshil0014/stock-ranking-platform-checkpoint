from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stock_ranker.history_enrichment import (
    HistoryEnrichmentError,
    build_current_history_enrichment,
    compute_history_metrics,
    load_history,
)


def _history(start="2021-09-17", periods=1305, start_price=100.0, end_price=200.0):
    dates = pd.bdate_range(start, periods=periods)
    prices = np.geomspace(start_price, end_price, len(dates))
    return pd.DataFrame({"date": dates, "price": prices})


def test_metrics_keep_true_5y_missing_for_short_history():
    frame = _history(start="2023-09-18", periods=783)
    frame = frame.loc[frame.date.le(pd.Timestamp("2026-09-18"))]
    metrics = compute_history_metrics(frame, cutoff="2026-09-18")
    assert metrics["strict_cagr_3y"] is not None
    assert metrics["strict_cagr_5y"] is None
    assert metrics["history_months"] < 60


def test_days_since_high_uses_cutoff_and_observed_peak():
    frame = pd.DataFrame({
        "date": pd.to_datetime(["2026-09-14", "2026-09-15", "2026-09-18"]),
        "price": [10.0, 12.0, 11.0],
    })
    metrics = compute_history_metrics(frame, cutoff="2026-09-18")
    assert metrics["recorded_high_date"] == "2026-09-15"
    assert metrics["days_since_recorded_high"] == 3
    assert metrics["distance_from_recorded_high"] == pytest.approx(11 / 12 - 1)


def test_terminal_staleness_is_rejected():
    frame = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-20", "2026-08-21"]),
        "price": [10.0, 11.0],
    })
    with pytest.raises(HistoryEnrichmentError, match="terminal history lag"):
        compute_history_metrics(frame, cutoff="2026-09-18")


def test_accepted_short_terminal_lag_is_explicitly_flagged():
    frame = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-01", "2026-09-04"]),
        "price": [10.0, 11.0],
    })
    metrics = compute_history_metrics(frame, cutoff="2026-09-18")
    assert metrics["terminal_lag_days"] == 14
    assert metrics["terminal_history_quality"] == "ACCEPTED_STALE_8_21D"


def test_enrichment_never_labels_short_history_estimate_observed(tmp_path: Path):
    history_root = tmp_path / "history"
    history_root.mkdir()
    dates = pd.bdate_range("2023-09-18", "2026-09-18")
    pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "adjusted_close": np.geomspace(100.0, 180.0, len(dates)),
    }).to_csv(history_root / "YOUNG.csv", index=False)
    facts = pd.DataFrame([{
        "isin": "INE000000001",
        "ticker": "YOUNG",
        "derived_research_sector": "Retailing",
        "listing_date": "2023-09-18",
        "recorded_high_date": "2026-09-18",
        "recorded_high": 180.0,
        "screener_return_3y_pct": 80.0,
        "screener_return_5y_pct": np.nan,
        "screener_all_time_high_price": 180.0,
    }])
    result = build_current_history_enrichment(
        facts,
        primary_root=history_root,
        recovery_root=None,
        cutoff="2026-09-18",
    ).iloc[0]
    assert result["cagr_5y_observed"] == 0
    assert result["long_term_growth_is_observed"] == 0
    assert result["long_term_growth_source"] == "ESTIMATED_HISTORY_SECTOR_SHRUNK"
    assert pd.notna(result["long_term_growth_value"])


def test_missing_history_gets_neutral_sector_estimate_not_nan(tmp_path: Path):
    root = tmp_path / "history"
    root.mkdir()
    dates = pd.bdate_range("2021-09-17", "2026-09-18")
    pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "adjusted_close": np.geomspace(100.0, 150.0, len(dates)),
    }).to_csv(root / "MATURE.csv", index=False)
    facts = pd.DataFrame([
        {
            "isin": "INE000000001", "ticker": "MATURE",
            "derived_research_sector": "Sector A", "listing_date": "2020-01-01",
            "recorded_high_date": "2026-09-18", "recorded_high": 150.0,
            "screener_return_3y_pct": np.nan, "screener_return_5y_pct": np.nan,
            "screener_all_time_high_price": np.nan,
        },
        {
            "isin": "INE000000002", "ticker": "MISSING",
            "derived_research_sector": "Sector A", "listing_date": np.nan,
            "recorded_high_date": "2025-01-01", "recorded_high": 50.0,
            "screener_return_3y_pct": np.nan, "screener_return_5y_pct": np.nan,
            "screener_all_time_high_price": np.nan,
        },
    ])
    result = build_current_history_enrichment(
        facts, primary_root=root, recovery_root=None, cutoff="2026-09-18"
    ).set_index("ticker")
    assert result.loc["MATURE", "long_term_growth_is_observed"]
    assert not result.loc["MISSING", "long_term_growth_is_observed"]
    assert result.loc["MISSING", "long_term_growth_source"] == "ESTIMATED_SECTOR_MEDIAN_ONLY"
    assert result.loc["MISSING", "long_term_growth_value"] == pytest.approx(
        result.loc["MATURE", "strict_cagr_5y"]
    )
    assert result.loc["MISSING", "days_since_recorded_high"] == (
        pd.Timestamp("2026-09-18") - pd.Timestamp("2025-01-01")
    ).days


def test_load_history_prefers_adjusted_close(tmp_path: Path):
    path = tmp_path / "x.csv"
    pd.DataFrame({
        "date": ["2026-09-17", "2026-09-18"],
        "raw_close": [100.0, 110.0],
        "adjusted_close": [50.0, 55.0],
    }).to_csv(path, index=False)
    got = load_history(path, cutoff="2026-09-18")
    assert got["price"].tolist() == [50.0, 55.0]


def test_history_age_is_not_mislabeled_as_listing_age_when_listing_date_missing():
    frame = pd.DataFrame({
        "date": pd.to_datetime(["2024-09-18", "2025-09-18", "2026-09-18"]),
        "price": [100.0, 120.0, 150.0],
    })
    metrics = compute_history_metrics(frame, cutoff="2026-09-18", listing_date=np.nan)
    assert metrics["history_age_basis"] == "OBSERVED_PRICE_HISTORY_SPAN"
    assert not metrics["listing_date_available"]
    assert metrics["listing_age_months"] is None
    assert not metrics["listing_date_consistent_with_history_start"]


def test_listing_age_is_separate_when_official_listing_date_exists():
    frame = pd.DataFrame({
        "date": pd.to_datetime(["2024-09-18", "2025-09-18", "2026-09-18"]),
        "price": [100.0, 120.0, 150.0],
    })
    metrics = compute_history_metrics(frame, cutoff="2026-09-18", listing_date="2024-09-10")
    assert metrics["listing_date_available"]
    assert metrics["listing_age_months"] > metrics["history_months"]
    assert metrics["listing_date_consistent_with_history_start"]


def test_raw_bse_risk_fallback_never_becomes_adjusted_return_history(tmp_path: Path):
    primary = tmp_path / "primary"
    raw = tmp_path / "raw"
    primary.mkdir(); raw.mkdir()
    dates = pd.bdate_range("2023-01-02", "2026-09-18")
    pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "close": np.geomspace(50.0, 100.0, len(dates)),
    }).to_csv(raw / "BSE-123456.csv", index=False)
    facts = pd.DataFrame([{
        "isin": "INE000000999",
        "ticker": "BSE-123456",
        "derived_research_sector": "Industrials",
        "listing_date": np.nan,
        "recorded_high_date": np.nan,
        "recorded_high": np.nan,
        "screener_return_3y_pct": np.nan,
        "screener_return_5y_pct": np.nan,
        "screener_all_time_high_price": np.nan,
    }])
    row = build_current_history_enrichment(
        facts,
        primary_root=primary,
        recovery_root=None,
        raw_risk_root=raw,
        cutoff="2026-09-18",
    ).iloc[0]
    assert row["history_quality"] == "RAW_RISK_ONLY"
    assert not row["adjusted_history_available"]
    assert row["risk_metric_source"] == "OFFICIAL_BSE_RAW_CLOSE"
    assert row["return_metric_source"] == "UNAVAILABLE_UNADJUSTED_CORPORATE_ACTIONS"
    assert pd.notna(row["full_history_max_drawdown"])
    assert pd.notna(row["days_since_recorded_high"])
    assert pd.isna(row.get("strict_cagr_3y"))
    assert pd.isna(row.get("strict_cagr_5y"))
    assert row["long_term_growth_source"] == "ESTIMATED_SECTOR_MEDIAN_ONLY"
