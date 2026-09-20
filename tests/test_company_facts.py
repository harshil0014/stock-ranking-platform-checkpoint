from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from stock_ranker.company_facts import (
    CompanyFactResult,
    build_company_facts,
    load_company_fact_snapshot,
    promote_company_fact_snapshot,
    resolve_company_fact_snapshot,
    write_company_fact_snapshot,
)
from stock_ranker.web_assets import APP_JS, INDEX_HTML
from stock_ranker.live_website import company_facts_coverage, live_overview, live_stock
from stock_ranker.secondary_facts import YAHOO_REQUIRED_COLUMNS
from stock_ranker.bulk_classification import BULK_CLASSIFICATION_VERSION


def _market() -> pd.DataFrame:
    rows = []
    for ticker, isin, sector, eligible in (
        ("AAA", "INE000A01001", "Industrials", True),
        ("BSE-2", "INE000A01002", None, False),
    ):
        row = {
            "ticker": ticker, "company": ticker + " Limited", "isin": isin,
            "primary_exchange": "NSE" if ticker == "AAA" else "BSE",
            "exchange_security_id": ticker, "series": "EQ", "listing_date": "2015-01-01",
            "identity_status": "OFFICIAL_MASTER", "trade_date": "2026-08-19",
            "latest_price": 100.0, "previous_close": 99.0, "day_change": 1.0,
            "day_change_pct": 1.0101, "open": 99.0, "high": 101.0, "low": 98.0,
            "volume": 1000, "traded_value": 100000, "transaction_count": 20,
            "snapshot_source": "Official exchange EOD", "sector": sector,
            "industry": sector, "basic_industry": None,
            "classification_status": "CLASSIFIED" if sector else "UNCLASSIFIED",
            "classification_source": "Official classification" if sector else None,
            "size_segment": "SMALL", "roce": .2 if eligible else None,
            "debt_to_equity": .3 if eligible else None,
            "profit_growth_yoy": .1 if eligible else None,
            "baseline_eligible": eligible, "baseline_score": 1.0 if eligible else None,
            "baseline_sector_rank": 1.0 if eligible else None,
            "baseline_reason_code": "ELIGIBLE" if eligible else "NO_CLASSIFICATION",
            "v2_eligible": eligible, "research_v2_score": 60.0 if eligible else None,
            "research_v2_sector_rank": 1.0 if eligible else None,
            "v2_reason_code": "ELIGIBLE" if eligible else "NO_CLASSIFICATION",
        }
        rows.append(row)
    return pd.DataFrame(rows)


def _build(tmp_path: Path):
    history = tmp_path / "history"
    history.mkdir()
    dates = pd.date_range("2020-08-19", "2026-08-19", freq="7D")
    pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "adjusted_close": range(10, 10 + len(dates))}).to_csv(history / "AAA.csv", index=False)
    filings = tmp_path / "filings.csv"
    pd.DataFrame([{
        "ticker": "AAA", "annual_report_selection_status": "SELECTED",
        "annual_report_audit_status": "EXTRACTED", "annual_report_financial_year": "2025-26",
        "annual_report_reporting_basis": "STANDALONE", "annual_report_source_url": "https://example.test/report.pdf",
        "annual_report_pdf_sha256": "a" * 64, "fundamental_data_contract_version": "contract_v1",
        "annual_report_profit": json.dumps({"current_value": 120, "prior_value": 100, "unit": "INR crore", "label": "PAT"}),
    }]).to_csv(filings, index=False)
    professor = tmp_path / "professor.csv"
    pd.DataFrame([{
        "isin": "INE000A01001", "reference_rank": 2, "workbook_sip_rank": 3,
        "workbook_industry": "Engineering", "workbook_evidence_status": "EXACT",
        "workbook_current_price": 95, "workbook_market_cap": 500,
        "workbook_cagr_10y": 12, "workbook_cagr_5y": 10,
        "workbook_cagr_3y": 8, "workbook_cagr_1y": 6,
    }]).to_csv(professor, index=False)
    return build_company_facts(
        _market(), history_root=history, filing_provenance_path=filings,
        professor_strategy_path=professor, market_fingerprint="b" * 64,
    )


