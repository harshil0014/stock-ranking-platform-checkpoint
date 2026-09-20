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


def test_accepted_screener_group_is_coherent_current_product_taxonomy(tmp_path: Path):
    facts = pd.DataFrame([{
        "ticker": "CHEM", "company": "Chemical Ltd", "trade_date": "2026-09-15",
        "latest_price": 100, "official_sector": "Chemicals",
        "official_industry": "Legacy classification", "official_classification_source": "NSE",
        "secondary_identity_status": "EXCHANGE_SYMBOL_MATCH", "secondary_sector": "Basic Materials",
        "screener_current_status": "ACCEPTED_EXACT_ISIN_CURRENT_REFERENCE",
        "screener_industry_group": "Chemicals & Petrochemicals",
        "screener_industry": "Specialty Chemicals",
        "screener_source_observed_at": "2026-09-15T00:00:00+00:00",
        "baseline_eligible": True, "baseline_yoy_growth": .1,
        "baseline_cagr_3y": .08, "baseline_cagr_5y": .06,
        "baseline_days_since_recorded_high": 4, "baseline_reason_code": "ELIGIBLE",
    }])
    row = add_product_classification_and_baseline(facts, history_root=tmp_path).iloc[0]
    assert row["product_sector"] == "Chemicals & Petrochemicals"
    assert row["product_industry"] == "Specialty Chemicals"
    assert row["product_classification_evidence"] == "EXACT_ISIN_SCREENER_CURRENT_REFERENCE"
    assert row["official_sector"] == "Chemicals"  # retained as separate provenance


def test_material_one_year_reference_conflict_is_quarantined_not_substituted(
    tmp_path: Path,
):
    facts = pd.DataFrame([{
        "ticker": "SPLIT", "company": "Split Basis Ltd",
        "trade_date": "2026-09-18", "latest_price": 100,
        "official_sector": "Industrial Products",
        "official_classification_source": "NSE",
        "secondary_identity_status": "EXCHANGE_SYMBOL_MATCH",
        "screener_current_status": "ACCEPTED_EXACT_ISIN_CURRENT_REFERENCE",
        "screener_industry_group": "Industrial Products",
        "screener_return_1y_pct": 10.0,
        "baseline_eligible": True, "baseline_yoy_growth": 1.0,
        "baseline_cagr_3y": .20, "baseline_cagr_5y": .15,
        "baseline_days_since_recorded_high": 3,
        "baseline_reason_code": "ELIGIBLE",
    }])
    row = add_product_classification_and_baseline(
        facts, history_root=tmp_path
    ).iloc[0]
    assert not bool(row["product_baseline_eligible"])
    assert row["product_baseline_reason_code"] == "ONE_YEAR_RETURN_REFERENCE_CONFLICT"
    assert "quarantined" in row["product_baseline_reason"]
    assert pd.isna(row["product_baseline_score"])


def test_small_one_year_reference_difference_remains_rankable(tmp_path: Path):
    facts = pd.DataFrame([{
        "ticker": "SAFE", "company": "Safe Basis Ltd",
        "trade_date": "2026-09-18", "latest_price": 100,
        "official_sector": "Industrial Products",
        "official_classification_source": "NSE",
        "secondary_identity_status": "EXCHANGE_SYMBOL_MATCH",
        "screener_current_status": "ACCEPTED_EXACT_ISIN_CURRENT_REFERENCE",
        "screener_industry_group": "Industrial Products",
        "screener_return_1y_pct": 8.0,
        "baseline_eligible": True, "baseline_yoy_growth": .10,
        "baseline_cagr_3y": .08, "baseline_cagr_5y": .06,
        "baseline_days_since_recorded_high": 3,
        "baseline_reason_code": "ELIGIBLE",
    }])
    row = add_product_classification_and_baseline(
        facts, history_root=tmp_path
    ).iloc[0]
    assert bool(row["product_baseline_eligible"])
    assert row["product_baseline_yoy_growth"] == .10


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
        "screener_industry_group": "Industrial Products",
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
    assert row["product_baseline_reason_code"] == "UNCLASSIFIED"


