from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from io import StringIO
import json
import inspect
from pathlib import Path

import pandas as pd
import pytest

from stock_ranker.real_research_v2 import (
    RealResearchV2Bundle,
    build_matched_cohort_comparison,
    extract_exact_reported_metrics,
    load_real_research_v2_bundle,
    parse_nse_xbrl,
    select_point_in_time_filing,
    taxonomy_family_from_filename,
)
from stock_ranker.baseline import calculate_baseline_rankings
import stock_ranker.real_research_v2 as real_module
from stock_ranker.web_assets import APP_JS
from stock_ranker.website import (
    _fair_baseline_comparison_group,
    _real_v2_provenance_groups,
    analyze_website_request,
)
from stock_ranker.v2_contracts import (
    V2_CONTRIBUTION_COLUMNS,
    V2_METRIC_COLUMNS,
    V2_SCORE_COLUMNS,
)
from marketdata.runners.acquire_nse_annual_reports import select_annual_report


MAPPING = {
    "metrics": {
        "roce": {"concepts": ["ReturnOnCapitalEmployed"], "unit": "pure", "period_type": "annual_duration"},
        "debt_to_equity": {"concepts": ["DebtEquityRatio"], "unit": "pure", "period_type": "instant"},
        "profit_growth_yoy": {"concepts": ["ProfitGrowthYoY"], "unit": "pure", "period_type": "annual_duration"},
    }
}


def _xml(*facts: str, contexts: str = "") -> bytes:
    default_contexts = """
      <xbrli:context id="annual"><xbrli:entity><xbrli:identifier scheme="NSE">TEST</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-04-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period></xbrli:context>
      <xbrli:context id="quarter"><xbrli:entity><xbrli:identifier scheme="NSE">TEST</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-01-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period></xbrli:context>
      <xbrli:context id="instant"><xbrli:entity><xbrli:identifier scheme="NSE">TEST</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-03-31</xbrli:instant></xbrli:period></xbrli:context>
    """
    body = "".join(facts) or """
      <nse:ReturnOnCapitalEmployed contextRef="annual" unitRef="pure">0</nse:ReturnOnCapitalEmployed>
      <nse:DebtEquityRatio contextRef="instant" unitRef="pure">1.25</nse:DebtEquityRatio>
      <nse:ProfitGrowthYoY contextRef="annual" unitRef="pure">0.10</nse:ProfitGrowthYoY>
    """
    return f"""<?xml version="1.0"?>
    <xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:nse="https://nse.example/taxonomy">
      {contexts or default_contexts}
      <xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>
      <xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>
      {body}
    </xbrli:xbrl>""".encode()


def _document(*facts: str):
    return parse_nse_xbrl(
        _xml(*facts), filename="INTEGRATED_FILING_INDAS_1_01012026000000_WEB.xml"
    )


def test_xbrl_parses_namespaces_duration_instant_units_and_zero() -> None:
    document = _document()
    assert document.taxonomy_family == "INDAS"
    assert document.contexts["annual"].start_date == "2025-04-01"
    assert document.contexts["instant"].instant == "2026-03-31"
    assert document.units["pure"] == "xbrli:pure"
    metrics, provenance, missing = extract_exact_reported_metrics(
        document, MAPPING, "2026-03-31"
    )
    assert metrics == {"roce": 0.0, "debt_to_equity": 1.25, "profit_growth_yoy": 0.1}
    assert provenance["roce"]["context_id"] == "annual"
    assert missing == []


@pytest.mark.parametrize("family", ["INDAS", "BANKING", "NBFC_INDAS", "LI"])
def test_taxonomy_families_are_generic(family: str) -> None:
    assert taxonomy_family_from_filename(
        f"INTEGRATED_FILING_{family}_123_01012026000000_WEB.xml"
    ) == family


@pytest.mark.parametrize("payload", [b"<broken", b"<!DOCTYPE x><x/>", b"<!ENTITY x 'y'><x/>"])
def test_xbrl_rejects_malformed_or_active_declarations(payload: bytes) -> None:
    with pytest.raises(ValueError):
        parse_nse_xbrl(payload, filename="INTEGRATED_FILING_INDAS_1_1_WEB.xml")


