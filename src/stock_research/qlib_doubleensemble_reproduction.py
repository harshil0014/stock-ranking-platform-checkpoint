"""Qlib-free orchestration for the official DoubleEnsemble reproduction."""

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
from uuid import uuid4

import numpy as np
import pandas as pd

from stock_research.adapters import convert_qlib_predictions
from stock_research.comparison import compare_evaluations
from stock_research.evaluation import EvaluationProtocol, evaluate_signals
from stock_research.fingerprints import fingerprint_file, model_configuration_fingerprint
from stock_research.qlib_lightgbm_compatibility import (
    QlibLightGBMCompatibilityConfig,
    validate_frozen_lightgbm_inputs,
)
from stock_research.synthetic_qlib import write_canonical_csv, write_canonical_json


MODEL_ID = "qlib_doubleensemble_v0_9_7"
DEFAULT_OUTPUT_ROOT = Path("research/generated/qlib-doubleensemble")
DEFAULT_LINEAR_BATCH = Path("research/generated/qlib-linear/final-locked-20260731")
DEFAULT_LIGHTGBM_BATCH = Path(
    "research/generated/qlib-lightgbm/official-local-recorder-opt-in-20260731"
)
DEFAULT_INTERPRETER = Path(".venv-qlib/Scripts/python.exe")
DEFAULT_ENVIRONMENT_REPORT = Path("research/generated/qlib-environment-verified.json")
DEFAULT_SPECIFICATION = Path(
    "research/specifications/qlib_doubleensemble_frozen_protocol.json"
)
LIGHTGBM_SPECIFICATION = Path(
    "research/specifications/qlib_lightgbm_frozen_protocol.json"
)
RUNNER_PATH = Path("research/runners/qlib_doubleensemble_runner.py")
PLANNED_MANIFEST = Path(
    "research/manifests/qlib_doubleensemble_reproduction_planned.json"
)
SUBPROCESS_CONTROLS = {
    "PYTHONHASHSEED": "20260730",
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}
FORBIDDEN_ENVIRONMENT = (
    "MLFLOW_ALLOW_FILE_STORE", "MLFLOW_TRACKING_URI", "MLFLOW_REGISTRY_URI",
    "MLFLOW_TRACKING_USERNAME", "MLFLOW_TRACKING_PASSWORD",
    "MLFLOW_TRACKING_TOKEN", "DATABRICKS_HOST", "DATABRICKS_TOKEN",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "AZURE_STORAGE_CONNECTION_STRING", "GOOGLE_APPLICATION_CREDENTIALS",
)
MODEL_PARAMETERS: dict[str, Any] = {
    "base_model": "gbm", "loss": "mse", "num_models": 3,
    "enable_sr": True, "enable_fs": True, "alpha1": 1.0, "alpha2": 1.0,
    "bins_sr": 10, "bins_fs": 5, "decay": 0.5,
    "sample_ratios": [0.8, 0.7, 0.6, 0.5, 0.4],
    "sub_weights": [1.0, 1.0, 1.0], "epochs": 28,
    "early_stopping_rounds": None, "colsample_bytree": 0.8879,
    "learning_rate": 0.2, "subsample": 0.8789, "lambda_l1": 205.6999,
    "lambda_l2": 580.9768, "max_depth": 8, "num_leaves": 210,
    "num_threads": 1, "verbosity": -1, "seed": 20260730,
    "feature_fraction_seed": 20260730, "bagging_seed": 20260730,
    "data_random_seed": 20260730, "deterministic": True,
    "force_col_wise": True,
}


