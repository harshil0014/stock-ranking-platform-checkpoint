from stock_ranker.bse_annual_report_fallback import (
    exact_bse_identity_map,
    select_bse_annual_report_announcement,
)


def test_bse_identity_mapping_is_exact_isin_and_rejects_ambiguity() -> None:
    rows = [
        {"ISIN_NUMBER": "INE000A01001", "SCRIP_CD": "500001", "scrip_id": "A", "Issuer_Name": "A Ltd"},
        {"ISIN_NUMBER": "INE000A01002", "SCRIP_CD": "500002", "scrip_id": "B", "Issuer_Name": "B Ltd"},
        {"ISIN_NUMBER": "INE000A01002", "SCRIP_CD": "500003", "scrip_id": "B2", "Issuer_Name": "B Ltd"},
    ]
    result = exact_bse_identity_map(rows)
    assert result["INE000A01001"]["bse_scrip_code"] == "500001"
    assert "INE000A01002" not in result


def test_bse_annual_report_selection_requires_exact_code_pdf_and_pre_cutoff_dissemination() -> None:
    rows = [
        {"SCRIP_CD": 500001, "NEWSSUB": "Reg. 34 (1) Annual Report", "ATTACHMENTNAME": "report.pdf", "DissemDT": "2026-08-20T10:00:00", "NEWSID": "a"},
        {"SCRIP_CD": 500001, "NEWSSUB": "Annual Report", "ATTACHMENTNAME": "late.pdf", "DissemDT": "2026-08-22T10:00:00", "NEWSID": "b"},
        {"SCRIP_CD": 500002, "NEWSSUB": "Annual Report", "ATTACHMENTNAME": "wrong.pdf", "DissemDT": "2026-08-19T10:00:00", "NEWSID": "c"},
    ]
    selected, status = select_bse_annual_report_announcement(
        rows, scrip_code="500001", cutoff="2026-08-21T23:59:59",
    )
    assert status == "SELECTED_BSE_EXACT_REGULATION_34_CANDIDATE"
    assert selected["NEWSID"] == "a"
