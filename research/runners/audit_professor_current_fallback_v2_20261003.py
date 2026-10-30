"""Audit direct current-field fills without changing the accepted snapshot."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "experiments/professor-current-fallback-20261003"
OUT = BASE / "equal-priority-v2"
BEFORE = BASE / "current_company_facts_professor_overlay.csv.gz"
AFTER = OUT / "current_company_facts_equal_priority.csv.gz"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    assert sha(BEFORE) == summary["base_overlay_sha256"]
    fills = pd.read_csv(OUT / "direct_filled_cells.csv")
    coverage = pd.read_csv(OUT / "coverage_before_after.csv")
    assert len(fills) == summary["direct_fields_filled"]
    assert fills[["isin", "target_field"]].duplicated().sum() == 0
    expected = {(str(x.isin), str(x.target_field)): x for x in fills.itertuples(index=False)}
    seen = set()
    rows = 0
    with gzip.open(BEFORE, "rt", encoding="utf-8", newline="") as old_file, gzip.open(
        AFTER, "rt", encoding="utf-8", newline=""
    ) as new_file:
        old_reader, new_reader = csv.DictReader(old_file), csv.DictReader(new_file)
        assert old_reader.fieldnames and new_reader.fieldnames
        assert set(old_reader.fieldnames).issubset(new_reader.fieldnames)
        for old, new in zip(old_reader, new_reader, strict=True):
            rows += 1
            assert old["isin"] == new["isin"]
            for field in old_reader.fieldnames:
                key = (old["isin"], field)
                if key in expected:
                    entry = expected[key]
                    assert old[field] == "", key
                    assert new[field] == old[entry.source_field] == str(entry.value), key
                    assert new[f"{field}_source"] == "PROFESSOR_EXCEL"
                    assert entry.provenance == "PROFESSOR_EXCEL"
                    assert entry.current_only and entry.policy == "EQUAL_PRIORITY_CURRENT_FALLBACK"
                    seen.add(key)
                else:
                    assert old[field] == new[field], key
    assert rows == summary["rows"] and seen == set(expected)
    for x in coverage.itertuples(index=False):
        assert x.missing_before - x.missing_after == x.filled
    accepted = ROOT / "data/company_facts"
    state_path = accepted / "accepted_state.json"
    assert sha(state_path) == summary["accepted_state_sha256"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    company_path = accepted / state["snapshot_path"] / "company_facts.csv"
    assert sha(company_path) == summary["accepted_company_facts_sha256"]
    audit = {
        "schema": "professor_current_equal_priority_audit_v1",
        "status": "PASS",
        "rows": rows,
        "direct_fills_verified": len(seen),
        "original_nonmissing_cells_preserved": True,
        "accepted_state_sha256": sha(state_path),
        "accepted_company_facts_sha256": sha(company_path),
        "base_overlay_sha256": sha(BEFORE),
        "equal_priority_overlay_sha256": sha(AFTER),
        "historical_or_production_files_modified": False,
    }
    (OUT / "audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