def test_fact_layer_preserves_identity_history_filing_and_model_boundaries(tmp_path: Path) -> None:
    result = _build(tmp_path)
    aaa = result.facts.set_index("ticker").loc["AAA"]
    bse = result.facts.set_index("ticker").loc["BSE-2"]
    assert len(result.facts) == 2
    assert aaa["history_5y_usable"]
    assert aaa["recorded_high_date"] == aaa["history_end_date"]
    assert aaa["annual_profit_current"] == 120
    assert aaa["annual_report_reporting_basis"] == "STANDALONE"
    assert aaa["professor_industry"] == "Engineering"
    assert aaa["professor_workbook_market_cap"] == 500
    assert aaa["research_v2_score"] == 60
    assert bse["history_status"] == "NO_ACCEPTED_ADJUSTED_HISTORY"
    assert bse["classification_reason"].startswith("NO AUTHORITATIVE")
    assert pd.isna(bse["market_cap"])


def test_measured_coverage_and_no_guessed_classification(tmp_path: Path) -> None:
    result = _build(tmp_path)
    metrics = result.coverage["metrics"]
    assert metrics["identity"]["count"] == 2
    assert metrics["classification"]["count"] == 1
    assert metrics["history_5y"]["count"] == 1
    assert metrics["market_cap"]["count"] == 0
    assert result.facts.loc[result.facts.ticker.eq("BSE-2"), "derived_research_sector"].isna().all()
    assert result.coverage["strict_v2_boundary"].startswith("Page completeness")


def test_secondary_facts_enrich_pages_without_overriding_official_model_facts(tmp_path: Path) -> None:
    base = _build(tmp_path)
    yahoo_path = tmp_path / "yahoo.csv"
    observation = {column: None for column in YAHOO_REQUIRED_COLUMNS}
    observation.update({
        "ticker": "AAA", "isin": "INE000A01001", "primary_exchange": "NSE",
        "provider_symbol": "AAA.NS", "provider_version": "1.5.1",
        "retrieved_at": "2026-08-22T00:00:00+00:00", "source_as_of": "2026-08-22T00:00:00+00:00",
        "last_checked_at": "2026-08-22T00:00:00+00:00", "last_changed_at": "2026-08-22T00:00:00+00:00",
        "next_check_due": "2026-08-23T00:00:00+00:00", "freshness_status": "CURRENT",
        "identity_status": "EXCHANGE_SYMBOL_MATCH", "identity_reason": "exact",
        "returned_symbol": "AAA.NS", "returned_exchange": "NSI", "returned_quote_type": "EQUITY",
        "company_profile": "Secondary profile", "sector": "Different provider sector",
        "market_cap": 5000, "shares_outstanding": 50, "trailing_pe": 12,
        "annual_income_status": "USEFUL_FACTS", "quarterly_income_status": "USEFUL_FACTS",
        "balance_sheet_status": "USEFUL_FACTS", "cash_flow_status": "USEFUL_FACTS",
        "corporate_actions_status": "USEFUL_FACTS", "holder_data_status": "USEFUL_FACTS",
    })
    pd.DataFrame([observation]).to_csv(yahoo_path, index=False)
    pd.DataFrame([
        {"ticker": "AAA", "statement": "annual_income", "canonical_concept": "total_revenue", "provider_concept": "Total Revenue", "period_end": "2026-03-31", "value": 900, "unit": "INR", "source": "Yahoo Finance", "verification_status": "SECONDARY_REFERENCE", "reporting_basis": "YAHOO_PROVIDER_BASIS_UNSPECIFIED"},
        {"ticker": "AAA", "statement": "quarterly_income", "canonical_concept": "net_income", "provider_concept": "Net Income", "period_end": "2026-06-30", "value": 30, "unit": "INR", "source": "Yahoo Finance", "verification_status": "SECONDARY_REFERENCE", "reporting_basis": "YAHOO_PROVIDER_BASIS_UNSPECIFIED"},
    ]).to_csv(yahoo_path.with_name("financial_facts.csv"), index=False)
    result = build_company_facts(
        _market(), history_root=tmp_path / "history", yahoo_observations_path=yahoo_path,
        market_fingerprint="b" * 64,
    )
    aaa = result.facts.set_index("ticker").loc["AAA"]
    assert aaa["official_sector"] == "Industrials"
    assert aaa["secondary_sector"] == "Different provider sector"
    assert aaa["market_cap"] == 5000
    assert aaa["secondary_annual_revenue"] == 900
    assert aaa["secondary_quarterly_net_income"] == 30
    assert aaa["roce"] == base.facts.set_index("ticker").loc["AAA", "roce"]
    assert result.coverage["metrics"]["quarterly_financials"]["count"] == 1


