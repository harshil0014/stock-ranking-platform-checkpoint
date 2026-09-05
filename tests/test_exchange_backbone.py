from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest

from stock_ranker.exchange_backbone import (
    ACTION_COLUMNS, BACKLOG_COLUMNS, CLASSIFICATION_STATES, DOCUMENT_COLUMNS,
    FINANCIAL_COLUMNS, SHAREHOLDING_COLUMNS, accounting_family,
    audit_derived_classifications, canonical_json_bytes, due_backlog,
    initialize_backlog, normalize_bse_actions, normalize_nse_actions,
    normalize_nse_documents, normalize_nse_shareholding, parse_exchange_xbrl,
    parse_shareholding_inline_xbrl, select_latest_revisions, update_backlog,
)


def test_classification_audit_demotes_secondary_provider_labels() -> None:
    facts = pd.DataFrame([{
        "ticker": "ABC", "isin": "INE000A01001", "official_sector": None,
        "official_industry": None, "official_basic_industry": None,
        "official_classification_source": None, "derived_research_sector": "Industrials",
        "derived_research_industry": "Tools", "derived_research_basic_industry": None,
        "secondary_source": "Yahoo Finance via yfinance", "secondary_source_as_of": "2026-08-20",
        "secondary_sector": "Industrials", "secondary_industry": "Tools",
    }])
    result = audit_derived_classifications(facts)
    assert result.loc[0, "confidence_status"] == "DERIVED_SECONDARY_REFERENCE_ONLY"
    assert bool(result.loc[0, "ranking_grade"]) is False
    assert set(result["confidence_status"]).issubset(CLASSIFICATION_STATES)


def test_classification_audit_accepts_explicit_primary_business_evidence() -> None:
    facts = pd.DataFrame([{
        "ticker": "ABC", "isin": "INE000A01001", "official_sector": None,
        "official_industry": None, "official_basic_industry": None,
        "official_classification_source": None, "derived_research_sector": "Industrials",
        "derived_research_industry": "Tools", "derived_research_basic_industry": None,
        "secondary_source": None, "secondary_source_as_of": None,
        "secondary_sector": None, "secondary_industry": None,
    }])
    evidence = pd.DataFrame([{
        "isin": "INE000A01001", "source_url": "https://example.invalid/annual-report.pdf",
        "evidence_type": "AUDITED_SEGMENT_REVENUE", "evidence_date": "2026-03-31",
        "derivation_rule": "ONE_SEGMENT_OVER_50_PERCENT_REVENUE",
        "macro_economic_sector": "Industrials",
    }])
    result = audit_derived_classifications(facts, segment_evidence=evidence)
    assert result.loc[0, "confidence_status"] == "DERIVED_PRIMARY_EVIDENCE"
    assert bool(result.loc[0, "ranking_grade"]) is True


def test_bulk_nse_shareholding_and_revision_supersession() -> None:
    rows = [
        {"symbol": "ABC", "isin": "INE000A01001", "date": "30-JUN-2026", "broadcastDate": "10-JUL-2026 10:00:00", "recordId": "1", "pr_and_prgrp": "60", "public_val": "40", "revisedData": "N", "xbrl": "https://nse/1.xml"},
        {"symbol": "ABC", "isin": "INE000A01001", "date": "30-JUN-2026", "broadcastDate": "11-JUL-2026 10:00:00", "revisionDate": "11-JUL-2026 10:00:00", "recordId": "2", "pr_and_prgrp": "59", "public_val": "41", "revisedData": "Y", "xbrl": "https://nse/2.xml"},
    ]
    result = normalize_nse_shareholding(rows, source_sha256="a" * 64)
    assert tuple(result.columns) == SHAREHOLDING_COLUMNS
    assert len(result) == 1
    assert result.loc[0, "promoter_pct"] == 59
    assert result.loc[0, "revision_status"] == "REVISED"


def test_shareholding_inline_xbrl_extracts_only_explicit_rollups() -> None:
    payload = b"""<html xmlns:ix='http://www.xbrl.org/2013/inlineXBRL'>
    <ix:nonFraction name='in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares' contextRef='ShareholdingOfPromoterAndPromoterGroup_ContextI'>55.78</ix:nonFraction>
    <ix:nonFraction name='in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares' contextRef='PublicShareholding_ContextI'>44.22</ix:nonFraction></html>"""
    result = parse_shareholding_inline_xbrl(payload, metadata={
        "ticker": "ABC", "isin": "INE000A01001", "as_of_date": "2026-06-30",
    })
    assert result["promoter_pct"] == pytest.approx(55.78)
    assert result["public_pct"] == pytest.approx(44.22)
    assert result["fii_pct"] is None


def _xbrl(value: str = "120") -> bytes:
    return f"""<xbrl xmlns='http://www.xbrl.org/2003/instance' xmlns:i='urn:indas'>
      <context id='FY'><entity><identifier scheme='x'>INE000A01001</identifier></entity>
      <period><startDate>2025-04-01</startDate><endDate>2026-03-31</endDate></period></context>
      <unit id='INR'><measure>iso4217:INR</measure></unit>
      <i:RevenueFromOperations contextRef='FY' unitRef='INR'>{value}</i:RevenueFromOperations>
      <i:UnmappedFiledFact contextRef='FY' unitRef='INR'>7</i:UnmappedFiledFact>
    </xbrl>""".encode()


