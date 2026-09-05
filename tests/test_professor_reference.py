from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from stock_ranker.professor_reference import (
    benchmark_professor_reference,
    export_professor_reference,
    extract_professor_reference,
)
from stock_ranker.research_website import professor_reference
from stock_ranker.web_assets import APP_JS, INDEX_HTML


MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE = "http://schemas.openxmlformats.org/package/2006/relationships"


def _cell(address: str, value: object, formula: str | None = None) -> str:
    if isinstance(value, str):
        return f'<c r="{address}" t="inlineStr"><is><t>{value}</t></is></c>'
    f = f"<f>{formula}</f>" if formula else ""
    return f'<c r="{address}">{f}<v>{value}</v></c>'


def _sheet(rows: dict[int, list[str]]) -> str:
    body = "".join(f'<row r="{row}">{"".join(cells)}</row>' for row, cells in rows.items())
    return f'<worksheet xmlns="{MAIN}"><sheetData>{body}</sheetData></worksheet>'


def _workbook(path: Path) -> None:
    sheets = {
        "NAV-Auto": _sheet({1: [_cell("H1", 46000)]}),  # 2025-12-09
        "Stock Picker": _sheet({
            2: [_cell("B2", "Alpha Limited"), _cell("C2", 200, 'GOOGLEFINANCE(N2,"price")'),
                _cell("F2", 200, "MAX(D2,F2)"), _cell("G2", 46000, "INDEX(...)"),
                _cell("H2", 0, "TODAY()-G2"), _cell("N2", "NSE:ALPHA"),
                _cell("V2", .1487), _cell("W2", .2599)],
            3: [_cell("B3", "Beta Limited"), _cell("C3", 120), _cell("F3", 150),
                _cell("G3", 45990), _cell("H3", 10), _cell("N3", "NSE:BETA"),
                _cell("V3", .0372), _cell("W3", .0627)],
            4: [_cell("B4", "BSE Only"), _cell("N4", "BOM:123456")],
        }),
        "CAGR": _sheet({
            3: [_cell("A3", "NSE:ALPHA"), _cell("H3", .25)],
            4: [_cell("A4", "NSE:BETA"), _cell("H4", .2)],
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
        for index, content in enumerate(sheets.values(), 1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", content)


def _history(path: Path, ticker: str, values: list[float]) -> None:
    dates = ["2020-12-09", "2022-12-09", "2024-12-09", "2025-12-09"]
    pd.DataFrame({"date": dates, "raw_close": values, "adjusted_close": values}).to_csv(
        path / f"{ticker}.csv", index=False
    )


def test_extracts_cached_cells_formulas_and_exact_identity_benchmark(tmp_path: Path) -> None:
    workbook = tmp_path / "reference.xlsx"
    _workbook(workbook)
    reference, metadata = extract_professor_reference(workbook)
    assert metadata["cached_as_of_date"] == "2025-12-09"
    assert metadata["stock_picker_rows"] == 3
    alpha = reference.loc[reference["reference_ticker"].eq("NSE:ALPHA")].iloc[0]
    assert alpha["price_cell"] == "Stock Picker!C2"
    assert alpha["price_formula"] == 'GOOGLEFINANCE(N2,"price")'
    assert alpha["reference_yoy_growth"] == .25

    market = pd.DataFrame([
        {"ticker": "ALPHA", "company": "Alpha Limited", "sector": "Sector A", "listing_date": "2020-01-01", "classification_status": "CLASSIFIED", "research_v2_score": 60, "research_v2_sector_rank": 1, "v2_eligible": True, "v2_reason_code": "ELIGIBLE"},
        {"ticker": "BETA", "company": "Beta Limited", "sector": "Sector A", "listing_date": "2020-01-01", "classification_status": "CLASSIFIED", "research_v2_score": 40, "research_v2_sector_rank": 2, "v2_eligible": True, "v2_reason_code": "ELIGIBLE"},
    ])
    market_path = tmp_path / "market.csv"
    market.to_csv(market_path, index=False)
    cache = tmp_path / "cache"; cache.mkdir()
    _history(cache, "ALPHA", [80, 100, 160, 200])
    _history(cache, "BETA", [100, 100, 100, 120])
    evaluation = {
        "primary_horizon_months": 12, "protocol_sha256": "protocol", "very_low_primary_sample_size": True,
        "horizons": {"12": {"rank_ic_observation_count": 3,
            "research_v2_rank_ic": {"mean": 0.0}, "matched_baseline_rank_ic": {"mean": -0.1},
            "pairwise": {"research_v2": {"pairwise_accuracy": .55}, "matched_baseline": {"pairwise_accuracy": .5}}}},
    }
    evaluation_path = tmp_path / "evaluation.json"
    evaluation_path.write_text(json.dumps(evaluation), encoding="utf-8")
    result = benchmark_professor_reference(
        workbook, live_market_path=market_path, history_cache=cache,
        evaluation_summary_path=evaluation_path,
    )
    assert result.audit["exact_identity_match_count"] == 2
    assert result.audit["reference_verdict"] == "PARTIAL MATCH"
    assert result.audit["research_v2_verdict"] == "INSUFFICIENT EVIDENCE"
    assert set(result.stock_comparison["identity_status"]) == {"MATCHED_EXACT_NSE", "BSE_ONLY_NO_SUBSTITUTION"}
    assert result.sector_summary.loc[0, "matched_stock_count"] == 2
    output = tmp_path / "output"
    manifest = export_professor_reference(result, output)
    assert manifest.is_file()
    assert json.loads(manifest.read_text())["benchmark_version"] == "professor_reference_benchmark_v1"


def test_reference_module_does_not_embed_company_specific_results() -> None:
    source = Path(__file__).parents[1].joinpath("src/stock_ranker/professor_reference.py").read_text(encoding="utf-8")
    for forbidden in ("RELIANCE", "BAJFINANCE", "COFORGE", "TITAN"):
        assert forbidden not in source
    assert "fuzzy" not in source.lower()


def test_prepared_reference_is_visible_with_scientific_boundaries() -> None:
    data = professor_reference("Information Technology")
    assert data["available"] is True
    assert data["audit"]["reference_verdict"] == "PARTIAL MATCH"
    assert data["audit"]["research_v2_verdict"] == "INSUFFICIENT EVIDENCE"
    assert data["audit"]["exact_identity_match_count"] == 33
    assert data["audit"]["worksheet_count"] == 23
    assert data["audit"]["stock_picker_rank_formula_cells"] == 0
    assert data["rows"]
    assert all(row["sector"] == "Information Technology" for row in data["rows"])
    assert "no sector rank" in data["warning"].lower()
    rendered = INDEX_HTML + APP_JS
    assert "Professor Reference → Baseline V1 → Research V2" in rendered
    assert "loadProfessorReference" in APP_JS
