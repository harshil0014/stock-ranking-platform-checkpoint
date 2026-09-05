from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import pytest

from stock_ranker.screener_historical_fundamentals import (
    SCREENER_HISTORICAL_CONTRACT_VERSION,
    build_screener_pit_cohorts,
    calibrate_screener_against_gold,
    official_clock_from_availability,
    parse_screener_historical_workbook,
)
from stock_ranker.screener_manual_batch import ingest_screener_manual_batch


ROOT = Path(__file__).resolve().parents[1]


def _serial(year: int) -> int:
    return (datetime(year, 3, 31) - datetime(1899, 12, 30)).days


def _cell(ref: str, value: object = None, *, formula: str | None = None) -> str:
    if isinstance(value, str):
        payload = f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is>'
    elif value is None:
        payload = f'<c r="{ref}">'
    else:
        payload = f'<c r="{ref}"><v>{value}</v>'
    if formula is not None:
        payload += f"<f>{formula.replace('&', '&amp;')}</f>"
    return payload + "</c>"


def _workbook(
    path: Path, *, company: str = "ALPHA LTD", bad_formula: bool = False,
    blank_cells: set[str] | None = None,
) -> str:
    columns = "BCDEFGHIJK"
    data_cells = [_cell("B1", company), _cell("B2", 2.1), _cell("B3", 2.1)]
    for index, column in enumerate(columns):
        year = 2017 + index
        values = {
            16: _serial(year), 27: 1 + index, 28: 10 + index, 30: 8 + index,
            56: _serial(year), 57: 10, 58: 90 + index, 59: 10 + index,
        }
        for row, value in values.items():
            ref = f"{column}{row}"
            data_cells.append(_cell(ref, None if ref in (blank_cells or set()) else value))
    balance_cells = []
    for index in range(1, len(columns)):
        current, previous = columns[index], columns[index - 1]
        denominator = f"{previous}4+{previous}5+{previous}6+{current}4+{current}5+{current}6"
        formula = (
            f"IF(({denominator})>0,('Profit & Loss'!{current}10+"
            f"'Profit & Loss'!{current}9)*2/({denominator}),\"\")"
        )
        if bad_formula and current == "C":
            formula = "1+1"
        balance_cells.append(_cell(f"{current}24", formula=formula))
    sheet = lambda cells: (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData><row>{''.join(cells)}</row></sheetData></worksheet>"
    )
    with ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Data Sheet" sheetId="1" r:id="rId1"/>'
            '<sheet name="Balance Sheet" sheetId="2" r:id="rId2"/></sheets></workbook>'
        ))
        archive.writestr("xl/_rels/workbook.xml.rels", (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="x" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="x" Target="worksheets/sheet2.xml"/></Relationships>'
        ))
        archive.writestr("xl/worksheets/sheet1.xml", sheet(data_cells))
        archive.writestr("xl/worksheets/sheet2.xml", sheet(balance_cells))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(path: Path, workbook_hash: str, **changes: object) -> dict[str, object]:
    row = {
        "ticker": "ALPHA", "isin": "INE000A01001", "company": "Alpha Limited",
        "workbook_company": "ALPHA LTD", "workbook_sha256": workbook_hash,
        "reporting_basis": "STANDALONE", "source_observed_at": "2026-08-31T12:00:00+05:30",
        "basis_attestation": "explicit standalone export",
    }
    row.update(changes)
    return row


def test_standard_workbook_is_parsed_without_an_excel_runtime(tmp_path: Path) -> None:
    path = tmp_path / "alpha.xlsx"
    workbook_hash = _workbook(path)
    result = parse_screener_historical_workbook(path, _manifest(path, workbook_hash))
    assert len(result) == 9
    latest = result.iloc[-1]
    assert latest["period_end"] == "2026-03-31"
    assert latest["current_pat"] == 17
    assert latest["prior_pat"] == 16
    assert latest["debt_to_equity"] == pytest.approx(19 / 109)
    assert latest["roce"] == pytest.approx((19 + 10) * 2 / ((10 + 98 + 18) + (10 + 99 + 19)))
    assert latest["contract_version"] == SCREENER_HISTORICAL_CONTRACT_VERSION


