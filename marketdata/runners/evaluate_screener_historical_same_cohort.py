"""Run the outcome phase of the frozen Screener historical protocol."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.screener_historical_evaluation import (  # noqa: E402
    calculate_frozen_future_returns,
    evaluate_frozen_same_cohort,
    export_frozen_evaluation,
    validate_frozen_inputs,
)


def run(
    readiness_root: Path,
    protocol_path: Path,
    history_root: Path,
    blind_root: Path,
    output: Path,
) -> str:
    membership, protocol, readiness = validate_frozen_inputs(
        readiness_root, protocol_path, history_root, blind_root
    )
    future_returns = calculate_frozen_future_returns(membership, history_root)
    cohort_hash = sha256((readiness_root / "cohort_membership.csv").read_bytes()).hexdigest()
    blind_hash = readiness["input_fingerprints"]["blind_manifest"]
    evaluation = evaluate_frozen_same_cohort(
        membership,
        future_returns,
        protocol_fingerprint=readiness["protocol_fingerprint"],
        cohort_fingerprint=cohort_hash,
        blind_manifest_fingerprint=blind_hash,
    )
    provenance = {
        "schema_version": 1,
        "protocol_identifier": protocol["protocol_identifier"],
        "protocol_fingerprint": readiness["protocol_fingerprint"],
        "cohort_membership_sha256": cohort_hash,
        "blind_manifest_sha256": blind_hash,
        "outcome_history_hashes": readiness["input_fingerprints"]["outcome_history_files"],
        "rankings_frozen_before_outcome_access": True,
        "outcomes_opened_only_after_readiness_gate_passed": True,
        "models_or_cohort_changed_after_reveal": False,
    }
    return export_frozen_evaluation(evaluation, output, provenance)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the frozen expanded historical cohort.")
    parser.add_argument("--readiness-root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--history-root", type=Path, required=True)
    parser.add_argument("--blind-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        fingerprint = run(
            args.readiness_root, args.protocol, args.history_root,
            args.blind_root, args.output,
        )
        print(json.dumps({"evaluation_fingerprint": fingerprint}, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"historical evaluation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
