from __future__ import annotations

from pathlib import Path

import pandas as pd

from stock_ranker.product_classification import add_product_classification_and_baseline


def _history(path: Path, ticker: str) -> None:
    dates = pd.date_range("2019-01-01", "2026-08-19", freq="B")
    pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "adjusted_close": range(100, 100 + len(dates))}).to_csv(path / f"{ticker}.csv", index=False)


def test_product_classification_uses_official_then_exact_secondary(tmp_path: Path):
    _history(tmp_path, "SECONDARY")
    provider_current = float(pd.read_csv(tmp_path / "SECONDARY.csv").iloc[-1]["adjusted_close"])
    facts = pd.DataFrame([
        {"ticker": "OFFICIAL", "company": "Official Ltd", "listing_date": "2000-01-01", "trade_date": "2026-08-19", "latest_price": 10,
         "official_sector": "Official Sector", "official_industry": "Official Industry", "official_basic_industry": None,
         "official_classification_source": "NSE", "secondary_identity_status": "EXCHANGE_SYMBOL_MATCH", "secondary_sector": "Wrong Secondary",
         "secondary_industry": "Wrong", "secondary_source": "Yahoo", "secondary_source_as_of": "2026-08-19", "baseline_eligible": True,
         "baseline_yoy_growth": .1, "baseline_cagr_3y": .2, "baseline_cagr_5y": .3, "baseline_days_since_recorded_high": 5,
         "baseline_reason_code": "ELIGIBLE", "history_reason": "ok"},
        {"ticker": "SECONDARY", "company": "Secondary Ltd", "listing_date": "2010-01-01", "trade_date": "2026-08-19", "latest_price": provider_current,
         "official_sector": None, "official_industry": None, "official_basic_industry": None, "official_classification_source": None,
         "secondary_identity_status": "EXCHANGE_SYMBOL_MATCH", "secondary_sector": "Reference Sector", "secondary_industry": "Reference Industry",
         "secondary_source": "Yahoo", "secondary_source_as_of": "2026-08-19", "baseline_eligible": False, "baseline_reason_code": "UNCLASSIFIED"},
        {"ticker": "REJECTED", "company": "Rejected Ltd", "listing_date": "2010-01-01", "trade_date": "2026-08-19", "latest_price": 10,
         "official_sector": None, "official_industry": None, "official_basic_industry": None, "official_classification_source": None,
         "secondary_identity_status": "NAME_ONLY", "secondary_sector": "Guessed", "secondary_industry": None,
         "secondary_source": "Yahoo", "secondary_source_as_of": "2026-08-19", "baseline_eligible": False, "baseline_reason_code": "UNCLASSIFIED"},
    ])
    result = add_product_classification_and_baseline(facts, history_root=tmp_path).set_index("ticker")
    assert result.loc["OFFICIAL", "product_sector"] == "Official Sector"
    assert result.loc["OFFICIAL", "product_classification_evidence"] == "OFFICIAL"
    assert result.loc["SECONDARY", "product_sector"] == "Reference Sector"
    assert result.loc["SECONDARY", "product_classification_evidence"] == "EXACT_IDENTITY_SECONDARY_REFERENCE"
    assert bool(result.loc["SECONDARY", "product_baseline_eligible"])
    assert result.loc["REJECTED", "product_classification_evidence"] == "UNCLASSIFIED"
    assert not bool(result.loc["REJECTED", "product_baseline_eligible"])


def test_product_baseline_reuses_unchanged_metric_values(tmp_path: Path):
    facts = pd.DataFrame([{
        "ticker": "A", "company": "A Ltd", "listing_date": "2000-01-01", "trade_date": "2026-08-19", "latest_price": 10,
        "official_sector": "Sector", "official_industry": None, "official_basic_industry": None,
        "official_classification_source": "NSE", "secondary_identity_status": "NOT_CHECKED", "secondary_sector": None,
        "baseline_eligible": True, "baseline_yoy_growth": 0.12, "baseline_cagr_3y": 0.08,
        "baseline_cagr_5y": 0.06, "baseline_days_since_recorded_high": 9,
        "baseline_reason_code": "ELIGIBLE", "history_reason": "ok",
    }])
    row = add_product_classification_and_baseline(facts, history_root=tmp_path).iloc[0]
    assert row["product_baseline_yoy_growth"] == 0.12
    assert row["product_baseline_cagr_3y"] == 0.08
    assert row["product_baseline_cagr_5y"] == 0.06
    assert row["product_baseline_days_since_recorded_high"] == 9
    assert row["product_baseline_score"] == 1
    assert row["product_baseline_sector_rank"] == 1