def test_blank_incomplete_year_is_skipped_without_losing_complete_years(tmp_path: Path) -> None:
    path = tmp_path / "alpha-with-one-incomplete-year.xlsx"
    workbook_hash = _workbook(path, blank_cells={"F30"})
    result = parse_screener_historical_workbook(path, _manifest(path, workbook_hash))
    assert len(result) == 7
    assert "2021-03-31" not in set(result["period_end"])
    assert "2022-03-31" not in set(result["period_end"])
    assert result.iloc[-1]["period_end"] == "2026-03-31"


def test_workbook_requires_hash_identity_basis_and_unchanged_screener_formula(tmp_path: Path) -> None:
    path = tmp_path / "alpha.xlsx"
    workbook_hash = _workbook(path)
    with pytest.raises(ValueError, match="hash mismatch"):
        parse_screener_historical_workbook(path, _manifest(path, "0" * 64))
    with pytest.raises(ValueError, match="STANDALONE"):
        parse_screener_historical_workbook(path, _manifest(path, workbook_hash, reporting_basis="CONSOLIDATED"))
    with pytest.raises(ValueError, match="company mismatch"):
        parse_screener_historical_workbook(path, _manifest(path, workbook_hash, workbook_company="BETA LTD"))
    bad = tmp_path / "bad.xlsx"
    bad_hash = _workbook(bad, bad_formula=True)
    with pytest.raises(ValueError, match="unexpected Screener ROCE formula"):
        parse_screener_historical_workbook(bad, _manifest(bad, bad_hash))


def test_official_clock_is_exact_and_selects_latest_available_period() -> None:
    availability = pd.DataFrame([
        {"isin":"INE000A01001","financial_year":"2023-2024","pit_available":True,
         "dissemination_timestamp":"2024-06-30T10:00:00+05:30","source_url":"https://nse.example/fy24.pdf",
         "availability_status":"EXPLICIT_NSE_TIMESTAMP_AVAILABLE"},
        {"isin":"INE000A01001","financial_year":"2024-2025","pit_available":True,
         "dissemination_timestamp":"2025-08-08T10:00:00+05:30","source_url":"https://nse.example/fy25.pdf",
         "availability_status":"EXPLICIT_NSE_TIMESTAMP_AVAILABLE"},
    ])
    clock = official_clock_from_availability(availability)
    normalized = pd.DataFrame([
        {"ticker":"ALPHA","company":"Alpha","isin":"INE000A01001","period_end":"2024-03-31",
         "prior_period_end":"2023-03-31","reporting_basis":"STANDALONE","roce":.2,"debt_to_equity":.1,
         "current_pat":120,"prior_pat":100,"source_observed_at":"2026-08-31T00:00:00Z"},
        {"ticker":"ALPHA","company":"Alpha","isin":"INE000A01001","period_end":"2025-03-31",
         "prior_period_end":"2024-03-31","reporting_basis":"STANDALONE","roce":.3,"debt_to_equity":.2,
         "current_pat":130,"prior_pat":120,"source_observed_at":"2026-08-31T00:00:00Z"},
    ])
    result = build_screener_pit_cohorts(normalized, clock, [date(2024, 8, 7), date(2025, 8, 7), date(2025, 8, 9)])
    assert result.accepted[["ranking_date", "period_end"]].astype(str).values.tolist() == [
        ["2024-08-07", "2024-03-31 00:00:00+00:00"],
        ["2025-08-07", "2024-03-31 00:00:00+00:00"],
        ["2025-08-09", "2025-03-31 00:00:00+00:00"],
    ]


