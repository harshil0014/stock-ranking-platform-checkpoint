"""Independent roundtrip audit of the current-only professor fallback overlay."""

from __future__ import annotations

import hashlib
import json
import csv
import gzip
import math
import re
from pathlib import Path

import openpyxl
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments/professor-current-fallback-20261003"
ACCEPTED = ROOT / "data/company_facts"
WORKBOOK = Path(r"C:\Users\Harshil\Downloads\_Organized\Documents\Copy of OK Strategy - Master Sheet v4.3 (1).xlsx")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def equal_or_missing(a: pd.Series, b: pd.Series) -> bool:
    left, right = a.astype("string"), b.astype("string")
    return bool(((left == right) | (left.isna() & right.isna())).fillna(False).all())


def main() -> None:
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    state_path = ACCEPTED / "accepted_state.json"
    assert sha(state_path) == summary["accepted_state_sha256"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    source_path = ACCEPTED / state["snapshot_path"] / "company_facts.csv"
    assert sha(source_path) == summary["accepted_company_facts_sha256"]
    original = pd.read_csv(source_path, low_memory=False).set_index("isin")
    overlay = pd.read_csv(OUT / "current_company_facts_professor_overlay.csv.gz", low_memory=False).set_index("isin")
    assert original.index.is_unique and overlay.index.is_unique
    fills = pd.read_csv(OUT / "filled_cells.csv")
    counts = pd.read_csv(OUT / "coverage_before_after.csv")
    assert original.index.equals(overlay.index)
    assert len(original) == len(overlay) == summary["company_rows"]
    allowed = set(counts["field"])
    unchanged_columns = []
    for column in original:
        old, new = original[column], overlay[column]
        if column not in allowed:
            assert equal_or_missing(old, new), column
            unchanged_columns.append(column)
        else:
            mask = old.notna() & old.astype("string").str.strip().ne("")
            assert equal_or_missing(old[mask], new[mask]), column
    changed = set()
    for x in fills.itertuples(index=False):
        assert x.provenance == "PROFESSOR_EXCEL" and x.current_only
        assert x.field in allowed
        assert x.field not in original or pd.isna(original.at[x.isin, x.field]) or str(original.at[x.isin, x.field]).strip() == ""
        actual = overlay.at[x.isin, x.field]
        if x.field in {"professor_industry", "professor_workbook_ath_date"}:
            assert str(actual) == str(x.value), (x.isin, x.field)
        else:
            assert math.isclose(float(actual), float(x.value), rel_tol=0, abs_tol=1e-12), (x.isin, x.field)
        assert overlay.at[x.isin, "professor_excel_source"] == "PROFESSOR_EXCEL"
        assert x.field in overlay.at[x.isin, "professor_excel_filled_fields"].split(";")
        changed.add((x.isin, x.field))
    assert len(changed) == len(fills) == summary["filled_cells"]
    assert sha(WORKBOOK) == summary["source_workbook_sha256"]
    cells: dict[str, set[tuple[int, int]]] = {"CAGR": set(), "ATH": set()}
    for x in fills.itertuples(index=False):
        for address in str(x.source_cells).split(";"):
            match = re.fullmatch(r"([A-Z]+)(\d+)", address)
            assert match, address
            cells[x.source_sheet].add((int(match.group(2)), openpyxl.utils.column_index_from_string(match.group(1))))
    workbook = openpyxl.load_workbook(WORKBOOK, read_only=True, data_only=True)
    source_values = {}
    for sheet, wanted in cells.items():
        max_row = max(r for r, _ in wanted)
        max_col = max(c for _, c in wanted)
        for rownum, row in enumerate(workbook[sheet].iter_rows(min_row=1, max_row=max_row, max_col=max_col, values_only=True), 1):
            for colnum in range(1, max_col + 1):
                if (rownum, colnum) in wanted:
                    source_values[(sheet, rownum, colnum)] = row[colnum - 1]
    workbook.close()
    for x in fills.itertuples(index=False):
        for address in str(x.source_cells).split(";"):
            match = re.fullmatch(r"([A-Z]+)(\d+)", address)
            assert match
            value = source_values[(x.source_sheet, int(match.group(2)), openpyxl.utils.column_index_from_string(match.group(1)))]
            if x.field == "professor_industry":
                assert str(value).strip() == str(x.value)
            elif x.field == "professor_workbook_ath_date":
                assert pd.Timestamp(value).date().isoformat() == str(x.value)
            else:
                assert math.isclose(float(value), float(x.value), rel_tol=0, abs_tol=1e-12)
    for row in counts.itertuples(index=False):
        assert int(row.missing_before) - int(row.missing_after) == int(row.filled)
        old = original[row.field] if row.field in original else pd.Series(pd.NA, index=original.index)
        new = overlay[row.field]
        old_missing = old.isna() | old.astype("string").str.strip().eq("").fillna(False)
        new_missing = new.isna() | new.astype("string").str.strip().eq("").fillna(False)
        assert int(old_missing.sum()) == row.missing_before
        assert int(new_missing.sum()) == row.missing_after
        actual_changes = set(zip(new.index[old_missing & ~new_missing], [row.field] * int((old_missing & ~new_missing).sum())))
        assert actual_changes == {k for k in changed if k[1] == row.field}
    assert int((overlay["professor_excel_source"] == "PROFESSOR_EXCEL").sum()) == summary["stocks_with_fills"]
    # Independently compare the original raw CSV text of every protected cell.
    fill_keys = set(changed)
    with source_path.open("r", encoding="utf-8", newline="") as source, gzip.open(
        OUT / "current_company_facts_professor_overlay.csv.gz", "rt", encoding="utf-8", newline=""
    ) as enriched:
        old_reader, new_reader = csv.DictReader(source), csv.DictReader(enriched)
        assert set(old_reader.fieldnames or []).issubset(set(new_reader.fieldnames or []))
        for old_row, new_row in zip(old_reader, new_reader, strict=True):
            assert old_row["isin"] == new_row["isin"]
            for column in old_reader.fieldnames or []:
                if (old_row["isin"], column) not in fill_keys:
                    assert old_row[column] == new_row[column], (old_row["isin"], column)
    audit = {
        "schema": "professor_current_fallback_roundtrip_audit_v1",
        "status": "PASS",
        "original_company_rows": len(original),
        "original_columns_semantically_unchanged": len(unchanged_columns),
        "existing_nonmissing_values_preserved": True,
        "changed_cells_exactly_equal_fill_ledger": len(changed),
        "workbook_cells_verified": sum(len(str(x).split(";")) for x in fills["source_cells"]),
        "matched_stocks_with_fills": summary["stocks_with_fills"],
        "accepted_state_sha256": sha(state_path),
        "accepted_company_facts_sha256": sha(source_path),
        "overlay_sha256": sha(OUT / "current_company_facts_professor_overlay.csv.gz"),
        "historical_panels_touched": False,
    }
    (OUT / "roundtrip_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