def test_xbrl_normalizes_known_and_retains_unknown_concepts() -> None:
    result = parse_exchange_xbrl(_xbrl(), filename="INTEGRATED_FILING_INDAS_1.xml", metadata={
        "symbol": "ABC", "isin": "INE000A01001", "consolidated": "Standalone",
        "available_at": "2026-05-01T10:00:00+05:30", "source_url": "https://nse/file.xml",
    })
    assert tuple(result.columns) == FINANCIAL_COLUMNS
    assert set(result["canonical_concept"]) == {"revenue", "unknown:UnmappedFiledFact"}
    assert result["period_type"].eq("ANNUAL").all()


@pytest.mark.parametrize("payload", [b"", b"<!DOCTYPE x><x/>", b"<xbrl>"])
def test_xbrl_rejects_empty_unsafe_or_malformed(payload: bytes) -> None:
    with pytest.raises(ValueError):
        parse_exchange_xbrl(payload, filename="x.xml", metadata={})


@pytest.mark.parametrize("filename,expected", [
    ("INTEGRATED_FILING_BANKING_1.xml", "BANKING"),
    ("INTEGRATED_FILING_NBFC_INDAS_1.xml", "NBFC_INDAS"),
    ("INTEGRATED_FILING_LIFE_INSURANCE_1.xml", "LIFE_INSURANCE"),
    ("INTEGRATED_FILING_REIT_1.xml", "REIT_INVIT"),
    ("INTEGRATED_FILING_INDAS_1.xml", "INDAS"),
])
def test_accounting_family_dispatch(filename: str, expected: str) -> None:
    assert accounting_family(filename) == expected


def test_nse_and_bse_actions_are_identity_safe() -> None:
    nse = normalize_nse_actions([{
        "symbol": "ABC", "isin": "INE000A01001", "subject": "Bonus 1:1",
        "exDate": "10-Aug-2026", "recDate": "11-Aug-2026",
    }], source_sha256="a" * 64)
    market = pd.DataFrame([{"exchange_security_id": "500001", "ticker": "BSE-500001", "isin": "INE000A01001"}])
    bse = normalize_bse_actions([{"scrip_code": 500001, "Purpose": "Dividend Rs 2", "Ex_date": "12 Aug 2026"}], market, source_sha256="b" * 64)
    assert tuple(nse.columns) == ACTION_COLUMNS
    assert nse.loc[0, "action_type"] == "BONUS"
    assert bse.loc[0, "ticker"] == "BSE-500001"
    assert bse.loc[0, "action_type"] == "DIVIDEND"


def test_document_index_classifies_without_downloading_pdf() -> None:
    result = normalize_nse_documents([{
        "symbol": "ABC", "sm_isin": "INE000A01001", "desc": "Annual Report",
        "attchmntText": "Annual report FY26", "an_dt": "10-Aug-2026 12:00:00",
        "seq_id": "9", "attchmntFile": "https://nsearchives/report.pdf",
    }], source_sha256="c" * 64)
    assert tuple(result.columns) == DOCUMENT_COLUMNS
    assert result.loc[0, "document_type"] == "ANNUAL_REPORT"


def test_durable_backlog_priority_retry_and_completion() -> None:
    candidates = pd.DataFrame([
        {"ticker": "RICH", "isin": "2", "provider_symbol": "RICH.NS", "priority": 2},
        {"ticker": "EMPTY", "isin": "1", "provider_symbol": "EMPTY.NS", "priority": 0},
    ])
    backlog = initialize_backlog(candidates)
    assert tuple(backlog.columns) == BACKLOG_COLUMNS
    assert due_backlog(backlog, now="2026-08-22T00:00:00+00:00", limit=1).loc[0, "ticker"] == "EMPTY"
    backlog = update_backlog(backlog, "EMPTY", status="TRANSIENT_FAILED", error_class="RATE_LIMIT",
                             attempted_at="2026-08-22T00:00:00+00:00", retry_after="2026-08-23T00:00:00+00:00")
    assert due_backlog(backlog, now="2026-08-22T01:00:00+00:00", limit=2)["ticker"].tolist() == ["RICH"]
    backlog = update_backlog(backlog, "RICH", status="ACCEPTED", error_class=None,
                             attempted_at="2026-08-22T01:00:00+00:00")
    assert backlog.set_index("ticker").loc["RICH", "completion_status"] == "ACCEPTED"


def test_latest_revision_keeps_distinct_historical_periods() -> None:
    frame = pd.DataFrame([
        {**{column: None for column in SHAREHOLDING_COLUMNS}, "ticker": "ABC", "isin": "I", "as_of_date": "2025-03-31", "filing_id": "1", "promoter_pct": 60},
        {**{column: None for column in SHAREHOLDING_COLUMNS}, "ticker": "ABC", "isin": "I", "as_of_date": "2026-03-31", "filing_id": "2", "promoter_pct": 55},
    ])
    result = select_latest_revisions(frame, key=("isin", "as_of_date"))
    assert len(result) == 2
    assert result["promoter_pct"].tolist() == [60, 55]


def test_canonical_json_is_deterministic_and_finite() -> None:
    left = canonical_json_bytes({"b": 2, "a": 1})
    right = canonical_json_bytes({"a": 1, "b": 2})
    assert left == right
    assert sha256(left).hexdigest() == sha256(right).hexdigest()
    with pytest.raises(ValueError):
        canonical_json_bytes({"bad": float("nan")})