def test_ranking_date_filing_must_be_public_by_market_close_cutoff() -> None:
    normalized = pd.DataFrame([{
        "ticker":"ALPHA", "company":"Alpha", "isin":"INE000A01001",
        "period_end":"2025-03-31", "prior_period_end":"2024-03-31",
        "reporting_basis":"STANDALONE", "roce":.2, "debt_to_equity":.1,
        "current_pat":10, "prior_pat":5,
        "source_observed_at":"2026-01-01T00:00:00Z",
    }])
    base_clock = {
        "isin":"INE000A01001", "period_end":"2025-03-31", "filing_id":"one",
        "official_filing_url":"https://nse.example/one", "availability_status":"EXPLICIT",
    }
    before_close = build_screener_pit_cohorts(
        normalized,
        pd.DataFrame([{**base_clock, "official_available_at":"2025-08-07T09:59:59Z"}]),
        [date(2025, 8, 7)],
    )
    after_close = build_screener_pit_cohorts(
        normalized,
        pd.DataFrame([{**base_clock, "official_available_at":"2025-08-07T10:00:01Z"}]),
        [date(2025, 8, 7)],
    )
    assert before_close.accepted["ticker"].tolist() == ["ALPHA"]
    assert after_close.accepted.empty
    assert after_close.rejected.iloc[0]["period_status"] == "OFFICIAL_FILING_AFTER_RANKING_DATE"


def test_negative_leverage_and_zero_prior_profit_remain_ineligible() -> None:
    clock = pd.DataFrame([{
        "isin":"INE000A01001", "period_end":"2025-03-31",
        "official_available_at":"2025-06-01T00:00:00Z", "filing_id":"one",
        "official_filing_url":"https://nse.example/one", "availability_status":"EXPLICIT",
    }])
    row = {"ticker":"ALPHA","company":"Alpha","isin":"INE000A01001","period_end":"2025-03-31",
           "prior_period_end":"2024-03-31","reporting_basis":"STANDALONE","roce":.2,
           "debt_to_equity":-0.1,"current_pat":10,"prior_pat":5,"source_observed_at":"2026-01-01T00:00:00Z"}
    result = build_screener_pit_cohorts(pd.DataFrame([row]), clock, [date(2025, 8, 7)])
    assert result.accepted.empty
    assert "NEGATIVE_DEBT_TO_EQUITY" in result.rejected["period_status"].tolist()
    result = build_screener_pit_cohorts(pd.DataFrame([{**row, "debt_to_equity":.1, "prior_pat":0}]), clock, [date(2025, 8, 7)])
    assert "ZERO_PRIOR_PAT" in result.rejected["period_status"].tolist()


def test_latest_invalid_period_does_not_fall_back_to_older_fundamentals() -> None:
    clock = pd.DataFrame([
        {"isin":"INE000A01001", "period_end":"2024-03-31",
         "official_available_at":"2024-06-01T00:00:00Z", "filing_id":"old",
         "official_filing_url":"https://nse.example/old", "availability_status":"EXPLICIT"},
        {"isin":"INE000A01001", "period_end":"2025-03-31",
         "official_available_at":"2025-06-01T00:00:00Z", "filing_id":"new",
         "official_filing_url":"https://nse.example/new", "availability_status":"EXPLICIT"},
    ])
    base = {"ticker":"ALPHA", "company":"Alpha", "isin":"INE000A01001",
            "reporting_basis":"STANDALONE", "roce":.2, "current_pat":10,
            "prior_pat":5, "source_observed_at":"2026-01-01T00:00:00Z"}
    rows = pd.DataFrame([
        {**base, "period_end":"2024-03-31", "prior_period_end":"2023-03-31", "debt_to_equity":.1},
        {**base, "period_end":"2025-03-31", "prior_period_end":"2024-03-31", "debt_to_equity":-.1},
    ])
    result = build_screener_pit_cohorts(rows, clock, [date(2025, 8, 7)])
    assert result.accepted.empty
    latest = result.rejected.loc[result.rejected["period_end"].astype(str).str[:10].eq("2025-03-31")]
    assert latest.iloc[0]["period_status"] == "NEGATIVE_DEBT_TO_EQUITY"