def test_xbrl_rejects_conflicting_duplicate_facts() -> None:
    facts = (
        '<nse:DebtEquityRatio contextRef="instant" unitRef="pure">1</nse:DebtEquityRatio>',
        '<nse:DebtEquityRatio contextRef="instant" unitRef="pure">2</nse:DebtEquityRatio>',
    )
    with pytest.raises(ValueError, match="conflicting"):
        _document(*facts)


def test_missing_is_distinct_from_explicit_zero_and_proxy_is_rejected() -> None:
    document = _document(
        '<nse:ReturnOnAssets contextRef="annual" unitRef="pure">0</nse:ReturnOnAssets>'
    )
    metrics, _, missing = extract_exact_reported_metrics(document, MAPPING, "2026-03-31")
    assert metrics == {}
    assert set(missing) == {"roce", "debt_to_equity", "profit_growth_yoy"}


def test_units_and_periods_are_not_silently_substituted() -> None:
    document = _document(
        '<nse:ReturnOnCapitalEmployed contextRef="quarter" unitRef="pure">9</nse:ReturnOnCapitalEmployed>'
    )
    metrics, _, missing = extract_exact_reported_metrics(document, MAPPING, "2026-03-31")
    assert metrics == {}
    assert "roce" in missing


def _filing(created: str, *, seq: str, basis: str = "Consolidated", period: str = "31-Mar-2026") -> dict[str, object]:
    return {
        "creation_Date": created, "broadcast_Date": created,
        "qe_Date": period, "consolidated": basis, "seq_Id": seq,
    }


def test_point_in_time_revision_selection_uses_exchange_dissemination() -> None:
    cutoff = datetime.fromisoformat("2026-08-07T15:30:00+05:30")
    original = _filing("30-Apr-2026 23:08:27", seq="1")
    revision = _filing("07-Aug-2026 15:29:59", seq="2")
    future = _filing("07-Aug-2026 15:30:01", seq="3")
    selected, status = select_point_in_time_filing([original, future, revision], cutoff)
    assert status == "SELECTED"
    assert selected is revision
    assert selected["broadcast_Date"] == revision["broadcast_Date"]


def test_post_cutoff_revision_cannot_rewrite_history() -> None:
    cutoff = datetime.fromisoformat("2026-08-07T15:30:00+05:30")
    original = _filing("30-Apr-2026 23:08:27", seq="1")
    future = _filing("08-Aug-2026 00:00:00", seq="2")
    assert select_point_in_time_filing([original], cutoff)[0] == original
    assert select_point_in_time_filing([original, future], cutoff)[0] == original


def test_selection_requires_timezone_and_consolidated_annual_period() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        select_point_in_time_filing([], datetime(2026, 8, 7, 15, 30))
    cutoff = datetime.fromisoformat("2026-08-07T15:30:00+05:30")
    assert select_point_in_time_filing(
        [_filing("01-Apr-2026 10:00:00", seq="1", basis="Standalone")], cutoff
    )[1] == "NO_CONSOLIDATED_FILING"
    assert select_point_in_time_filing(
        [_filing("01-Feb-2026 10:00:00", seq="1", period="31-Dec-2025")], cutoff
    )[1] == "NO_COMPARABLE_PRIOR_PERIOD"


def test_adapter_contains_no_ticker_specific_accounting_rule() -> None:
    assert "BAJAJFINSV" not in inspect.getsource(real_module)


