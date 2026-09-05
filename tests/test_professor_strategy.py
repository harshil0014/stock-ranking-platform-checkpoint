from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import pytest

from stock_ranker.professor_strategy import (
    benchmark_professor_strategy,
    export_professor_strategy,
    extract_ok_strategy_workbook,
)
from stock_ranker.web_assets import APP_JS, INDEX_HTML


MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE = "http://schemas.openxmlformats.org/package/2006/relationships"


def _cell(address: str, value: object, formula: str | None = None) -> str:
    if isinstance(value, str):
        return f'<c r="{address}" t="inlineStr"><is><t>{value}</t></is></c>'
    inner = f"<f>{formula}</f>" if formula else ""
    return f'<c r="{address}">{inner}<v>{value}</v></c>'


def _sheet(rows: dict[int, list[str]]) -> str:
    body = "".join(f'<row r="{row}">{"".join(cells)}</row>' for row, cells in rows.items())
    return f'<worksheet xmlns="{MAIN}"><sheetData>{body}</sheetData></worksheet>'


def _workbook(path: Path) -> None:
    sheets = {
        "Instructions": _sheet({1: [_cell("L1", 46200)]}),
        "SIP Portfolio": _sheet({
            1: [_cell("B1", 7500)], 2: [_cell("B2", 36)], 3: [_cell("B3", 30)],
            7: [_cell("B7", "NSE:ALPHA"), _cell("C7", "Alpha"), _cell("I7", 2.0),
                _cell("J7", .3), _cell("K7", .2), _cell("L7", .1), _cell("N7", 1, "rank(I7,$I$7:$I$20)")],
            8: [_cell("B8", "BOM:123456"), _cell("C8", "Beta"), _cell("I8", 1.0),
                _cell("J8", .2), _cell("K8", .1), _cell("L8", .05), _cell("N8", 2, "rank(I8,$I$7:$I$20)")],
        }),
        "CAGR": _sheet({
            3: [_cell("A3", "NSE:ALPHA"), _cell("B3", "Alpha"), _cell("H3", "Industrial Products")],
            4: [_cell("A4", "NSE:ALPHA"), _cell("B4", "Alpha"), _cell("H4", "Industrial Products")],
        }),
    }
    workbook_sheets = "".join(
        f'<sheet name="{name}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheets, 1)
    )
    rels = "".join(
        f'<Relationship Id="rId{index}" Type="{OFFICE}/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, len(sheets) + 1)
    )
    with ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", f'<workbook xmlns="{MAIN}" xmlns:r="{OFFICE}"><sheets>{workbook_sheets}</sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", f'<Relationships xmlns="{PACKAGE}">{rels}</Relationships>')
        for index, value in enumerate(sheets.values(), 1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", value)


def _acceptance() -> pd.DataFrame:
    return pd.DataFrame([
        {"requested_code": "NSE:ALPHA", "reference_rank": 2, "canonical_company": "Alpha",
         "research_v2_eligible": False, "baseline_sector_rank": 1},
        {"requested_code": "BOM:123456", "reference_rank": 1, "canonical_company": "Beta",
         "research_v2_eligible": False, "baseline_sector_rank": None},
    ])


def test_extracts_only_explicit_rank_and_preserves_duplicate_cell_provenance(tmp_path: Path) -> None:
    workbook = tmp_path / "strategy.xlsx"; _workbook(workbook)
    sip, cagr, audit = extract_ok_strategy_workbook(workbook)
    assert sip["workbook_sip_rank"].tolist() == [1.0, 2.0]
    assert audit["sip_rank_formulas_exact"] is True
    assert audit["sip_cached_ranks_recalculate_exactly"] is True
    assert audit["rank_formula_count"] == 2
    assert cagr.iloc[0]["cagr_cells"] == "CAGR!A3:I3;CAGR!A4:I4"


def test_benchmark_reports_partial_match_and_exact_code_screener_evidence(tmp_path: Path) -> None:
    workbook = tmp_path / "strategy.xlsx"; _workbook(workbook)
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"universe": ["NSE:ALPHA", "BOM:123456"],
        "reference_ranking": [{"rank": 1, "code": "BOM:123456"}, {"rank": 2, "code": "NSE:ALPHA"}]}), encoding="utf-8")
    acceptance = tmp_path / "acceptance.csv"; _acceptance().to_csv(acceptance, index=False)
    screener = tmp_path / "screener.csv"
    pd.DataFrame([{"Name": "Alpha", "NSE Code": "ALPHA", "BSE Code": None,
                   "Industry": "Plastic Products"}]).to_csv(screener, index=False)
    result = benchmark_professor_strategy(
        workbook, request_path=request, acceptance_csv=acceptance,
        screener_export_path=screener, screener_source_date=date(2026, 8, 21),
    )
    assert result.audit["reference_verdict"] == "PARTIAL MATCH"
    assert result.audit["research_v2_verdict"] == "INSUFFICIENT EVIDENCE"
    alpha = result.securities.set_index("requested_code").loc["NSE:ALPHA"]
    assert alpha["screener_industry"] == "Plastic Products"
    assert alpha["workbook_industry"] == "Industrial Products"
    manifest = export_professor_strategy(result, tmp_path / "output")
    assert json.loads(manifest.read_text(encoding="utf-8"))["strategy_fingerprint"]


def test_screener_export_never_uses_name_matching_or_missing_source_date(tmp_path: Path) -> None:
    workbook = tmp_path / "strategy.xlsx"; _workbook(workbook)
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"universe": ["NSE:ALPHA", "BOM:123456"],
        "reference_ranking": [{"rank": 1, "code": "BOM:123456"}, {"rank": 2, "code": "NSE:ALPHA"}]}), encoding="utf-8")
    acceptance = tmp_path / "acceptance.csv"; _acceptance().to_csv(acceptance, index=False)
    screener = tmp_path / "screener.csv"
    pd.DataFrame([{"Name": "Alpha", "Industry": "Plastic Products"}]).to_csv(screener, index=False)
    with pytest.raises(ValueError, match="source date"):
        benchmark_professor_strategy(workbook, request_path=request, acceptance_csv=acceptance,
                                     screener_export_path=screener)


def test_professor_ui_preserves_four_layer_evidence_and_negative_results() -> None:
    assert "Professor Reference → Workbook SIP → Baseline V1 → Research V2" in INDEX_HTML
    assert "Workbook SIP rank" in APP_JS
    assert "No validated Screener export" in APP_JS
    assert "never silently replace the canonical sector" in APP_JS
