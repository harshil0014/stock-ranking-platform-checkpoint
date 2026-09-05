import json
from pathlib import Path


def test_all_28_near_complete_records_have_terminal_adjudication():
    path = Path(__file__).parents[1] / "marketdata/specifications/pit_near_complete_adjudication_v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload["records"]
    assert payload["population"] == len(records) == 28
    assert len({row["ticker"] for row in records}) == 28
    counts = {status: sum(row["status"] == status for row in records) for status in {row["status"] for row in records}}
    assert counts == payload["resolution_counts"] == {"PROMOTED": 14, "ALREADY_PROMOTED": 2, "QUARANTINED": 12}
    assert all(row["resolution"] for row in records)


def test_quarantine_does_not_convert_accounting_absence_to_zero():
    path = Path(__file__).parents[1] / "marketdata/specifications/pit_near_complete_adjudication_v1.json"
    records = {row["ticker"]: row for row in json.loads(path.read_text(encoding="utf-8"))["records"]}
    assert records["NATIONALUM"]["resolution"] == "DEBT_TO_EQUITY_DASH_NOT_ZERO"
    assert records["AIAENG"]["resolution"] == "CURRENT_DEBT_TO_EQUITY_DASH_NOT_NUMERIC_ZERO"
    assert records["ROUTE"]["resolution"] == "DEBT_RATIO_NOT_FURNISHED_DESPITE_DEBT_FREE_DISCLOSURE"
    assert records["KPIL"]["resolution"] == "MULTIPLE_ROCE_DEFINITIONS_NO_FROZEN_SELECTION_POLICY"
