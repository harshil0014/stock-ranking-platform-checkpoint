from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest

from stock_ranker.pit_annual_report_validation import (
    FUNDAMENTAL_CONTRACT,
    VALIDATION_SCHEMA,
    export_annual_report_validation,
    validate_reviewed_annual_reports,
)


ROOT = Path(__file__).parents[1]
REAL_ACQUISITION = ROOT / "data/marketdata/pit-fundamental-probe-2026-08-21-50/annual_reports"


def _write_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    acquisition = tmp_path / "acquisition"
    text_root = tmp_path / "text"
    (acquisition / "pdf").mkdir(parents=True)
    text_root.mkdir()
    records = []
    provenance = []
    coverage = []
    definitions = [
        ("GOOD", "INE000000001", "Good Limited", 0.1, 0.2, 20.0, 10.0, "COMPLETE_DIRECT_DISCLOSURE", ""),
        ("NEG", "INE000000002", "Negative Limited", 0.3, -0.4, 30.0, -20.0, "COMPLETE_DIRECT_DISCLOSURE", ""),
        ("MISS", "INE000000003", "Missing Limited", None, None, 4.0, 2.0, "UNRESOLVED", "UNRESOLVED_NO_NUMERIC_DEBT_EQUITY_DISCLOSURE"),
    ]
    for ticker, isin, company, roce, debt, current, prior, status, unresolved in definitions:
        pdf = acquisition / "pdf" / f"{ticker}.pdf"
        pdf.write_bytes(f"official-{ticker}".encode())
        digest = sha256(pdf.read_bytes()).hexdigest()
        (text_root / f"{ticker}.txt").write_text(
            "\n".join([
                "=== PDF PAGE 1 ===", f"Standalone identity {isin}",
                "=== PDF PAGE 2 ===", "Return on Capital Employed evidence",
                "=== PDF PAGE 3 ===", "Debt Equity Ratio evidence",
                "=== PDF PAGE 4 ===", "Profit for the year evidence",
            ]), encoding="utf-8",
        )
        metric = lambda page, label: {"label": label, "page": page, "anchors": [label], "formula": "direct issuer formula"}
        roce_evidence = metric(2, "Return on Capital Employed")
        debt_evidence = metric(3, "Debt Equity Ratio")
        if status == "COMPLETE_DIRECT_DISCLOSURE":
            roce_evidence["canonical_decimal"] = roce
            debt_evidence["canonical_decimal"] = debt
        records.append({
            "ticker": ticker, "company": company, "isin": isin, "pdf_sha256": digest,
            "review_status": status, "unresolved_reason": unresolved,
            "roce": roce_evidence, "debt_to_equity": debt_evidence,
            "profit": {"label": "Profit for the year", "page": 4,
                       "anchors": ["Profit for the year"], "current_value": current,
                       "prior_value": prior, "unit": "INR crore"},
            "comparability_warning": "",
        })
        provenance.append({
            "ticker": ticker, "selection_status": "SELECTED", "pdf_path": f"pdf/{ticker}.pdf",
            "pdf_sha256": digest, "source_url": f"https://nsearchives.nseindia.com/{ticker}.pdf",
            "selected_metadata": {"disseminationDateTime": "01-AUG-2026 10:00:00"},
        })
        coverage.append({"ticker": ticker, "company": company, "isin": isin})
    specification = tmp_path / "specification.json"
    specification.write_text(json.dumps({
        "schema_version": VALIDATION_SCHEMA,
        "fundamental_data_contract_version": FUNDAMENTAL_CONTRACT,
        "reporting_basis": "STANDALONE", "financial_year": "2025-26",
        "period_end": "2026-03-31", "records": records,
    }), encoding="utf-8")
    (acquisition / "annual_report_provenance.json").write_text(
        json.dumps(provenance), encoding="utf-8"
    )
    coverage_path = tmp_path / "coverage.csv"
    pd.DataFrame(coverage).to_csv(coverage_path, index=False)
    return specification, coverage_path, acquisition, text_root


def test_reviewed_validation_separates_complete_invalid_leverage_and_unresolved(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path)
    result = validate_reviewed_annual_reports(*paths)
    assert result.summary["complete_direct_disclosure_count"] == 2
    assert result.summary["v2_numeric_policy_usable_count"] == 1
    assert result.summary["ambiguous_or_unresolved_count"] == 1
    assert result.summary["wrong_accepted_value_count"] == 0
    statuses = result.records.set_index("ticker")["final_validation_status"].to_dict()
    assert statuses == {
        "GOOD": "COMPLETE_PIT_SAFE_CANDIDATE",
        "MISS": "UNRESOLVED_NO_NUMERIC_DEBT_EQUITY_DISCLOSURE",
        "NEG": "COMPLETE_BUT_V2_INVALID_LEVERAGE",
    }
    good = result.records.set_index("ticker").loc["GOOD"]
    assert good["profit_growth_yoy"] == pytest.approx(1.0)


