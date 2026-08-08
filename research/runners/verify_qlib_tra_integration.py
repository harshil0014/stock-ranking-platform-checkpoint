"""Verify a completed official Qlib TRA frozen-protocol batch."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd


EXPECTED_PROTOCOL = (
    "210bca5c4ac474f766a3caf549d8adc4dc06ae22b3378eb70f4ed224f6978782"
)
EXPECTED_TRA_SOURCE = (
    "a3ea48722ffbcb795733de57805ea4a07f40477cfcacebc0b495be418ba25a6b"
)
EXPECTED_DATASET_SOURCE = (
    "b484666b36be3302ff496e4ae8f5de01ea279783acfdd5212edf996f8136b8b6"
)
EXPECTED_CONTROLS = {
    "CUDA_VISIBLE_DEVICES": "",
    "PYTHONHASHSEED": "20260730",
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read required JSON artifact {path}: {exc}") from exc


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"required artifact is missing: {path}")


def verify(batch: Path) -> None:
    if not batch.is_dir():
        raise ValueError(f"batch directory does not exist: {batch}")
    runs = sorted(path for path in batch.glob("run-*") if path.is_dir())
    if [path.name for path in runs] != ["run-01", "run-02"]:
        raise ValueError("batch must contain exactly run-01 and run-02")

    reproducibility = _load(batch / "reproducibility_report.json")
    if (
        reproducibility.get("status") != "passed"
        or reproducibility.get("tolerance") != 1e-12
        or any(
            difference > 1e-12
            for difference in reproducibility.get("maximum_differences", {}).values()
        )
        or set(reproducibility.get("maximum_differences", {}))
        != {"score", "score_0", "score_1", "score_2"}
        or not all(reproducibility.get("exact_checks", {}).values())
    ):
        raise ValueError("TRA reproducibility report failed")

    run_ids: set[str] = set()
    model_fingerprints: set[str] = set()
    for run in runs:
        required = [
            "tra_runner_metadata.json",
            "official_dataset_audit.json",
            "phase_summary.json",
            "tra_predictions_raw.csv",
            "tra_state_scores.csv",
            "tra_signals.csv",
            "scientific_gate.json" if run.name == "run-01" else "completed_manifest.json",
            "completed_manifest.json",
            "artifact_inventory.json",
            "model_status_comparison.json",
            "qlib_tra_evaluation/evaluation_summary.json",
        ]
        for relative in required:
            _require_file(run / relative)

        metadata = _load(run / "tra_runner_metadata.json")
        dataset_audit = _load(run / "official_dataset_audit.json")
        phase = _load(run / "phase_summary.json")
        manifest = _load(run / "completed_manifest.json")
        inventory = _load(run / "artifact_inventory.json")
        comparison = _load(run / "model_status_comparison.json")
        evaluation = _load(run / "qlib_tra_evaluation/evaluation_summary.json")
        predictions = pd.read_csv(run / "tra_predictions_raw.csv")
        states = pd.read_csv(run / "tra_state_scores.csv")
        signals = pd.read_csv(run / "tra_signals.csv")

        if (
            metadata.get("status") != "completed"
            or metadata.get("model_class")
            != "qlib.contrib.model.pytorch_tra.TRAModel"
            or metadata.get("dataset_class")
            != "qlib.contrib.data.dataset.MTSDatasetH"
            or metadata.get("qlib_version") != "0.9.7"
            or metadata.get("torch_version") != "2.4.1+cpu"
            or metadata.get("tra_source_sha256") != EXPECTED_TRA_SOURCE
            or metadata.get("dataset_source_sha256") != EXPECTED_DATASET_SOURCE
            or metadata.get("evaluation_protocol_fingerprint") != EXPECTED_PROTOCOL
            or metadata.get("subprocess_environment_controls") != EXPECTED_CONTROLS
            or metadata.get("deterministic_algorithms_enabled") is not True
            or metadata.get("fit_call_count") != 1
            or metadata.get("predict_call_count") != 1
            or metadata.get("fit_returned_normally") is not True
            or metadata.get("prediction_count") != 1200
            or metadata.get("state_score_columns")
            != ["score_0", "score_1", "score_2"]
            or metadata.get("logdir") is not None
            or metadata.get("pickle_written") is not False
            or metadata.get("torch_save_used") is not False
        ):
            raise ValueError(f"runner metadata mismatch: {run.name}")
        if (
            dataset_audit.get("status") != "passed"
            or dataset_audit.get("official_matches_independent") is not True
            or dataset_audit.get("feature_tensor_suffix") != [60, 10]
            or dataset_audit.get("memory_state_tensor_suffix") != [59, 3]
            or dataset_audit.get("segment_rows")
            != {"train": 3600, "valid": 900, "test": 1200}
        ):
            raise ValueError(f"official sequence audit failed: {run.name}")
        phases = phase.get("phases", [])
        if (
            [item.get("name") for item in phases]
            != ["pretraining", "routed_training"]
            or not all(item.get("history_length", 0) > 0 for item in phases)
            or phase.get("final_selected_phase") != "routed_training"
        ):
            raise ValueError(f"phase evidence mismatch: {run.name}")
        if (
            len(predictions) != 1200
            or len(states) != 1200
            or len(signals) != 1200
            or predictions[["datetime", "instrument"]].duplicated().any()
            or states[["datetime", "instrument"]].duplicated().any()
            or not predictions["score"].map(pd.notna).all()
            or not states[["score_0", "score_1", "score_2"]].map(pd.notna).all().all()
            or predictions["datetime"].nunique() != 40
        ):
            raise ValueError(f"prediction artifact mismatch: {run.name}")
        if (
            manifest.get("status") != "completed"
            or manifest.get("evaluation_protocol_fingerprint") != EXPECTED_PROTOCOL
            or comparison.get("evaluation_protocol_fingerprint") != EXPECTED_PROTOCOL
            or "winner" in comparison
            or comparison.get("portfolio_metrics_calculated") is not False
            or comparison.get("investment_claim") is not False
            or evaluation.get("valid_ic_dates") != 40
            or evaluation.get("valid_rank_ic_dates") != 40
        ):
            raise ValueError(f"evaluation or comparison mismatch: {run.name}")

        run_ids.add(metadata["run_id"])
        model_fingerprints.update(
            row["model_configuration_fingerprint"]
            for row in comparison["evaluated_models"]
        )
        excluded = set(inventory["self_referential_exclusions"])
        for entry in inventory["artifacts"]:
            relative = entry["relative_path"]
            path = run / relative
            if (
                relative in excluded
                or not path.is_file()
                or path.stat().st_size != entry["size_bytes"]
                or _hash(path) != entry["sha256"]
            ):
                raise ValueError(f"inventory mismatch: {run.name}/{relative}")
        for artifact in manifest.get("evaluation_artifacts", []):
            path = Path(artifact["path"])
            if not path.is_file() or _hash(path) != artifact["sha256"]:
                raise ValueError(f"manifest artifact mismatch: {path}")

    if len(run_ids) != 2:
        raise ValueError("run IDs must be distinct")
    if len(model_fingerprints) != 4:
        raise ValueError("comparison must preserve four model fingerprints")

    import qlib
    import torch
    from qlib.contrib.data.dataset import MTSDatasetH
    from qlib.contrib.model.pytorch_tra import TRAModel

    if (
        qlib.__version__ != "0.9.7"
        or torch.__version__ != "2.4.1+cpu"
        or f"{TRAModel.__module__}.{TRAModel.__name__}"
        != "qlib.contrib.model.pytorch_tra.TRAModel"
        or f"{MTSDatasetH.__module__}.{MTSDatasetH.__name__}"
        != "qlib.contrib.data.dataset.MTSDatasetH"
    ):
        raise ValueError("official environment identity mismatch")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify an official Qlib TRA frozen-protocol batch."
    )
    parser.add_argument("batch_directory", type=Path)
    args = parser.parse_args(argv)
    try:
        verify(args.batch_directory)
    except Exception as exc:
        print(f"TRA verification failed: {exc}", file=sys.stderr)
        return 1
    print(f"TRA integration verification passed: {args.batch_directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
