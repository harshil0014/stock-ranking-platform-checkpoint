"""Audit two offline builds and optionally promote their identical immutable bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import pandas as pd
from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_ranker.data_state import atomic_write_json
from audit_website_gap_root_causes import build_audit
from datetime import date, datetime, timezone


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-one", type=Path, required=True)
    parser.add_argument("--candidate-two", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, default=ROOT / "data/company_facts")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--promote", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("audit output must be fresh")
    old_pointer = (args.state_root / "accepted_state.json").read_bytes()
    before_path = resolve_company_fact_snapshot(args.state_root)
    paths = [resolve_company_fact_snapshot(p) for p in (args.candidate_one, args.candidate_two)]
    before, after = load_company_fact_snapshot(before_path), load_company_fact_snapshot(paths[0])
    hashes = {}
    for name in ("company_facts.csv", "coverage_summary.json", "manifest.json"):
        hashes[name] = digest(paths[0] / name)
        if hashes[name] != digest(paths[1] / name):
            raise ValueError(f"nondeterministic candidate: {name}")
    a = before.facts.set_index("isin").sort_index()
    b = after.facts.set_index("isin").sort_index()
    if not a.index.equals(b.index):
        raise ValueError("accepted security identities changed")
    changed = []
    for col in a.columns:
        mask = ~(a[col].eq(b[col]) | (a[col].isna() & b[col].isna()))
        for isin in a.index[mask]:
            changed.append({"isin": isin, "ticker": b.at[isin, "ticker"], "field": col,
                            "before": a.at[isin, col], "after": b.at[isin, col]})
        if mask.any() and (col.startswith("v2_") or col.startswith("strict_")
                           or col in {"ticker", "company", "primary_exchange", "product_sector", "product_industry"}):
            raise ValueError(f"protected field changed: {col}")
    if before.manifest["market_fingerprint"] != after.manifest["market_fingerprint"]:
        raise ValueError("market evidence changed")
    args.output.mkdir(parents=True)
    changes = pd.DataFrame(changed, columns=["isin", "ticker", "field", "before", "after"])
    changes.to_csv(args.output / "all_field_changes.csv", index=False, lineterminator="\n")
    coverage = []
    for name, metric in after.coverage["metrics"].items():
        old = before.coverage["metrics"].get(name, {}).get("count", 0)
        coverage.append({"field": name, "before": old, "after": metric["count"],
                         "newly_surfaced": metric["count"] - old,
                         "still_missing": len(b) - metric["count"]})
    pd.DataFrame(coverage).to_csv(args.output / "coverage_before_after.csv", index=False, lineterminator="\n")
    gaps, display, summary = build_audit(after.facts, as_of=date.fromisoformat(after.manifest["trade_date"]))
    gaps.to_csv(args.output / "remaining_all_gaps.csv", index=False, lineterminator="\n")
    category = "category" if "category" in gaps else "data_item"
    for name, group in gaps.groupby(category, sort=True):
        group.to_csv(args.output / f"remaining_missing_{name}.csv", index=False, lineterminator="\n")
    display.to_csv(args.output / "display_states.csv", index=False, lineterminator="\n")
    atomic_write_json(args.output / "before_pointer.json", json.loads(old_pointer))
    report = {"before_fingerprint": before.manifest["fingerprint"],
              "after_fingerprint": after.manifest["fingerprint"], "deterministic_artifact_hashes": hashes,
              "securities": len(b), "companies_with_changed_fields": int(changes["isin"].nunique()),
              "changes_by_field": changes.groupby("field").size().to_dict(),
              "coverage": coverage, "remaining": summary, "promoted": False}
    if args.promote:
        if (args.state_root / "accepted_state.json").read_bytes() != old_pointer:
            raise ValueError("accepted state advanced during audit")
        destination = args.state_root / "snapshots" / paths[0].name
        if not destination.exists():
            shutil.copytree(paths[0], destination)
        load_company_fact_snapshot(destination)
        if any(digest(destination / name) != expected for name, expected in hashes.items()):
            raise ValueError("immutable destination differs from verified candidate")
        pointer = json.loads((args.candidate_one / "accepted_state.json").read_text())
        pointer["accepted_at"] = datetime.now(timezone.utc).isoformat()
        pointer["snapshot_path"] = destination.relative_to(args.state_root).as_posix()
        atomic_write_json(args.state_root / "accepted_state.json", pointer)
        report["promoted"] = True
    atomic_write_json(args.output / "acceptance.json", report)
    print(json.dumps({k: v for k, v in report.items() if k not in {"coverage", "remaining", "changes_by_field"}}, default=int))


if __name__ == "__main__":
    main()