def test_exact_bulk_classification_is_separate_and_does_not_override_official(tmp_path: Path) -> None:
    bulk_path = tmp_path / "bulk.csv"
    pd.DataFrame([
        {
            "ticker": "AAA", "isin": "INE000A01001", "primary_exchange": "NSE",
            "canonical_security_id": "AAA", "provider_symbol": "AAA.NS",
            "provider_exchange": "NSI", "provider_quote_type": "EQUITY",
            "sector": "Technology", "industry": None,
            "official_bse_code": "NOT_APPLICABLE", "official_bse_isin": "NOT_APPLICABLE",
            "official_bse_symbol": "NOT_APPLICABLE", "identity_source": "Canonical NSE exchange symbol",
            "identity_method": "EXACT_CANONICAL_NSE_SYMBOL",
            "source": "Yahoo Finance bulk equity screener sector membership",
            "retrieved_at": "2026-08-23T00:00:00+00:00", "method_version": BULK_CLASSIFICATION_VERSION,
        },
        {
            "ticker": "BSE-2", "isin": "INE000A01002", "primary_exchange": "BSE",
            "canonical_security_id": "BSE-2", "provider_symbol": "BETA.BO",
            "provider_exchange": "BSE", "provider_quote_type": "EQUITY",
            "sector": "Technology", "industry": None,
            "official_bse_code": "BSE-2", "official_bse_isin": "INE000A01002",
            "official_bse_symbol": "BETA", "identity_source": "BSE official ListofScripData",
            "identity_method": "EXACT_BSE_CODE_AND_ISIN",
            "source": "Yahoo Finance bulk equity screener sector membership",
            "retrieved_at": "2026-08-23T00:00:00+00:00", "method_version": BULK_CLASSIFICATION_VERSION,
        },
    ]).to_csv(bulk_path, index=False)
    result = build_company_facts(
        _market(), history_root=tmp_path / "history",
        bulk_classifications_path=bulk_path,
        bulk_classification_fingerprint="c" * 64,
        market_fingerprint="b" * 64,
    )
    rows = result.facts.set_index("ticker")
    assert rows.loc["AAA", "official_sector"] == "Industrials"
    assert pd.isna(rows.loc["AAA", "product_sector"])
    assert rows.loc["AAA", "bulk_classification_sector"] == "Technology"
    assert rows.loc["BSE-2", "derived_research_sector"] == "Technology"
    assert pd.isna(rows.loc["BSE-2", "product_sector"])
    assert rows.loc["BSE-2", "bulk_classification_identity_method"] == "EXACT_BSE_CODE_AND_ISIN"


