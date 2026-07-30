"""Verify terminal evidence from the official local-recorder LightGBM batch."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence
from urllib.parse import urlparse


class VerificationFailure(RuntimeError):
    """Concise failure while checking preserved batch evidence."""


def _directory(value: str) -> Path:
    path = Path(value)
    if not path.exists():
        raise argparse.ArgumentTypeError(
            f"batch directory does not exist: {path}"
        )
    if not path.is_dir():
        raise argparse.ArgumentTypeError(
            f"batch directory is not a directory: {path}"
        )
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify an official local-recorder Qlib LightGBM batch, "
            "including an honestly preserved terminal blocker."
        )
    )
    parser.add_argument("batch_directory", type=_directory)
    return parser


def _read(path: Path, batch: Path) -> dict[str, Any]:
    if not path.is_file():
        raise VerificationFailure(
            f"missing artifact: {path.relative_to(batch).as_posix()}"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationFailure(f"invalid JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise VerificationFailure(f"JSON artifact is not an object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require(value: bool, message: str) -> None:
    if not value:
        raise VerificationFailure(message)


def verify(batch: Path) -> None:
    report = _read(batch / "batch_report.json", batch)
    if report.get("status") == "completed":
        _verify_completed(batch, report)
        return
    proposed = _read(
        batch / "proposed_registry_status_update.json", batch
    )
    run = batch / "run-01"
    request = _read(run / "runner_request.json", batch)
    execution = _read(run / "execution_report.json", batch)
    failure = _read(run / "local_recorder_failure.json", batch)
    manifest = _read(run / "experiment_manifest.json", batch)
    inventory = _read(run / "artifact_inventory.json", batch)

    _require(report.get("status") == "blocked", "batch is not blocked")
    _require(
        report.get("attempted_run_count") == 1
        and report.get("successful_run_count") == 0,
        "unexpected successful or attempted run count",
    )
    _require(
        report.get("second_run_attempted") is False
        and not (batch / "run-02").exists(),
        "a prohibited second run exists",
    )
    _require(
        report.get("three_model_comparison_produced") is False,
        "comparison was incorrectly reported",
    )
    _require(
        proposed.get("qlib_lightgbm_status") == "adoption_specified"
        and proposed.get("proposed_changes") == [],
        "registry promotion was incorrectly proposed",
    )
    _require(
        failure.get("blocker_id")
        == "mlflow_file_store_opt_in_required",
        "unexpected local-recorder blocker",
    )
    _require(
        failure.get("qlib_initialization_succeeded") is True,
        "Qlib initialization success was not preserved",
    )
    _require(
        failure.get("r_start_completed") is False
        and failure.get("lgbmodel_fit_started") is False
        and failure.get("lgbmodel_predict_started") is False,
        "execution advanced past the recorded blocker",
    )
    _require(
        failure.get("environment_opt_in_changed") is False
        and failure.get("fallback_used") is False,
        "an unauthorized opt-in or fallback was used",
    )
    stderr = str(execution.get("stderr", ""))
    _require(
        execution.get("exit_code") != 0
        and "MLFLOW_ALLOW_FILE_STORE=true" in stderr
        and "filesystem tracking backend" in stderr,
        "MLflow file-store rejection is not preserved",
    )
    _require(manifest.get("status") == "failed", "manifest is not failed")
    _require(
        manifest.get("predictions_produced") is False
        and manifest.get("evaluation_produced") is False,
        "manifest reports downstream results",
    )
    uri = request.get("tracking_uri", "")
    parsed = urlparse(uri)
    _require(
        parsed.scheme == "file" and not parsed.netloc,
        "request did not use a hostless local file URI",
    )
    _require(
        request.get("experiment_name")
        == "qlib-lightgbm-offline-synthetic",
        "experiment name mismatch",
    )
    _require(
        request.get("model_construction", {}).get("parameters", {})
        .get("num_threads") == 1,
        "frozen single-thread model setting is missing",
    )
    forbidden = (
        "qlib_lightgbm_predictions.csv",
        "qlib_lightgbm_signals.csv",
        "reproducibility_report.json",
        "model_comparison.csv",
        "model_comparison.json",
    )
    _require(
        all(not (run / name).exists() for name in forbidden),
        "prediction, comparison, or reproducibility artifacts exist",
    )
    for entry in inventory.get("artifacts", []):
        relative = entry.get("relative_path")
        _require(isinstance(relative, str), "invalid inventory entry")
        artifact = run / relative
        _require(artifact.is_file(), f"missing inventoried file: {relative}")
        _require(
            artifact.stat().st_size == entry.get("size_bytes")
            and _sha256(artifact) == entry.get("sha256"),
            f"inventory mismatch: {relative}",
        )


def _verify_completed(batch: Path, report: dict[str, Any]) -> None:
    reproduction = _read(batch / "reproducibility_report.json", batch)
    _require(
        report.get("official_local_recorder") is True
        and report.get("registry_source_mutated_at_runtime") is False,
        "completed batch lacks official local-recorder provenance",
    )
    _require(
        reproduction.get("passed") is True
        and reproduction.get("tolerance") == 1e-12
        and reproduction.get("maximum_prediction_difference") <= 1e-12
        and reproduction.get("maximum_gain_importance_difference") <= 1e-12
        and reproduction.get("maximum_split_importance_difference") <= 1e-12,
        "fixed reproducibility acceptance did not pass",
    )
    runs = [batch / "run-01", batch / "run-02"]
    _require(all(run.is_dir() for run in runs), "expected two run directories")
    recorder_ids: set[str] = set()
    protocols: set[str] = set()
    model_fingerprints: set[str] = set()
    expected_controls = {
        "MKL_NUM_THREADS": "1",
        "MLFLOW_ALLOW_FILE_STORE": "true",
        "NUMEXPR_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
    }
    for run in runs:
        metadata = _read(run / "qlib_lightgbm_metadata.json", batch)
        audit = _read(run / "qlib_recorder_audit.json", batch)
        manifest = _read(run / "experiment_manifest.json", batch)
        inventory = _read(run / "artifact_inventory.json", batch)
        comparison = _read(run / "model_comparison.json", batch)
        _require(
            metadata.get("status") == "completed"
            and metadata.get("model_class")
            == "qlib.contrib.model.gbdt.LGBModel"
            and metadata.get("versions", {}).get("qlib") == "0.9.7"
            and metadata.get("versions", {}).get("lightgbm") == "4.6.0"
            and metadata.get("versions", {}).get("mlflow") == "3.14.0",
            f"official model/version metadata mismatch: {run.name}",
        )
        _require(
            metadata.get("subprocess_environment_controls")
            == expected_controls
            and metadata.get("parent_mlflow_allow_file_store") is None
            and metadata.get("subprocess_only_file_store_opt_in") is True,
            f"subprocess-only environment boundary failed: {run.name}",
        )
        uri = str(audit.get("tracking_uri", ""))
        parsed = urlparse(uri)
        tracking = Path(audit.get("tracking_directory", "")).resolve()
        _require(
            parsed.scheme == "file"
            and not parsed.netloc
            and tracking.is_relative_to(run.resolve()),
            f"tracking is not local to the run: {run.name}",
        )
        _require(
            audit.get("implementation")
            == "qlib.workflow.expm.MLflowExpManager"
            and audit.get("recorder_implementation")
            == "qlib.workflow.recorder.MLflowRecorder"
            and audit.get("recorder_final_status") == "FINISHED"
            and audit.get("file_store_opt_in_observed") == "true"
            and audit.get("workflow_files"),
            f"recorder audit mismatch: {run.name}",
        )
        recorder_ids.add(str(audit.get("recorder_id")))
        _require(
            metadata.get("training_completed") is True
            and metadata.get("prediction_completed") is True
            and metadata.get("prediction_count") == 1200
            and metadata.get("direct_lightgbm_fit_used") is False
            and metadata.get("network_used") is False
            and metadata.get("mlflow_server_started") is False,
            f"model execution boundary mismatch: {run.name}",
        )
        _require(
            manifest.get("status") == "completed",
            f"manifest is not completed: {run.name}",
        )
        forbidden_keys = {
            "winner", "universal_winner", "sharpe", "portfolio_return",
            "profitability",
        }
        _require(
            not forbidden_keys.intersection(comparison),
            f"forbidden comparison claim: {run.name}",
        )
        models = comparison.get("models", [])
        _require(
            len(models) == 3
            and comparison.get("coverage_differences_reported") is True
            and comparison.get("portfolio_metrics_calculated") is False,
            f"three-model comparison mismatch: {run.name}",
        )
        protocols.update(
            item.get("evaluation_protocol_fingerprint") for item in models
        )
        model_fingerprints.update(
            item.get("model_configuration_fingerprint") for item in models
        )
        for entry in inventory.get("artifacts", []):
            relative = entry.get("relative_path")
            _require(isinstance(relative, str), "invalid inventory entry")
            artifact = run / relative
            _require(
                artifact.is_file()
                and artifact.stat().st_size == entry.get("size_bytes")
                and _sha256(artifact) == entry.get("sha256"),
                f"inventory mismatch: {run.name}/{relative}",
            )
    _require(len(recorder_ids) == 2, "recorder IDs are not unique")
    _require(len(protocols) == 1, "models do not share one protocol")
    _require(len(model_fingerprints) == 3, "model fingerprints are not distinct")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        verify(args.batch_directory)
    except Exception as exc:
        print(f"Verification failed: {exc}", file=sys.stderr)
        return 1
    print("Qlib LightGBM local-recorder evidence verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
