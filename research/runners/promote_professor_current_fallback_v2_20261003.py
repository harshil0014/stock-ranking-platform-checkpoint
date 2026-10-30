"""Fill blank current growth fields from the trusted professor overlay.

This creates an isolated, equal-priority current-data candidate. It does not
change accepted snapshots, historical rows, scores, model weights, or the site.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "experiments/professor-current-fallback-20261003"
OUT = BASE / "equal-priority-v2"
SOURCE_OVERLAY = BASE / "current_company_facts_professor_overlay.csv.gz"
SOURCE_LEDGER = BASE / "filled_cells.csv"
MAPPING = {
    "product_baseline_yoy_growth": "professor_workbook_cagr_1y",
    "product_baseline_cagr_3y": "professor_workbook_cagr_3y",
    "product_baseline_cagr_5y": "professor_workbook_cagr_5y",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    v1 = json.loads((BASE / "summary.json").read_text(encoding="utf-8"))
    source_sha, ledger_sha = sha(SOURCE_OVERLAY), sha(SOURCE_LEDGER)
    ledger = pd.read_csv(SOURCE_LEDGER)
    by_key = {(str(r.isin), str(r.field)): r for r in ledger.itertuples(index=False)}
    assert len(by_key) == len(ledger)
    fills = []
    output_path = OUT / "current_company_facts_equal_priority.csv.gz"
    provenance_columns = [f"{field}_source" for field in MAPPING]
    with gzip.open(SOURCE_OVERLAY, "rt", encoding="utf-8", newline="") as source, gzip.open(
        output_path, "wt", encoding="utf-8", newline=""
    ) as output:
        reader = csv.DictReader(source)
        assert reader.fieldnames and set(MAPPING).issubset(reader.fieldnames)
        writer = csv.DictWriter(output, fieldnames=list(reader.fieldnames) + provenance_columns, lineterminator="\n")
        writer.writeheader()
        row_count = 0
        for row in reader:
            row_count += 1
            isin = row["isin"]
            for target, source_field in MAPPING.items():
                provenance_field = f"{target}_source"
                row[provenance_field] = ""
                if row[target].strip():
                    continue
                evidence = by_key.get((isin, source_field))
                if evidence is None:
                    continue
                assert row[source_field].strip(), (isin, source_field)
                # This is a direct, compatible current return metric. No
                # conversion or risk/age discount is applied to its value.
                row[target] = row[source_field]
                row[provenance_field] = "PROFESSOR_EXCEL"
                fills.append({
                    "isin": isin, "ticker": row["ticker"], "company": row["company"],
                    "target_field": target, "source_field": source_field,
                    "value": row[target], "provenance": "PROFESSOR_EXCEL",
                    "source_sheet": evidence.source_sheet, "source_table": evidence.source_table,
                    "source_cells": evidence.source_cells, "source_code": evidence.source_code,
                    "match_method": evidence.match_method,
                    "workbook_sha256": evidence.workbook_sha256,
                    "current_only": True, "policy": "EQUAL_PRIORITY_CURRENT_FALLBACK",
                })
            writer.writerow(row)
    assert row_count == v1["company_rows"]
    fills_df = pd.DataFrame(fills)
    fills_df.to_csv(OUT / "direct_filled_cells.csv", index=False)
    before_after = []
    original = pd.read_csv(SOURCE_OVERLAY, usecols=["isin", *MAPPING], low_memory=False)
    updated = pd.read_csv(output_path, usecols=["isin", *MAPPING], low_memory=False)
    assert original["isin"].equals(updated["isin"])
    for field in MAPPING:
        before, after = int(original[field].isna().sum()), int(updated[field].isna().sum())
        count = int(fills_df.target_field.eq(field).sum())
        assert before - after == count
        before_after.append({"field": field, "missing_before": before,
                             "missing_after": after, "filled": count})
    pd.DataFrame(before_after).to_csv(OUT / "coverage_before_after.csv", index=False)
    summary = {
        "schema": "professor_current_equal_priority_v2",
        "base_overlay_sha256": source_sha,
        "base_fill_ledger_sha256": ledger_sha,
        "source_workbook_sha256": v1["source_workbook_sha256"],
        "accepted_company_facts_sha256": v1["accepted_company_facts_sha256"],
        "accepted_state_sha256": v1["accepted_state_sha256"],
        "rows": row_count,
        "workbook_matched_unique_stocks": v1["matched_unique_stocks"],
        "workbook_unmatched_source_rows": v1["unmatched_source_rows"],
        "workbook_ambiguous_source_rows": v1["ambiguous_source_rows"],
        "direct_fields_filled": len(fills),
        "stocks_with_direct_fills": int(fills_df["isin"].nunique()),
        "fills_by_field": dict(Counter(x["target_field"] for x in fills)),
        "total_professor_filled_cells_including_v1": v1["filled_cells"] + len(fills),
        "same_priority_as_other_current_values": True,
        "differential_penalty_or_rank_weight": False,
        "existing_nonmissing_cells_overwritten": 0,
        "accepted_snapshot_modified": False,
        "historical_v12_v13_modified": False,
        "production_or_website_modified": False,
        "not_recomputed": ["product_baseline_score", "product_baseline_sector_rank", "product_baseline_eligible"],
        "ath_direct_fills": 0,
        "ath_reason": "No accepted recorded_high/recorded_high_date blank has a matching professor ATH value; no substitution was needed.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert sha(SOURCE_OVERLAY) == source_sha and sha(SOURCE_LEDGER) == ledger_sha
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
