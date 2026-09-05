from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from stock_ranker.pit_accounting_promotion import (
    load_promoted_additions, merge_candidate_fundamentals, validated_fundamental_candidates,
)
from stock_ranker.v2_contracts import FUNDAMENTAL_COLUMNS


def _record(ticker: str = "ABC", timestamp: str = "01-AUG-2026 10:00:00", debt: float = 0.4):
    selected = {
        "roce": {"current_value": 0.12, "prior_value": 0.10, "unit": "", "page": 10},
        "debt_to_equity": {"current_value": debt, "prior_value": 0.5, "unit": "", "page": 10},
        "profit": {"current_value": 120.0, "prior_value": 100.0, "unit": "INR crore", "page": 8},
    }
    return {"ticker": ticker, "company": "ABC Ltd", "isin": "INE000A01000", "sector": "Test",
            "validation_status": "INDEPENDENTLY_VALIDATED",
            "identity_chain_status": "EXACT_NSE_METADATA_PACKET_ISIN_AND_PDF_HASH",
            "exchange_dissemination_timestamp": timestamp, "selected": selected,
            "source_url": "https://example.invalid/report.pdf", "pdf_sha256": "a" * 64}


def test_only_pre_cutoff_independently_validated_records_enter_candidate() -> None:
    frame, accepted, deferred = validated_fundamental_candidates(
        [_record(), _record("LATE", "16-AUG-2026 10:00:00")], ranking_date=date(2026, 8, 7)
    )
    assert frame["ticker"].tolist() == ["ABC"]
    assert frame.iloc[0]["profit_growth_yoy"] == pytest.approx(0.2)
    assert [item["ticker"] for item in accepted] == ["ABC"]
    assert deferred == [{"ticker": "LATE", "reason": "OFFICIAL_REPORT_AVAILABLE_AFTER_RANKING_DATE", "available_date": "2026-08-16"}]


def test_negative_leverage_cannot_enter_candidate() -> None:
    with pytest.raises(ValueError, match="negative leverage"):
        validated_fundamental_candidates([_record(debt=-0.1)], ranking_date=date(2026, 8, 7))


def test_candidate_merge_rejects_overlap_and_preserves_schema() -> None:
    existing = pd.DataFrame([["ABC", "2026-03-31", "2026-07-01", 0.1, 0.2, 0.3]], columns=FUNDAMENTAL_COLUMNS)
    with pytest.raises(ValueError, match="overlap"):
        merge_candidate_fundamentals(existing, existing)


def test_promoted_spec_preserves_point_in_time_boundary(tmp_path) -> None:
    import json
    record = _record()
    item = {
        "ticker": "ABC", "company": "ABC Ltd", "isin": "INE000A01000", "sector": "Test",
        "available_date": "2026-08-01", "source_url": "https://example.invalid/a.pdf", "pdf_sha256": "a" * 64,
        "roce": {"value": 0.12}, "debt_to_equity": {"value": 0.4},
        "profit": {"value": 120.0, "prior": 100.0},
    }
    late = dict(item, ticker="LATE", available_date="2026-08-16")
    path = tmp_path / "spec.json"
    path.write_text(json.dumps({
        "schema_version": "pit_independently_validated_additions_v1",
        "fundamental_data_contract_version": "nse_audited_standalone_fundamentals_v1",
        "reporting_basis": "STANDALONE", "period_end": "2026-03-31", "records": [item, late],
    }), encoding="utf-8")
    fundamentals, identity, deferred = load_promoted_additions(path, ranking_date=date(2026, 8, 7))
    assert fundamentals["ticker"].tolist() == ["ABC"]
    assert identity["ticker"].tolist() == ["ABC"]
    assert deferred[0]["ticker"] == "LATE"


def test_source_controlled_additions_are_exact_and_pit_filtered() -> None:
    specification = (
        Path(__file__).parents[1]
        / "marketdata/specifications/pit_independently_validated_additions_v1.json"
    )
    current, identities, deferred = load_promoted_additions(
        specification, ranking_date=date(2026, 8, 21)
    )
    original = {
        "ADANIGREEN", "ALKEM", "DMART", "DYNAMATECH", "FSL", "GESHIP", "IFBAGRO",
        "INDIAMART", "IMFA", "KEC", "OBEROIRLTY", "QUESS", "SONATSOFTW", "VEEDOL", "WELENT"
    }
    recovered = {
        "ADSL", "ATGL", "CEMPRO", "GRAPHITE", "GULFOILLUB", "ICIL", "JKPAPER",
        "JSWENERGY", "MARKSANS", "NEOGEN", "SOLARINDS", "SWSOLAR", "VARROC", "WABAG",
    }
    assert set(current["ticker"]) == original | recovered
    assert len(current) == 29
    assert identities["ticker"].tolist() == current["ticker"].tolist()
    assert deferred == []

    earlier, _, deferred = load_promoted_additions(
        specification, ranking_date=date(2026, 8, 7)
    )
    assert "DYNAMATECH" not in earlier["ticker"].tolist()
    assert {item["ticker"] for item in deferred} == {
        "ADSL", "DYNAMATECH", "GULFOILLUB", "JKPAPER",
    }

    import json
    payload = json.loads(specification.read_text(encoding="utf-8"))
    assert payload["pdfium_179_blind_records_sha256"] == "db3187df8f2c117454b9b9acabeacdb88566b875a8b05144cedeecaeb1c88175"
    assert payload["pdfium_179_deep_row_safe_records_sha256"] == "d27edbbc3ae6e752dc720ded1496d5a2c8d08d48933cef5d5169afc133f16535"
    records = {item["ticker"]: item for item in payload["records"]}
    assert (records["ALKEM"]["roce"]["value"], records["ALKEM"]["debt_to_equity"]["value"]) == (0.139, 0.0)
    assert (records["IMFA"]["profit"]["value"], records["IMFA"]["profit"]["prior"]) == (424.36, 378.09)
    assert (records["VEEDOL"]["roce"]["value"], records["VEEDOL"]["debt_to_equity"]["value"]) == (0.1823, 0.02)
    assert (records["ICIL"]["debt_to_equity"]["value"], records["GRAPHITE"]["profit"]["value"]) == (0.36, 264.60)
    assert (records["VARROC"]["profit"]["value"], records["WABAG"]["profit"]["prior"]) == (2881.93, 2713.0)
