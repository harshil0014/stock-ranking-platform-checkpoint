"""Fictional local fixtures for manual statutory-document recovery boundaries."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "marketdata/runners"))
from manual_financial_recovery import (
    another_document_required,
    candidate_identity,
    classify_residual_blocker,
    identify,
    load_current_reference,
    pdf_facts,
    xml_facts,
)


def test_nested_supplement_preserves_prior_and_is_repeatable(tmp_path):
    import io, zipfile
    from manual_financial_recovery import supplement_archive
    pack=tmp_path/'pack'; pack.mkdir()
    old=pack/'manual'/'old'; old.mkdir(parents=True)
    with zipfile.ZipFile(old/'archive.zip','w') as z:z.writestr('original.xml',b'<original/>')
    (pack/'manual_latest.json').write_text(json.dumps({'batch':'manual/old'}))
    inner=io.BytesIO()
    with zipfile.ZipFile(inner,'w') as z:z.writestr('report.pdf',b'%PDF-fixture')
    new=tmp_path/'new.zip'
    with zipfile.ZipFile(new,'w') as z:z.writestr('nested.zip',inner.getvalue())
    first=supplement_archive(pack,[new]); assert first==supplement_archive(pack,[new])
    with zipfile.ZipFile(first) as z:
        assert z.read('original.xml')==b'<original/>'
        assert len(z.namelist())==2
    newer=pack/'manual'/'new'; newer.mkdir()
    (newer/'archive.zip').write_bytes(first.read_bytes())
    (pack/'manual_latest.json').write_text(json.dumps({'batch':'manual/new'}))
    assert supplement_archive(pack,[new])==first


def test_pdf_preserves_nse_identity_exchange():
    rows=pdf_facts([PDF],[PDF],{**IDENTITY,'primary_exchange':'NSE'},'fixture')
    assert rows and {r['exchange'] for r in rows}=={'NSE'}


def test_auditor_disclaimer_is_not_silently_accepted():
    source=PDF+'\nDisclaimer of Opinion\n'
    rows=pdf_facts([source],[source],IDENTITY,'fixture')
    assert rows and all('AUDITOR_DISCLAIMER_REQUIRES_REVIEW' in r['rejection_reasons'] for r in rows)


def test_nse_isin_allows_supporting_dual_listing_code():
    row={**IDENTITY,'primary_exchange':'NSE','exchange_security_id':'EXAMPLE'}
    found,status=identify('INE001A01010 BSE code: 500001',[row],'pdf',b'')
    assert found==row and status=='EXACT_EMBEDDED_ISIN'


def test_sebi_integrated_filing_exact_identity_and_inr_units():
    raw=xml().decode().replace('http://www.bseindia.com/xbrl/fin/2020-03-31/in-bse-fin','http://www.sebi.gov.in/xbrl/2026-01-31/in-capmkt').replace('</x:xbrl>','<f:NameOfTheCompany>Fictional Limited</f:NameOfTheCompany></x:xbrl>').encode()
    identity={**IDENTITY,'primary_exchange':'NSE','exchange_security_id':'FICTIONAL'}
    found,status=identify(raw.decode(),[identity],'xml',raw)
    assert found==identity and status=='EXACT_EMBEDDED_ISIN'
    rows=xml_facts(raw,identity,'fixture')
    revenue=next(r for r in rows if r['canonical_concept']=='revenue')
    assert revenue['value']=='100000' and revenue['unit']=='INR'
    assert revenue['review_status']=='ACCEPTED_CURRENT_REFERENCE'
    assert not revenue['pit_usable'] and revenue['available_at'] is None
    conflicting=raw.replace(b'Fictional Limited',b'Unrelated Limited')
    assert identify(conflicting.decode(),[identity],'xml',conflicting)[0] is None

IDENTITY = {"ticker": "BSE-500001", "isin": "INE001A01010", "company": "Fictional Limited", "exchange_security_id": "500001"}


def xml(extra="", scenario=""):
    return f'''<x:xbrl xmlns:x="http://www.xbrl.org/2003/instance" xmlns:f="http://www.bseindia.com/xbrl/fin/2020-03-31/in-bse-fin">
<x:context id="annual"><x:entity><x:identifier scheme="http://www.bseindia.com/bse-fin/ScripCode">500001</x:identifier></x:entity>
<x:period><x:startDate>2025-04-01</x:startDate><x:endDate>2026-03-31</x:endDate></x:period>{scenario}</x:context>
<x:unit id="INR"><x:measure>iso4217:INR</x:measure></x:unit>
<f:ISIN contextRef="annual">INE001A01010</f:ISIN>
<f:NatureOfReportStandaloneConsolidated contextRef="annual">Standalone</f:NatureOfReportStandaloneConsolidated>
<f:WhetherResultsAreAuditedOrUnaudited contextRef="annual">Audited</f:WhetherResultsAreAuditedOrUnaudited>
<f:LevelOfRoundingUsedInFinancialStatements contextRef="annual">Lakhs</f:LevelOfRoundingUsedInFinancialStatements>
<f:DateOfBoardMeetingWhenFinancialResultsWereApproved contextRef="annual">2026-05-01</f:DateOfBoardMeetingWhenFinancialResultsWereApproved>
<f:RevenueFromOperations contextRef="annual" unitRef="INR">100000</f:RevenueFromOperations>
<f:ProfitBeforeTax contextRef="annual" unitRef="INR">100</f:ProfitBeforeTax>
<f:TaxExpense contextRef="annual" unitRef="INR">20</f:TaxExpense>
<f:ProfitLossForPeriod contextRef="annual" unitRef="INR">80</f:ProfitLossForPeriod>{extra}</x:xbrl>'''.encode()


def test_embedded_identity_not_filename_and_conflict_rejection():
    raw = xml()
    assert identify("", [IDENTITY], "xml", raw)[0] == IDENTITY
    assert identify("", [IDENTITY], "xml", raw.replace(b">500001<", b">500002<"))[0] is None
    assert identify("Fictional Limited", [IDENTITY], "pdf", b"")[0] is None
    assert identify("Fictional Ltd. BSE Security Code: 500001", [IDENTITY], "pdf", b"")[0] == IDENTITY
    assert identify("Fictional Limited Stock Code No: 500001", [IDENTITY], "pdf", b"")[0] == IDENTITY


def test_instance_inr_not_double_scaled_and_board_date_not_pit():
    rows = xml_facts(xml(), IDENTITY, "fixture")
    revenue = next(r for r in rows if r["canonical_concept"] == "revenue")
    assert revenue["value"] == "100000" and revenue["unit"] == "INR"
    assert revenue["presentation_rounding"] == "Lakhs"
    assert revenue["available_at"] is None and revenue["pit_usable"] is False
    assert revenue["review_status"] == "ACCEPTED_CURRENT_REFERENCE"


def test_old_embedded_isin_is_associated_but_never_accepted_as_current_identity():
    current = {**IDENTITY, "isin": "INE001A01028", "primary_exchange": "BSE"}
    raw = xml().replace(b"INE001A01010", b"INE001A01011")
    found, status = candidate_identity(raw.decode(), [current], "xml", raw)
    assert found == current
    assert status == "EMBEDDED_ISIN_CANONICAL_CONFLICT"
    document = {"identity_status": "IDENTITY_UNRESOLVED", "candidate_identity_status": status,
                "source_type": "BSE_XBRL_XML"}
    assert classify_residual_blocker([document], [], [], ["pat"]) == "IDENTITY_AMBIGUITY"
    assert another_document_required([document], [], []) is True


def test_no_fact_blocker_distinguishes_identity_from_parser():
    unresolved = {"identity_status": "IDENTITY_UNRESOLVED", "candidate_identity_status": "IDENTITY_UNRESOLVED",
                  "source_type": "ANNUAL_REPORT_PDF", "error": None}
    exact = {**unresolved, "identity_status": "EXACT_EMBEDDED_ISIN"}
    assert classify_residual_blocker([unresolved], [], [], ["pat"]).startswith("IDENTITY_VALIDATION_FAILED:")
    assert classify_residual_blocker([exact], [], [], ["pat"]).startswith("PARSER_LIMITATION:")


def test_conflicting_xml_duplicates_never_select_last():
    extra = '<f:RevenueFromOperations contextRef="annual" unitRef="INR">999</f:RevenueFromOperations>'
    rows = [r for r in xml_facts(xml(extra), IDENTITY, "fixture") if r["canonical_concept"] == "revenue"]
    assert len(rows) == 2
    assert all(r["review_status"] == "REJECTED" for r in rows)


def test_dimension_and_reconciliation_fail_closed():
    assert all(r["review_status"] == "REJECTED" for r in xml_facts(xml(scenario="<x:scenario/>"), IDENTITY, "fixture"))
    broken = xml().replace(b">80<", b">81<")
    assert all(r["review_status"] == "REJECTED" for r in xml_facts(broken, IDENTITY, "fixture"))


PDF = '''Standalone Statement of Profit and Loss
For the year ended March 31, 2026 March 31, 2025
(Rs in Lakhs)
Revenue from operations 100.00 0.00
As per our report of even date. Chartered Accountants
'''


def test_pdf_concordance_units_zero_and_missing():
    rows = pdf_facts([PDF], [PDF], IDENTITY, "fixture")
    assert [r["value"] for r in rows] == ["10000000.00", "0.00"]
    assert all(r["review_status"] == "ACCEPTED_CURRENT_REFERENCE" for r in rows)
    missing = PDF.replace("0.00\n", "-\n")
    assert all(r["review_status"] == "REJECTED" for r in pdf_facts([missing], [missing], IDENTITY, "fixture"))
    assert all(r["review_status"] == "REJECTED" for r in pdf_facts([PDF], [PDF.replace("100.00", "101.00")], IDENTITY, "fixture"))


def test_pdf_whole_rupee_unit_is_not_scaled():
    source = PDF.replace("(Rs in Lakhs)", "(Amount in Rupees)")
    rows = pdf_facts([source], [source], IDENTITY, "fixture")
    assert [r["value"] for r in rows] == ["100.00", "0.00"]
    assert all(r["unit"] == "INR" and r["review_status"] == "ACCEPTED_CURRENT_REFERENCE" for r in rows)


@pytest.mark.parametrize("change", [lambda p:p.replace("Standalone", "Consolidated"), lambda p:p.replace("Statement", "Restated Statement"), lambda p:p.replace("(Rs in Lakhs)", ""), lambda p:p.replace("As per our report of even date. Chartered Accountants", "")])
def test_pdf_context_unknown_rejected(change):
    source = change(PDF)
    assert all(r["review_status"] == "REJECTED" for r in pdf_facts([source], [source], IDENTITY, "fixture"))


def test_balance_snapshot_not_annual_flow():
    source = PDF.replace("Statement of Profit and Loss", "Balance Sheet").replace("Revenue from operations", "Total Assets")
    assert {r["period_type"] for r in pdf_facts([source], [source], IDENTITY, "fixture")} == {"INSTANT"}


def test_manual_loader_rejects_path_escape(tmp_path):
    (tmp_path / "manual_latest.json").write_text(json.dumps({"batch":"../outside", "report_sha256":"bad"}))
    with pytest.raises(ValueError, match="escapes"):
        load_current_reference(tmp_path)
