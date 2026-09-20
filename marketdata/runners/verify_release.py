"""Fail closed unless runtime evidence matches the frozen validated release."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.company_facts import load_company_fact_snapshot  # noqa: E402
from stock_ranker.live_market import load_live_market_bundle  # noqa: E402
from stock_ranker.universe_completion import validate_completion  # noqa: E402
from stock_research.current_price_ensemble import validate_current_price_ensemble  # noqa: E402


def _manifest_fingerprint(path: Path) -> str:
    return str(json.loads(path.read_text(encoding="utf-8"))["fingerprint"])


def _validate_inventory(root: Path) -> None:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["artifacts"]:
        path = root / str(entry["path"])
        if not path.is_file() or path.stat().st_size != int(entry["size"]):
            raise ValueError(f"release artifact missing or size-mismatched: {path}")
        if sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"release artifact hash mismatch: {path}")


def verify(state_path: Path, data_root: Path) -> dict:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    market_root = data_root / "live_market/snapshots" / (
        "2026-09-18-" + state["accepted_market_fingerprint"]
    )
    fact_root = data_root / "company_facts/snapshots" / (
        "2026-09-18-" + state["accepted_company_fingerprint"]
    )
    market = load_live_market_bundle(market_root)
    facts = load_company_fact_snapshot(fact_root)
    completion_root = data_root / "analysis/complete_universe_20260918_run_05"
    completion = validate_completion(completion_root)
    candidate_root = data_root / "analysis/current_price_ensemble_v5_20260918_run_01"
    candidate = validate_current_price_ensemble(candidate_root)
    audit_root = ROOT / "data/analysis/completed_universe_frozen_audit_20260920_run_01"
    reconciliation_root = ROOT / "data/analysis/universe_reconciliation_20260920_run_01"
    website_audit_root = ROOT / "data/analysis/release_website_audit_20260920_run_01"
    _validate_inventory(audit_root)
    _validate_inventory(reconciliation_root)
    _validate_inventory(website_audit_root)
    checks = {
        "accepted_market_fingerprint": market.fingerprint,
        "accepted_company_fingerprint": facts.manifest["fingerprint"],
        "completion_fingerprint": _manifest_fingerprint(completion_root / "manifest.json"),
        "candidate_fingerprint": _manifest_fingerprint(candidate_root / "manifest.json"),
        "final_audit_fingerprint": _manifest_fingerprint(audit_root / "manifest.json"),
        "universe_reconciliation_fingerprint": _manifest_fingerprint(reconciliation_root / "manifest.json"),
        "website_audit_fingerprint": _manifest_fingerprint(website_audit_root / "manifest.json"),
    }
    for key, actual in checks.items():
        if actual != state[key]:
            raise ValueError(f"validated release mismatch for {key}")
    if len(market.market) != state["accepted_universe_count"]:
        raise ValueError("accepted market universe count mismatch")
    if len(facts.facts) != state["accepted_universe_count"]:
        raise ValueError("accepted company-fact universe count mismatch")
    if completion["ranked_count"] != state["accepted_universe_count"]:
        raise ValueError("complete ranking count mismatch")
    if completion["remaining_missing_cell_count"] != 0:
        raise ValueError("complete ranking contains missing cells")
    if candidate["ranked"] != completion["candidate_ranked_count"]:
        raise ValueError("candidate ranking count is stale or inconsistent")
    return {"status": "VERIFIED", **checks, "universe_count": len(market.market)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--state", type=Path,
        default=ROOT / "release/validated_state_20260920.json",
    )
    parser.add_argument(
        "--data-root", type=Path,
        default=Path(os.environ.get("STOCK_RANKER_DATA_ROOT", ROOT / "data")),
    )
    args = parser.parse_args()
    print(json.dumps(verify(args.state, args.data_root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