def test_reduced_history_tiers_preserve_primary_ranks_and_never_mix_peer_pools(tmp_path: Path):
    def history(ticker: str, dates: list[str], prices: list[float]) -> None:
        pd.DataFrame({"date": dates, "adjusted_close": prices}).to_csv(
            tmp_path / f"{ticker}.csv", index=False
        )

    history("THREE", ["2023-08-18", "2025-08-19", "2026-08-19"], [70, 90, 100])
    history("ONE", ["2025-08-19", "2026-08-19"], [90, 100])
    recent = pd.date_range("2026-06-01", "2026-08-19", freq="B")
    pd.DataFrame({"date": recent.strftime("%Y-%m-%d"), "adjusted_close": range(100, 100 + len(recent))}).to_csv(
        tmp_path / "RECENT.csv", index=False
    )
    common = {
        "company": "Company", "listing_date": "2000-01-01", "trade_date": "2026-08-19",
        "official_sector": "Sector", "official_classification_source": "NSE",
        "secondary_identity_status": "NOT_CHECKED", "secondary_sector": None,
        "baseline_eligible": False, "history_reason": "short history",
    }
    facts = pd.DataFrame([
        {**common, "ticker": "PRIMARY_A", "latest_price": 100, "baseline_eligible": True,
         "baseline_yoy_growth": .20, "baseline_cagr_3y": .15, "baseline_cagr_5y": .10,
         "baseline_days_since_recorded_high": 3, "baseline_reason_code": "ELIGIBLE"},
        {**common, "ticker": "PRIMARY_B", "latest_price": 100, "baseline_eligible": True,
         "baseline_yoy_growth": .10, "baseline_cagr_3y": .05, "baseline_cagr_5y": .02,
         "baseline_days_since_recorded_high": 9, "baseline_reason_code": "ELIGIBLE"},
        {**common, "ticker": "THREE", "latest_price": 100, "baseline_reason_code": "INSUFFICIENT_5Y_HISTORY"},
        {**common, "ticker": "ONE", "latest_price": 100, "baseline_reason_code": "INSUFFICIENT_3Y_HISTORY"},
        {**common, "ticker": "RECENT", "latest_price": float(100 + len(recent) - 1),
         "listing_date": "2026-06-01", "baseline_reason_code": "INSUFFICIENT_1Y_HISTORY"},
    ])
    result = add_product_classification_and_baseline(facts, history_root=tmp_path).set_index("ticker")
    assert result.loc["PRIMARY_A", "product_baseline_sector_rank"] == 1
    assert result.loc["PRIMARY_B", "product_baseline_sector_rank"] == 2
    assert result.loc["PRIMARY_A", "product_baseline_ranking_tier"] == "PRIMARY_5Y"
    assert result.loc["PRIMARY_A", "product_baseline_confidence"] == "PRIMARY"
    assert result.loc["THREE", "product_baseline_ranking_tier"] == "REDUCED_3Y"
    assert result.loc["ONE", "product_baseline_ranking_tier"] == "REDUCED_1Y"
    assert result.loc["RECENT", "product_baseline_ranking_tier"] == "RECENCY_ONLY"
    assert result.loc["THREE", "product_baseline_sector_rank"] == 1
    assert result.loc["ONE", "product_baseline_sector_rank"] == 1
    assert result.loc["RECENT", "product_baseline_sector_rank"] == 1
    assert result["product_baseline_eligible"].all()
    assert result.loc["PRIMARY_A", "product_baseline_feature_count"] == 4
    assert result.loc["RECENT", "product_baseline_feature_count"] == 1


def test_recency_only_requires_a_minimum_real_observation_window(tmp_path: Path):
    pd.DataFrame({
        "date": ["2026-08-17", "2026-08-19"], "adjusted_close": [99, 100],
    }).to_csv(tmp_path / "NEW.csv", index=False)
    facts = pd.DataFrame([{
        "ticker": "NEW", "company": "New Ltd", "listing_date": "2026-08-17",
        "trade_date": "2026-08-19", "latest_price": 100,
        "official_sector": "Sector", "official_classification_source": "NSE",
        "secondary_identity_status": "NOT_CHECKED", "secondary_sector": None,
        "baseline_eligible": False, "baseline_reason_code": "INSUFFICIENT_1Y_HISTORY",
    }])
    row = add_product_classification_and_baseline(facts, history_root=tmp_path).iloc[0]
    assert not bool(row["product_baseline_eligible"])
    assert row["product_baseline_reason_code"] == "INSUFFICIENT_RANKING_HISTORY"
    assert pd.isna(row["product_baseline_score"])
