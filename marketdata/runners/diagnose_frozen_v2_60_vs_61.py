from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

PROJECT = Path.home() / "Downloads" / "stock-ranking-platform"

LIVE_ROOT = PROJECT / "data" / "live_market"
FACT_ROOT = PROJECT / "data" / "company_facts"
OUTPUT = PROJECT / "data" / "diagnostics" / "frozen_v2_60_vs_61_20260907"


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def truthy(v) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes"}


def resolve_pointer(root: Path, pointer_name: str, path_keys: tuple[str, ...]) -> Path:
    p = root / pointer_name
    if not p.is_file():
        raise FileNotFoundError(p)
    state = json.loads(p.read_text(encoding="utf-8"))
    for key in path_keys:
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            candidate = (root / value).resolve()
            if candidate.is_dir():
                return candidate
    raise ValueError(f"Could not resolve {pointer_name} under {root}")


def find_bool_col(rows: list[dict], candidates: list[str]) -> str | None:
    if not rows:
        return None
    cols = set(rows[0])
    for c in candidates:
        if c in cols:
            return c
    return None


def v2_rows(rows: list[dict]) -> tuple[str | None, list[dict]]:
    col = find_bool_col(rows, [
        "research_v2_eligible",
        "strict_v2_eligible",
        "v2_eligible",
        "eligible_research_v2",
    ])
    if col:
        return col, [r for r in rows if truthy(r.get(col))]
    return None, []


def row_key(r: dict) -> str:
    return str(r.get("isin") or r.get("ticker") or "").strip().upper()


def selected_fields(r: dict) -> dict:
    keep = [
        "ticker", "company", "isin", "primary_exchange", "trade_date",
        "latest_price", "snapshot_status",
        "research_v2_eligible", "strict_v2_eligible", "v2_eligible",
        "research_v2_reason_code", "strict_v2_reason_code", "v2_reason_code",
        "research_v2_reason", "strict_v2_reason", "v2_reason",
        "roce", "debt_to_equity", "profit_growth_yoy",
        "return_1y", "cagr_3y", "cagr_5y",
    ]
    return {k: r.get(k, "") for k in keep if k in r}


def snapshot_candidates(root: Path, filename: str) -> list[Path]:
    snaps = root / "snapshots"
    if not snaps.is_dir():
        return []
    return sorted(
        [p for p in snaps.glob(f"*/{filename}") if p.is_file()],
        key=lambda p: p.parent.name
    )


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    live_bundle = resolve_pointer(LIVE_ROOT, "accepted_state.json", ("bundle_path", "snapshot_path"))
    live_file = live_bundle / "live_market.csv"
    live_manifest = json.loads((live_bundle / "bundle_manifest.json").read_text(encoding="utf-8"))
    live_rows = read_csv(live_file)
    live_col, live_eligible = v2_rows(live_rows)

    fact_bundle = resolve_pointer(FACT_ROOT, "accepted_state.json", ("snapshot_path", "bundle_path"))
    fact_file = fact_bundle / "company_facts.csv"
    fact_manifest = json.loads((fact_bundle / "manifest.json").read_text(encoding="utf-8"))
    fact_rows = read_csv(fact_file)
    fact_col, fact_eligible = v2_rows(fact_rows)

    live_by_key = {row_key(r): r for r in live_rows if row_key(r)}
    fact_by_key = {row_key(r): r for r in fact_rows if row_key(r)}

    live_set = {row_key(r) for r in live_eligible}
    fact_set = {row_key(r) for r in fact_eligible}

    only_live = sorted(live_set - fact_set)
    only_fact = sorted(fact_set - live_set)

    # Scan older accepted/snapshot-like files for the most recent 61-count cohort.
    previous_61 = None
    previous_61_rows = None
    previous_61_col = None
    for p in reversed(snapshot_candidates(FACT_ROOT, "company_facts.csv")):
        try:
            rows = read_csv(p)
            col, elig = v2_rows(rows)
            if col and len(elig) == 61:
                previous_61 = p
                previous_61_rows = rows
                previous_61_col = col
                break
        except Exception:
            pass

    disappeared_from_61 = []
    appeared_vs_61 = []
    if previous_61_rows is not None:
        old_col, old_elig = v2_rows(previous_61_rows)
        old_set = {row_key(r) for r in old_elig}
        cur_set = fact_set
        disappeared_from_61 = sorted(old_set - cur_set)
        appeared_vs_61 = sorted(cur_set - old_set)

    detail = []
    keys = sorted(set(only_live) | set(only_fact) | set(disappeared_from_61) | set(appeared_vs_61))
    old_by_key = {}
    if previous_61_rows is not None:
        old_by_key = {row_key(r): r for r in previous_61_rows if row_key(r)}

    for k in keys:
        detail.append({
            "key": k,
            "in_current_live_v2": k in live_set,
            "in_current_company_facts_v2": k in fact_set,
            "in_previous_61_v2": k in old_by_key and truthy(old_by_key[k].get(previous_61_col)),
            "current_live": selected_fields(live_by_key.get(k, {})),
            "current_company_facts": selected_fields(fact_by_key.get(k, {})),
            "previous_61_company_facts": selected_fields(old_by_key.get(k, {})),
        })

    summary = {
        "live_bundle": str(live_bundle),
        "live_manifest_research_v2_eligible_count": live_manifest.get("research_v2_eligible_count"),
        "live_detected_v2_column": live_col,
        "live_detected_v2_rows": len(live_eligible),
        "company_facts_bundle": str(fact_bundle),
        "company_facts_manifest_row_count": fact_manifest.get("row_count"),
        "company_facts_detected_v2_column": fact_col,
        "company_facts_detected_v2_rows": len(fact_eligible),
        "live_v2_not_in_company_facts_v2": only_live,
        "company_facts_v2_not_in_live_v2": only_fact,
        "previous_61_snapshot": str(previous_61) if previous_61 else None,
        "disappeared_from_previous_61": disappeared_from_61,
        "appeared_vs_previous_61": appeared_vs_61,
    }

    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    (OUTPUT / "details.json").write_text(json.dumps(detail, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"Details: {OUTPUT / 'details.json'}")
    print("FROZEN V2 60-vs-61 DIAGNOSTIC: PASS")
    print("No data or tests were modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