def test_screener_bundle_enriches_current_product_by_exact_isin_without_changing_v2(tmp_path: Path) -> None:
    market_path = tmp_path / "screener_market.csv"
    history_path = tmp_path / "screener_history.csv"
    audit_path = tmp_path / "screener_audit.csv"
    pd.DataFrame([
        {
            "isin": "INE000A01001", "market_merge_status": "ACCEPTED",
            "snapshot__Name": "AAA Limited", "snapshot__Industry Group": "Industrial Manufacturing",
            "snapshot__Industry": "Industrial Machinery", "snapshot__Market Capitalization": 500,
            "snapshot__Return on capital employed": 21.5,
        },
        {
            "isin": "INE000A01002", "market_merge_status": "ACCEPTED",
            "snapshot__Name": "BSE-2 Limited", "snapshot__Industry Group": "Technology",
            "snapshot__Industry": "Software", "snapshot__Market Capitalization": 250,
            "snapshot__Return on capital employed": 18.25,
            "snapshot__Return on equity": 16.0, "snapshot__Debt to equity": 0.4,
            "snapshot__Profit growth": 12.0, "snapshot__Promoter holding": 55.0,
        },
    ]).to_csv(market_path, index=False)
    pd.DataFrame([{"isin": "INE000A01002", "period_end": "2025-03-31"}]).to_csv(history_path, index=False)
    pd.DataFrame([{"isin": "INE000A01002", "file_status": "ACCEPTED"}]).to_csv(audit_path, index=False)
    result = build_company_facts(
        _market(), history_root=tmp_path / "history",
        screener_market_path=market_path, screener_history_path=history_path,
        screener_workbook_audit_path=audit_path,
        screener_bundle_fingerprint="d" * 64,
        screener_source_observed_at="2026-09-01T00:00:00+00:00",
        market_fingerprint="b" * 64,
    )
    rows = result.facts.set_index("ticker")
    assert rows.loc["AAA", "product_sector"] == "Industrial Manufacturing"
    assert rows.loc["AAA", "official_sector"] == "Industrials"
    assert rows.loc["AAA", "roce"] == pytest.approx(0.2)
    assert rows.loc["BSE-2", "product_sector"] == "Technology"
    assert rows.loc["BSE-2", "product_classification_evidence"] == "EXACT_ISIN_SCREENER_CURRENT_REFERENCE"
    assert rows.loc["BSE-2", "market_cap"] == 2_500_000_000
    assert rows.loc["BSE-2", "screener_roce_pct"] == 18.25
    assert pd.isna(rows.loc["BSE-2", "roce"])
    assert not bool(rows.loc["BSE-2", "v2_eligible"])
    assert bool(rows.loc["BSE-2", "screener_historical_financials_available"])
    assert bool(rows.loc["BSE-2", "screener_workbook_available"])
    assert result.coverage["metrics"]["roce"]["count"] == 2
    assert result.coverage["metrics"]["strict_v2_eligible"]["count"] == 1


def test_accepted_legacy_workbook_identity_is_surfaced_without_a_market_override(tmp_path: Path) -> None:
    control = build_company_facts(
        _market(), history_root=tmp_path / "control-history",
        market_fingerprint="b" * 64,
    )
    result = build_company_facts(
        _market(), history_root=tmp_path / "history",
        screener_workbook_isins={"INE000A01001"},
        market_fingerprint="b" * 64,
    )

    row = result.facts.set_index("ticker").loc["AAA"]
    assert bool(row["screener_workbook_available"])
    assert row["quarterly_results_status"] == "SCREENER_STANDALONE_HISTORY_AVAILABLE"
    assert bool(row["v2_eligible"]) == bool(control.facts.set_index("ticker").loc["AAA", "v2_eligible"])