def test_bundle_manifest_fingerprint_and_tamper_detection(tmp_path: Path) -> None:
    csvs = {
        "universe.csv": "ticker,company,sector\nAAA,Alpha,Industrials\n",
        "prices.csv": "ticker,date,adjusted_close\nAAA,2026-08-07,100\n",
        "fundamentals.csv": "ticker,period_end,available_date,roce,debt_to_equity,profit_growth_yoy\n",
        "eligibility.csv": "ticker,company,sector,ranking_date,eligible,reason_code,reason\nAAA,Alpha,Industrials,2026-08-07,False,MISSING_REQUIRED_ACCOUNTING_FACT,Missing\n",
        "rankings.csv": "ticker,company,sector,ranking_date\n",
        "comparison.csv": "ticker,company,sector\nAAA,Alpha,Industrials\n",
        "comparison_sector_summary.csv": "sector,research_v2_exclusions\nIndustrials,1\n",
        "filing_provenance.csv": "ticker,selection_status\nAAA,SELECTED\n",
    }
    for name, content in csvs.items():
        (tmp_path / name).write_text(content, encoding="utf-8", newline="\n")
    (tmp_path / "bundle_metadata.json").write_text(
        '{"ranking_date":"2026-08-07"}\n', encoding="utf-8", newline="\n"
    )
    entries = [
        {"path": path.name, "sha256": sha256(path.read_bytes()).hexdigest(),
         "size": path.stat().st_size}
        for path in sorted(tmp_path.iterdir())
    ]
    fingerprint = sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (tmp_path / "bundle_manifest.json").write_text(
        json.dumps({"schema_version": 1, "bundle_fingerprint": fingerprint,
                    "files": entries}), encoding="utf-8", newline="\n"
    )
    assert load_real_research_v2_bundle(tmp_path).fingerprint == fingerprint
    (tmp_path / "universe.csv").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_real_research_v2_bundle(tmp_path)


def test_real_website_mode_exposes_exclusions_comparison_and_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    eligibility = pd.DataFrame([{
        "ticker": "AAA", "company": "Alpha", "sector": "Industrials",
        "ranking_date": "2026-08-07", "eligible": False,
        "reason_code": "MISSING_REQUIRED_ACCOUNTING_FACT",
        "reason": "Official XBRL lacks the exact accepted fact.",
    }])
    comparison = pd.DataFrame([{
        "ticker": "AAA", "company": "Alpha", "sector": "Industrials",
        "original_baseline_sector_rank": 1,
        "matched_baseline_sector_rank": None,
        "baseline_score": 1.5, "eligible_peer_count": 0,
        "comparison_status": "INELIGIBLE",
        "research_v2_sector_rank": None, "research_v2_score": None,
        "eligible": False, "reason_code": "MISSING_REQUIRED_ACCOUNTING_FACT",
        "reason": "Official XBRL lacks the exact accepted fact.", "rank_movement": None,
    }])
    filing = pd.DataFrame([{
        "ticker": "AAA", "selection_status": "SELECTED",
        "reason_code": "MISSING_REQUIRED_ACCOUNTING_FACT", "taxonomy_family": "INDAS",
        "period_end": "31-MAR-2026", "submission_type": "Original",
        "statement_basis": "Consolidated", "audited": "Audited",
        "broadcast_timestamp": "30-Apr-2026 23:08:23",
        "exchange_dissemination_timestamp": "30-Apr-2026 23:08:27",
        "revision_timestamp": None, "revision_remarks": None,
        "xbrl_sha256": "a" * 64, "fact_provenance": "{}",
    }])
    bundle = RealResearchV2Bundle(
        Path("fixture"), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        eligibility, pd.DataFrame(), comparison,
        pd.DataFrame([{"sector": "Industrials", "baseline_top_5": "AAA",
                      "research_v2_top_5": "", "top_5_overlap": "",
                      "entered_research_v2_top_5": "",
                      "left_research_v2_top_5": "AAA",
                      "research_v2_exclusions": 1}]), filing,
        {"ranking_date": "2026-08-07", "filing_cutoff": "2026-08-07T15:30:00+05:30",
         "eligible_count": 0, "excluded_count": 1,
         "status": "PARTIAL_UNSUPPORTED_OFFICIAL_DATA_COVERAGE",
         "baseline_bundle_fingerprint": "b" * 64},
        "c" * 64,
    )
    monkeypatch.setattr("stock_ranker.website.load_real_research_v2_bundle", lambda _: bundle)
    result = analyze_website_request({
        "input_source": "prepared_real_research_v2", "method": "research_v2"
    })
    assert result["provenance"]["data_mode"] == "REAL POINT-IN-TIME RESEARCH V2"
    assert len(result["results"]) == len(result["comparison"]) == 1
    assert result["comparison_sector_summary"][0]["research_v2_exclusions"] == 1
    xbrl = result["results"][0]["explanation"][
        "integrated_filing_xbrl_evidence_corroborating"
    ]
    assert xbrl["xbrl_sha_256"] == "a" * 64
    assert "original_baseline_sector_rank" in result["comparison_export_csv"]
    assert "matched_baseline_sector_rank" in result["comparison_export_csv"]
    json.dumps(result, allow_nan=False)