def test_exact_workbook_rows_remain_eligible_when_combined_with_precision_rows() -> None:
    clock = pd.DataFrame([{
        "isin":"INE000A01001", "period_end":"2025-03-31",
        "official_available_at":"2025-06-01T00:00:00Z", "filing_id":"one",
        "official_filing_url":"https://nse.example/one", "availability_status":"EXPLICIT",
    }])
    workbook = {
        "ticker":"ALPHA", "company":"Alpha", "isin":"INE000A01001",
        "period_end":"2025-03-31", "prior_period_end":"2024-03-31",
        "reporting_basis":"STANDALONE", "roce":.2, "debt_to_equity":.1,
        "current_pat":10, "prior_pat":5, "source_observed_at":"2026-01-01T00:00:00Z",
        "source_value_method":"screener_standard_workbook_v2_1",
    }
    other = {**workbook, "ticker":"BETA", "isin":"INE000A01002", "source_precision_status":"PASS"}
    combined = pd.DataFrame([workbook, other])
    result = build_screener_pit_cohorts(combined, clock, [date(2025, 8, 7)])
    assert result.accepted["ticker"].tolist() == ["ALPHA"]


def test_mixed_march_and_december_annual_periods_parse_deterministically() -> None:
    rows = []
    clocks = []
    for ticker, isin, period_end in (
        ("MARCH", "INE000A01001", "2024-03-31"),
        ("DEC", "INE000A01002", "2023-12-31"),
    ):
        rows.append({
            "ticker": ticker, "company": ticker, "isin": isin,
            "period_end": period_end, "prior_period_end": "2023-03-31",
            "reporting_basis": "STANDALONE", "roce": .2, "debt_to_equity": .1,
            "current_pat": 10, "prior_pat": 5,
            "source_observed_at": "2026-09-01T12:42:23+00:00",
        })
        clocks.append({
            "isin": isin, "period_end": period_end,
            "official_available_at": "2024-06-01T00:00:00+00:00",
            "filing_id": ticker, "official_filing_url": f"https://nse.example/{ticker}",
            "availability_status": "EXPLICIT",
        })
    result = build_screener_pit_cohorts(
        pd.DataFrame(rows), pd.DataFrame(clocks), [date(2024, 8, 7)]
    )
    assert result.accepted["ticker"].tolist() == ["MARCH", "DEC"]


def test_calibration_requires_exact_identity_and_pat_but_not_statutory_ratio_equality() -> None:
    normalized = pd.DataFrame([{
        "ticker":"ALPHA","isin":"INE000A01001","period_end":"2026-03-31",
        "current_pat":12.35,"prior_pat":10.11,"roce":.2,"debt_to_equity":.3,
    }])
    gold = [{
        "ticker":"ALPHA","isin":"INE000A01001","profit":{"current_value":123.49,"prior_value":101.08,"unit":"INR million"},
        "roce":{"canonical_decimal":.15},"debt_to_equity":{"canonical_decimal":.25},
    }]
    detail, summary = calibrate_screener_against_gold(normalized, gold)
    assert summary["calibration_status"] == "PASS"
    assert detail.loc[0, "roce_method_delta"] == pytest.approx(.05)
    assert detail.loc[0, "debt_to_equity_method_delta"] == pytest.approx(.05)


def test_calibration_manifest_has_14_unique_exact_isins_and_hashes() -> None:
    manifest = json.loads((ROOT / "marketdata/specifications/screener_historical_calibration_14_v1.json").read_text(encoding="utf-8"))
    assert manifest["contract_version"] == SCREENER_HISTORICAL_CONTRACT_VERSION
    assert len(manifest["records"]) == 14
    assert len({row["isin"] for row in manifest["records"]}) == 14
    assert all(len(row["workbook_sha256"]) == 64 for row in manifest["records"])
    assert all(row["reporting_basis"] == "STANDALONE" for row in manifest["records"])


