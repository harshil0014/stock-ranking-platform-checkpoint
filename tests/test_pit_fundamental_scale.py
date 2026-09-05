from __future__ import annotations

import json

import pandas as pd
import pytest

from marketdata.runners import acquire_nse_annual_reports as annual_reports
from marketdata.runners import audit_nse_annual_reports as annual_report_audit

from stock_ranker.identity_continuity import (
    build_identity_continuity,
    parse_nse_name_history,
    parse_nse_symbol_history,
)
from stock_ranker.pit_fundamental_scale import (
    audit_historical_report_availability,
    build_pit_fundamental_population,
    select_report_download_batch,
)
from stock_ranker.pit_annual_report_packets import build_annual_report_review_packets


def test_scale_population_is_exact_identity_baseline_ready_v2_gap() -> None:
    facts = pd.DataFrame([
        {"ticker": "B", "company": "B Ltd", "isin": "INE000A01002", "primary_exchange": "NSE", "product_sector": "Industrials", "product_baseline_eligible": True, "v2_eligible": False},
        {"ticker": "A", "company": "A Bank", "isin": "INE000A01001", "primary_exchange": "NSE", "product_sector": "Financial Services", "product_baseline_eligible": True, "v2_eligible": False},
        {"ticker": "C", "company": "C Ltd", "isin": "INE000A01003", "primary_exchange": "NSE", "product_sector": "Industrials", "product_baseline_eligible": True, "v2_eligible": True},
        {"ticker": "D", "company": "D Ltd", "isin": "BAD", "primary_exchange": "NSE", "product_sector": "Industrials", "product_baseline_eligible": True, "v2_eligible": False},
    ])
    result = build_pit_fundamental_population(facts)
    assert set(result["ticker"]) == {"A", "B"}
    assert result.set_index("ticker").loc["A", "conventional_roce_applicability"] == "REVIEW_FINANCIAL_ENTITY"
    assert result.set_index("ticker").loc["B", "conventional_roce_applicability"] == "STANDARD_PROBE"


def test_download_batch_is_deterministic_sector_diverse_and_nonfinancial() -> None:
    frame = pd.DataFrame([
        {"ticker": ticker, "company": ticker, "isin": f"INE000A01{i:03d}", "sector": sector, "selection_key": key, "selection_status": "SELECTED", "conventional_roce_applicability": applicability, "source_url": f"https://nsearchives.nseindia.com/{ticker}.pdf"}
        for i, (ticker, sector, key, applicability) in enumerate([
            ("A1", "A", "01", "STANDARD_PROBE"), ("A2", "A", "03", "STANDARD_PROBE"),
            ("B1", "B", "02", "STANDARD_PROBE"), ("FIN", "F", "00", "REVIEW_FINANCIAL_ENTITY"),
        ])
    ])
    result = select_report_download_batch(frame, 2)
    assert set(result["ticker"]) == {"A1", "B1"}
    pd.testing.assert_frame_equal(result, select_report_download_batch(frame.sample(frac=1, random_state=7), 2))


def test_historical_availability_never_infers_timestamp_from_filename(tmp_path) -> None:
    population = pd.DataFrame([{
        "ticker": "TEST", "isin": "INE000A01001", "sector": "Industrials",
        "conventional_roce_applicability": "STANDARD_PROBE",
    }])
    (tmp_path / "TEST.json").write_text(json.dumps({"data": [
        {"fromYr": "2023", "toYr": "2024", "disseminationDateTime": "-", "fileName": "https://nsearchives.nseindia.com/report_01082024.pdf"},
        {"fromYr": "2024", "toYr": "2025", "disseminationDateTime": "01-AUG-2025 12:00:00", "fileName": "https://nsearchives.nseindia.com/current.pdf"},
    ]}), encoding="utf-8")
    result, summary = audit_historical_report_availability(
        population, tmp_path, {"2023-2024": "2024-08-07", "2024-2025": "2025-08-07"}
    )
    old = result.loc[result["financial_year"].eq("2023-2024")].iloc[0]
    new = result.loc[result["financial_year"].eq("2024-2025")].iloc[0]
    assert old["availability_status"] == "REPORT_PRESENT_TIMESTAMP_UNRESOLVED"
    assert not bool(old["pit_available"])
    assert new["availability_status"] == "EXPLICIT_NSE_TIMESTAMP_AVAILABLE"
    assert bool(new["pit_available"])
    assert summary["strict_availability_rule"].startswith("Explicit NSE")


def test_official_identity_continuity_uses_edges_without_fuzzy_matching() -> None:
    symbols = parse_nse_symbol_history(
        b"Example Limited,OLD,NEW,01-Jan-2020\nExample Limited,OLDER,OLD,01-Jan-2015\n"
    )
    names = parse_nse_name_history(
        b"NCH_SYMBOL,NCH_PREV_NAME,NCH_NEW_NAME,NCH_DT\nNEW,Old Name,New Name,02-Jan-2020\n"
    )
    current = pd.DataFrame([{
        "ticker": "NEW", "company": "New Name", "isin": "INE000A01001", "primary_exchange": "NSE",
    }])
    result, summary = build_identity_continuity(
        current, symbols, names, symbol_source_sha256="a" * 64, name_source_sha256="b" * 64,
    )
    assert set(result.loc[result["evidence_type"].eq("SYMBOL_CHANGE"), "historical_symbol"]) == {"OLD", "OLDER"}
    assert summary["symbol_transition_count"] == 2
    assert summary["name_transition_count"] == 1
    assert summary["automatic_price_series_merge_count"] == 0