def test_reliance_provenance_ui_separates_xbrl_and_expands_annual_report_objects() -> None:
    filing = {
        "selection_status": "SELECTED",
        "reason_code": "MISSING_REQUIRED_ACCOUNTING_FACT",
        "statement_basis": "Consolidated",
        "exchange_dissemination_timestamp": "24-Apr-2026 22:57:14",
        "source_xbrl_url": "https://example.invalid/reliance.xml",
        "xbrl_sha256": "a" * 64,
        "annual_report_selection_status": "SELECTED",
        "annual_report_audit_status": "EXTRACTED",
        "annual_report_source_url": "https://example.invalid/reliance.pdf",
        "annual_report_pdf_filename": "RELIANCE_2025_2026.pdf",
        "annual_report_pdf_sha256": "b" * 64,
        "annual_report_financial_year": "2025-26",
        "annual_report_submission_type": "New",
        "annual_report_broadcast_timestamp": "28-MAY-2026 13:39:47",
        "annual_report_exchange_dissemination_timestamp": "28-MAY-2026 13:39:48",
        "annual_report_reporting_basis": "STANDALONE",
        "fundamental_data_contract_version": "nse_audited_standalone_fundamentals_v1",
        "annual_report_roce": {
            "canonical_decimal": 0.207,
            "label": "Return on Capital Employed (%)",
            "page": 132,
            "table": "Standalone statutory ratios",
            "formula": "Issuer ROCE formula",
        },
        "annual_report_debt_to_equity": {
            "canonical_decimal": 0.41,
            "label": "Debt-Equity Ratio",
            "page": 132,
            "table": "Standalone statutory ratios",
            "formula": "Total Debt / Total Equity",
        },
        "annual_report_profit": {
            "current_value": 43851,
            "prior_value": 35262,
            "unit": "INR crore",
            "label": "Profit for the year",
            "page": 80,
            "comparability_warning": "",
        },
    }

    groups = _real_v2_provenance_groups(
        filing,
        {"profit_growth_yoy": 0.24357665475582779},
        "NSE Audited Standalone Fundamentals v1",
    )

    assert set(groups) == {
        "final_research_v2_fundamentals",
        "integrated_filing_xbrl_evidence_corroborating",
        "nse_annual_report_fundamental_provenance",
    }
    assert all(
        not isinstance(value, dict)
        for group in groups.values()
        for value in group.values()
    )
    final = groups["final_research_v2_fundamentals"]
    assert final["fundamental_data_contract"] == "NSE Audited Standalone Fundamentals v1"
    assert final["reporting_basis"] == "STANDALONE"
    assert final["roce_value"] == "20.7%"
    assert final["roce_source_page"] == 132
    assert final["roce_issuer_formula_or_basis"] == "Issuer ROCE formula"
    assert final["debt_to_equity_value"] == 0.41
    assert final["debt_to_equity_issuer_formula_or_basis"] == "Total Debt / Total Equity"
    assert final["fy2025_26_pat_or_profit"] == "43,851 INR crore"
    assert final["fy2024_25_pat_or_profit"] == "35,262 INR crore"
    assert final["profit_growth_yoy"] == "24.3577%"
    xbrl = groups["integrated_filing_xbrl_evidence_corroborating"]
    assert xbrl["xbrl_stage_reason_code"] == "MISSING_REQUIRED_ACCOUNTING_FACT"
    assert xbrl["xbrl_statement_basis"] == "Consolidated"
    assert "Fundamental contract" in APP_JS


