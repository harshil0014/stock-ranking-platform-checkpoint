"""Create the no-blank, fully ranked, provenance-preserving universe view."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot  # noqa: E402
from stock_ranker.universe_completion import ESTIMATE_CODES, complete_universe  # noqa: E402
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
    result = complete_universe(facts.facts, candidate)
    output.mkdir(parents=True)
    result.completed.to_csv(output / "completed_company_facts.csv", index=False, lineterminator="\n")
    result.estimate_codes.to_csv(output / "field_estimate_codes.csv", index=False, lineterminator="\n")
    result.rankings.to_csv(output / "complete_rankings.csv", index=False, lineterminator="\n")
    result.resolved_exclusions.to_csv(output / "resolved_exclusions_audit.csv", index=False, lineterminator="\n")
    result.field_summary.to_csv(output / "field_completion_summary.csv", index=False, lineterminator="\n")
    (output / "estimate_codebook.json").write_text(
        json.dumps(ESTIMATE_CODES, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = {
        **result.summary,
        "accepted_company_fingerprint": facts.manifest["fingerprint"],
        "accepted_market_fingerprint": facts.manifest["market_fingerprint"],
        "candidate_ranked_count": candidate_summary["ranked"],
        "candidate_fingerprint": json.loads(
            (candidate_root / "manifest.json").read_text(encoding="utf-8")
        )["fingerprint"],
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    artifacts = [
        {"path": path.name, "sha256": _sha(path), "size": path.stat().st_size}
        for path in sorted(output.iterdir())
    ]
    fingerprint = sha256(json.dumps(
        artifacts, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    (output / "manifest.json").write_text(json.dumps({
        "schema_version": "complete_universe_manifest_v1",
        "fingerprint": fingerprint,
        "artifacts": artifacts,
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