def test_identity_continuity_rejects_ambiguous_current_identity() -> None:
    current = pd.DataFrame([
        {"ticker": "A", "company": "A", "isin": "INE000A01001", "primary_exchange": "NSE"},
        {"ticker": "B", "company": "B", "isin": "INE000A01001", "primary_exchange": "NSE"},
    ])
    with pytest.raises(ValueError, match="unique ticker and ISIN"):
        build_identity_continuity(
            current, pd.DataFrame(columns=["old_symbol", "new_symbol", "effective_date", "company"]),
            pd.DataFrame(columns=["symbol", "old_company_name", "new_company_name", "effective_date"]),
            symbol_source_sha256="a" * 64, name_source_sha256="b" * 64,
        )


def test_bounded_report_download_is_hash_verified_and_resumable(tmp_path, monkeypatch) -> None:
    metadata_root = tmp_path / "metadata-root"
    (metadata_root / "metadata").mkdir(parents=True)
    metadata_file = metadata_root / "metadata/A.json"
    metadata_file.write_text('{"data": []}\n', encoding="utf-8")
    source_url = "https://nsearchives.nseindia.com/annual_reports/A.pdf"
    provenance = [{
        "ticker": "A", "selection_status": "SELECTED", "source_url": source_url,
        "pdf_filename": "A.pdf", "metadata_path": "metadata/A.json",
        "metadata_sha256": __import__("hashlib").sha256(metadata_file.read_bytes()).hexdigest(),
        "selected_metadata": {"disseminationDateTime": "01-AUG-2026 12:00:00"},
    }]
    (metadata_root / "annual_report_provenance.json").write_text(
        json.dumps(provenance), encoding="utf-8"
    )
    batch = tmp_path / "batch.csv"
    pd.DataFrame([{
        "ticker": "A", "isin": "INE000A01001", "company": "A Ltd",
        "sector": "Industrials", "source_url": source_url,
    }]).to_csv(batch, index=False)
    calls = []
    monkeypatch.setattr(annual_reports, "_fetch", lambda *args, **kwargs: calls.append(args[0]) or b"%PDF-1.7\nproof")
    output = tmp_path / "output"
    first = annual_reports.download_selected_metadata_reports(metadata_root, batch, output)
    assert first["downloaded_count"] == 1
    assert first["resumable_checkpointing"] is True
    assert calls == [source_url]
    calls.clear()
    resumed = annual_reports.download_selected_metadata_reports(metadata_root, batch, output, resume=True)
    assert resumed["downloaded_count"] == 1
    assert calls == []


def test_review_packets_are_locators_and_never_accepted_values(tmp_path) -> None:
    acquisition = tmp_path / "acquisition"
    audit = tmp_path / "audit"
    (audit / "text").mkdir(parents=True)
    acquisition.mkdir()
    (audit / "text/A.txt").write_text("Identity INE000A01001", encoding="utf-8")
    (acquisition / "annual_report_provenance.json").write_text(json.dumps([{
        "ticker": "A", "selection_status": "SELECTED", "source_url": "https://nsearchives.nseindia.com/A.pdf",
        "pdf_sha256": "a" * 64, "selected_metadata": {"disseminationDateTime": "01-AUG-2026 12:00:00"},
    }]), encoding="utf-8")
    page = {
        "page": 42, "roce": ["Return on Capital Employed 12.5%"],
        "debt_to_equity": ["Debt Equity Ratio 0.40"],
        "profit": ["Profit after tax 100 80"], "formula_language": True,
    }
    (audit / "candidate_audit.json").write_text(json.dumps([{
        "ticker": "A", "audit_status": "EXTRACTED", "text_path": "text/A.txt",
        "text_sha256": "b" * 64, "candidate_pages": [page],
    }]), encoding="utf-8")
    cohort = pd.DataFrame([{
        "ticker": "A", "company": "A Ltd", "isin": "INE000A01001", "sector": "Industrials",
    }])
    matrix, packets, summary = build_annual_report_review_packets(cohort, acquisition, audit)
    assert matrix.iloc[0]["packet_status"] == "REVIEW_PACKET_COMPLETE"
    assert matrix.iloc[0]["acceptance_status"] == "NOT_ACCEPTED_REQUIRES_ACCOUNTING_REVIEW"
    assert packets[0]["evidence"]["roce"][0]["numeric_tokens_untrusted_locator_only"] == ["12.5%"]
    assert summary["complete_review_packet_count"] == 1
    assert summary["accepted_record_count"] == 0
    assert summary["automatic_promotion_permitted"] is False


def test_parallel_audit_preserves_deterministic_ticker_order(tmp_path, monkeypatch) -> None:
    acquisition = tmp_path / "acquisition"
    acquisition.mkdir()
    (acquisition / "annual_report_provenance.json").write_text(json.dumps([
        {"ticker": "B", "selection_status": "SELECTED"},
        {"ticker": "A", "selection_status": "SELECTED"},
    ]), encoding="utf-8")
    monkeypatch.setattr(annual_report_audit, "_audit_entry", lambda entry, *_: {
        "ticker": entry["ticker"], "selection_status": "SELECTED", "audit_status": "EXTRACTED",
        "roce_candidate_page_count": 1, "debt_equity_candidate_page_count": 1,
        "profit_candidate_page_count": 1,
    })
    output = tmp_path / "audit"
    summary = annual_report_audit.audit(acquisition, output, workers=2)
    records = json.loads((output / "candidate_audit.json").read_text(encoding="utf-8"))
    assert [row["ticker"] for row in records] == ["A", "B"]
    assert summary["extracted_count"] == 2
