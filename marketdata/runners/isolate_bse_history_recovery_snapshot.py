"""Create a company-fact snapshot containing only audited history/Baseline changes."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.company_facts import (  # noqa: E402
    _json_bytes,
    _sha256_bytes,
    load_company_fact_snapshot,
)
from stock_ranker.data_state import atomic_write_json  # noqa: E402


EXACT_HISTORY_FIELDS = {
    "corporate_action_history_status",
    "recorded_high", "recorded_high_date",
    "high_52w", "high_52w_date", "low_52w", "low_52w_date",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        return list(reader.fieldnames), list(reader)


def run(prior_root: Path, candidate_root: Path, output: Path) -> dict[str, object]:
    prior = load_company_fact_snapshot(prior_root)
    candidate = load_company_fact_snapshot(candidate_root)
    if output.exists():
        raise FileExistsError(f"output must be fresh: {output}")
    if prior.manifest["market_fingerprint"] != candidate.manifest["market_fingerprint"]:
        raise ValueError("market fingerprint changed")

    old_fields, old_rows = read_rows(prior_root / "company_facts.csv")
    new_fields, new_rows = read_rows(candidate_root / "company_facts.csv")
    if old_fields != new_fields:
        raise ValueError("candidate schema changed")
    new_by_isin = {row["isin"]: row for row in new_rows}
    if len(new_by_isin) != len(new_rows) or {r["isin"] for r in old_rows} != set(new_by_isin):
        raise ValueError("candidate identities changed")
    allowed = set(EXACT_HISTORY_FIELDS)
    allowed.update(name for name in old_fields if name.startswith("history_") or name.startswith("product_baseline_"))

    merged: list[dict[str, str]] = []
    changed_by_field: dict[str, int] = {}
    for old in old_rows:
        new = new_by_isin[old["isin"]]
        row = dict(old)
        for field in allowed:
            if old[field] != new[field]:
                row[field] = new[field]
                changed_by_field[field] = changed_by_field.get(field, 0) + 1
        merged.append(row)

    output.mkdir(parents=True)
    csv_path = output / "company_facts.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=old_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(merged)

    # Candidate coverage is correct for changed history/Baseline fields. Restore
    # the three metrics affected by unrelated loader drift in the dirty worktree.
    coverage = copy.deepcopy(candidate.coverage)
    for metric in ("balance_sheet", "cash_flow", "screener_detailed_workbooks"):
        coverage["metrics"][metric] = copy.deepcopy(prior.coverage["metrics"][metric])
    atomic_write_json(output / "coverage_summary.json", coverage)

    import pandas as pd
    facts = pd.read_csv(csv_path, low_memory=False)
    canonical_rows = json.loads(facts.to_json(orient="records", date_format="iso", double_precision=15))
    manifest = dict(candidate.manifest)
    manifest["fingerprint"] = _sha256_bytes(_json_bytes({
        "schema_version": manifest["schema_version"],
        "market_fingerprint": manifest["market_fingerprint"],
        "screener_bundle_fingerprint": manifest["screener_bundle_fingerprint"],
        "facts": canonical_rows,
        "coverage": coverage,
    }))
    manifest["artifacts"] = {
        "company_facts.csv": sha256(csv_path),
        "coverage_summary.json": sha256(output / "coverage_summary.json"),
    }
    atomic_write_json(output / "manifest.json", manifest)
    load_company_fact_snapshot(output)
    report = {
        "prior_fingerprint": prior.manifest["fingerprint"],
        "candidate_fingerprint": candidate.manifest["fingerprint"],
        "isolated_fingerprint": manifest["fingerprint"],
        "market_fingerprint": manifest["market_fingerprint"],
        "allowed_fields": sorted(allowed),
        "changed_by_field": changed_by_field,
        "changed_companies": len({r["isin"] for r, old in zip(merged, old_rows) if r != old}),
        "unrelated_field_changes": 0,
    }
    atomic_write_json(output / "isolation_report.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run(args.prior.resolve(), args.candidate.resolve(), args.output.resolve())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
