"""Product-side orchestration for official local-recorder Qlib LightGBM runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import numpy as np
import pandas as pd

from stock_research.adapters import convert_qlib_predictions
from stock_research.comparison import compare_evaluations
from stock_research.evaluation import EvaluationProtocol, evaluate_signals
from stock_research.fingerprints import (
    fingerprint_file,
    model_configuration_fingerprint,
)
from stock_research.qlib_lightgbm_compatibility import (
    DEFAULT_ENVIRONMENT_REPORT,
    DEFAULT_FROZEN_SPECIFICATION,
    DEFAULT_INTERPRETER,
    DEFAULT_LINEAR_BATCH,
    DEFAULT_OUTPUT_ROOT,
    FIT_CONFIGURATION,
    MODEL_CONSTRUCTION,
    MODEL_ID,
    validate_frozen_lightgbm_inputs,
)
from stock_research.synthetic_qlib import (
    THREAD_CONTROLS,
    write_canonical_csv,
    write_canonical_json,
)


EXPERIMENT_NAME = "qlib-lightgbm-offline-synthetic"
LIGHTGBM_SUBPROCESS_CONTROLS = {
    "MLFLOW_ALLOW_FILE_STORE": "true",
    **THREAD_CONTROLS,
}
FORBIDDEN_MLFLOW_ENVIRONMENT = (
    "MLFLOW_TRACKING_URI",
    "MLFLOW_REGISTRY_URI",
    "MLFLOW_TRACKING_USERNAME",
    "MLFLOW_TRACKING_PASSWORD",
    "MLFLOW_TRACKING_TOKEN",
)
RUNNER_PATH = Path("research/runners/qlib_lightgbm_local_runner.py")
PLANNED_MANIFEST = Path(
    "research/manifests/qlib_lightgbm_local_reproduction_planned.json"
)


@dataclass(frozen=True, slots=True)
class QlibLightGBMReproductionConfig:
    seed: int = 20260730
    output_root: Path = DEFAULT_OUTPUT_ROOT
    frozen_linear_batch: Path = DEFAULT_LINEAR_BATCH
    qlib_interpreter: Path = DEFAULT_INTERPRETER
    environment_report: Path = DEFAULT_ENVIRONMENT_REPORT
    frozen_specification: Path = DEFAULT_FROZEN_SPECIFICATION
    reruns: int = 2
    reproducibility_tolerance: float = 1e-12
    batch_id: str | None = None
    keep_failed_artifacts: bool = True
    resume_completed_run_one: bool = False

    def __post_init__(self) -> None:
        if self.seed != 20260730:
            raise ValueError("seed is frozen at 20260730")
        if isinstance(self.reruns, bool) or self.reruns != 2:
            raise ValueError("reruns must be exactly 2")
        tolerance = float(self.reproducibility_tolerance)
        if not np.isfinite(tolerance) or tolerance != 1e-12:
            raise ValueError("reproducibility_tolerance is frozen at 1e-12")
        for field in (
            "output_root", "frozen_linear_batch", "qlib_interpreter",
            "environment_report", "frozen_specification",
        ):
            object.__setattr__(self, field, Path(getattr(self, field)))


@dataclass(frozen=True, slots=True)
class QlibLightGBMReproductionPlan:
    batch_id: str
    output_directory: Path
    commands: tuple[tuple[str, ...], ...]
    selected_source_run: Path
    environment_fingerprint: str
    resolved_lock_sha256: str
    qlib_gbdt_source_sha256: str
    model_configuration_fingerprint: str
    evaluation_protocol_fingerprint: str
    tracking_uris: tuple[str, ...]
    subprocess_environment_controls: dict[str, str]
    parent_mlflow_allow_file_store: str | None


@dataclass(frozen=True, slots=True)
class QlibLightGBMRunResult:
    run_id: str
    directory: Path
    execution_report: dict[str, Any]
    lightgbm_evaluation: dict[str, Any]
    linear_evaluation: dict[str, Any]
    research_v2_evaluation: dict[str, Any]


@dataclass(frozen=True, slots=True)
class QlibLightGBMBatchResult:
    batch_id: str
    directory: Path
    runs: tuple[QlibLightGBMRunResult, ...]
    reproducibility: dict[str, Any]


def _model_configuration(specification: dict[str, Any]) -> dict[str, Any]:
    parameters = {
        key: value for key, value in MODEL_CONSTRUCTION.items()
        if key not in {"loss", "num_boost_round", "early_stopping_rounds"}
    }
    return {
        "model_id": MODEL_ID,
        "upstream_package": "pyqlib==0.9.7",
        "upstream_class": "qlib.contrib.model.gbdt.LGBModel",
        "lightgbm_version": "4.6.0",
        "loss": MODEL_CONSTRUCTION["loss"],
        "num_boost_round": MODEL_CONSTRUCTION["num_boost_round"],
        "early_stopping_rounds":
            MODEL_CONSTRUCTION["early_stopping_rounds"],
        "parameters": parameters,
        "fit_configuration": FIT_CONFIGURATION,
        "features": specification["feature_list"],
        "seed": 20260730,
        "training_segment": "train",
        "validation_use": "early_stopping_only",
        "prediction_segment": "test",
    }


def _beneath(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def build_lightgbm_subprocess_environment(
    base: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, str | None]]:
    """Inject the authorized opt-in into this child environment only."""

    parent = dict(os.environ if base is None else base)
    observed = parent.get("MLFLOW_ALLOW_FILE_STORE")
    if observed is not None:
        raise ValueError(
            "parent MLFLOW_ALLOW_FILE_STORE must be absent; the opt-in "
            "is subprocess-only"
        )
    inherited_remote = {
        name: parent[name]
        for name in FORBIDDEN_MLFLOW_ENVIRONMENT if name in parent
    }
    if inherited_remote:
        raise ValueError(
            "remote MLflow environment is prohibited: "
            f"{sorted(inherited_remote)}"
        )
    child = dict(parent)
    child.update(LIGHTGBM_SUBPROCESS_CONTROLS)
    audit = {
        "parent_mlflow_allow_file_store": observed,
        "subprocess_only_opt_in": "true",
    }
    return child, audit


def validate_local_recorder_paths(
    run_directory: str | Path,
) -> dict[str, str | Path]:
    """Return the only permitted local Qlib recorder paths and URI."""

    run = Path(run_directory).resolve()
    provider = (run / "qlib-provider").resolve()
    tracking = (run / "qlib-workflow/mlruns").resolve()
    if run.as_posix().startswith("//"):
        raise ValueError("UNC or network run directories are prohibited")
    if not _beneath(provider, run) or not _beneath(tracking, run):
        raise ValueError("recorder paths must remain beneath the run directory")
    uri = tracking.as_uri()
    parsed = urlparse(uri)
    if parsed.scheme != "file" or parsed.netloc:
        raise ValueError("tracking URI must be a hostless local file URI")
    repository = Path(subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()).resolve()
    if _beneath(run, repository):
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", str(run)],
            capture_output=True, check=False,
        )
        if ignored.returncode != 0:
            raise ValueError(f"run directory is not ignored by Git: {run}")
    for path in (run, provider, tracking):
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path)],
            capture_output=True, check=False,
        )
        if tracked.returncode == 0:
            raise ValueError(f"recorder path is source-controlled: {path}")
    return {
        "run_directory": run,
        "provider_path": provider,
        "tracking_path": tracking,
        "tracking_uri": uri,
    }


def _compatibility_config(
    config: QlibLightGBMReproductionConfig,
):
    from stock_research.qlib_lightgbm_compatibility import (
        QlibLightGBMCompatibilityConfig,
    )
    return QlibLightGBMCompatibilityConfig(
        seed=config.seed,
        attempts=1,
        output_root=config.output_root,
        frozen_linear_batch=config.frozen_linear_batch,
        qlib_interpreter=config.qlib_interpreter,
        environment_report=config.environment_report,
        frozen_specification=config.frozen_specification,
        batch_id=config.batch_id,
        keep_failed_artifacts=config.keep_failed_artifacts,
    )


def plan_qlib_lightgbm_reproduction(
    config: QlibLightGBMReproductionConfig | None = None,
) -> QlibLightGBMReproductionPlan:
    selected = config or QlibLightGBMReproductionConfig()
    specification, source_run, environment = (
        validate_frozen_lightgbm_inputs(_compatibility_config(selected))
    )
    if not RUNNER_PATH.is_file():
        raise ValueError(f"local-recorder runner is missing: {RUNNER_PATH}")
    batch_id = selected.batch_id or str(uuid4())
    directory = selected.output_root / batch_id
    if directory.exists() and not selected.resume_completed_run_one:
        raise ValueError(f"refusing preexisting batch directory: {directory}")
    if selected.resume_completed_run_one:
        run_one = directory / "run-01"
        if (
            not run_one.is_dir()
            or (directory / "run-02").exists()
            or not (run_one / "qlib_lightgbm_metadata.json").is_file()
            or not (run_one / "qlib_lightgbm_predictions.csv").is_file()
        ):
            raise ValueError(
                "resume requires one completed runner output and no run-02"
            )
    _, environment_audit = build_lightgbm_subprocess_environment()
    local = [
        validate_local_recorder_paths(directory / f"run-{number:02d}")
        for number in range(1, 3)
    ]
    commands = tuple(
        (
            str(selected.qlib_interpreter),
            str(RUNNER_PATH),
            str(directory / f"run-{number:02d}/runner_request.json"),
        )
        for number in range(1, 3)
    )
    return QlibLightGBMReproductionPlan(
        batch_id=batch_id,
        output_directory=directory,
        commands=commands,
        selected_source_run=source_run,
        environment_fingerprint=specification["environment_fingerprint"],
        resolved_lock_sha256=environment["lock_sha256"],
        qlib_gbdt_source_sha256=environment["gbdt_source_sha256"],
        model_configuration_fingerprint=model_configuration_fingerprint(
            _model_configuration(specification)
        ),
        evaluation_protocol_fingerprint=
            specification["evaluation_protocol_fingerprint"],
        tracking_uris=tuple(str(item["tracking_uri"]) for item in local),
        subprocess_environment_controls=
            dict(LIGHTGBM_SUBPROCESS_CONTROLS),
        parent_mlflow_allow_file_store=
            environment_audit["parent_mlflow_allow_file_store"],
    )


def _protocol(source_run: Path) -> EvaluationProtocol:
    raw = json.loads(
        (source_run / "evaluation_protocol.json").read_text(encoding="utf-8")
    )
    return EvaluationProtocol(
        label_name=raw["label_name"],
        label_definition=raw["label_definition"],
        label_dataset_fingerprint=raw["label_dataset_fingerprint"],
        train_start=raw["train"]["start"],
        train_end=raw["train"]["end"],
        validation_start=raw["validation"]["start"],
        validation_end=raw["validation"]["end"],
        test_start=raw["test"]["start"],
        test_end=raw["test"]["end"],
        purge_days=raw["purge_days"],
        embargo_days=raw["embargo_days"],
        evaluation_frequency=raw["evaluation_frequency"],
        metric_definitions=raw["metric_definitions"],
        annualization_factor=raw["annualization_factor"],
        minimum_cross_sectional_observations=
            raw["minimum_cross_sectional_observations"],
        test_universe_policy=raw["test_universe_policy"],
    )


def _inventory(directory: Path) -> list[dict[str, Any]]:
    excluded = {
        "artifact_inventory.json", "execution_report.json",
        "experiment_manifest.json",
    }
    rows = []
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        relative = path.relative_to(directory).as_posix()
        if relative in excluded:
            continue
        rows.append({
            "relative_path": relative,
            "sha256": fingerprint_file(path),
            "size_bytes": path.stat().st_size,
            "role": relative.split("/", 1)[0],
            "producing_environment": (
                "qlib-python-3.12"
                if relative.startswith((
                    "qlib_", "lightgbm_", "diagnostic_"
                )) else "product-python-3.13"
            ),
            "generated_timestamp": datetime.fromtimestamp(
                path.stat().st_mtime, timezone.utc
            ).isoformat(),
        })
    return rows


def finalize_failed_lightgbm_batch(
    batch_directory: str | Path,
) -> dict[str, Any]:
    """Complete terminal evidence for an already failed first official run."""

    batch = Path(batch_directory)
    run = batch / "run-01"
    execution_path = run / "execution_report.json"
    request_path = run / "runner_request.json"
    if not execution_path.is_file() or not request_path.is_file():
        raise ValueError("failed batch lacks its execution report or request")
    if (batch / "run-02").exists():
        raise ValueError("refusing failure finalization after a second run")
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    request = json.loads(request_path.read_text(encoding="utf-8"))
    stderr = str(execution.get("stderr", ""))
    blocker = (
        "MLFLOW_ALLOW_FILE_STORE=true" in stderr
        and "filesystem tracking backend" in stderr
    )
    if execution.get("exit_code") == 0 or not blocker:
        raise ValueError("execution does not contain the accepted new blocker")
    reason = (
        "Installed MLflow requires explicit MLFLOW_ALLOW_FILE_STORE=true "
        "opt-in before Qlib's local file-backed experiment can start."
    )
    diagnostics = {
        "schema_version": "1.0",
        "status": "blocked",
        "blocker_id": "mlflow_file_store_opt_in_required",
        "failure_type": "MlflowException",
        "failure_reason": reason,
        "qlib_initialization_succeeded":
            "qlib successfully initialized" in stderr,
        "r_start_completed": False,
        "lgbmodel_fit_started": False,
        "lgbmodel_predict_started": False,
        "second_run_attempted": False,
        "environment_opt_in_changed": False,
        "fallback_used": False,
        "registry_promotion_permitted": False,
        "stderr_preserved_in": "execution_report.json",
    }
    write_canonical_json(
        diagnostics, run / "local_recorder_failure.json"
    )
    write_canonical_json({
        "schema_version": "1.0",
        "run_id": request["run_id"],
        "model_id": MODEL_ID,
        "status": "failed",
        "failure_reason": reason,
        "blocker_id": diagnostics["blocker_id"],
        "source_manifest": str(PLANNED_MANIFEST),
        "model_configuration_fingerprint":
            request["model_configuration_fingerprint"],
        "evaluation_protocol_fingerprint":
            request["evaluation_protocol_fingerprint"],
        "predictions_produced": False,
        "evaluation_produced": False,
        "registry_promotion_permitted": False,
        "evidence_scope": (
            "Offline synthetic local-recorder compatibility evidence; "
            "not a LightGBM reproduction."
        ),
    }, run / "experiment_manifest.json")
    write_canonical_json({
        "schema_version": "1.0",
        "self_referential_exclusions": [
            "artifact_inventory.json", "execution_report.json",
            "experiment_manifest.json",
        ],
        "artifacts": _inventory(run),
    }, run / "artifact_inventory.json")
    write_canonical_json({
        "schema_version": "1.0",
        "batch_id": batch.name,
        "status": "blocked",
        "blocker_id": diagnostics["blocker_id"],
        "failure_reason": reason,
        "attempted_run_count": 1,
        "successful_run_count": 0,
        "second_run_attempted": False,
        "reproducibility_evaluated": False,
        "three_model_comparison_produced": False,
        "registry_source_mutated_at_runtime": False,
    }, batch / "batch_report.json")
    write_canonical_json({
        "schema_version": "1.0",
        "proposed_changes": [],
        "qlib_lightgbm_status": "adoption_specified",
        "promotion_blocked": True,
        "reason": reason,
    }, batch / "proposed_registry_status_update.json")
    return diagnostics


def _runner_request(
    *,
    run_id: str,
    directory: Path,
    source_run: Path,
    specification: dict[str, Any],
    environment: dict[str, Any],
    environment_report: Path,
    plan: QlibLightGBMReproductionPlan,
) -> tuple[dict[str, Any], dict[str, Path]]:
    local = validate_local_recorder_paths(directory)
    parameters = {
        key: value for key, value in MODEL_CONSTRUCTION.items()
        if key not in {"loss", "num_boost_round", "early_stopping_rounds"}
    }
    outputs = {
        "predictions": directory / "qlib_lightgbm_predictions.csv",
        "runner_metadata": directory / "qlib_lightgbm_metadata.json",
        "training_history": directory / "lightgbm_training_history.json",
        "feature_importance_gain":
            directory / "lightgbm_feature_importance_gain.csv",
        "feature_importance_split":
            directory / "lightgbm_feature_importance_split.csv",
        "model_dump": directory / "lightgbm_model_dump.json",
        "recorder_audit": directory / "qlib_recorder_audit.json",
    }
    request = {
        "schema_version": "1.0",
        "run_id": run_id,
        "model_id": MODEL_ID,
        "run_directory": str(directory.resolve()),
        "panel_path": str(
            (source_run / "synthetic_qlib_panel.csv").resolve()
        ),
        "panel_sha256":
            specification["canonical_file_hashes"][
                "synthetic_qlib_panel.csv"
            ],
        "environment_report": str(environment_report.resolve()),
        "environment_report_sha256": environment["report_sha256"],
        "environment_fingerprint":
            specification["environment_fingerprint"],
        "resolved_lock": str(environment["lock_path"].resolve()),
        "resolved_lock_sha256": environment["lock_sha256"],
        "qlib_gbdt_source": str(environment["gbdt_source"].resolve()),
        "qlib_gbdt_source_sha256": environment["gbdt_source_sha256"],
        "feature_columns": specification["feature_list"],
        "label_name": specification["label_name"],
        "segments": {
            "train": specification["splits"]["train"],
            "valid": specification["splits"]["validation"],
            "test": specification["splits"]["test"],
        },
        "model_construction": {
            "loss": MODEL_CONSTRUCTION["loss"],
            "num_boost_round": MODEL_CONSTRUCTION["num_boost_round"],
            "early_stopping_rounds":
                MODEL_CONSTRUCTION["early_stopping_rounds"],
            "parameters": parameters,
        },
        "fit_configuration": FIT_CONFIGURATION,
        "model_configuration_fingerprint":
            plan.model_configuration_fingerprint,
        "dataset_fingerprints": specification["dataset_fingerprints"],
        "evaluation_protocol_fingerprint":
            plan.evaluation_protocol_fingerprint,
        "thread_controls": THREAD_CONTROLS,
        "subprocess_environment_controls":
            LIGHTGBM_SUBPROCESS_CONTROLS,
        "parent_environment": {
            "MLFLOW_ALLOW_FILE_STORE": None,
            "remote_mlflow_environment_present": False,
        },
        "subprocess_only_file_store_opt_in": True,
        "provider_path": str(local["provider_path"]),
        "tracking_path": str(local["tracking_path"]),
        "tracking_uri": local["tracking_uri"],
        "experiment_name": EXPERIMENT_NAME,
        "recorder_name": run_id,
        "expected_test_rows": 1200,
        "outputs": {
            name: str(path.resolve()) for name, path in outputs.items()
        },
    }
    return request, outputs


def _execute_run(
    *,
    number: int,
    config: QlibLightGBMReproductionConfig,
    plan: QlibLightGBMReproductionPlan,
    specification: dict[str, Any],
    source_run: Path,
    environment: dict[str, Any],
    labels: pd.DataFrame,
    protocol: EvaluationProtocol,
) -> QlibLightGBMRunResult:
    directory = plan.output_directory / f"run-{number:02d}"
    reuse_runner = config.resume_completed_run_one and number == 1
    if reuse_runner:
        request = json.loads(
            (directory / "runner_request.json").read_text(encoding="utf-8")
        )
        run_id = request["run_id"]
        outputs = {
            name: Path(path) for name, path in request["outputs"].items()
        }
        execution = json.loads(
            (directory / "execution_report.json").read_text(encoding="utf-8")
        )
        if execution.get("exit_code") != 0:
            raise ValueError("resumed runner execution did not complete")
        execution["product_postprocessing_resumed_without_retraining"] = True
        write_canonical_json(
            execution, directory / "execution_report.json"
        )
    else:
        run_id = str(uuid4())
        if directory.exists():
            raise ValueError(f"refusing preexisting run directory: {directory}")
        directory.mkdir(parents=True)
        write_canonical_json({
            "schema_version": "1.0",
            "accepted_source_run": str(source_run),
            "canonical_file_hashes": specification["canonical_file_hashes"],
            "accepted_baseline_hashes":
                specification["accepted_baseline_hashes"],
            "source_artifacts_rewritten": False,
        }, directory / "frozen_input_reference.json")
        request, outputs = _runner_request(
            run_id=run_id, directory=directory, source_run=source_run,
            specification=specification, environment=environment,
            environment_report=config.environment_report, plan=plan,
        )
        request_path = directory / "runner_request.json"
        write_canonical_json(request, request_path)
        command = [
            str(config.qlib_interpreter.resolve()),
            str(RUNNER_PATH.resolve()),
            str(request_path.resolve()),
        ]
        process_environment, environment_audit = (
            build_lightgbm_subprocess_environment()
        )
        started = datetime.now(timezone.utc).isoformat()
        start = time.perf_counter()
        completed = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            env=process_environment, check=False,
        )
        execution = {
            "schema_version": "1.0",
            "run_id": run_id,
            "command": command,
            "thread_controls": THREAD_CONTROLS,
            "subprocess_environment_controls":
                LIGHTGBM_SUBPROCESS_CONTROLS,
            "parent_environment": environment_audit,
            "exit_code": completed.returncode,
            "duration_seconds": time.perf_counter() - start,
            "started_at": started,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "status": (
                "completed" if completed.returncode == 0 else "failed"
            ),
        }
        write_canonical_json(execution, directory / "execution_report.json")
        if completed.returncode != 0:
            if (
                "MLFLOW_ALLOW_FILE_STORE=true" in completed.stderr
                and "filesystem tracking backend" in completed.stderr
            ):
                finalize_failed_lightgbm_batch(plan.output_directory)
            else:
                write_canonical_json({
                    "schema_version": "1.0",
                    "run_id": run_id,
                    "model_id": MODEL_ID,
                    "status": "failed",
                    "failure_reason": completed.stderr.strip(),
                    "predictions_produced":
                        outputs["predictions"].is_file(),
                    "registry_promotion_permitted": False,
                }, directory / "experiment_manifest.json")
            if not config.keep_failed_artifacts:
                shutil.rmtree(directory)
            raise RuntimeError(
                f"Qlib LightGBM run {number} failed: "
                f"{completed.stderr.strip()}"
            )
    missing = [name for name, path in outputs.items() if not path.is_file()]
    if missing:
        raise RuntimeError(f"runner outputs are missing: {missing}")
    metadata = json.loads(
        outputs["runner_metadata"].read_text(encoding="utf-8")
    )
    audit = json.loads(outputs["recorder_audit"].read_text(encoding="utf-8"))
    if (
        metadata.get("status") != "completed"
        or metadata.get("run_id") != run_id
        or metadata.get("model_class")
        != "qlib.contrib.model.gbdt.LGBModel"
        or metadata.get("model_configuration_fingerprint")
        != plan.model_configuration_fingerprint
        or metadata.get("evaluation_protocol_fingerprint")
        != plan.evaluation_protocol_fingerprint
        or metadata.get("prediction_count") != 1200
        or metadata.get("thread_controls") != THREAD_CONTROLS
        or metadata.get("subprocess_environment_controls")
        != LIGHTGBM_SUBPROCESS_CONTROLS
        or audit.get("tracking_uri_local_file_only") is not True
        or audit.get("recorder_implementation")
        != "qlib.workflow.recorder.MLflowRecorder"
        or audit.get("recorder_final_status") != "FINISHED"
        or audit.get("file_store_opt_in_observed") != "true"
        or audit.get("workflow_files") == []
    ):
        raise RuntimeError("Qlib runner metadata or recorder audit mismatch")

    lightgbm_signals, dropped = convert_qlib_predictions(
        outputs["predictions"],
        source_run / "qlib_instrument_mapping.csv",
        model_id=MODEL_ID,
        run_id=run_id,
        upstream_model_id=MODEL_ID,
        upstream_run_id=run_id,
    )
    if not dropped.empty or len(lightgbm_signals) != 1200:
        raise RuntimeError("LightGBM signal conversion count mismatch")
    write_canonical_csv(
        lightgbm_signals, directory / "qlib_lightgbm_signals.csv"
    )
    write_canonical_csv(
        dropped, directory / "qlib_unmapped_report.csv"
    )

    linear_signals = pd.read_csv(source_run / "qlib_signals.csv")
    v2_signals = pd.read_csv(source_run / "research_v2_signals.csv")
    linear_summary = json.loads(
        (
            source_run / "evaluation_qlib/evaluation_summary.json"
        ).read_text(encoding="utf-8")
    )
    v2_summary = json.loads(
        (
            source_run
            / "evaluation_research_v2/evaluation_summary.json"
        ).read_text(encoding="utf-8")
    )
    datasets = specification["dataset_fingerprints"]
    lightgbm_eval = evaluate_signals(
        lightgbm_signals, labels, protocol,
        model_configuration_fingerprint=
            plan.model_configuration_fingerprint,
        dataset_fingerprints=datasets,
        provenance={
            "implementation": "Qlib v0.9.7 LGBModel",
            "workflow": "official local file-backed MLflowExpManager",
            "evidence_scope": "offline synthetic-only reproduction",
        },
        output_dir=directory / "evaluation_lightgbm",
    )
    linear_eval = evaluate_signals(
        linear_signals, labels, protocol,
        model_configuration_fingerprint=
            linear_summary["model_configuration_fingerprint"],
        dataset_fingerprints=datasets,
        provenance=linear_summary["provenance"],
        output_dir=directory / "evaluation_linear",
    )
    v2_eval = evaluate_signals(
        v2_signals, labels, protocol,
        model_configuration_fingerprint=
            v2_summary["model_configuration_fingerprint"],
        dataset_fingerprints=datasets,
        provenance=v2_summary["provenance"],
        output_dir=directory / "evaluation_research_v2",
    )
    summaries = [
        lightgbm_eval.summary, linear_eval.summary, v2_eval.summary
    ]
    protocols = {
        item["evaluation_protocol_fingerprint"] for item in summaries
    }
    models = {
        item["model_configuration_fingerprint"] for item in summaries
    }
    if len(protocols) != 1 or len(models) != 3:
        raise RuntimeError("three-model fairness fingerprint boundary failed")
    if any(item["valid_ic_dates"] < 2 for item in summaries):
        raise RuntimeError("three-model evaluation lacks finite IC dates")
    comparison = compare_evaluations(
        summaries, output_path=directory / "model_comparison.csv"
    )
    write_canonical_json({
        "schema_version": "1.0",
        "evaluation_protocol_fingerprint": protocol.fingerprint,
        "model_configuration_fingerprints": sorted(models),
        "coverage_differences_reported": True,
        "portfolio_metrics_calculated": False,
        "models": comparison.to_dict("records"),
    }, directory / "model_comparison.json")
    write_canonical_json({
        "schema_version": "1.0",
        "proposed_changes": [{
            "registry_id": "qlib_lightgbm",
            "proposed_status": "synthetic_reproduced",
        }],
        "runtime_mutated_registry": False,
        "conditional_on_batch_verification": True,
        "evidence_scope": (
            "Offline synthetic-only reproduction; not real-market "
            "validation, investment evidence, or benchmark reproduction."
        ),
    }, directory / "proposed_registry_status_update.json")
    write_canonical_json({
        "schema_version": "1.0",
        "run_id": run_id,
        "model_id": MODEL_ID,
        "status": "completed",
        "source_manifest": str(PLANNED_MANIFEST),
        "source_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True,
            text=True, check=True,
        ).stdout.strip(),
        "worktree_status": subprocess.run(
            ["git", "status", "--short"], capture_output=True,
            text=True, check=True,
        ).stdout.strip(),
        "model_configuration": _model_configuration(specification),
        "model_configuration_fingerprint":
            plan.model_configuration_fingerprint,
        "evaluation_protocol_fingerprint": protocol.fingerprint,
        "dataset_fingerprints": datasets,
        "evaluation_artifacts": [
            {
                "path": str(path),
                "sha256": fingerprint_file(path),
            }
            for path in (
                directory / "evaluation_lightgbm/evaluation_summary.json",
                directory / "evaluation_linear/evaluation_summary.json",
                directory
                / "evaluation_research_v2/evaluation_summary.json",
                directory / "model_comparison.csv",
            )
        ],
        "notes": "Official local-recorder offline synthetic reproduction.",
        "evidence_scope": "offline synthetic-only reproduction",
    }, directory / "experiment_manifest.json")
    write_canonical_json({
        "schema_version": "1.0",
        "self_referential_exclusions": [
            "artifact_inventory.json", "execution_report.json",
            "experiment_manifest.json",
        ],
        "artifacts": _inventory(directory),
    }, directory / "artifact_inventory.json")
    return QlibLightGBMRunResult(
        run_id=run_id,
        directory=directory,
        execution_report=execution,
        lightgbm_evaluation=lightgbm_eval.summary,
        linear_evaluation=linear_eval.summary,
        research_v2_evaluation=v2_eval.summary,
    )


def compare_lightgbm_reproduction_runs(
    first: str | Path,
    second: str | Path,
    *,
    tolerance: float = 1e-12,
) -> dict[str, Any]:
    if tolerance != 1e-12:
        raise ValueError("tolerance is frozen at 1e-12")
    one, two = Path(first), Path(second)
    first_predictions = pd.read_csv(
        one / "qlib_lightgbm_predictions.csv"
    )
    second_predictions = pd.read_csv(
        two / "qlib_lightgbm_predictions.csv"
    )
    keys = ["datetime", "instrument"]
    order_identical = first_predictions[keys].equals(
        second_predictions[keys]
    )
    prediction_difference = (
        float(np.max(np.abs(
            first_predictions["score"].to_numpy(float)
            - second_predictions["score"].to_numpy(float)
        ))) if order_identical else float("inf")
    )
    differences: dict[str, float] = {}
    importance_order = True
    for kind, column in (
        ("gain", "importance_gain"), ("split", "importance_split")
    ):
        left = pd.read_csv(
            one / f"lightgbm_feature_importance_{kind}.csv"
        )
        right = pd.read_csv(
            two / f"lightgbm_feature_importance_{kind}.csv"
        )
        importance_order &= left["feature"].equals(right["feature"])
        differences[kind] = (
            float(np.max(np.abs(
                left[column].to_numpy(float)
                - right[column].to_numpy(float)
            ))) if importance_order else float("inf")
        )
    first_metadata = json.loads(
        (one / "qlib_lightgbm_metadata.json").read_text(encoding="utf-8")
    )
    second_metadata = json.loads(
        (two / "qlib_lightgbm_metadata.json").read_text(encoding="utf-8")
    )
    checks = {
        "prediction_order_identical": order_identical,
        "importance_feature_order_identical": importance_order,
        "dataset_fingerprints_identical":
            first_metadata["dataset_fingerprints"]
            == second_metadata["dataset_fingerprints"],
        "model_configuration_fingerprint_identical":
            first_metadata["model_configuration_fingerprint"]
            == second_metadata["model_configuration_fingerprint"],
        "evaluation_protocol_fingerprint_identical":
            first_metadata["evaluation_protocol_fingerprint"]
            == second_metadata["evaluation_protocol_fingerprint"],
        "best_iteration_identical":
            first_metadata["best_iteration"]
            == second_metadata["best_iteration"],
        "tree_count_identical":
            first_metadata["tree_count"] == second_metadata["tree_count"],
        "thread_controls_identical":
            first_metadata["thread_controls"]
            == second_metadata["thread_controls"],
        "subprocess_environment_controls_identical":
            first_metadata["subprocess_environment_controls"]
            == second_metadata["subprocess_environment_controls"]
            == LIGHTGBM_SUBPROCESS_CONTROLS,
        "status_counts_identical": (
            pd.read_csv(one / "evaluation_lightgbm/daily_ic.csv")["status"]
            .value_counts().to_dict()
            == pd.read_csv(
                two / "evaluation_lightgbm/daily_ic.csv"
            )["status"].value_counts().to_dict()
        ),
    }
    passed = (
        all(checks.values())
        and prediction_difference <= tolerance
        and differences["gain"] <= tolerance
        and differences["split"] <= tolerance
    )
    report = {
        "schema_version": "1.0",
        "tolerance": tolerance,
        "maximum_prediction_difference": prediction_difference,
        "maximum_gain_importance_difference": differences["gain"],
        "maximum_split_importance_difference": differences["split"],
        "checks": checks,
        "passed": passed,
        "tolerance_relaxed": False,
    }
    if not passed:
        raise RuntimeError(
            f"Qlib LightGBM reproducibility acceptance failed: {report}"
        )
    return report


def run_qlib_lightgbm_reproduction(
    config: QlibLightGBMReproductionConfig | None = None,
) -> QlibLightGBMBatchResult:
    selected = config or QlibLightGBMReproductionConfig()
    plan = plan_qlib_lightgbm_reproduction(selected)
    specification, source_run, environment = (
        validate_frozen_lightgbm_inputs(_compatibility_config(selected))
    )
    protocol = _protocol(source_run)
    if protocol.fingerprint != plan.evaluation_protocol_fingerprint:
        raise ValueError("frozen evaluation protocol fingerprint mismatch")
    labels = pd.read_csv(
        source_run / "synthetic_labels.csv",
        dtype={"as_of_date": str, "label_end_date": str},
        float_precision="round_trip",
    )
    plan.output_directory.mkdir(
        parents=True, exist_ok=selected.resume_completed_run_one
    )
    completed_runs = []
    for number in range(1, 3):
        completed_runs.append(_execute_run(
            number=number, config=selected, plan=plan,
            specification=specification, source_run=source_run,
            environment=environment, labels=labels, protocol=protocol,
        ))
    runs = tuple(completed_runs)
    reproducibility = compare_lightgbm_reproduction_runs(
        runs[0].directory, runs[1].directory,
        tolerance=selected.reproducibility_tolerance,
    )
    reproducibility.update({
        "batch_id": plan.batch_id,
        "evaluation_protocol_fingerprint": protocol.fingerprint,
    })
    write_canonical_json(
        reproducibility,
        plan.output_directory / "reproducibility_report.json",
    )
    write_canonical_json({
        "schema_version": "1.0",
        "batch_id": plan.batch_id,
        "status": "completed",
        "run_ids": [run.run_id for run in runs],
        "official_local_recorder": True,
        "run_one_retrained": False,
        "run_one_product_postprocessing_resumed":
            selected.resume_completed_run_one,
        "registry_source_mutated_at_runtime": False,
        "evidence_scope": (
            "Offline deterministic synthetic-only reproduction; not "
            "real-market validation, investment evidence, or benchmark "
            "reproduction."
        ),
    }, plan.output_directory / "batch_report.json")
    return QlibLightGBMBatchResult(
        batch_id=plan.batch_id,
        directory=plan.output_directory,
        runs=runs,
        reproducibility=reproducibility,
    )
