"""Verify a completed official DoubleEnsemble batch with Python 3.12."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify(batch: Path) -> None:
    if not batch.is_dir():
        raise ValueError(f"batch directory does not exist: {batch}")
    runs = sorted(path for path in batch.glob("run-*") if path.is_dir())
    batch_report = _load(batch / "batch_execution_report.json")
    blocked = batch_report.get("status") == "blocked"
    expected_runs = ["run-01"] if blocked else ["run-01", "run-02"]
    if [path.name for path in runs] != expected_runs:
        raise ValueError(f"batch must contain exactly {expected_runs}")
    if blocked:
        failure = _load(runs[0] / "scientific_acceptance_failure.json")
        if (
            failure.get("blocker_id")
            != "official_frozen_configuration_constant_signal"
            or failure.get("second_run_attempted") is not False
            or failure.get("tree_counts") != [1, 1, 1]
            or failure.get("constant_signal_dates") != 40
            or failure.get("registry_promotion_permitted") is not False
        ):
            raise ValueError("blocked-batch evidence mismatch")
    else:
        report = _load(batch / "reproducibility_report.json")
        if (
            report.get("passed") is not True
            or report.get("tolerance") != 1e-12
            or report.get("tolerance_relaxed") is not False
        ):
            raise ValueError("reproducibility report failed")
    run_ids = set()
    for run in runs:
        metadata = _load(run / "doubleensemble_runner_metadata.json")
        manifest = _load(
            run / ("failed_manifest.json" if blocked else "completed_manifest.json")
        )
        inventory = _load(run / "artifact_inventory.json")
        predictions = pd.read_csv(run / "doubleensemble_predictions_raw.csv")
        signals = pd.read_csv(run / "doubleensemble_signals.csv")
        summaries = _load(run / "submodel_summary.json")
        selected = _load(run / "submodel_selected_features.json")
        comparison = (
            None if blocked else _load(run / "four_model_comparison.json")
        )
        if (
            metadata["model_class"]
            != "qlib.contrib.model.double_ensemble.DEnsembleModel"
            or metadata["qlib_version"] != "0.9.7"
            or metadata["dependency_versions"]["lightgbm"] != "4.6.0"
            or metadata["source_sha256"]
            != "780d60f334bcac2e2d0b07f97022f4b9fa40b6a570befe6fa690094a52eaf462"
            or metadata["submodel_count"] != 3
            or len(predictions) != 1200
            or len(signals) != 1200
            or len(summaries) != 3
            or len(selected) != 3
            or manifest["status"] != ("failed" if blocked else "completed")
            or (
                not blocked
                and (
                    len(comparison["model_configuration_fingerprints"]) != 4
                    or comparison["evaluation_protocol_fingerprint"]
                    != "210bca5c4ac474f766a3caf549d8adc4dc06ae22b3378eb70f4ed224f6978782"
                )
            )
        ):
            raise ValueError(f"acceptance metadata mismatch: {run.name}")
        run_ids.add(metadata["run_id"])
        excluded = set(inventory["self_referential_exclusions"])
        for entry in inventory["artifacts"]:
            path = run / entry["relative_path"]
            if (
                entry["relative_path"] in excluded
                or not path.is_file()
                or path.stat().st_size != entry["size_bytes"]
                or _hash(path) != entry["sha256"]
            ):
                raise ValueError(
                    f"inventory mismatch: {run.name}/{entry['relative_path']}"
                )
        for artifact in manifest.get("evaluation_artifacts", []):
            path = Path(artifact["path"])
            if not path.is_file() or _hash(path) != artifact["sha256"]:
                raise ValueError(f"manifest artifact mismatch: {path}")
    if len(run_ids) != len(expected_runs):
        raise ValueError("run IDs must be distinct")

    import lightgbm
    import qlib
    from qlib.contrib.model.double_ensemble import DEnsembleModel

    if (
        qlib.__version__ != "0.9.7"
        or lightgbm.__version__ != "4.6.0"
        or f"{DEnsembleModel.__module__}.{DEnsembleModel.__name__}"
        != "qlib.contrib.model.double_ensemble.DEnsembleModel"
    ):
        raise ValueError("official environment identity mismatch")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify an official Qlib DoubleEnsemble reproduction batch."
    )
    parser.add_argument("batch_directory", type=Path)
    args = parser.parse_args(argv)
    try:
        verify(args.batch_directory)
    except Exception as exc:
        print(f"DoubleEnsemble verification failed: {exc}", file=sys.stderr)
        return 1
    print(f"DoubleEnsemble integration verification passed: {args.batch_directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
