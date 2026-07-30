"""Verify a preserved, blocked Qlib LightGBM compatibility attempt."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence


class VerificationFailure(RuntimeError):
    """Expected failure while validating compatibility evidence."""


def _batch_directory(value: str) -> Path:
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
            "Verify evidence from the single blocked official Qlib "
            "LightGBM compatibility attempt."
        )
    )
    parser.add_argument(
        "batch_directory",
        type=_batch_directory,
        help="existing generated Qlib LightGBM compatibility batch",
    )
    return parser


def _read_json(path: Path, batch: Path) -> dict[str, Any]:
    if not path.is_file():
        raise VerificationFailure(
            f"missing required artifact: {path.relative_to(batch).as_posix()}"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationFailure(
            f"invalid JSON artifact {path.relative_to(batch).as_posix()}: "
            f"{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise VerificationFailure(
            "JSON artifact must contain an object: "
            f"{path.relative_to(batch).as_posix()}"
        )
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationFailure(message)


def verify(batch: Path) -> None:
    attempt = batch / "attempt-01"
    _require(attempt.is_dir(), "missing required attempt directory: attempt-01")
    _require(
        not (batch / "attempt-02").exists(),
        "unexpected second compatibility attempt",
    )

    batch_report = _read_json(batch / "batch_execution_report.json", batch)
    proposed = _read_json(
        batch / "proposed_registry_status_update.json", batch
    )
    metadata = _read_json(
        attempt / "qlib_lightgbm_runner_metadata.json", batch
    )
    failure = _read_json(attempt / "compatibility_failure.json", batch)
    execution = _read_json(attempt / "execution_report.json", batch)
    manifest = _read_json(attempt / "failed_manifest.json", batch)
    history = _read_json(
        attempt / "lightgbm_training_history.json", batch
    )
    inventory = _read_json(attempt / "artifact_inventory.json", batch)

    _require(batch_report.get("status") == "blocked", "batch is not blocked")
    _require(batch_report.get("attempt_count") == 1, "attempt count is not one")
    _require(
        batch_report.get("second_attempt_permitted") is False,
        "batch permits a prohibited second attempt",
    )
    _require(
        batch_report.get("registry_source_mutated_at_runtime") is False,
        "runtime registry mutation was reported",
    )
    _require(
        proposed.get("qlib_lightgbm_status") == "adoption_specified"
        and proposed.get("proposed_changes") == [],
        "registry evidence incorrectly promotes LightGBM",
    )

    _require(
        metadata.get("model_class")
        == "qlib.contrib.model.gbdt.LGBModel",
        "official Qlib LGBModel was not recorded",
    )
    _require(
        metadata.get("versions", {}).get("qlib") == "0.9.7",
        "Qlib version is not 0.9.7",
    )
    _require(
        metadata.get("versions", {}).get("lightgbm") == "4.6.0",
        "LightGBM version is not 4.6.0",
    )
    _require(
        metadata.get("qlib_gbdt_source_sha256")
        == "062874b847ebd6426b5f54a263d5dbce49b18d528ea35dae96b6a31dbf7f3c66",
        "Qlib gbdt.py source hash mismatch",
    )
    _require(
        metadata.get("environment_fingerprint")
        == "a7d1b7472d2f5e09927b8859aec082c8e986b5ee30f82289635e4b11e91eea99",
        "environment fingerprint mismatch",
    )
    _require(
        metadata.get("resolved_lock_sha256")
        == "7028da531668b7d119e249e4258112977ea8618bbe8f378864ad8af84f6e924b",
        "resolved lock hash mismatch",
    )
    _require(
        metadata.get("evaluation_protocol_fingerprint")
        == "210bca5c4ac474f766a3caf549d8adc4dc06ae22b3378eb70f4ed224f6978782",
        "evaluation protocol fingerprint mismatch",
    )
    _require(
        metadata.get("dataset_fingerprints", {}).get("labels")
        == "7412fc79f8af0acf87b1cb22209842d153e8a6b6e9370e147b43e454ca247f2d",
        "label dataset fingerprint mismatch",
    )
    _require(
        metadata.get("thread_controls")
        == {
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
        },
        "single-thread controls do not match the frozen protocol",
    )
    for key in (
        "provider_initialized",
        "mlflow_initialized",
        "network_used",
        "pickle_written",
        "predictions_written",
    ):
        _require(metadata.get(key) is False, f"prohibited action recorded: {key}")

    _require(failure.get("status") == "blocked", "failure is not blocked")
    _require(failure.get("blocker_matched") is True, "blocker did not match")
    _require(
        failure.get("training_completed_before_workflow_failure") is True,
        "training did not complete before the workflow failure",
    )
    _require(
        failure.get("predictions_attempted") is False,
        "prediction was attempted after the blocker",
    )
    _require(
        failure.get("fallback_used") is False
        and failure.get("parameters_relaxed") is False,
        "fallback or parameter relaxation was recorded",
    )
    traceback = str(failure.get("traceback", ""))
    _require(
        "R.log_metrics" in traceback
        and "Please run qlib.init() first using qlib" in traceback,
        "failure evidence does not identify the R.log_metrics dependency",
    )
    _require(execution.get("exit_code") != 0, "runner unexpectedly exited zero")
    _require(
        execution.get("blocker_matched") is True,
        "execution report did not match the blocker",
    )
    _require(manifest.get("status") == "blocked", "manifest is not blocked")
    _require(
        manifest.get("predictions_produced") is False
        and manifest.get("evaluation_produced") is False,
        "manifest reports prohibited downstream artifacts",
    )
    _require(
        isinstance(history.get("train", {}).get("l2"), list)
        and isinstance(history.get("valid", {}).get("l2"), list)
        and len(history["train"]["l2"]) >= int(metadata.get("tree_count", 0))
        and len(history["valid"]["l2"]) >= int(metadata.get("tree_count", 0)),
        "substantive train/valid history is missing",
    )

    for entry in inventory.get("artifacts", []):
        relative = entry.get("relative_path")
        _require(isinstance(relative, str), "invalid inventory path")
        artifact = attempt / relative
        _require(artifact.is_file(), f"missing inventoried artifact: {relative}")
        _require(
            artifact.stat().st_size == entry.get("size_bytes"),
            f"size mismatch for inventoried artifact: {relative}",
        )
        _require(
            _sha256(artifact) == entry.get("sha256"),
            f"SHA-256 mismatch for inventoried artifact: {relative}",
        )

    forbidden = (
        "qlib_lightgbm_signals.csv",
        "qlib_lightgbm_predictions.csv",
        "comparison.csv",
        "comparison.json",
    )
    _require(
        all(not (attempt / name).exists() for name in forbidden),
        "prohibited prediction or comparison artifact exists",
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        verify(args.batch_directory)
    except Exception as exc:
        print(f"Verification failed: {exc}", file=sys.stderr)
        return 1
    print("Qlib LightGBM compatibility blocker verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