@dataclass(frozen=True, slots=True)
class QlibDoubleEnsembleReproductionConfig:
    output_root: Path = DEFAULT_OUTPUT_ROOT
    frozen_linear_batch: Path = DEFAULT_LINEAR_BATCH
    accepted_lightgbm_batch: Path = DEFAULT_LIGHTGBM_BATCH
    qlib_interpreter: Path = DEFAULT_INTERPRETER
    environment_report: Path = DEFAULT_ENVIRONMENT_REPORT
    frozen_specification: Path = DEFAULT_SPECIFICATION
    seed: int = 20260730
    reruns: int = 2
    reproducibility_tolerance: float = 1e-12
    batch_id: str | None = None
    keep_failed_artifacts: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or self.seed != 20260730:
            raise ValueError("seed is frozen at 20260730")
        if isinstance(self.reruns, bool) or self.reruns != 2:
            raise ValueError("reruns must be exactly 2")
        if float(self.reproducibility_tolerance) != 1e-12:
            raise ValueError("reproducibility_tolerance is frozen at 1e-12")
        for name in (
            "output_root", "frozen_linear_batch", "accepted_lightgbm_batch",
            "qlib_interpreter", "environment_report", "frozen_specification",
        ):
            object.__setattr__(self, name, Path(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class QlibDoubleEnsembleReproductionPlan:
    batch_id: str
    output_directory: Path
    commands: tuple[tuple[str, ...], ...]
    selected_source_run: Path
    selected_lightgbm_run: Path
    model_configuration_fingerprint: str
    evaluation_protocol_fingerprint: str
    environment_fingerprint: str
    resolved_lock_sha256: str
    doubleensemble_source_sha256: str
    subprocess_environment_controls: dict[str, str]
    model_parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class QlibDoubleEnsembleRunResult:
    run_id: str
    directory: Path
    execution_report: dict[str, Any]
    evaluations: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class QlibDoubleEnsembleBatchResult:
    batch_id: str
    directory: Path
    runs: tuple[QlibDoubleEnsembleRunResult, ...]
    reproducibility: dict[str, Any]


def finalize_doubleensemble_failed_batch(
    batch_directory: str | Path,
) -> dict[str, Any]:
    """Finalize a stopped one-run batch without invoking the runner again."""

    batch = Path(batch_directory)
    run = batch / "run-01"
    if not run.is_dir() or (batch / "run-02").exists():
        raise ValueError("failure finalization requires only run-01")
    execution = _read_json(run / "execution_report.json")
    metadata = _read_json(run / "doubleensemble_runner_metadata.json")
    evaluation = _read_json(
        run / "qlib_doubleensemble_evaluation/evaluation_summary.json"
    )
    daily = pd.read_csv(run / "qlib_doubleensemble_evaluation/daily_ic.csv")
    predictions = pd.read_csv(run / "doubleensemble_predictions_raw.csv")
    if (
        execution.get("exit_code") != 0
        or metadata.get("submodel_count") != 3
        or evaluation.get("valid_ic_dates") != 0
        or evaluation.get("valid_rank_ic_dates") != 0
        or set(daily["status"]) != {"constant_signal"}
        or predictions["score"].nunique() != 1
    ):
        raise ValueError("batch does not contain the accepted constant-signal blocker")
    reason = (
        "The official frozen DEnsembleModel trained three one-tree, "
        "zero-split submodels and produced a constant test signal. All 40 "
        "evaluation dates therefore have constant_signal status, with zero "
        "valid IC and Rank IC dates."
    )
    diagnostics = {
        "schema_version": "1.0", "status": "blocked",
        "blocker_id": "official_frozen_configuration_constant_signal",
        "failure_reason": reason, "official_fit_completed": True,
        "prediction_completed": True, "submodel_count": 3,
        "tree_counts": metadata["tree_counts"],
        "prediction_count": len(predictions),
        "unique_prediction_count": int(predictions["score"].nunique()),
        "evaluation_date_count": evaluation["evaluation_date_count"],
        "constant_signal_dates": int((daily["status"] == "constant_signal").sum()),
        "valid_ic_dates": evaluation["valid_ic_dates"],
        "valid_rank_ic_dates": evaluation["valid_rank_ic_dates"],
        "second_run_attempted": False, "configuration_changed": False,
        "tolerance_changed": False, "fallback_used": False,
        "registry_promotion_permitted": False,
    }
    write_canonical_json(
        diagnostics, run / "scientific_acceptance_failure.json"
    )
    write_canonical_json({
        "schema_version": "1.0", "run_id": metadata["run_id"],
        "model_id": MODEL_ID, "status": "failed",
        "failure_reason": reason,
        "blocker_id": diagnostics["blocker_id"],
        "source_manifest": str(PLANNED_MANIFEST),
        "model_configuration_fingerprint":
            metadata["model_configuration_fingerprint"],
        "evaluation_protocol_fingerprint":
            metadata["evaluation_protocol_fingerprint"],
        "official_fit_completed": True, "predictions_produced": True,
        "evaluation_completed": True,
        "four_model_comparison_produced": False,
        "registry_promotion_permitted": False,
        "evidence_scope": "official frozen offline synthetic compatibility evidence",
    }, run / "failed_manifest.json")
    write_canonical_json({
        "schema_version": "1.0",
        "self_referential_exclusions": [
            "artifact_inventory.json", "execution_report.json",
            "failed_manifest.json",
        ], "artifacts": _inventory(run),
    }, run / "artifact_inventory.json")
    write_canonical_json({
        "schema_version": "1.0", "batch_id": batch.name,
        "status": "blocked", "blocker_id": diagnostics["blocker_id"],
        "failure_reason": reason, "attempted_run_count": 1,
        "successful_runner_count": 1, "accepted_run_count": 0,
        "second_run_attempted": False,
        "reproducibility_evaluated": False,
        "four_model_comparison_produced": False,
        "registry_source_mutated_at_runtime": False,
    }, batch / "batch_execution_report.json")
    write_canonical_json({
        "schema_version": "1.0", "proposed_changes": [],
        "qlib_doubleensemble_status": "adoption_specified",
        "promotion_blocked": True, "reason": reason,
    }, batch / "proposed_registry_status_update.json")
    return diagnostics


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def build_doubleensemble_subprocess_environment(
    base: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, bool]]:
    parent = dict(os.environ if base is None else base)
    present = sorted(name for name in FORBIDDEN_ENVIRONMENT if parent.get(name))
    if present:
        raise ValueError(f"prohibited inherited environment variables: {present}")
    audit = {name: bool(parent.get(name)) for name in SUBPROCESS_CONTROLS}
    child = dict(parent)
    child.update(SUBPROCESS_CONTROLS)
    return child, audit


def _model_configuration(specification: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_id": MODEL_ID,
        "upstream_package": "pyqlib==0.9.7",
        "upstream_class":
            "qlib.contrib.model.double_ensemble.DEnsembleModel",
        "paper": "DoubleEnsemble (IEEE ICDM 2020)",
        "base_model": "gbm",
        "parameters": MODEL_PARAMETERS,
        "features": specification["feature_list"],
        "numpy_seed": 20260730,
        "training_segments": ["train", "valid"],
        "prediction_segment": "test",
        "validation_use": "official_internal_validation_no_early_stopping",
    }


def _validate(
    config: QlibDoubleEnsembleReproductionConfig,
) -> tuple[dict[str, Any], Path, Path, dict[str, Any]]:
    specification = _read_json(config.frozen_specification)
    if specification.get("seed") != 20260730:
        raise ValueError("frozen specification seed mismatch")
    compatibility = QlibLightGBMCompatibilityConfig(
        frozen_linear_batch=config.frozen_linear_batch,
        qlib_interpreter=config.qlib_interpreter,
        environment_report=config.environment_report,
        frozen_specification=LIGHTGBM_SPECIFICATION,
    )
    light_spec, source_run, environment = validate_frozen_lightgbm_inputs(
        compatibility
    )
    shared = (
        "label_dataset_fingerprint", "evaluation_protocol_fingerprint",
        "environment_fingerprint", "resolved_lock_sha256",
    )
    for key in shared:
        if specification.get(key) != light_spec.get(key):
            raise ValueError(f"DoubleEnsemble frozen {key} mismatch")
    if specification.get("canonical_file_hashes") != {
        key: light_spec["canonical_file_hashes"][key]
        for key in specification["canonical_file_hashes"]
    }:
        raise ValueError("canonical frozen input hashes mismatch")
    if config.accepted_lightgbm_batch.as_posix() != specification[
        "accepted_lightgbm_batch"
    ]:
        raise ValueError("accepted LightGBM batch differs from specification")
    lightgbm_run = config.accepted_lightgbm_batch / "run-01"
    lightgbm_signal = lightgbm_run / "qlib_lightgbm_signals.csv"
    if (
        not lightgbm_signal.is_file()
        or fingerprint_file(lightgbm_signal)
        != specification["accepted_baseline_hashes"]["qlib_lightgbm_signals.csv"]
        or len(pd.read_csv(lightgbm_signal)) != 1200
    ):
        raise ValueError("accepted LightGBM signals mismatch")
    baseline_sources = {
        "qlib_linear_signals.csv": source_run / "qlib_signals.csv",
        "research_v2_signals.csv": source_run / "research_v2_signals.csv",
        "research_v2_ineligible.csv":
            source_run / "research_v2_eligibility_report.csv",
        "qlib_lightgbm_signals.csv": lightgbm_signal,
    }
    for name, path in baseline_sources.items():
        if fingerprint_file(path) != specification[
            "accepted_baseline_hashes"
        ][name]:
            raise ValueError(f"accepted baseline hash mismatch: {name}")
    counts = specification["accepted_baseline_counts"]
    if (
        len(pd.read_csv(baseline_sources["qlib_linear_signals.csv"]))
        != counts["qlib_linear_signals"]
        or len(pd.read_csv(baseline_sources["research_v2_signals.csv"]))
        != counts["research_v2_signals"]
        or len(pd.read_csv(baseline_sources["research_v2_ineligible.csv"])
               .query("eligible == False"))
        != counts["research_v2_ineligible"]
    ):
        raise ValueError("accepted baseline counts mismatch")
    source = (
        config.qlib_interpreter.resolve().parents[1]
        / "Lib/site-packages/qlib/contrib/model/double_ensemble.py"
    )
    if (
        not source.is_file()
        or fingerprint_file(source)
        != specification["qlib_doubleensemble_source_sha256"]
    ):
        raise ValueError("installed DoubleEnsemble source hash mismatch")
    if not RUNNER_PATH.is_file():
        raise ValueError(f"DoubleEnsemble runner is missing: {RUNNER_PATH}")
    environment = {
        **environment,
        "doubleensemble_source": source,
        "doubleensemble_source_sha256": fingerprint_file(source),
    }
    return specification, source_run, lightgbm_run, environment


def plan_qlib_doubleensemble_reproduction(
    config: QlibDoubleEnsembleReproductionConfig | None = None,
) -> QlibDoubleEnsembleReproductionPlan:
    selected = config or QlibDoubleEnsembleReproductionConfig()
    specification, source_run, lightgbm_run, environment = _validate(selected)
    build_doubleensemble_subprocess_environment()
    batch_id = selected.batch_id or str(uuid4())
    directory = selected.output_root / batch_id
    if directory.exists():
        raise ValueError(f"refusing preexisting batch directory: {directory}")
    commands = tuple(
        (
            str(selected.qlib_interpreter),
            str(RUNNER_PATH),
            str(directory / f"run-{number:02d}/runner_request.json"),
        )
        for number in range(1, 3)
    )
    return QlibDoubleEnsembleReproductionPlan(
        batch_id=batch_id, output_directory=directory, commands=commands,
        selected_source_run=source_run,
        selected_lightgbm_run=lightgbm_run,
        model_configuration_fingerprint=model_configuration_fingerprint(
            _model_configuration(specification)
        ),
        evaluation_protocol_fingerprint=
            specification["evaluation_protocol_fingerprint"],
        environment_fingerprint=specification["environment_fingerprint"],
        resolved_lock_sha256=environment["lock_sha256"],
        doubleensemble_source_sha256=
            environment["doubleensemble_source_sha256"],
        subprocess_environment_controls=dict(SUBPROCESS_CONTROLS),
        model_parameters=dict(MODEL_PARAMETERS),
    )


def _protocol(source_run: Path) -> EvaluationProtocol:
    raw = _read_json(source_run / "evaluation_protocol.json")
    return EvaluationProtocol(
        label_name=raw["label_name"], label_definition=raw["label_definition"],
        label_dataset_fingerprint=raw["label_dataset_fingerprint"],
        train_start=raw["train"]["start"], train_end=raw["train"]["end"],
        validation_start=raw["validation"]["start"],
        validation_end=raw["validation"]["end"],
        test_start=raw["test"]["start"], test_end=raw["test"]["end"],
        purge_days=raw["purge_days"], embargo_days=raw["embargo_days"],
        evaluation_frequency=raw["evaluation_frequency"],
        metric_definitions=raw["metric_definitions"],
        annualization_factor=raw["annualization_factor"],
        minimum_cross_sectional_observations=
            raw["minimum_cross_sectional_observations"],
        test_universe_policy=raw["test_universe_policy"],
    )


def _inventory(directory: Path) -> list[dict[str, Any]]:
    excluded = {"artifact_inventory.json", "execution_report.json",
                "completed_manifest.json", "failed_manifest.json"}
    rows = []
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        relative = path.relative_to(directory).as_posix()
        if relative in excluded:
            continue
        rows.append({
            "relative_path": relative, "sha256": fingerprint_file(path),
            "size_bytes": path.stat().st_size,
            "role": relative.split("/", 1)[0],
            "producing_environment": (
                "qlib-python-3.12"
                if relative.startswith((
                    "doubleensemble_", "submodel", "combined_",
                    "per_submodel_",
                )) else "product-python-3.13"
            ),
            "generated_timestamp": datetime.fromtimestamp(
                path.stat().st_mtime, timezone.utc
            ).isoformat(),
        })
    return rows


def _copy_inputs(
    directory: Path, source_run: Path, lightgbm_run: Path,
    specification: dict[str, Any],
) -> dict[str, Path]:
    sources = {
        name: source_run / name
        for name in specification["canonical_file_hashes"]
    }
    sources.update({
        "accepted_qlib_linear_signals.csv": source_run / "qlib_signals.csv",
        "accepted_research_v2_signals.csv":
            source_run / "research_v2_signals.csv",
        "accepted_research_v2_ineligible.csv":
            source_run / "research_v2_eligibility_report.csv",
        "accepted_qlib_lightgbm_signals.csv":
            lightgbm_run / "qlib_lightgbm_signals.csv",
    })
    copied: dict[str, Path] = {}
    inventory = []
    for name, source in sources.items():
        destination = directory / name
        shutil.copy2(source, destination)
        if fingerprint_file(source) != fingerprint_file(destination):
            raise RuntimeError(f"copied input changed bytes: {name}")
        copied[name] = destination
        inventory.append({
            "name": name, "source": str(source),
            "sha256": fingerprint_file(destination),
            "size_bytes": destination.stat().st_size,
        })
    write_canonical_json({
        "schema_version": "1.0", "source_artifacts_rewritten": False,
        "copied_inputs": inventory,
    }, directory / "copied_input_inventory.json")
    write_canonical_json({
        "schema_version": "1.0", "accepted_source_run": str(source_run),
        "accepted_lightgbm_run": str(lightgbm_run),
        "label_dataset_fingerprint":
            specification["label_dataset_fingerprint"],
        "evaluation_protocol_fingerprint":
            specification["evaluation_protocol_fingerprint"],
    }, directory / "frozen_input_reference.json")
    return copied


def _outputs(directory: Path) -> dict[str, Path]:
    return {
        "predictions": directory / "doubleensemble_predictions_raw.csv",
        "metadata": directory / "doubleensemble_runner_metadata.json",
        "submodel_summary": directory / "submodel_summary.json",
        "selected_features": directory / "submodel_selected_features.json",
        "combined_gain": directory / "combined_feature_importance_gain.csv",
        "combined_split": directory / "combined_feature_importance_split.csv",
        "per_gain": directory / "per_submodel_feature_importance_gain.csv",
        "per_split": directory / "per_submodel_feature_importance_split.csv",
        "model_dump_1": directory / "submodel-01-dump.json",
        "model_dump_2": directory / "submodel-02-dump.json",
        "model_dump_3": directory / "submodel-03-dump.json",
    }


def _execute_run(
    number: int, config: QlibDoubleEnsembleReproductionConfig,
    plan: QlibDoubleEnsembleReproductionPlan, specification: dict[str, Any],
    source_run: Path, lightgbm_run: Path, environment: dict[str, Any],
    protocol: EvaluationProtocol, labels: pd.DataFrame,
) -> QlibDoubleEnsembleRunResult:
    directory = plan.output_directory / f"run-{number:02d}"
    if directory.exists():
        raise ValueError(f"refusing preexisting run directory: {directory}")
    directory.mkdir(parents=True)
    copied = _copy_inputs(directory, source_run, lightgbm_run, specification)
    outputs = _outputs(directory)
    run_id = str(uuid4())
    report = _read_json(config.environment_report)
    request = {
        "schema_version": "1.0", "run_id": run_id, "model_id": MODEL_ID,
        "panel_path": str(copied["synthetic_qlib_panel.csv"].resolve()),
        "panel_sha256":
            specification["canonical_file_hashes"]["synthetic_qlib_panel.csv"],
        "environment_report": str(config.environment_report.resolve()),
        "environment_report_sha256":
            specification["environment_report_sha256"],
        "environment_fingerprint": specification["environment_fingerprint"],
        "resolved_lock": str(Path(report["resolved_lock"]).resolve()),
        "resolved_lock_sha256": specification["resolved_lock_sha256"],
        "doubleensemble_source":
            str(environment["doubleensemble_source"].resolve()),
        "doubleensemble_source_sha256":
            environment["doubleensemble_source_sha256"],
        "feature_columns": specification["feature_list"],
        "label_name": specification["label_name"],
        "segments": {
            "train": _read_json(copied["split.json"])["train"],
            "valid": _read_json(copied["split.json"])["validation"],
            "test": _read_json(copied["split.json"])["test"],
        },
        "model_parameters": MODEL_PARAMETERS, "numpy_seed": 20260730,
        "model_configuration_fingerprint":
            plan.model_configuration_fingerprint,
        "dataset_fingerprints": _read_json(
            copied["dataset_fingerprints.json"]
        ),
        "evaluation_protocol_fingerprint": protocol.fingerprint,
        "subprocess_environment_controls": SUBPROCESS_CONTROLS,
        "expected_test_rows": 1200,
        "outputs": {
            name: str(path.resolve()) for name, path in outputs.items()
        },
    }
    request_path = directory / "runner_request.json"
    write_canonical_json(request, request_path)
    command = [
        str(config.qlib_interpreter.resolve()), str(RUNNER_PATH.resolve()),
        str(request_path.resolve()),
    ]
    child, parent_audit = build_doubleensemble_subprocess_environment()
    started = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()
    completed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8",
        env=child, check=False,
    )
    execution = {
        "schema_version": "1.0", "run_id": run_id, "command": command,
        "subprocess_environment_controls": SUBPROCESS_CONTROLS,
        "parent_control_presence": parent_audit,
        "exit_code": completed.returncode,
        "duration_seconds": time.perf_counter() - start,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "stdout": completed.stdout, "stderr": completed.stderr,
        "status": "completed" if completed.returncode == 0 else "failed",
    }
    write_canonical_json(execution, directory / "execution_report.json")
    if completed.returncode != 0:
        write_canonical_json({
            "schema_version": "1.0", "run_id": run_id, "status": "failed",
            "failure_reason": completed.stderr.strip(),
            "registry_promotion_permitted": False,
        }, directory / "failed_manifest.json")
        write_canonical_json({
            "schema_version": "1.0",
            "self_referential_exclusions": [
                "artifact_inventory.json", "execution_report.json",
                "failed_manifest.json",
            ], "artifacts": _inventory(directory),
        }, directory / "artifact_inventory.json")
        if not config.keep_failed_artifacts:
            shutil.rmtree(directory)
        raise RuntimeError(
            f"Qlib DoubleEnsemble run {number} failed: "
            f"{completed.stderr.strip()}"
        )
    missing = [name for name, path in outputs.items() if not path.is_file()]
    if missing:
        raise RuntimeError(f"runner outputs are missing: {missing}")
    metadata = _read_json(outputs["metadata"])
    if (
        metadata.get("status") != "completed"
        or metadata.get("run_id") != run_id
        or metadata.get("model_class")
        != "qlib.contrib.model.double_ensemble.DEnsembleModel"
        or metadata.get("submodel_count") != 3
        or metadata.get("prediction_count") != 1200
        or metadata.get("model_configuration_fingerprint")
        != plan.model_configuration_fingerprint
        or metadata.get("subprocess_environment_controls")
        != SUBPROCESS_CONTROLS
    ):
        raise RuntimeError("DoubleEnsemble runner metadata mismatch")

    signals, dropped = convert_qlib_predictions(
        outputs["predictions"], copied["qlib_instrument_mapping.csv"],
        model_id=MODEL_ID, run_id=run_id, upstream_model_id=MODEL_ID,
        upstream_run_id=run_id,
    )
    if not dropped.empty or len(signals) != 1200:
        raise RuntimeError("DoubleEnsemble signal conversion mismatch")
    write_canonical_csv(signals, directory / "doubleensemble_signals.csv")

    baseline_paths = {
        "research_v2": copied["accepted_research_v2_signals.csv"],
        "qlib_linear": copied["accepted_qlib_linear_signals.csv"],
        "qlib_lightgbm": copied["accepted_qlib_lightgbm_signals.csv"],
    }
    baseline_summaries = {
        "research_v2": _read_json(
            source_run / "evaluation_research_v2/evaluation_summary.json"
        ),
        "qlib_linear": _read_json(
            source_run / "evaluation_qlib/evaluation_summary.json"
        ),
        "qlib_lightgbm": _read_json(
            lightgbm_run / "evaluation_lightgbm/evaluation_summary.json"
        ),
    }
    datasets = specification.get(
        "dataset_fingerprints",
        _read_json(copied["dataset_fingerprints.json"]),
    )
    evaluations = []
    de_eval = evaluate_signals(
        signals, labels, protocol,
        model_configuration_fingerprint=plan.model_configuration_fingerprint,
        dataset_fingerprints=datasets,
        provenance={
            "implementation": "Qlib v0.9.7 DEnsembleModel",
            "paper": "IEEE ICDM 2020 DoubleEnsemble",
            "base_model": "gbm",
            "evidence_scope": "frozen offline synthetic-only reproduction",
        },
        output_dir=directory / "qlib_doubleensemble_evaluation",
    )
    evaluations.append(de_eval.summary)
    for name, signal_path in baseline_paths.items():
        prior = baseline_summaries[name]
        result = evaluate_signals(
            pd.read_csv(signal_path), labels, protocol,
            model_configuration_fingerprint=
                prior["model_configuration_fingerprint"],
            dataset_fingerprints=datasets, provenance=prior["provenance"],
            output_dir=directory / f"{name}_evaluation",
        )
        evaluations.append(result.summary)
    protocols = {
        item["evaluation_protocol_fingerprint"] for item in evaluations
    }
    models = {
        item["model_configuration_fingerprint"] for item in evaluations
    }
    if len(protocols) != 1 or len(models) != 4:
        raise RuntimeError("four-model fairness fingerprint boundary failed")
    if any(item["valid_ic_dates"] < 2 for item in evaluations):
        raise RuntimeError("four-model evaluation lacks finite IC dates")
    comparison = compare_evaluations(
        evaluations, output_path=directory / "four_model_comparison.csv"
    )
    records = comparison.to_dict("records")
    forbidden = (
        "winner", "recommendation", "sharpe", "portfolio_return",
        "profitability", "real_market",
    )
    serialized = json.dumps(records).lower()
    if any(term in serialized for term in forbidden):
        raise RuntimeError("four-model comparison contains forbidden claims")
    write_canonical_json({
        "schema_version": "1.0",
        "evaluation_protocol_fingerprint": protocol.fingerprint,
        "model_configuration_fingerprints": sorted(models),
        "coverage_differences_reported": True,
        "portfolio_metrics_calculated": False,
        "models": records,
    }, directory / "four_model_comparison.json")
    manifest_paths = [
        directory / "qlib_doubleensemble_evaluation/evaluation_summary.json",
        directory / "research_v2_evaluation/evaluation_summary.json",
        directory / "qlib_linear_evaluation/evaluation_summary.json",
        directory / "qlib_lightgbm_evaluation/evaluation_summary.json",
        directory / "four_model_comparison.csv",
    ]
    write_canonical_json({
        "schema_version": "1.0", "run_id": run_id, "model_id": MODEL_ID,
        "status": "completed", "source_manifest": str(PLANNED_MANIFEST),
        "model_configuration": _model_configuration(specification),
        "model_configuration_fingerprint":
            plan.model_configuration_fingerprint,
        "evaluation_protocol_fingerprint": protocol.fingerprint,
        "dataset_fingerprints": datasets,
        "evaluation_artifacts": [
            {"path": str(path), "sha256": fingerprint_file(path)}
            for path in manifest_paths
        ],
        "evidence_scope": "official frozen offline synthetic-only reproduction",
    }, directory / "completed_manifest.json")
    write_canonical_json({
        "schema_version": "1.0",
        "self_referential_exclusions": [
            "artifact_inventory.json", "execution_report.json",
            "completed_manifest.json",
        ], "artifacts": _inventory(directory),
    }, directory / "artifact_inventory.json")
    return QlibDoubleEnsembleRunResult(
        run_id=run_id, directory=directory, execution_report=execution,
        evaluations=tuple(evaluations),
    )