def test_fair_comparison_inspect_view_uses_frozen_matched_cohort_values() -> None:
    hindunilvr = _fair_baseline_comparison_group({
        "original_baseline_sector_rank": 4,
        "matched_baseline_sector_rank": 4,
        "research_v2_sector_rank": 2,
        "rank_movement": 2,
        "eligible_peer_count": 4,
        "comparison_status": "MATCHED_COHORT",
    })
    assert hindunilvr == {
        "original_baseline_sector_rank": 4,
        "matched_cohort_baseline_sector_rank": 4,
        "research_v2_sector_rank": 2,
        "matched_cohort_rank_movement": "+2",
        "eligible_peer_count": 4,
        "comparison_status": "MATCHED_COHORT",
        "comparison_explanation": (
            "Rank movement compares Research V2 only with Baseline V1 reranked "
            "on the same Research-V2-eligible sector cohort. The original "
            "Baseline rank is shown for context and is not used to calculate movement."
        ),
    }
    different_original = _fair_baseline_comparison_group({
        "original_baseline_sector_rank": 9,
        "matched_baseline_sector_rank": 4,
        "research_v2_sector_rank": 2,
        "rank_movement": 2,
        "eligible_peer_count": 4,
        "comparison_status": "MATCHED_COHORT",
    })
    assert different_original["matched_cohort_rank_movement"] == "+2"

    reliance = _fair_baseline_comparison_group({
        "original_baseline_sector_rank": 3,
        "matched_baseline_sector_rank": 1,
        "research_v2_sector_rank": 1,
        "rank_movement": None,
        "eligible_peer_count": 1,
        "comparison_status": "SINGLE_ELIGIBLE_PEER",
    })
    assert reliance["original_baseline_sector_rank"] == 3
    assert reliance["matched_cohort_baseline_sector_rank"] == 1
    assert reliance["research_v2_sector_rank"] == 1
    assert reliance["matched_cohort_rank_movement"] is None
    assert reliance["eligible_peer_count"] == 1
    assert reliance["comparison_status"] == "SINGLE_ELIGIBLE_PEER"


def test_real_website_export_uses_final_standalone_contract_reason_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {
        "NOREPORT": "NO_ELIGIBLE_ANNUAL_REPORT",
        "BADPDF": "ANNUAL_REPORT_EXTRACTION_FAILED",
        "NOROCE": "MISSING_EXPLICIT_ROCE",
        "SUBSTITUTE": "SUBSTITUTE_ONLY",
        "SBILIFE": "MISSING_EXPLICIT_ROCE",
        "ELIGIBLE": "ELIGIBLE",
    }
    eligibility = pd.DataFrame([
        {
            "ticker": ticker, "company": ticker, "sector": ticker,
            "ranking_date": "2026-08-07", "eligible": reason == "ELIGIBLE",
            "reason_code": reason, "reason": f"Final reason for {ticker}",
        }
        for ticker, reason in expected.items()
    ])
    eligible_ranking = {
        "ticker": "ELIGIBLE", "company": "ELIGIBLE", "sector": "ELIGIBLE",
        "sector_rank": 1, "research_v2_score": 50.0,
        "method_version": "research_v2_point_in_time_weighted",
    }
    eligible_ranking.update({column: 0.0 for column in V2_METRIC_COLUMNS})
    eligible_ranking.update({column: 50.0 for column in V2_SCORE_COLUMNS})
    eligible_ranking.update({column: 0.0 for column in V2_CONTRIBUTION_COLUMNS})
    provenance = pd.DataFrame([
        {
            "ticker": ticker,
            "reason_code": "NO_CONSOLIDATED_FILING",
            "selection_status": "SELECTED",
        }
        for ticker in expected
    ])
    comparison = pd.DataFrame([
        {
            "ticker": ticker, "company": ticker, "sector": ticker,
            "eligible": reason == "ELIGIBLE", "eligible_peer_count": int(reason == "ELIGIBLE"),
            "comparison_status": "SINGLE_ELIGIBLE_PEER" if reason == "ELIGIBLE" else "INELIGIBLE",
            "reason_code": reason, "reason": f"Final reason for {ticker}",
        }
        for ticker, reason in expected.items()
    ])
    bundle = RealResearchV2Bundle(
        Path("fixture"), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), eligibility,
        pd.DataFrame([eligible_ranking]), comparison, pd.DataFrame(), provenance,
        {
            "ranking_date": "2026-08-07",
            "filing_cutoff": "2026-08-07T15:30:00+05:30",
            "eligible_count": 1, "excluded_count": 5,
            "status": "AUDITED_STANDALONE_CONTRACT",
            "baseline_bundle_fingerprint": "b" * 64,
            "fundamental_data_contract_version": "nse_audited_standalone_fundamentals_v1",
        },
        "c" * 64,
    )
    monkeypatch.setattr("stock_ranker.website.load_real_research_v2_bundle", lambda _: bundle)

    result = analyze_website_request({
        "input_source": "prepared_real_research_v2", "method": "research_v2"
    })
    exported = pd.read_csv(StringIO(result["export_csv"])).set_index("ticker")

    assert exported["reason_code"].to_dict() == expected
    assert exported.loc["SBILIFE", "reason_code"] != "NO_CONSOLIDATED_FILING"


