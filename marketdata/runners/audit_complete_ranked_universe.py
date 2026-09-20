"""Write the exhaustive internal Codex-vs-system audit from accepted evidence."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.company_facts import (  # noqa: E402
    load_company_fact_snapshot, resolve_company_fact_snapshot,
)
from stock_ranker.internal_codex_audit import (  # noqa: E402
    audit_complete_universe,
    freeze_independent_judgments,
)
from stock_research.current_price_ensemble import validate_current_price_ensemble  # noqa: E402


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def run(output: Path, candidate_root: Path) -> dict:
    if output.exists():
        raise ValueError("fresh output directory required")
    snapshot = resolve_company_fact_snapshot(ROOT / "data/company_facts")
    facts = load_company_fact_snapshot(snapshot)
    candidate_summary = validate_current_price_ensemble(candidate_root)
    candidate = pd.read_csv(candidate_root / "rankings.csv", low_memory=False)
    # Freeze and persist the independent benchmark before the comparator is
    # allowed to read production scores/ranks.  The read-back makes the
    # artifact, rather than an in-memory mutable frame, the comparison input.
    output.mkdir(parents=True)
    frozen_path = output / "frozen_codex_judgments.csv"
    frozen = freeze_independent_judgments(facts.facts, candidate)
    frozen.to_csv(frozen_path, index=False, lineterminator="\n")
    frozen_sha256 = _sha(frozen_path)
    frozen = pd.read_csv(frozen_path, low_memory=False)
    result = audit_complete_universe(facts.facts, frozen_judgments=frozen)
    summary = {
        **result.summary,
        "accepted_company_fingerprint": facts.manifest["fingerprint"],
        "accepted_market_fingerprint": facts.manifest["market_fingerprint"],
        "candidate_fingerprint": json.loads(
            (candidate_root / "manifest.json").read_text(encoding="utf-8")
        )["fingerprint"],
        "candidate_ranked_count": candidate_summary["ranked"],
        "frozen_judgments_sha256": frozen_sha256,
    }
    result.rows.to_csv(output / "stock_by_stock_audit.csv", index=False, lineterminator="\n")
    result.disagreements.to_csv(
        output / "meaningful_disagreements.csv", index=False, lineterminator="\n"
    )
    result.sectors.to_csv(output / "sector_reconciliation.csv", index=False, lineterminator="\n")
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    artifacts = [{
        "path": path.name, "sha256": _sha(path), "size": path.stat().st_size,
    } for path in sorted(output.iterdir())]
    fingerprint = sha256(json.dumps(
        artifacts, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    (output / "manifest.json").write_text(json.dumps({
        "schema_version": "codex_internal_audit_manifest_v2",
        "fingerprint": fingerprint, "artifacts": artifacts,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary | {"fingerprint": fingerprint}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, default=(
        ROOT / "data/analysis/current_price_ensemble_v5_20260918_run_01"
    ))
    args = parser.parse_args()
    print(json.dumps(run(args.output, args.candidate), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