def test_screener_unique_exchange_code_fallback_is_current_only_and_rejects_quarantine(tmp_path: Path) -> None:
    market = _market().copy()
    market.loc[market["ticker"].eq("BSE-2"), "exchange_security_id"] = "519606"

    accepted_path = tmp_path / "screener_exchange_fallback.csv"
    pd.DataFrame([
        {
            "isin": "INEOLD001001", "primary_exchange": "BSE",
            "exchange_security_id": "519606", "market_merge_status": "ACCEPTED",
            "snapshot__Name": "Identity Continuity Limited",
            "snapshot__Industry Group": "Technology",
            "snapshot__Industry": "Software",
            "snapshot__Market Capitalization": 250,
            "snapshot__Return on capital employed": 99.0,
        },
        {
            "isin": "INEQUAR00101", "primary_exchange": "BSE",
            "exchange_security_id": "534796",
            "market_merge_status": "CONFLICT_QUARANTINED",
            "snapshot__Name": "Quarantined Limited",
            "snapshot__Industry Group": "Financial Services",
        },
    ]).to_csv(accepted_path, index=False)

    result = build_company_facts(
        market, history_root=tmp_path / "history",
        screener_market_path=accepted_path,
        screener_bundle_fingerprint="e" * 64,
        screener_source_observed_at="2026-09-01T00:00:00+00:00",
        market_fingerprint="b" * 64,
    )
    row = result.facts.set_index("ticker").loc["BSE-2"]

    assert row["isin"] == "INE000A01002"
    assert row["screener_source_isin"] == "INEOLD001001"
    assert row["screener_match_method"] == "UNIQUE_PRIMARY_EXCHANGE_SECURITY_ID"
    assert row["screener_current_status"] == "ACCEPTED_UNIQUE_EXCHANGE_CODE_CURRENT_REFERENCE"
    assert row["product_sector"] == "Technology"
    assert row["product_classification_evidence"] == "UNIQUE_EXCHANGE_CODE_SCREENER_CURRENT_REFERENCE"

    assert pd.isna(row["roce"])
    assert not bool(row["v2_eligible"])
    assert result.coverage["metrics"]["screener_exact_isin_current"]["count"] == 0
    assert result.coverage["metrics"]["screener_unique_exchange_code_current"]["count"] == 1
    assert result.coverage["metrics"]["screener_current_reference"]["count"] == 1

    quarantined_market = market.copy()
    quarantined_market.loc[
        quarantined_market["ticker"].eq("BSE-2"), "exchange_security_id"
    ] = "534796"
    rejected = build_company_facts(
        quarantined_market, history_root=tmp_path / "history2",
        screener_market_path=accepted_path,
        screener_bundle_fingerprint="f" * 64,
        screener_source_observed_at="2026-09-01T00:00:00+00:00",
        market_fingerprint="b" * 64,
    )
    rejected_row = rejected.facts.set_index("ticker").loc["BSE-2"]
    assert pd.isna(rejected_row["screener_current_status"])
    assert pd.isna(rejected_row["screener_source_isin"])
    assert rejected.coverage["metrics"]["screener_unique_exchange_code_current"]["count"] == 0