def test_annual_report_selection_is_exchange_time_point_in_time_safe() -> None:
    before = {
        "fromYr": "2025", "toYr": "2026", "submission_type": "New",
        "disseminationDateTime": "07-Aug-2026 15:29:59",
        "fileName": "https://nsearchives.nseindia.com/annual_reports/before.pdf",
    }
    after = {**before, "submission_type": "Revised",
             "disseminationDateTime": "07-Aug-2026 15:30:01",
             "fileName": "https://nsearchives.nseindia.com/annual_reports/after.pdf"}
    cutoff = datetime.fromisoformat("2026-08-07T15:30:00+05:30")
    selected, status = select_annual_report([before, after], cutoff)
    assert status == "SELECTED"
    assert selected is before


def test_annual_report_mapping_preserves_direct_labels_formula_basis_and_pat() -> None:
    mapping = json.loads(
        (Path(__file__).parents[1] / "marketdata/specifications/nse_annual_report_research_v2_mapping.json").read_text(encoding="utf-8")
    )
    assert mapping["fundamental_data_contract_version"] == "nse_audited_standalone_fundamentals_v1"
    assert mapping["reporting_basis"] == "STANDALONE"
    assert len(mapping["accepted"]) == 34
    assert {row["reporting_basis"] for row in mapping["accepted"]} == {"STANDALONE"}
    reliance = next(row for row in mapping["accepted"] if row["ticker"] == "RELIANCE")
    assert reliance["ticker"] == "RELIANCE"
    assert reliance["reporting_basis"] == "STANDALONE"
    assert reliance["roce"]["label"] == "Return on Capital Employed (%)"
    assert reliance["roce"]["canonical_decimal"] == 0.207
    assert "Average Capital Employed" in reliance["roce"]["formula"]
    assert reliance["debt_to_equity"]["label"] == "Debt-Equity Ratio"
    assert reliance["debt_to_equity"]["formula"] == "Total Debt / Total Equity"
    assert reliance["profit"]["current_value"] == 43851
    assert reliance["profit"]["prior_value"] == 35262
    assert reliance["profit"]["current_value"] / reliance["profit"]["prior_value"] - 1 == pytest.approx(
        43851 / 35262 - 1, abs=1e-15
    )


def test_roa_roe_roev_and_roic_are_never_accepted_as_roce() -> None:
    mapping_text = (
        Path(__file__).parents[1]
        / "marketdata/specifications/nse_annual_report_research_v2_mapping.json"
    ).read_text(encoding="utf-8")
    mapping = json.loads(mapping_text)
    accepted = json.dumps(mapping["accepted"]).lower()
    for substitute in ("return on assets", "return on equity", "roev", "roic"):
        assert substitute not in accepted
    exclusions = {row["ticker"]: row for row in mapping["reviewed_exclusions"]}
    assert set(exclusions) == {"SBIN", "SHRIRAMFIN", "HDFCLIFE"}
    assert all(row["classification"] == "SUBSTITUTE_ONLY" for row in exclusions.values())