def _maximum_difference(
    left: Path, right: Path, columns: list[str], keys: list[str],
) -> tuple[float, bool]:
    first, second = pd.read_csv(left), pd.read_csv(right)
    ordered = first[keys].equals(second[keys])
    if not ordered:
        return float("inf"), False
    values = [
        np.max(np.abs(first[column].to_numpy(float)
                      - second[column].to_numpy(float)))
        for column in columns
    ]
    return float(max(values, default=0.0)), True


def compare_doubleensemble_runs(
    first: str | Path, second: str | Path, *, tolerance: float = 1e-12,
) -> dict[str, Any]:
    if tolerance != 1e-12:
        raise ValueError("tolerance is frozen at 1e-12")
    one, two = Path(first), Path(second)
    prediction, prediction_order = _maximum_difference(
        one / "doubleensemble_predictions_raw.csv",
        two / "doubleensemble_predictions_raw.csv",
        ["score"], ["datetime", "instrument"],
    )
    differences: dict[str, float] = {}
    order_checks: dict[str, bool] = {}
    comparisons = {
        "combined_gain": (
            "combined_feature_importance_gain.csv", ["importance_gain"],
            ["feature"],
        ),
        "combined_split": (
            "combined_feature_importance_split.csv", ["importance_split"],
            ["feature"],
        ),
        "per_submodel_gain": (
            "per_submodel_feature_importance_gain.csv", ["importance_gain"],
            ["submodel", "feature"],
        ),
        "per_submodel_split": (
            "per_submodel_feature_importance_split.csv", ["importance_split"],
            ["submodel", "feature"],
        ),
    }
    for name, (filename, columns, keys) in comparisons.items():
        differences[name], order_checks[name] = _maximum_difference(
            one / filename, two / filename, columns, keys
        )
    first_meta = _read_json(one / "doubleensemble_runner_metadata.json")
    second_meta = _read_json(two / "doubleensemble_runner_metadata.json")
    selected_identical = json.loads(
        (one / "submodel_selected_features.json").read_text(encoding="utf-8")
    ) == json.loads(
        (two / "submodel_selected_features.json").read_text(encoding="utf-8")
    )
    summary_identical = json.loads(
        (one / "submodel_summary.json").read_text(encoding="utf-8")
    ) == json.loads(
        (two / "submodel_summary.json").read_text(encoding="utf-8")
    )
    checks = {
        "prediction_order_identical": prediction_order,
        "importance_order_identical": all(order_checks.values()),
        "selected_features_identical": selected_identical,
        "submodel_summary_identical": summary_identical,
        "normalized_model_dumps_identical":
            first_meta["normalized_model_dump_sha256"]
            == second_meta["normalized_model_dump_sha256"],
        "dataset_fingerprints_identical":
            first_meta["dataset_fingerprints"]
            == second_meta["dataset_fingerprints"],
        "model_configuration_fingerprint_identical":
            first_meta["model_configuration_fingerprint"]
            == second_meta["model_configuration_fingerprint"],
        "evaluation_protocol_fingerprint_identical":
            first_meta["evaluation_protocol_fingerprint"]
            == second_meta["evaluation_protocol_fingerprint"],
        "process_controls_identical":
            first_meta["subprocess_environment_controls"]
            == second_meta["subprocess_environment_controls"]
            == SUBPROCESS_CONTROLS,
    }
    passed = (
        all(checks.values()) and prediction <= tolerance
        and all(value <= tolerance for value in differences.values())
    )
    report = {
        "schema_version": "1.0", "tolerance": tolerance,
        "maximum_prediction_difference": prediction,
        **{
            f"maximum_{name}_difference": value
            for name, value in differences.items()
        },
        "checks": checks, "passed": passed, "tolerance_relaxed": False,
    }
    if not passed:
        raise RuntimeError(
            f"DoubleEnsemble reproducibility acceptance failed: {report}"
        )
    return report


