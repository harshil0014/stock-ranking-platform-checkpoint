"""Product-side orchestration for the blocked Qlib LightGBM proof."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any
from uuid import uuid4

import pandas as pd

from stock_research.fingerprints import (
    fingerprint_file,
    model_configuration_fingerprint,
)
from stock_research.synthetic_qlib import THREAD_CONTROLS, write_canonical_json


MODEL_ID = "qlib_lightgbm_v0_9_7"
DEFAULT_OUTPUT_ROOT = Path("research/generated/qlib-lightgbm")
DEFAULT_LINEAR_BATCH = Path(
    "research/generated/qlib-linear/final-locked-20260731"
)
DEFAULT_INTERPRETER = Path(".venv-qlib/Scripts/python.exe")
DEFAULT_ENVIRONMENT_REPORT = Path(
    "research/generated/qlib-environment-verified.json"
)
DEFAULT_FROZEN_SPECIFICATION = Path(
    "research/specifications/qlib_lightgbm_frozen_protocol.json"
)
RUNNER_PATH = Path(
    "research/runners/qlib_lightgbm_compatibility_runner.py"
)
MODEL_CONSTRUCTION = {
    "loss": "mse",
    "learning_rate": 0.05,
    "num_leaves": 31,
    "max_depth": -1,
    "min_data_in_leaf": 20,
    "feature_fraction": 1.0,
    "bagging_fraction": 1.0,
    "bagging_freq": 0,
    "lambda_l1": 0.0,
    "lambda_l2": 0.0,
    "num_threads": 1,
    "seed": 20260730,
    "feature_fraction_seed": 20260730,
    "bagging_seed": 20260730,
    "data_random_seed": 20260730,
    "deterministic": True,
    "force_col_wise": True,
    "verbosity": -1,
    "num_boost_round": 200,
    "early_stopping_rounds": 20,
}
FIT_CONFIGURATION = {
    "verbose_eval": 0,
    "validation_use": "early_stopping_only",
    "test_labels_used": False,
}


@dataclass(frozen=True, slots=True)
class QlibLightGBMCompatibilityConfig:
    output_root: Path = DEFAULT_OUTPUT_ROOT
    frozen_linear_batch: Path = DEFAULT_LINEAR_BATCH
    qlib_interpreter: Path = DEFAULT_INTERPRETER
    environment_report: Path = DEFAULT_ENVIRONMENT_REPORT
    frozen_specification: Path = DEFAULT_FROZEN_SPECIFICATION
    seed: int = 20260730
    attempts: int = 1
    batch_id: str | None = None
    keep_failed_artifacts: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or self.seed != 20260730:
            raise ValueError("seed is frozen at 20260730")
        if isinstance(self.attempts, bool) or self.attempts != 1:
            raise ValueError("compatibility proof permits exactly one attempt")
        for field in (
            "output_root", "frozen_linear_batch", "qlib_interpreter",
            "environment_report", "frozen_specification",
        ):
            object.__setattr__(self, field, Path(getattr(self, field)))


@dataclass(frozen=True, slots=True)
class QlibLightGBMCompatibilityPlan:
    batch_id: str
    output_directory: Path
    command: tuple[str, ...]
    selected_source_run: Path
    environment_fingerprint: str
    resolved_lock_sha256: str
    qlib_gbdt_source_sha256: str
    model_configuration_fingerprint: str
    evaluation_protocol_fingerprint: str
    expected_status: str = "blocked"


@dataclass(frozen=True, slots=True)
class QlibLightGBMCompatibilityResult:
    batch_id: str
    directory: Path
    attempt_directory: Path
    status: str
    exit_code: int
    failure_reason: str


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _validate_environment(
    config: QlibLightGBMCompatibilityConfig,
    specification: dict[str, Any],
) -> dict[str, Any]:
    if not config.qlib_interpreter.is_file():
        raise ValueError(f"Qlib interpreter is missing: {config.qlib_interpreter}")
    report = _read_json(config.environment_report, "environment report")
    if report.get("status") != "verified":
        raise ValueError("Qlib environment is not verified")
    if report.get("environment_fingerprint") != specification[
        "environment_fingerprint"
    ]:
        raise ValueError("environment fingerprint differs from frozen specification")
    if fingerprint_file(config.environment_report) != specification[
        "environment_report_sha256"
    ]:
        raise ValueError("environment report file hash differs from frozen specification")
    reported_interpreter = Path(report.get("interpreter", ""))
    if reported_interpreter.resolve() != config.qlib_interpreter.resolve():
        raise ValueError("Qlib interpreter differs from verified report")
    imports = report.get("import_results", {})
    if (
        imports.get("qlib", {}).get("version") != "0.9.7"
        or imports.get("lightgbm", {}).get("version") != "4.6.0"
        or not imports.get("qlib.contrib.model.gbdt", {}).get("ok")
    ):
        raise ValueError("verified Qlib/LightGBM import results do not match")
    lock_path = Path(report.get("resolved_lock", ""))
    if not lock_path.is_file():
        raise ValueError("resolved dependency lock is missing")
    lock_hash = fingerprint_file(lock_path)
    if lock_hash != specification["resolved_lock_sha256"]:
        raise ValueError("dependency-lock hash differs from frozen specification")
    environment_root = config.qlib_interpreter.resolve().parents[1]
    gbdt_source = (
        environment_root
        / "Lib/site-packages/qlib/contrib/model/gbdt.py"
    )
    if not gbdt_source.is_file():
        raise ValueError(f"installed Qlib gbdt.py is missing: {gbdt_source}")
    source_hash = fingerprint_file(gbdt_source)
    if source_hash != specification["qlib_gbdt_source_sha256"]:
        raise ValueError("installed Qlib gbdt.py hash differs from frozen specification")
    return {
        "report": report,
        "report_sha256": fingerprint_file(config.environment_report),
        "lock_path": lock_path,
        "lock_sha256": lock_hash,
        "gbdt_source": gbdt_source,
        "gbdt_source_sha256": source_hash,
    }


def _validate_baseline_counts(run: Path, specification: dict[str, Any]) -> None:
    linear = pd.read_csv(run / "qlib_signals.csv")
    research_v2 = pd.read_csv(run / "research_v2_signals.csv")
    eligibility = pd.read_csv(run / "research_v2_eligibility_report.csv")
    expected = specification["accepted_baseline_counts"]
    if len(linear) != expected["qlib_linear_signals"]:
        raise ValueError("accepted Qlib Linear signal count mismatch")
    if set(linear["model_id"]) != {"qlib_linear_ols_v0_9_7"}:
        raise ValueError("accepted Qlib Linear model identity mismatch")
    if len(research_v2) != expected["research_v2_signals"]:
        raise ValueError("accepted Research V2 signal count mismatch")
    if set(research_v2["model_id"]) != {"research_v2_baseline"}:
        raise ValueError("accepted Research V2 model identity mismatch")
    ineligible = eligibility.loc[
        eligibility["eligible"].astype(str).str.lower().eq("false")
    ]
    if (
        len(ineligible) != expected["research_v2_ineligible"]
        or set(ineligible["ticker"]) != {"SYN030"}
    ):
        raise ValueError("accepted Research V2 exclusions mismatch")


def validate_frozen_lightgbm_inputs(
    config: QlibLightGBMCompatibilityConfig,
) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    """Validate both accepted runs and select the first completed run."""

    specification = _read_json(
        config.frozen_specification, "frozen LightGBM specification"
    )
    if config.frozen_linear_batch.as_posix() != specification[
        "accepted_source_batch"
    ]:
        raise ValueError("configured Linear batch differs from frozen specification")
    if not config.frozen_linear_batch.is_dir():
        raise ValueError(
            f"accepted Linear batch is missing: {config.frozen_linear_batch}"
        )
    valid_runs: list[Path] = []
    for run in sorted(
        path for path in config.frozen_linear_batch.glob("run-*")
        if path.is_dir()
    ):
        manifest = _read_json(run / "experiment_manifest.json", "Linear manifest")
        if manifest.get("status") != "completed":
            continue
        for name, expected_hash in specification[
            "canonical_file_hashes"
        ].items():
            path = run / name
            if not path.is_file() or fingerprint_file(path) != expected_hash:
                raise ValueError(
                    f"accepted input hash mismatch: {run.name}/{name}"
                )
        fingerprints = _read_json(
            run / "dataset_fingerprints.json", "dataset fingerprints"
        )
        if fingerprints != specification["dataset_fingerprints"]:
            raise ValueError(f"dataset fingerprints mismatch: {run.name}")
        protocol = _read_json(
            run / "evaluation_protocol.json", "evaluation protocol"
        )
        if protocol.get("label_dataset_fingerprint") != specification[
            "label_dataset_fingerprint"
        ]:
            raise ValueError(f"label fingerprint mismatch: {run.name}")
        metadata = _read_json(
            run / "qlib_model_metadata.json", "Qlib Linear metadata"
        )
        if (
            manifest.get("evaluation_protocol_fingerprint")
            != specification["evaluation_protocol_fingerprint"]
            or metadata.get("dataset_fingerprints")
            != specification["dataset_fingerprints"]
        ):
            raise ValueError(f"accepted Linear metadata mismatch: {run.name}")
        valid_runs.append(run)
    if len(valid_runs) != 2:
        raise ValueError("accepted Linear batch must contain two valid runs")
    selected = valid_runs[0]
    if selected.name != specification["selected_source_run"]:
        raise ValueError("deterministic source-run selection mismatch")
    for name, expected_hash in specification["accepted_baseline_hashes"].items():
        path = selected / name
        if not path.is_file() or fingerprint_file(path) != expected_hash:
            raise ValueError(f"accepted baseline hash mismatch: {name}")
    _validate_baseline_counts(selected, specification)
    environment = _validate_environment(config, specification)
    if not RUNNER_PATH.is_file():
        raise ValueError(f"compatibility runner is missing: {RUNNER_PATH}")
    return specification, selected, environment


def _model_configuration(specification: dict[str, Any]) -> dict[str, Any]:
    parameters = {
        key: value for key, value in MODEL_CONSTRUCTION.items()
        if key not in {"loss", "num_boost_round", "early_stopping_rounds"}
    }
    return {
        "model_id": MODEL_ID,
        "upstream_class": "qlib.contrib.model.gbdt.LGBModel",
        "qlib_version": "0.9.7",
        "lightgbm_version": "4.6.0",
        "loss": MODEL_CONSTRUCTION["loss"],
        "num_boost_round": MODEL_CONSTRUCTION["num_boost_round"],
        "early_stopping_rounds": MODEL_CONSTRUCTION[
            "early_stopping_rounds"
        ],
        "parameters": parameters,
        "fit_configuration": FIT_CONFIGURATION,
        "features": specification["feature_list"],
        "seed": 20260730,
        "attempts": 1,
        "expected_result": "blocked_at_qlib_workflow_logging",
    }


def build_qlib_lightgbm_plan(
    config: QlibLightGBMCompatibilityConfig | None = None,
) -> QlibLightGBMCompatibilityPlan:
    selected = config or QlibLightGBMCompatibilityConfig()
    specification, source_run, environment = (
        validate_frozen_lightgbm_inputs(selected)
    )
    batch_id = selected.batch_id or str(uuid4())
    directory = selected.output_root / batch_id
    command = (
        str(selected.qlib_interpreter),
        str(RUNNER_PATH),
        str(directory / "attempt-01/runner_request.json"),
    )
    return QlibLightGBMCompatibilityPlan(
        batch_id=batch_id,
        output_directory=directory,
        command=command,
        selected_source_run=source_run,
        environment_fingerprint=specification["environment_fingerprint"],
        resolved_lock_sha256=environment["lock_sha256"],
        qlib_gbdt_source_sha256=environment["gbdt_source_sha256"],
        model_configuration_fingerprint=model_configuration_fingerprint(
            _model_configuration(specification)
        ),
        evaluation_protocol_fingerprint=specification[
            "evaluation_protocol_fingerprint"
        ],
    )


def _inventory(directory: Path) -> list[dict[str, Any]]:
    excluded = {
        "artifact_inventory.json", "execution_report.json",
        "failed_manifest.json",
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
                if relative.startswith(("lightgbm_", "qlib_"))
                else "product-python-3.13"
            ),
            "generated_timestamp": datetime.fromtimestamp(
                path.stat().st_mtime, timezone.utc
            ).isoformat(),
        })
    return rows


def run_qlib_lightgbm_compatibility_proof(
    config: QlibLightGBMCompatibilityConfig | None = None,
) -> QlibLightGBMCompatibilityResult:
    selected = config or QlibLightGBMCompatibilityConfig()
    plan = build_qlib_lightgbm_plan(selected)
    if plan.output_directory.exists():
        raise ValueError(
            f"refusing preexisting batch directory: {plan.output_directory}"
        )
    specification, source_run, environment = (
        validate_frozen_lightgbm_inputs(selected)
    )
    attempt = plan.output_directory / "attempt-01"
    attempt.mkdir(parents=True)
    write_canonical_json({
        "schema_version": "1.0",
        "specification": str(selected.frozen_specification),
        "specification_sha256": fingerprint_file(
            selected.frozen_specification
        ),
        "accepted_source_batch": str(selected.frozen_linear_batch),
        "selected_source_run": str(source_run),
        "source_selection_rule": specification["source_selection_rule"],
        "canonical_file_hashes": specification["canonical_file_hashes"],
        "accepted_baseline_hashes": specification[
            "accepted_baseline_hashes"
        ],
        "inputs_copied": False,
        "source_artifacts_rewritten": False,
    }, attempt / "frozen_input_reference.json")
    parameters = {
        key: value for key, value in MODEL_CONSTRUCTION.items()
        if key not in {"loss", "num_boost_round", "early_stopping_rounds"}
    }
    outputs = {
        "runner_metadata": attempt / "qlib_lightgbm_runner_metadata.json",
        "training_history": attempt / "lightgbm_training_history.json",
        "feature_importance_gain":
            attempt / "lightgbm_feature_importance_gain.csv",
        "feature_importance_split":
            attempt / "lightgbm_feature_importance_split.csv",
        "model_dump": attempt / "diagnostic_lightgbm_model_dump.json",
        "failure_diagnostics": attempt / "compatibility_failure.json",
    }
    request = {
        "schema_version": "1.0",
        "run_id": str(uuid4()),
        "model_id": MODEL_ID,
        "panel_path": str(
            (source_run / "synthetic_qlib_panel.csv").resolve()
        ),
        "panel_sha256": specification["canonical_file_hashes"][
            "synthetic_qlib_panel.csv"
        ],
        "environment_report": str(selected.environment_report.resolve()),
        "environment_report_sha256": environment["report_sha256"],
        "environment_fingerprint": specification["environment_fingerprint"],
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
            "early_stopping_rounds": MODEL_CONSTRUCTION[
                "early_stopping_rounds"
            ],
            "parameters": parameters,
        },
        "fit_configuration": FIT_CONFIGURATION,
        "model_configuration_fingerprint":
            plan.model_configuration_fingerprint,
        "dataset_fingerprints": specification["dataset_fingerprints"],
        "evaluation_protocol_fingerprint":
            specification["evaluation_protocol_fingerprint"],
        "thread_controls": THREAD_CONTROLS,
        "outputs": {
            name: str(path.resolve()) for name, path in outputs.items()
        },
    }
    request_path = attempt / "runner_request.json"
    write_canonical_json(request, request_path)
    command = [
        str(selected.qlib_interpreter.resolve()),
        str(RUNNER_PATH.resolve()),
        str(request_path.resolve()),
    ]
    process_environment = os.environ.copy()
    process_environment.update(THREAD_CONTROLS)
    started_at = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()
    completed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8",
        env=process_environment, check=False,
    )
    duration = time.perf_counter() - start
    artifact_problem: str | None = None
    missing_outputs = [
        name for name, path in outputs.items() if not path.is_file()
    ]
    if missing_outputs:
        artifact_problem = f"runner outputs are missing: {sorted(missing_outputs)}"
    diagnostics_path = outputs["failure_diagnostics"]
    diagnostics = (
        _read_json(diagnostics_path, "compatibility diagnostics")
        if diagnostics_path.is_file() else {}
    )
    if artifact_problem is None:
        try:
            metadata = _read_json(
                outputs["runner_metadata"], "LightGBM runner metadata"
            )
            if (
                metadata.get("status") != "blocked"
                or metadata.get("model_class")
                != "qlib.contrib.model.gbdt.LGBModel"
                or metadata.get("model_configuration_fingerprint")
                != plan.model_configuration_fingerprint
                or metadata.get("evaluation_protocol_fingerprint")
                != plan.evaluation_protocol_fingerprint
                or metadata.get("best_iteration") is None
                or metadata.get("tree_count") is None
                or metadata.get("predictions_written") is not False
            ):
                raise ValueError("runner metadata acceptance fields mismatch")
            history = _read_json(
                outputs["training_history"], "LightGBM training history"
            )
            if not history or not {"train", "valid"}.issubset(history):
                raise ValueError("training history lacks train/valid metrics")
            gain = pd.read_csv(outputs["feature_importance_gain"])
            split = pd.read_csv(outputs["feature_importance_split"])
            if (
                list(gain["feature"]) != specification["feature_list"]
                or list(split["feature"]) != specification["feature_list"]
                or gain["importance_gain"].isna().any()
                or split["importance_split"].isna().any()
            ):
                raise ValueError("feature-importance artifacts mismatch")
            if not _read_json(
                outputs["model_dump"], "diagnostic LightGBM model dump"
            ):
                raise ValueError("diagnostic model dump is empty")
        except (
            OSError, KeyError, ValueError, pd.errors.ParserError
        ) as exc:
            artifact_problem = str(exc)
    blocker_matched = (
        completed.returncode != 0
        and diagnostics.get("blocker_matched") is True
        and diagnostics.get("predictions_attempted") is False
        and artifact_problem is None
    )
    status = "blocked" if blocker_matched else "failed"
    failure_reason = (
        artifact_problem
        or diagnostics.get("failure_message")
        or completed.stderr.strip()
        or "compatibility proof failed without diagnostics"
    )
    execution = {
        "schema_version": "1.0",
        "status": status,
        "expected_nonzero_exit": True,
        "blocker_matched": blocker_matched,
        "command": command,
        "exit_code": completed.returncode,
        "duration_seconds": duration,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "thread_controls": THREAD_CONTROLS,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    write_canonical_json(execution, attempt / "execution_report.json")
    write_canonical_json({
        "schema_version": "1.0",
        "status": status,
        "run_id": request["run_id"],
        "model_id": MODEL_ID,
        "failure_reason": failure_reason,
        "source_manifest":
            "research/manifests/qlib_lightgbm_compatibility_planned.json",
        "frozen_specification": str(selected.frozen_specification),
        "model_configuration_fingerprint":
            plan.model_configuration_fingerprint,
        "evaluation_protocol_fingerprint":
            plan.evaluation_protocol_fingerprint,
        "predictions_produced": False,
        "evaluation_produced": False,
        "registry_promotion_permitted": False,
        "evidence_scope": specification["evidence_scope"],
    }, attempt / "failed_manifest.json")
    write_canonical_json({
        "schema_version": "1.0",
        "self_referential_exclusions": [
            "artifact_inventory.json",
            "execution_report.json",
            "failed_manifest.json",
        ],
        "artifacts": _inventory(attempt),
    }, attempt / "artifact_inventory.json")
    write_canonical_json({
        "schema_version": "1.0",
        "batch_id": plan.batch_id,
        "status": status,
        "attempt_count": 1,
        "second_attempt_permitted": False,
        "failure_reason": failure_reason,
        "accepted_source_artifacts_rewritten": False,
        "registry_source_mutated_at_runtime": False,
    }, plan.output_directory / "batch_execution_report.json")
    write_canonical_json({
        "schema_version": "1.0",
        "proposed_changes": [],
        "qlib_lightgbm_status": "adoption_specified",
        "promotion_blocked": True,
        "reason": failure_reason,
    }, plan.output_directory / "proposed_registry_status_update.json")
    if not blocker_matched:
        raise RuntimeError(
            "official compatibility attempt did not produce the expected "
            f"workflow blocker: {failure_reason}"
        )
    return QlibLightGBMCompatibilityResult(
        batch_id=plan.batch_id,
        directory=plan.output_directory,
        attempt_directory=attempt,
        status=status,
        exit_code=completed.returncode,
        failure_reason=failure_reason,
    )