def test_standalone_contract_prioritizes_statutory_tables_and_preserves_warnings() -> None:
    mapping = json.loads(
        (Path(__file__).parents[1] / "marketdata/specifications/nse_annual_report_research_v2_mapping.json").read_text(encoding="utf-8")
    )
    accepted = {row["ticker"]: row for row in mapping["accepted"]}
    expected = {
        "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "BAJAJ-AUTO",
        "BEL", "CIPLA", "DRREDDY", "EICHERMOT", "ETERNAL", "GRASIM",
        "HCLTECH", "HINDALCO", "HINDUNILVR", "INDIGO", "INFY", "ITC",
        "JSWSTEEL", "LT", "M&M", "MAXHEALTH", "NESTLEIND", "POWERGRID",
        "RELIANCE", "SUNPHARMA", "TATACONSUM", "TATASTEEL", "TCS",
        "TECHM", "TITAN", "TMPV", "TRENT", "ULTRACEMCO", "WIPRO",
    }
    assert set(accepted) == expected
    for row in accepted.values():
        assert row["reporting_basis"] == "STANDALONE"
        assert "Standalone" in row["roce"]["table"]
        assert "Standalone" in row["debt_to_equity"]["table"]
        assert row["roce"]["formula"]
        assert row["debt_to_equity"]["formula"]
    for ticker in {"ADANIENT", "INDIGO", "JSWSTEEL", "LT", "TATASTEEL", "TMPV", "TRENT"}:
        assert accepted[ticker]["profit"]["comparability_warning"]
    assert "discontinued" in accepted["ADANIENT"]["profit"]["comparability_warning"].lower()
    assert "re-presented" in accepted["TMPV"]["profit"]["comparability_warning"].lower()


def test_fair_comparison_uses_only_matched_peers_and_marks_singletons() -> None:
    baseline_input = pd.DataFrame([
        {"ticker": "AAA", "company": "A", "sector": "S", "as_of_date": "2026-08-07", "current_price": 120, "close_1y_ago": 100, "close_3y_ago": 80, "close_5y_ago": 60, "ath_date": "2026-08-01"},
        {"ticker": "BBB", "company": "B", "sector": "S", "as_of_date": "2026-08-07", "current_price": 110, "close_1y_ago": 100, "close_3y_ago": 90, "close_5y_ago": 70, "ath_date": "2026-07-01"},
        {"ticker": "CCC", "company": "C", "sector": "S", "as_of_date": "2026-08-07", "current_price": 90, "close_1y_ago": 100, "close_3y_ago": 100, "close_5y_ago": 100, "ath_date": "2020-01-01"},
        {"ticker": "ONE", "company": "One", "sector": "Solo", "as_of_date": "2026-08-07", "current_price": 100, "close_1y_ago": 90, "close_3y_ago": 80, "close_5y_ago": 70, "ath_date": "2026-08-01"},
    ])
    original = calculate_baseline_rankings(baseline_input)
    universe = baseline_input.loc[:, ["ticker", "company", "sector"]]
    v2 = pd.DataFrame([
        {"ticker": "BBB", "sector": "S", "sector_rank": 1, "research_v2_score": 70},
        {"ticker": "AAA", "sector": "S", "sector_rank": 2, "research_v2_score": 60},
        {"ticker": "ONE", "sector": "Solo", "sector_rank": 1, "research_v2_score": 50},
    ])
    eligibility = universe.assign(
        eligible=lambda frame: frame["ticker"].ne("CCC"),
        reason_code=lambda frame: frame["ticker"].map(lambda value: "EXCLUDED" if value == "CCC" else "ELIGIBLE"),
        reason="fixture",
    )
    comparison, summary = build_matched_cohort_comparison(
        universe, baseline_input, original, v2, eligibility
    )
    eligible = comparison.loc[comparison["eligible"]]
    assert set(eligible.loc[eligible["sector"].eq("S"), "ticker"]) == {"AAA", "BBB"}
    assert eligible.loc[eligible["ticker"].eq("BBB"), "rank_movement"].iat[0] == 1
    assert comparison.loc[comparison["ticker"].eq("CCC"), "matched_baseline_sector_rank"].isna().all()
    solo = comparison.loc[comparison["ticker"].eq("ONE")].iloc[0]
    assert solo["comparison_status"] == "SINGLE_ELIGIBLE_PEER"
    assert pd.isna(solo["rank_movement"])
    assert summary.loc[summary["sector"].eq("Solo"), "top_5_overlap"].iat[0] == ""


def test_pdf_dependency_is_isolated_from_product_requirements() -> None:
    root = Path(__file__).parents[1]
    assert "pypdf" not in (root / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "pypdf==6.15.0" in (
        root / "marketdata/environment/requirements-marketdata.txt"
    ).read_text(encoding="utf-8")
    assert "from pypdf" not in (root / "src/stock_ranker/real_research_v2.py").read_text(encoding="utf-8")