def run_qlib_doubleensemble_reproduction(
    config: QlibDoubleEnsembleReproductionConfig | None = None,
) -> QlibDoubleEnsembleBatchResult:
    selected = config or QlibDoubleEnsembleReproductionConfig()
    plan = plan_qlib_doubleensemble_reproduction(selected)
    specification, source_run, lightgbm_run, environment = _validate(selected)
    protocol = _protocol(source_run)
    labels = pd.read_csv(
        source_run / "synthetic_labels.csv",
        dtype={"as_of_date": str, "label_end_date": str},
        float_precision="round_trip",
    )
    plan.output_directory.mkdir(parents=True)
    completed = []
    for number in range(1, 3):
        try:
            completed.append(_execute_run(
                number, selected, plan, specification, source_run,
                lightgbm_run, environment, protocol, labels,
            ))
        except Exception:
            if number == 1 and (plan.output_directory / "run-01").is_dir():
                summary = (
                    plan.output_directory / "run-01"
                    / "qlib_doubleensemble_evaluation/evaluation_summary.json"
                )
                if summary.is_file():
                    finalize_doubleensemble_failed_batch(
                        plan.output_directory
                    )
            raise
    runs = tuple(completed)
    reproducibility = compare_doubleensemble_runs(
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
        "schema_version": "1.0", "batch_id": plan.batch_id,
        "status": "completed", "run_ids": [run.run_id for run in runs],
        "successful_run_count": 2, "registry_source_mutated_at_runtime": False,
        "evidence_scope": "official frozen offline synthetic-only reproduction",
    }, plan.output_directory / "batch_execution_report.json")
    write_canonical_json({
        "schema_version": "1.0",
        "proposed_changes": [{
            "registry_id": "qlib_double_ensemble",
            "proposed_status": "synthetic_reproduced",
        }],
        "runtime_mutated_registry": False,
        "conditional_on_all_acceptance_gates": True,
        "evidence_scope": (
            "Official Qlib v0.9.7 DEnsembleModel on frozen offline "
            "synthetic data only."
        ),
    }, plan.output_directory / "proposed_registry_status_update.json")
    return QlibDoubleEnsembleBatchResult(
        batch_id=plan.batch_id, directory=plan.output_directory,
        runs=runs, reproducibility=reproducibility,
    )