def test_validation_rejects_report_hash_anchor_identity_and_lookahead(tmp_path: Path) -> None:
    specification, coverage, acquisition, text_root = _write_fixture(tmp_path)
    pdf = acquisition / "pdf/GOOD.pdf"
    pdf.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_reviewed_annual_reports(specification, coverage, acquisition, text_root)

    specification, coverage, acquisition, text_root = _write_fixture(tmp_path / "anchor")
    text = text_root / "GOOD.txt"
    text.write_text(text.read_text(encoding="utf-8").replace("Return on Capital Employed", "ROA"), encoding="utf-8")
    with pytest.raises(ValueError, match="evidence anchor absent"):
        validate_reviewed_annual_reports(specification, coverage, acquisition, text_root)

    specification, coverage, acquisition, text_root = _write_fixture(tmp_path / "future")
    provenance_path = acquisition / "annual_report_provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance[0]["selected_metadata"]["disseminationDateTime"] = "22-AUG-2026 00:00:00"
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    with pytest.raises(ValueError, match="unavailable at the ranking cutoff"):
        validate_reviewed_annual_reports(specification, coverage, acquisition, text_root)


def test_validation_export_is_deterministic_and_never_promotes_mapping(tmp_path: Path) -> None:
    paths = _write_fixture(tmp_path / "input")
    first = validate_reviewed_annual_reports(*paths)
    second = validate_reviewed_annual_reports(*paths)
    assert first.summary["records_fingerprint"] == second.summary["records_fingerprint"]
    export_annual_report_validation(first, tmp_path / "one")
    export_annual_report_validation(second, tmp_path / "two")
    assert (tmp_path / "one/reviewed_fundamental_candidates.csv").read_bytes() == (
        tmp_path / "two/reviewed_fundamental_candidates.csv"
    ).read_bytes()
    assert "accepted" not in json.loads((tmp_path / "one/validation_summary.json").read_text())


def test_review_spec_is_review_only_and_contains_exact_14_candidates() -> None:
    payload = json.loads(
        (ROOT / "marketdata/specifications/pit_annual_report_validation_14.json").read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == VALIDATION_SCHEMA
    assert payload["fundamental_data_contract_version"] == FUNDAMENTAL_CONTRACT
    assert payload["reporting_basis"] == "STANDALONE"
    assert len(payload["records"]) == 14
    assert {row["ticker"] for row in payload["records"]} == {
        "SHRIPISTON", "IDEA", "IGARASHI", "POWERINDIA", "BLUESTARCO", "TRF",
        "TRIDENT", "SHALBY", "AMBUJACEM", "PVRINOX", "VIMTALABS", "TVTODAY",
        "BOSCHLTD", "SHEKHAWATI",
    }
    assert "accepted" not in payload


@pytest.mark.skipif(not REAL_ACQUISITION.is_dir(), reason="ignored official probe evidence unavailable")
def test_cached_official_14_report_validation_acceptance() -> None:
    result = validate_reviewed_annual_reports(
        ROOT / "marketdata/specifications/pit_annual_report_validation_14.json",
        ROOT / "data/marketdata/pit-fundamental-probe-2026-08-21-50-analysis-v3/coverage_matrix.csv",
        REAL_ACQUISITION,
        ROOT / "data/marketdata/pit-fundamental-probe-2026-08-21-50/annual_report_audit/text",
    )
    assert result.summary["attempted_count"] == 14
    assert result.summary["complete_direct_disclosure_count"] == 13
    assert result.summary["v2_numeric_policy_usable_count"] == 12
    assert result.summary["unresolved_tickers"] == ["POWERINDIA"]
    assert result.records.loc[result.records.ticker.eq("IDEA"), "final_validation_status"].item() == (
        "COMPLETE_BUT_V2_INVALID_LEVERAGE"
    )
    indexed = result.records.set_index("ticker")
    assert indexed.loc["BOSCHLTD", "roce"] == pytest.approx(0.24)
    assert indexed.loc["IDEA", "debt_to_equity"] == pytest.approx(-4.14)
    assert pd.isna(indexed.loc["POWERINDIA", "debt_to_equity"])
    complete = indexed.loc[indexed.review_status.eq("COMPLETE_DIRECT_DISCLOSURE")]
    assert complete[["roce", "debt_to_equity", "current_profit", "prior_profit"]].notna().all().all()