def _manual_batch_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    checklist = pd.DataFrame([{
        "priority": "1", "ticker": "ALPHA", "company_name": "Alpha",
        "ISIN": "INE000A01001", "screener_url": "https://www.screener.in/company/ALPHA/",
        "historical_dates_helped": "2025-08-07", "downloaded": "",
    }])
    identity = pd.DataFrame([{
        "ticker": "ALPHA", "isin": "INE000A01001", "company": "Alpha Limited",
    }])
    queue = pd.DataFrame([{
        "ticker": "ALPHA", "isin": "INE000A01001", "ranking_date": "2025-08-07",
    }])
    clock = pd.DataFrame([{
        "isin": "INE000A01001", "period_end": "2025-03-31",
        "official_available_at": "2025-06-01T00:00:00Z", "filing_id": "one",
        "official_filing_url": "https://nse.example/one", "availability_status": "EXPLICIT",
    }])
    return checklist, identity, queue, clock


def test_manual_batch_exact_identity_is_parsed_and_hash_pinned(tmp_path: Path) -> None:
    workbook = tmp_path / "alpha-source.xlsx"
    _workbook(workbook)
    archive = tmp_path / "batch.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.write(workbook, "batch/Alpha.xlsx")
    checklist, identity, queue, clock = _manual_batch_inputs()
    result = ingest_screener_manual_batch(
        archive_path=archive, checklist=checklist, identity_master=identity,
        acquisition_queue=queue, official_clock=clock,
        source_directory=tmp_path / "cache", source_observed_at="2026-09-01T12:42:23Z",
        ranking_dates=[date(2025, 8, 7)], expected_count=1,
    )
    assert result.file_audit.loc[0, "file_status"] == "ACCEPTED", result.file_audit.loc[0, "reason"]
    assert len(result.normalized) == 9
    assert result.manifest_records[0]["isin"] == "INE000A01001"
    assert list((tmp_path / "cache" / "accepted").glob("*.xlsx"))
    assert not list((tmp_path / "cache" / "quarantine").glob("*.xlsx"))


def test_manual_batch_quarantines_wrong_company_without_forcing_identity(tmp_path: Path) -> None:
    workbook = tmp_path / "wrong.xlsx"
    _workbook(workbook, company="BETA LTD")
    archive = tmp_path / "batch.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.write(workbook, "batch/Alpha.xlsx")
    checklist, identity, queue, clock = _manual_batch_inputs()
    result = ingest_screener_manual_batch(
        archive_path=archive, checklist=checklist, identity_master=identity,
        acquisition_queue=queue, official_clock=clock,
        source_directory=tmp_path / "cache", source_observed_at="2026-09-01T12:42:23Z",
        ranking_dates=[date(2025, 8, 7)], expected_count=1,
    )
    assert result.file_audit.loc[0, "file_status"] == "QUARANTINED"
    assert "identity master" in result.file_audit.loc[0, "reason"]
    assert result.normalized.empty
    assert list((tmp_path / "cache" / "quarantine").glob("*.xlsx"))


def test_manual_batch_accepts_an_explicit_later_checklist_range(tmp_path: Path) -> None:
    workbook = tmp_path / "alpha-source.xlsx"
    _workbook(workbook)
    archive = tmp_path / "batch.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.write(workbook, "batch/Alpha.xlsx")
    checklist, identity, queue, clock = _manual_batch_inputs()
    checklist["priority"] = "51"
    result = ingest_screener_manual_batch(
        archive_path=archive, checklist=checklist, identity_master=identity,
        acquisition_queue=queue, official_clock=clock,
        source_directory=tmp_path / "cache", source_observed_at="2026-09-01T13:52:22Z",
        ranking_dates=[date(2025, 8, 7)], expected_count=1, priority_start=51,
    )
    assert result.file_audit.loc[0, "priority"] == 51
    assert result.file_audit.loc[0, "file_status"] == "ACCEPTED"