def test_bulk_exact_identity_is_used_only_after_existing_evidence(tmp_path: Path):
    facts = pd.DataFrame([
        {"ticker": "OFFICIAL", "company": "Official", "trade_date": "2026-08-21", "latest_price": 1,
         "official_sector": "Official", "official_classification_source": "NSE",
         "secondary_identity_status": "NOT_CHECKED", "secondary_sector": None,
         "bulk_classification_status": "ACCEPTED", "bulk_classification_sector": "Bulk",
         "baseline_eligible": False, "baseline_reason_code": "INSUFFICIENT_5Y_HISTORY"},
        {"ticker": "RICH", "company": "Rich", "trade_date": "2026-08-21", "latest_price": 1,
         "official_sector": None, "secondary_identity_status": "EXCHANGE_SYMBOL_MATCH",
         "secondary_sector": "Rich Secondary", "secondary_source": "Yahoo info",
         "bulk_classification_status": "ACCEPTED", "bulk_classification_sector": "Bulk",
         "baseline_eligible": False, "baseline_reason_code": "UNCLASSIFIED"},
        {"ticker": "BULK", "company": "Bulk", "trade_date": "2026-08-21", "latest_price": 1,
         "official_sector": None, "secondary_identity_status": "NOT_CHECKED", "secondary_sector": None,
         "bulk_classification_status": "ACCEPTED", "bulk_classification_sector": "Bulk",
         "bulk_classification_source": "Yahoo bulk", "bulk_classification_retrieved_at": "2026-08-23T00:00:00+00:00",
         "baseline_eligible": False, "baseline_reason_code": "UNCLASSIFIED"},
    ])
    result = add_product_classification_and_baseline(facts, history_root=tmp_path).set_index("ticker")
    assert result.loc["OFFICIAL", "product_sector"] == "Official"
    assert result.loc["RICH", "product_sector"] == "Rich Secondary"
    assert result.loc["BULK", "product_sector"] == "Bulk"
    assert result.loc["BULK", "product_classification_evidence"] == "EXACT_IDENTITY_SECONDARY_REFERENCE"
    assert result.loc["BULK", "product_classification_source"] == "Yahoo bulk"


def test_stale_exact_identity_history_uses_accepted_screener_current(tmp_path: Path):
    ticker = "BSE-500500"
    dates = pd.to_datetime(["2021-08-19", "2023-08-18", "2025-08-19"])
    pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "adjusted_close": [50.0, 75.0, 90.0],
    }).to_csv(tmp_path / f"{ticker}.csv", index=False)
    facts = pd.DataFrame([{
        "ticker": ticker, "company": "Exact BSE Ltd", "listing_date": "2000-01-01",
        "trade_date": "2026-08-19", "latest_price": 101.0,
        "official_sector": None, "secondary_identity_status": "NOT_CHECKED",
        "bulk_classification_status": "ACCEPTED", "bulk_classification_sector": "Industrials",
        "bulk_classification_source": "Exact source", "bulk_classification_retrieved_at": "2026-08-19",
        "screener_current_status": "ACCEPTED_EXACT_ISIN_CURRENT_REFERENCE",
        "screener_current_price": 100.0, "baseline_eligible": False,
        "baseline_reason_code": "UNCLASSIFIED",
    }])
    row = add_product_classification_and_baseline(facts, history_root=tmp_path).iloc[0]
    assert bool(row["product_baseline_eligible"])
    assert row["product_baseline_yoy_growth"] == 100.0 / 90.0 - 1
    assert row["product_baseline_days_since_recorded_high"] == 0
    assert "Screener Premium is authoritative" in row["product_baseline_reason"]


def test_stale_history_without_accepted_current_reference_remains_ineligible(tmp_path: Path):
    ticker = "BSE-500501"
    dates = pd.to_datetime(["2021-08-19", "2023-08-18", "2025-08-19"])
    pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "adjusted_close": [50.0, 75.0, 90.0],
    }).to_csv(tmp_path / f"{ticker}.csv", index=False)
    facts = pd.DataFrame([{
        "ticker": ticker, "company": "No Reference Ltd", "listing_date": "2000-01-01",
        "trade_date": "2026-08-19", "latest_price": 101.0,
        "official_sector": None, "secondary_identity_status": "NOT_CHECKED",
        "bulk_classification_status": "ACCEPTED", "bulk_classification_sector": "Industrials",
        "screener_current_status": "UNAVAILABLE", "screener_current_price": 100.0,
        "baseline_eligible": False, "baseline_reason_code": "UNCLASSIFIED",
    }])
    row = add_product_classification_and_baseline(facts, history_root=tmp_path).iloc[0]
    assert not bool(row["product_baseline_eligible"])
    assert row["product_baseline_reason_code"] == "CURRENT_PRICE_UNAVAILABLE"