def test_deterministic_snapshot_and_hash_validation(tmp_path: Path) -> None:
    result = _build(tmp_path)
    first = tmp_path / "one"
    second = tmp_path / "two"
    write_company_fact_snapshot(result, first)
    write_company_fact_snapshot(result, second)
    assert (first / "company_facts.csv").read_bytes() == (second / "company_facts.csv").read_bytes()
    assert load_company_fact_snapshot(first).manifest["fingerprint"] == result.manifest["fingerprint"]
    with (first / "company_facts.csv").open("a", encoding="utf-8") as handle:
        handle.write("tamper\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_company_fact_snapshot(first)


def test_atomic_promotion_is_idempotent_and_rejects_invalid_candidate(tmp_path: Path) -> None:
    result = _build(tmp_path)
    root = tmp_path / "state"
    first = promote_company_fact_snapshot(result, root)
    second = promote_company_fact_snapshot(result, root)
    assert first["fingerprint"] == second["fingerprint"]
    before = (root / "accepted_state.json").read_bytes()
    bad = CompanyFactResult(result.facts.drop(columns="isin"), result.coverage, result.manifest)
    with pytest.raises(ValueError, match="schema"):
        promote_company_fact_snapshot(bad, root)
    assert (root / "accepted_state.json").read_bytes() == before
    assert resolve_company_fact_snapshot(root).is_dir()


def test_company_page_has_complete_section_order_and_validated_screener_history() -> None:
    headings = [
        "Company Overview", "Company Profile", "Classification", "Market Data", "Price History Evidence",
        "Valuation", "Quarterly Results", "Annual Financials", "Balance Sheet",
        "Cash Flow", "Ratios / Quality", "Shareholding", "Peers",
        "Corporate Actions / Announcements / Documents", "Professor Reference",
        "Source Evidence", "Historical Validation",
    ]
    positions = [APP_JS.index(value) for value in headings]
    assert positions == sorted(positions)
    assert "renderCompanyFacts(data.company_facts)" in APP_JS
    assert "Historical Screener Premium standalone workbooks are identified by exact ISIN" in INDEX_HTML
    assert "official exchange evidence supplies the point-in-time clock" in INDEX_HTML
    assert "screener.in/api" not in APP_JS.lower()
    assert 'id="liveMaxPe"' in INDEX_HTML
    assert 'id="liveSort"' in INDEX_HTML
    assert "filters do not recompute model ranks" in INDEX_HTML


def test_accepted_company_fact_snapshot_and_reliance_page_are_internally_consistent() -> None:
    coverage = company_facts_coverage()
    assert coverage["coverage"]["universe_count"] == coverage["manifest"]["row_count"]
    assert (
        int(coverage["manifest"]["row_count"] * 0.90)
        <= coverage["coverage"]["metrics"]["current_price"]["count"]
        <= coverage["manifest"]["row_count"]
    )
    assert coverage["coverage"]["metrics"]["classification"]["count"] == 750
    assert (
        coverage["coverage"]["metrics"]["classification"]["count"]
        <= coverage["coverage"]["metrics"]["product_classified"]["count"]
        <= coverage["manifest"]["row_count"]
    )
    assert (
        0 < coverage["coverage"]["metrics"]["product_baseline_eligible"]["count"]
        <= coverage["coverage"]["metrics"]["product_classified"]["count"]
    )
    assert 0 < coverage["coverage"]["metrics"]["strict_v2_eligible"]["count"]
    assert (
        coverage["coverage"]["metrics"]["strict_v2_eligible"]["count"]
        <= coverage["coverage"]["metrics"]["product_classified"]["count"]
    )
    assert coverage["coverage"]["professor_cohort"]["cohort_size"] == 99
    data = live_stock("RELIANCE")
    facts = data["company_facts"]
    assert facts["overview"]["values"]["isin"] == data["stock"]["isin"]
    assert facts["annual_financials"]["values"]["annual_report_reporting_basis"] == "STANDALONE"
    assert facts["annual_financials"]["values"]["official_annual_reporting_basis"] == "CONSOLIDATED"
    assert facts["annual_financials"]["values"]["official_annual_revenue"] is not None
    assert facts["quarterly_results"]["values"]["official_quarterly_period_end"] is not None
    assert facts["balance_sheet"]["values"]["official_total_assets"] is not None
    assert facts["cash_flow"]["values"]["official_operating_cash_flow"] is not None
    assert facts["shareholding"]["values"]["shareholding_as_of"] is not None
    assert facts["corporate_actions_announcements_documents"]["values"]["latest_document_url"].startswith("https://")
    assert facts["ratios_quality"]["values"]["roce"] == pytest.approx(data["research_v2"]["factors"]["roce"], abs=1e-15)
    assert facts["market_data"]["values"]["latest_price"] == data["stock"]["latest_price"]
    assert data["bundle_fingerprint"] == coverage["manifest"]["market_fingerprint"]
    overview = live_overview()
    reliance = next(row for row in overview["rows"] if row["ticker"] == "RELIANCE")
    assert "market_cap" in reliance and "pe_ratio" in reliance
    assert reliance["sector_rank"] == data["baseline_v1"]["sector_rank"]