def test_manual_batch_accepts_exact_screener_name_prefix_with_exact_isin(tmp_path: Path) -> None:
    workbook = tmp_path / "jk-source.xlsx"
    _workbook(workbook, company="J K CEMENTS LTD")
    archive = tmp_path / "batch.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.write(workbook, "batch/J K Cements.xlsx")
    checklist, identity, queue, clock = _manual_batch_inputs()
    checklist.loc[0, ["ticker", "company_name", "ISIN"]] = [
        "JKCEMENT", "J K Cements", "INE823G01014",
    ]
    checklist.loc[0, "screener_url"] = "https://www.screener.in/company/JKCEMENT/"
    identity.loc[0, ["ticker", "isin", "company"]] = [
        "JKCEMENT", "INE823G01014", "JK Cement Limited",
    ]
    queue.loc[0, ["ticker", "isin"]] = ["JKCEMENT", "INE823G01014"]
    clock.loc[0, "isin"] = "INE823G01014"
    result = ingest_screener_manual_batch(
        archive_path=archive, checklist=checklist, identity_master=identity,
        acquisition_queue=queue, official_clock=clock,
        source_directory=tmp_path / "cache", source_observed_at="2026-09-01T14:15:02Z",
        ranking_dates=[date(2025, 8, 7)], expected_count=1,
    )
    assert result.file_audit.loc[0, "file_status"] == "ACCEPTED"
    assert result.file_audit.loc[0, "identity_validation_method"] == (
        "EXACT_SCREENER_REFERENCE_PREFIX_WITH_EXACT_TICKER_ISIN"
    )


def test_manual_batch_rejects_a_nonstandalone_checklist_url(tmp_path: Path) -> None:
    checklist, identity, queue, clock = _manual_batch_inputs()
    checklist.loc[0, "screener_url"] = "https://www.screener.in/company/ALPHA/consolidated/"
    archive = tmp_path / "batch.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("batch/Alpha.xlsx", b"not reached")
    with pytest.raises(ValueError, match="exact standalone ticker path"):
        ingest_screener_manual_batch(
            archive_path=archive, checklist=checklist, identity_master=identity,
            acquisition_queue=queue, official_clock=clock,
            source_directory=tmp_path / "cache", source_observed_at="2026-09-01T14:15:02Z",
            ranking_dates=[date(2025, 8, 7)], expected_count=1,
        )


def test_manual_batch_normalizes_standard_corporation_abbreviation(tmp_path: Path) -> None:
    workbook = tmp_path / "ongc-source.xlsx"
    _workbook(workbook, company="OIL AND NATURAL GAS CORPN LTD")
    archive = tmp_path / "batch.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.write(workbook, "batch/O N G C.xlsx")
    checklist, identity, queue, clock = _manual_batch_inputs()
    checklist.loc[0, ["ticker", "company_name", "ISIN", "screener_url"]] = [
        "ONGC", "O N G C", "INE213A01029", "https://www.screener.in/company/ONGC/",
    ]
    identity.loc[0, ["ticker", "isin", "company"]] = [
        "ONGC", "INE213A01029", "Oil & Natural Gas Corporation Limited",
    ]
    queue.loc[0, ["ticker", "isin"]] = ["ONGC", "INE213A01029"]
    clock.loc[0, "isin"] = "INE213A01029"
    result = ingest_screener_manual_batch(
        archive_path=archive, checklist=checklist, identity_master=identity,
        acquisition_queue=queue, official_clock=clock,
        source_directory=tmp_path / "cache", source_observed_at="2026-09-01T14:41:31Z",
        ranking_dates=[date(2025, 8, 7)], expected_count=1,
    )
    assert result.file_audit.loc[0, "file_status"] == "ACCEPTED", result.file_audit.loc[0, "reason"]
    assert result.file_audit.loc[0, "identity_validation_method"] == (
        "LEGAL_NAME_EXACT_NORMALIZATION"
    )
