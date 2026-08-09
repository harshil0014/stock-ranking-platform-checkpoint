"""Evaluate frozen blind rankings against cached future adjusted prices."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.walk_forward_evaluation import (  # noqa: E402
    BLIND_FINGERPRINT, calculate_future_returns, evaluate_walk_forward, export_evaluation,
)


def run(blind_root: Path, outcome_cache: Path, output: Path) -> str:
    prices_path = outcome_cache / "outcome_prices.csv"
    cache_manifest = json.loads((outcome_cache / "cache_manifest.json").read_text(encoding="utf-8"))
    if sha256(prices_path.read_bytes()).hexdigest() != cache_manifest["outcome_prices_sha256"]:
        raise ValueError("cached outcome-price hash mismatch")
    request_path = outcome_cache / "request_provenance.json"
    request_hash = sha256(request_path.read_bytes()).hexdigest()
    if request_hash != cache_manifest["request_provenance_sha256"]:
        raise ValueError("cached outcome-request provenance hash mismatch")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if request.get("blind_prediction_fingerprint") != BLIND_FINGERPRINT:
        raise ValueError("cached outcome request has wrong blind fingerprint")
    prices = pd.read_csv(prices_path)
    returns = calculate_future_returns(prices)
    evaluation = evaluate_walk_forward(blind_root, returns)
    provenance = {
        "schema_version": 1, "blind_prediction_fingerprint": BLIND_FINGERPRINT,
        "outcome_cache_manifest": cache_manifest,
        "outcome_request_provenance_sha256": request_hash,
        "predictions_frozen_before_outcome_acquisition": True,
        "models_or_mappings_changed_after_reveal": False,
    }
    return export_evaluation(evaluation, prices, provenance, output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate frozen walk-forward rankings.")
    parser.add_argument("--blind-root", type=Path, required=True)
    parser.add_argument("--outcome-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps({"evaluation_fingerprint": run(
            args.blind_root, args.outcome_cache, args.output
        )}, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"walk-forward evaluation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
