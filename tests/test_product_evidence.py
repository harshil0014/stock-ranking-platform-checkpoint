import pandas as pd
import importlib.util
from pathlib import Path

from stock_ranker.exchange_backbone import DOCUMENT_COLUMNS
from stock_ranker.product_evidence import enrich_presentation, field_display_state, official_document_index


def test_document_recovery_requires_exact_identity_official_source_and_hash():
    source = {"isin": "INE001A01010", "ticker": "ABC", "source_url": "https://nsearchives.nseindia.com/x.xml",
              "source_sha256": "a" * 64, "available_at": "2025-08-01T10:00:00+05:30"}
    frame = pd.DataFrame([source, {**source, "isin": "INE002A01010", "source_url": "https://untrusted.example/x"},
                          {**source, "isin": "INE003A01010", "source_sha256": None}])
    result = official_document_index(pd.DataFrame(columns=DOCUMENT_COLUMNS), frame, pd.DataFrame())
    assert result["isin"].tolist() == ["INE001A01010"]
    assert result.iloc[0]["document_type"] == "FINANCIAL_RESULTS_XBRL"
    assert result.iloc[0]["source_sha256"] == "a" * 64
    pd.testing.assert_frame_equal(result, official_document_index(result, frame, pd.DataFrame()))


def test_field_states_preserve_zero_and_do_not_invent_absence_cause():
    assert field_display_state("profit", 0, {})["state"] == "VALUE_AVAILABLE"
    assert field_display_state("roce", float("nan"), {"product_sector": "Financial Services"})["state"] == "ACCEPTED_EVIDENCE_NOT_FOUND"
    assert "No accepted" in field_display_state("latest_price", None, {"trade_date": "2026-09-07"})["reason"]


def test_structured_profile_preserves_values_and_explains_every_missing_field():
    sections = {"company_profile_secondary_reference": {"values": {"company_profile": None}},
                "ratios": {"values": {"roce": None, "profit": 0.0}}}
    fact = {"company": "ABC", "isin": "INE001A01010", "primary_exchange": "BSE"}
    enrich_presentation(sections, fact)
    assert sections["company_profile_secondary_reference"]["structured_identity"] == fact
    assert sections["ratios"]["values"] == {"roce": None, "profit": 0.0}
    assert set(sections["ratios"]["field_states"]) == {"roce", "profit"}
    assert sections["ratios"]["field_states"]["roce"]["reason"]


def test_bse_shareholding_never_queries_nse_ticker_and_quarantines_code_conflict(tmp_path, monkeypatch):
    path = Path(__file__).parents[1] / "marketdata/runners/acquire_exchange_backbone.py"
    spec = importlib.util.spec_from_file_location("backbone_acquisition_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    def fetch(url, **kwargs):
        calls.append(url)
        return {"Table": [{"FLD_ScripCode": 500002, "EndDate": "2026-06-30"}]}
    monkeypatch.setattr(module, "fetch_json", fetch)
    market = pd.DataFrame([
        {"ticker": "ABC", "isin": "INE001A01010", "primary_exchange": "NSE", "exchange_security_id": "ABC"},
        {"ticker": "BSE-500001", "isin": "INE002A01010", "primary_exchange": "BSE", "exchange_security_id": "500001"}])
    holdings, documents, counts = module._bse_shareholding(tmp_path, market, 10, prioritize_professor=False)
    assert len(calls) == 1 and "scripcode=500001" in calls[0]
    assert counts["failed"] == 1
    assert holdings.empty and documents.empty


def test_bse_filing_isin_must_match_even_when_scrip_code_matches():
    import pytest
    path = Path(__file__).parents[1] / "marketdata/runners/acquire_exchange_backbone.py"
    spec = importlib.util.spec_from_file_location("backbone_isin_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate_bse_shareholding_identity(b"<td>INE492N01022</td>", "INE492N01022")
    for value in (b"<td>INE492N01014</td>", b"<html>no identity</html>"):
        with pytest.raises(ValueError, match="ISIN conflict"):
            module.validate_bse_shareholding_identity(value, "INE492N01022")
