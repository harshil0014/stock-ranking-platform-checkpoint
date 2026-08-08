"""Qlib-free orchestration for the official frozen TRA reproduction."""

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
from stock_research.fingerprints import (
    fingerprint_file,
    model_configuration_fingerprint,
)
from stock_research.synthetic_qlib import write_canonical_csv, write_canonical_json


MODEL_ID = "qlib_tra_v0_9_7"
DEFAULT_OUTPUT_ROOT = Path("research/generated/qlib-tra")
DEFAULT_BATCH_ID = "official-frozen-tra-20260731"
DEFAULT_LINEAR_BATCH = Path("research/generated/qlib-linear/final-locked-20260731")
DEFAULT_LIGHTGBM_BATCH = Path(
    "research/generated/qlib-lightgbm/official-local-recorder-opt-in-20260731"
)
DEFAULT_DOUBLEENSEMBLE_BATCH = Path(
    "research/generated/qlib-doubleensemble/official-frozen-reproduction-20260731"
)
DEFAULT_INTERPRETER = Path(".venv-tra/Scripts/python.exe")
DEFAULT_ENVIRONMENT_REPORT = Path("research/environment/tra_environment_report.json")
DEFAULT_LOCK = Path("research/environment/tra_dependency_lock.txt")
DEFAULT_SPECIFICATION = Path("research/specifications/qlib_tra_frozen_protocol.json")
RUNNER_PATH = Path("research/runners/qlib_tra_runner.py")
PLANNED_MANIFEST = Path("research/manifests/qlib_tra_reproduction_planned.json")

SUBPROCESS_CONTROLS = {
    "CUDA_VISIBLE_DEVICES": "",
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
MODEL_CONFIG = {
    "input_size": 10, "hidden_size": 64, "num_layers": 2,
    "rnn_arch": "LSTM", "use_attn": True, "dropout": 0.0,
}
TRA_CONFIG = {
    "num_states": 3, "rnn_arch": "LSTM", "hidden_size": 32,
    "num_layers": 1, "dropout": 0.0, "tau": 1.0,
    "src_info": "LR_TPE",
}
MODEL_PARAMETERS = {
    "model_type": "RNN", "lr": 1e-3, "n_epochs": 100,
    "early_stop": 20, "update_freq": 1, "max_steps_per_epoch": None,
    "lamb": 1.0, "rho": 0.99, "alpha": 0.5, "seed": 20260730,
    "logdir": None, "eval_train": False, "eval_test": False,
    "pretrain": True, "init_state": None, "reset_router": False,
    "freeze_model": False, "freeze_predictors": False,
    "transport_method": "router", "memory_mode": "sample",
}
DATASET_CONFIG = {
    "seq_len": 60, "horizon": 1, "input_size": None, "num_states": 3,
    "batch_size": 1024, "n_samples": None, "memory_mode": "sample",
    "shuffle": True, "drop_last": True,
}


@dataclass(frozen=True, slots=True)
class QlibTRAReproductionConfig:
    output_root: Path = DEFAULT_OUTPUT_ROOT
    frozen_linear_batch: Path = DEFAULT_LINEAR_BATCH
    accepted_lightgbm_batch: Path = DEFAULT_LIGHTGBM_BATCH
    doubleensemble_batch: Path = DEFAULT_DOUBLEENSEMBLE_BATCH
    tra_interpreter: Path = DEFAULT_INTERPRETER
    environment_report: Path = DEFAULT_ENVIRONMENT_REPORT
    dependency_lock: Path = DEFAULT_LOCK
    frozen_specification: Path = DEFAULT_SPECIFICATION
    seed: int = 20260730
    reruns: int = 2
    reproducibility_tolerance: float = 1e-12
    timeout_seconds: int = 7200
    batch_id: str = DEFAULT_BATCH_ID
    keep_failed_artifacts: bool = True
    resume_completed_run_one: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or self.seed != 20260730:
            raise ValueError("seed is frozen at 20260730")
        if isinstance(self.reruns, bool) or self.reruns != 2:
            raise ValueError("reruns must be exactly 2")
        if float(self.reproducibility_tolerance) != 1e-12:
            raise ValueError("reproducibility_tolerance is frozen at 1e-12")
        if isinstance(self.timeout_seconds, bool) or self.timeout_seconds != 7200:
            raise ValueError("timeout_seconds is frozen at 7200")
        if not self.batch_id.strip():
            raise ValueError("batch_id must not be blank")
        for name in (
            "output_root", "frozen_linear_batch", "accepted_lightgbm_batch",
            "doubleensemble_batch", "tra_interpreter", "environment_report",
            "dependency_lock", "frozen_specification",
        ):
            object.__setattr__(self, name, Path(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class QlibTRAReproductionPlan:
    batch_id: str
    output_directory: Path
    commands: tuple[tuple[str, ...], ...]
    selected_source_run: Path
    selected_lightgbm_run: Path
    selected_doubleensemble_run: Path
    environment_fingerprint: str
    evaluation_protocol_fingerprint: str
    model_configuration_fingerprint: str
    model_config: dict[str, Any]
    tra_config: dict[str, Any]
    model_parameters: dict[str, Any]
    dataset_config: dict[str, Any]
    subprocess_environment_controls: dict[str, str]


@dataclass(frozen=True, slots=True)
class QlibTRARunResult:
    run_id: str
    directory: Path
    execution_report: dict[str, Any]
    evaluation_summary: dict[str, Any]


@dataclass(frozen=True, slots=True)
class QlibTRABatchResult:
    batch_id: str
    directory: Path
    runs: tuple[QlibTRARunResult, ...]
    reproducibility: dict[str, Any]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def build_tra_subprocess_environment(
    run_directory: str | Path,
    base: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, bool]]:
    parent = dict(os.environ if base is None else base)
    present = sorted(name for name in FORBIDDEN_ENVIRONMENT if parent.get(name))
    if present:
        raise ValueError(f"prohibited inherited environment variables: {present}")
    audit = {name: bool(parent.get(name)) for name in SUBPROCESS_CONTROLS}
    child = dict(parent)
    child.update(SUBPROCESS_CONTROLS)
    child["MPLCONFIGDIR"] = str(Path(run_directory) / "matplotlib-cache")
    return child, audit


def _model_configuration(specification: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_id": MODEL_ID,
        "upstream_package": "pyqlib==0.9.7",
        "upstream_class": "qlib.contrib.model.pytorch_tra.TRAModel",
        "dataset_class": "qlib.contrib.data.dataset.MTSDatasetH",
        "model_config": MODEL_CONFIG,
        "tra_config": TRA_CONFIG,
        "parameters": MODEL_PARAMETERS,
        "dataset_config": DATASET_CONFIG,
        "features": specification["feature_list"],
        "training_segments": ["train", "valid"],
        "prediction_segment": "test",
        "test_access": "upstream_final_post_selection_diagnostic",
    }


def _validate_inputs(
    config: QlibTRAReproductionConfig,
) -> tuple[dict[str, Any], Path, Path, Path, dict[str, Any]]:
    specification = _read_json(config.frozen_specification)
    environment = _read_json(config.environment_report)
    source_run = config.frozen_linear_batch / "run-01"
    lightgbm_run = config.accepted_lightgbm_batch / "run-01"
    doubleensemble_run = config.doubleensemble_batch / "run-01"
    for path in (
        config.tra_interpreter, config.dependency_lock, source_run,
        lightgbm_run, doubleensemble_run, RUNNER_PATH,
    ):
        if not path.exists():
            raise ValueError(f"required TRA input is missing: {path}")
    if (
        specification.get("seed") != 20260730
        or specification.get("evaluation_protocol_fingerprint")
        != "210bca5c4ac474f766a3caf549d8adc4dc06ae22b3378eb70f4ed224f6978782"
        or specification.get("label_dataset_fingerprint")
        != "7412fc79f8af0acf87b1cb22209842d153e8a6b6e9370e147b43e454ca247f2d"
    ):
        raise ValueError("TRA frozen specification fingerprint mismatch")
    if environment.get("status") != "verified":
        raise ValueError("TRA environment is not verified")
    if environment.get("torch_version") != "2.4.1+cpu":
        raise ValueError("TRA environment Torch version mismatch")
    if fingerprint_file(config.dependency_lock) != environment.get(
        "resolved_lock_sha256"
    ):
        raise ValueError("TRA dependency lock hash mismatch")
    source_root = config.tra_interpreter.resolve().parents[1] / "Lib/site-packages"
    tra_source = source_root / "qlib/contrib/model/pytorch_tra.py"
    dataset_source = source_root / "qlib/contrib/data/dataset.py"
    for path, key in (
        (tra_source, "tra_source_sha256"),
        (dataset_source, "dataset_source_sha256"),
    ):
        if fingerprint_file(path) != specification[key]:
            raise ValueError(f"installed source hash mismatch: {path}")
    canonical = {
        name: source_run / name
        for name in specification["canonical_file_hashes"]
    }
    for name, path in canonical.items():
        if fingerprint_file(path) != specification["canonical_file_hashes"][name]:
            raise ValueError(f"frozen canonical input hash mismatch: {name}")
    baselines = {
        "qlib_linear_signals.csv": source_run / "qlib_signals.csv",
        "research_v2_signals.csv": source_run / "research_v2_signals.csv",
        "research_v2_ineligible.csv":
            source_run / "research_v2_eligibility_report.csv",
        "qlib_lightgbm_signals.csv":
            lightgbm_run / "qlib_lightgbm_signals.csv",
    }
    for name, path in baselines.items():
        if fingerprint_file(path) != specification["accepted_baseline_hashes"][name]:
            raise ValueError(f"accepted baseline hash mismatch: {name}")
    if (
        len(pd.read_csv(baselines["research_v2_signals.csv"])) != 1160
        or len(pd.read_csv(baselines["qlib_linear_signals.csv"])) != 1200
        or len(pd.read_csv(baselines["qlib_lightgbm_signals.csv"])) != 1200
    ):
        raise ValueError("accepted baseline counts mismatch")
    blocker = _read_json(
        doubleensemble_run / "scientific_acceptance_failure.json"
    )
    if (
        blocker.get("blocker_id")
        != "official_frozen_configuration_constant_signal"
        or blocker.get("prediction_count") != 1200
        or blocker.get("valid_ic_dates") != 0
    ):
        raise ValueError("accepted DoubleEnsemble blocker mismatch")
    environment.update({
        "tra_source": tra_source,
        "dataset_source": dataset_source,
        "lock_sha256": fingerprint_file(config.dependency_lock),
    })
    return specification, source_run, lightgbm_run, doubleensemble_run, environment


def plan_qlib_tra_reproduction(
    config: QlibTRAReproductionConfig | None = None,
) -> QlibTRAReproductionPlan:
    selected = config or QlibTRAReproductionConfig()
    specification, source, lightgbm, doubleensemble, environment = _validate_inputs(
        selected
    )
    output = selected.output_root / selected.batch_id
    if output.exists() and not selected.resume_completed_run_one:
        raise ValueError(f"refusing preexisting batch directory: {output}")
    if selected.resume_completed_run_one and (
        not (output / "run-01/tra_runner_metadata.json").is_file()
        or not (output / "run-01/execution_report.json").is_file()
        or (output / "run-02").exists()
    ):
        raise ValueError(
            "resume requires one completed runner output and no run-02"
        )
    build_tra_subprocess_environment(output / "run-01")
    commands = tuple(
        (
            str(selected.tra_interpreter),
            str(RUNNER_PATH),
            str(output / f"run-{number:02d}" / "runner_request.json"),
        )
        for number in range(1, 3)
    )
    return QlibTRAReproductionPlan(
        batch_id=selected.batch_id,
        output_directory=output,
        commands=commands,
        selected_source_run=source,
        selected_lightgbm_run=lightgbm,
        selected_doubleensemble_run=doubleensemble,
        environment_fingerprint=environment["environment_fingerprint"],
        evaluation_protocol_fingerprint=
            specification["evaluation_protocol_fingerprint"],
        model_configuration_fingerprint=model_configuration_fingerprint(
            _model_configuration(specification)
        ),
        model_config=dict(MODEL_CONFIG),
        tra_config=dict(TRA_CONFIG),
        model_parameters=dict(MODEL_PARAMETERS),
        dataset_config=dict(DATASET_CONFIG),
        subprocess_environment_controls=dict(SUBPROCESS_CONTROLS),
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


def _copy_inputs(
    run: Path, plan: QlibTRAReproductionPlan, specification: dict[str, Any]
) -> dict[str, Path]:
    copied_dir = run / "copied_inputs"
    copied_dir.mkdir(parents=True)
    sources = {
        name: plan.selected_source_run / name
        for name in specification["canonical_file_hashes"]
    }
    sources.update({
        "accepted_research_v2_signals.csv":
            plan.selected_source_run / "research_v2_signals.csv",
        "accepted_research_v2_ineligible.csv":
            plan.selected_source_run / "research_v2_eligibility_report.csv",
        "accepted_qlib_linear_signals.csv":
            plan.selected_source_run / "qlib_signals.csv",
        "accepted_qlib_lightgbm_signals.csv":
            plan.selected_lightgbm_run / "qlib_lightgbm_signals.csv",
    })
    copied: dict[str, Path] = {}
    inventory = []
    for name, source in sources.items():
        destination = copied_dir / name
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
    }, run / "copied_input_inventory.json")
    return copied


def _runner_outputs(run: Path) -> dict[str, Path]:
    return {
        "predictions": run / "tra_predictions_raw.csv",
        "state_scores": run / "tra_state_scores.csv",
        "audit_labels": run / "tra_prediction_labels_audit.csv",
        "independent_audit": run / "sequence_boundary_report.json",
        "official_audit": run / "official_dataset_audit.json",
        "training_history": run / "training_history.json",
        "phase_summary": run / "phase_summary.json",
        "backbone_state": run / "backbone_state_manifest.json",
        "tra_state": run / "tra_state_manifest.json",
        "combined_state": run / "combined_state_fingerprint.json",
        "metadata": run / "tra_runner_metadata.json",
        "official_log": run / "official_training.log",
    }


def _request(
    run: Path,
    run_id: str,
    plan: QlibTRAReproductionPlan,
    config: QlibTRAReproductionConfig,
    specification: dict[str, Any],
    copied: dict[str, Path],
) -> dict[str, Any]:
    environment = _read_json(config.environment_report)
    split = _read_json(copied["split.json"])
    request = {
        "schema_version": "1.0", "run_id": run_id, "model_id": MODEL_ID,
        "panel_path": str(copied["synthetic_qlib_panel.csv"].resolve()),
        "panel_sha256": fingerprint_file(copied["synthetic_qlib_panel.csv"]),
        "labels_path": str(copied["synthetic_labels.csv"].resolve()),
        "labels_sha256": fingerprint_file(copied["synthetic_labels.csv"]),
        "expected_panel_rows": 6000, "expected_instrument_count": 30,
        "expected_test_rows": 1200,
        "feature_columns": specification["feature_list"],
        "label_name": specification["label_name"],
        "segments": {
            "train": split["train"], "valid": split["validation"],
            "test": split["test"],
        },
        "segment_row_counts": {"train": 3600, "valid": 900, "test": 1200},
        "model_config": MODEL_CONFIG, "tra_config": TRA_CONFIG,
        "model_parameters": MODEL_PARAMETERS, "dataset_config": DATASET_CONFIG,
        "subprocess_environment_controls": SUBPROCESS_CONTROLS,
        "environment_report": str(config.environment_report.resolve()),
        "environment_report_sha256": fingerprint_file(config.environment_report),
        "environment_fingerprint": environment["environment_fingerprint"],
        "resolved_lock": str(config.dependency_lock.resolve()),
        "resolved_lock_sha256": fingerprint_file(config.dependency_lock),
        "tra_source": environment["tra_source_path"],
        "tra_source_sha256": specification["tra_source_sha256"],
        "dataset_source": environment["dataset_source_path"],
        "dataset_source_sha256": specification["dataset_source_sha256"],
        "model_configuration_fingerprint":
            plan.model_configuration_fingerprint,
        "evaluation_protocol_fingerprint":
            plan.evaluation_protocol_fingerprint,
        "outputs": {
            name: str(path.resolve()) for name, path in _runner_outputs(run).items()
        },
    }
    write_canonical_json(request, run / "runner_request.json")
    return request


def _run_process(
    command: tuple[str, ...], run: Path, timeout: int
) -> dict[str, Any]:
    environment, parent = build_tra_subprocess_environment(run)
    started = datetime.now(timezone.utc)
    begin = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            command, cwd=Path.cwd(), env=environment, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
            check=False,
        )
        exit_code = completed.returncode
        stdout, stderr = completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = 124
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + "\nTRA runner exceeded 7200 seconds"
    report = {
        "schema_version": "1.0",
        "status": "failed" if exit_code else "completed",
        "command": list(command), "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_seconds": time.monotonic() - begin,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "stdout": stdout, "stderr": stderr,
        "subprocess_environment_controls": SUBPROCESS_CONTROLS,
        "parent_control_presence": parent,
    }
    write_canonical_json(report, run / "execution_report.json")
    return report


def _evaluate_run(
    run: Path,
    run_id: str,
    plan: QlibTRAReproductionPlan,
    copied: dict[str, Path],
) -> dict[str, Any]:
    raw = pd.read_csv(run / "tra_predictions_raw.csv")
    raw = raw.rename(columns={"datetime": "as_of_date", "instrument": "qlib_instrument"})
    signals, dropped = convert_qlib_predictions(
        raw, copied["qlib_instrument_mapping.csv"], model_id=MODEL_ID,
        run_id=run_id, upstream_model_id="TRAModel",
        upstream_run_id=run_id,
    )
    if len(signals) != 1200 or not dropped.empty:
        raise RuntimeError("TRA canonical signal conversion mismatch")
    write_canonical_csv(signals, run / "tra_signals.csv")
    labels = pd.read_csv(
        copied["synthetic_labels.csv"],
        dtype={"as_of_date": str, "label_end_date": str},
        float_precision="round_trip",
    )
    protocol = _protocol(plan.selected_source_run)
    tra_result = evaluate_signals(
        signals, labels, protocol,
        model_configuration_fingerprint=plan.model_configuration_fingerprint,
        dataset_fingerprints=_read_json(copied["dataset_fingerprints.json"]),
        provenance={"class": "qlib.contrib.model.pytorch_tra.TRAModel"},
        output_dir=run / "qlib_tra_evaluation",
    )
    accepted = (
        (
            copied["accepted_research_v2_signals.csv"],
            plan.selected_source_run
            / "evaluation_research_v2/evaluation_summary.json",
            "research_v2_evaluation",
        ),
        (
            copied["accepted_qlib_linear_signals.csv"],
            plan.selected_source_run / "evaluation_qlib/evaluation_summary.json",
            "qlib_linear_evaluation",
        ),
        (
            copied["accepted_qlib_lightgbm_signals.csv"],
            plan.selected_lightgbm_run
            / "evaluation_lightgbm/evaluation_summary.json",
            "qlib_lightgbm_evaluation",
        ),
    )
    summaries: list[dict[str, Any]] = []
    for signal_path, accepted_summary_path, output_name in accepted:
        accepted_summary = _read_json(accepted_summary_path)
        result = evaluate_signals(
            pd.read_csv(signal_path), labels, protocol,
            model_configuration_fingerprint=
                accepted_summary["model_configuration_fingerprint"],
            dataset_fingerprints=accepted_summary["dataset_fingerprints"],
            provenance=accepted_summary["provenance"],
            output_dir=run / output_name,
        )
        summaries.append(result.summary)
    summaries.append(tra_result.summary)
    comparison = compare_evaluations(
        summaries, output_path=run / "model_status_comparison.csv"
    )
    blocker = _read_json(
        plan.selected_doubleensemble_run / "scientific_acceptance_failure.json"
    )
    write_canonical_json({
        "schema_version": "1.0",
        "evaluated_models": json.loads(
            comparison.to_json(orient="records", date_format="iso")
        ),
        "status_only_models": [{
            "model_id": "qlib_doubleensemble_v0_9_7",
            "status": "compatibility_blocker",
            "reason": blocker["failure_reason"],
            "prediction_count": blocker["prediction_count"],
            "valid_ic_dates": 0, "valid_rank_ic_dates": 0,
        }],
        "evaluation_protocol_fingerprint":
            plan.evaluation_protocol_fingerprint,
        "portfolio_metrics_calculated": False,
        "investment_claim": False,
    }, run / "model_status_comparison.json")
    return tra_result.summary


def _scientific_gate(run: Path, execution: dict[str, Any]) -> dict[str, Any]:
    metadata = _read_json(run / "tra_runner_metadata.json")
    phase = _read_json(run / "phase_summary.json")
    evaluation = _read_json(
        run / "qlib_tra_evaluation/evaluation_summary.json"
    )
    daily = pd.read_csv(run / "qlib_tra_evaluation/daily_ic.csv")
    predictions = pd.read_csv(run / "tra_predictions_raw.csv")
    state = pd.read_csv(run / "tra_state_scores.csv")
    nonconstant = int(
        predictions.groupby("datetime")["score"].nunique().gt(1).sum()
    )
    checks = {
        "runner_completed": execution["exit_code"] == 0,
        "runtime_below_timeout":
            execution["duration_seconds"] < 7200 and not execution["timed_out"],
        "official_identity":
            metadata["model_class"]
            == "qlib.contrib.model.pytorch_tra.TRAModel"
            and metadata["dataset_class"]
            == "qlib.contrib.data.dataset.MTSDatasetH",
        "both_phases": len(phase["phases"]) == 2,
        "finite_selected_score": bool(
            np.isfinite(float(phase["final_selected_score"]))
        ),
        "one_public_predict": metadata["predict_call_count"] == 1,
        "prediction_count": len(predictions) == 1200,
        "unique_keys": bool(
            not predictions.duplicated(["datetime", "instrument"]).any()
        ),
        "finite_predictions": bool(
            np.isfinite(predictions["score"].to_numpy(float)).all()
        ),
        "three_state_scores":
            list(state.columns[-3:]) == ["score_0", "score_1", "score_2"],
        "nonconstant_dates": nonconstant >= 2,
        "valid_ic_dates": evaluation["valid_ic_dates"] >= 2,
        "valid_rank_ic_dates": evaluation["valid_rank_ic_dates"] >= 2,
        "sequence_audit":
            _read_json(run / "official_dataset_audit.json")["status"] == "passed",
        "finite_state":
            _read_json(run / "backbone_state_manifest.json")["all_finite"]
            and _read_json(run / "tra_state_manifest.json")["all_finite"],
        "no_fallback": not metadata["provider_initialized"]
            and not metadata["workflow_initialized"]
            and not metadata["network_used"],
    }
    gate = {
        "schema_version": "1.0",
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks, "nonconstant_dates": nonconstant,
        "valid_ic_dates": evaluation["valid_ic_dates"],
        "valid_rank_ic_dates": evaluation["valid_rank_ic_dates"],
    }
    write_canonical_json(gate, run / "scientific_gate.json")
    if gate["status"] != "passed":
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise RuntimeError(f"TRA run-01 scientific gate failed: {failed}")
    return gate


def compare_tra_runs(
    run_one: str | Path,
    run_two: str | Path,
    tolerance: float = 1e-12,
) -> dict[str, Any]:
    if tolerance != 1e-12:
        raise ValueError("TRA reproducibility tolerance is frozen at 1e-12")
    first, second = Path(run_one), Path(run_two)
    score_columns = ["score", "score_0", "score_1", "score_2"]
    differences: dict[str, float] = {}
    for column in score_columns:
        filename = (
            "tra_predictions_raw.csv" if column == "score"
            else "tra_state_scores.csv"
        )
        left, right = pd.read_csv(first / filename), pd.read_csv(second / filename)
        keys = ["datetime", "instrument"]
        if not left[keys].equals(right[keys]):
            raise RuntimeError(f"TRA {column} keys/order differ")
        differences[column] = float(
            np.max(np.abs(left[column].to_numpy() - right[column].to_numpy()))
        )
    meta_one = _read_json(first / "tra_runner_metadata.json")
    meta_two = _read_json(second / "tra_runner_metadata.json")
    phase_one = _read_json(first / "phase_summary.json")
    phase_two = _read_json(second / "phase_summary.json")
    state_one = _read_json(first / "combined_state_fingerprint.json")
    state_two = _read_json(second / "combined_state_fingerprint.json")
    exact = {
        "phase_lengths": [
            item["history_length"] for item in phase_one["phases"]
        ] == [item["history_length"] for item in phase_two["phases"]],
        "selected_epoch":
            phase_one["final_selected_epoch"] == phase_two["final_selected_epoch"],
        "stopping_epoch":
            phase_one["phases"][1]["stopping_epoch"]
            == phase_two["phases"][1]["stopping_epoch"],
        "backbone_state":
            state_one["backbone_state_fingerprint"]
            == state_two["backbone_state_fingerprint"],
        "tra_state":
            state_one["tra_state_fingerprint"]
            == state_two["tra_state_fingerprint"],
        "sequence_fingerprint":
            meta_one["sequence_boundary_fingerprint"]
            == meta_two["sequence_boundary_fingerprint"],
        "environment_fingerprint":
            meta_one["environment_fingerprint"]
            == meta_two["environment_fingerprint"],
        "model_fingerprint":
            meta_one["model_configuration_fingerprint"]
            == meta_two["model_configuration_fingerprint"],
        "protocol_fingerprint":
            meta_one["evaluation_protocol_fingerprint"]
            == meta_two["evaluation_protocol_fingerprint"],
        "controls":
            meta_one["subprocess_environment_controls"]
            == meta_two["subprocess_environment_controls"],
    }
    passed = (
        all(value <= tolerance for value in differences.values())
        and all(exact.values())
    )
    return {
        "schema_version": "1.0", "status": "passed" if passed else "failed",
        "tolerance": tolerance, "maximum_differences": differences,
        "exact_checks": exact,
    }


def _inventory(directory: Path) -> list[dict[str, Any]]:
    excluded = {
        "artifact_inventory.json", "execution_report.json",
        "completed_manifest.json", "failed_manifest.json",
    }
    rows = []
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        relative = path.relative_to(directory).as_posix()
        if relative in excluded or relative.startswith("matplotlib-cache/"):
            continue
        rows.append({
            "relative_path": relative, "sha256": fingerprint_file(path),
            "size_bytes": path.stat().st_size,
            "role": relative.split("/", 1)[0],
            "producing_environment":
                "tra-python-3.12" if relative.startswith((
                    "tra_", "official_", "backbone_", "combined_",
                    "training_", "phase_", "sequence_",
                )) else "product-python-3.13",
            "generated_timestamp": datetime.fromtimestamp(
                path.stat().st_mtime, timezone.utc
            ).isoformat(),
        })
    return rows


def _finalize_run(
    run: Path, run_id: str, plan: QlibTRAReproductionPlan
) -> None:
    evaluation = run / "qlib_tra_evaluation/evaluation_summary.json"
    write_canonical_json({
        "schema_version": "1.0", "run_id": run_id, "model_id": MODEL_ID,
        "status": "completed", "source_manifest": str(PLANNED_MANIFEST),
        "model_configuration_fingerprint":
            plan.model_configuration_fingerprint,
        "evaluation_protocol_fingerprint":
            plan.evaluation_protocol_fingerprint,
        "evaluation_artifacts": [{
            "path": str(evaluation), "sha256": fingerprint_file(evaluation),
        }],
        "evidence_scope":
            "official Qlib v0.9.7 TRAModel frozen synthetic sequence reproduction",
    }, run / "completed_manifest.json")
    write_canonical_json({
        "schema_version": "1.0",
        "self_referential_exclusions": [
            "artifact_inventory.json", "execution_report.json",
            "completed_manifest.json", "failed_manifest.json",
        ],
        "artifacts": _inventory(run),
    }, run / "artifact_inventory.json")


def run_qlib_tra_reproduction(
    config: QlibTRAReproductionConfig | None = None,
) -> QlibTRABatchResult:
    selected = config or QlibTRAReproductionConfig()
    plan = plan_qlib_tra_reproduction(selected)
    specification = _read_json(selected.frozen_specification)
    plan.output_directory.mkdir(
        parents=True, exist_ok=selected.resume_completed_run_one
    )
    results: list[QlibTRARunResult] = []
    try:
        for index, command in enumerate(plan.commands, start=1):
            run = plan.output_directory / f"run-{index:02d}"
            if index == 1 and selected.resume_completed_run_one:
                metadata = _read_json(run / "tra_runner_metadata.json")
                execution = _read_json(run / "execution_report.json")
                if (
                    execution.get("exit_code") != 0
                    or metadata.get("fit_call_count") != 1
                    or metadata.get("predict_call_count") != 1
                    or metadata.get("prediction_count") != 1200
                ):
                    raise RuntimeError(
                        "resume rejected incomplete run-01 runner evidence"
                    )
                runner_artifacts = (
                    "tra_predictions_raw.csv", "tra_state_scores.csv",
                    "backbone_state_manifest.json", "tra_state_manifest.json",
                    "combined_state_fingerprint.json", "training_history.json",
                    "phase_summary.json", "official_dataset_audit.json",
                    "sequence_boundary_report.json",
                )
                before = {
                    name: fingerprint_file(run / name)
                    for name in runner_artifacts
                }
                copied = {
                    path.name: path
                    for path in (run / "copied_inputs").iterdir()
                    if path.is_file()
                }
                run_id = metadata["run_id"]
                execution["product_postprocessing_resumed_without_retraining"] = True
                execution["runner_reinvoked"] = False
                execution["runner_artifact_hashes_before_resume"] = before
                write_canonical_json(execution, run / "execution_report.json")
            else:
                run.mkdir()
                copied = _copy_inputs(run, plan, specification)
                run_id = str(uuid4())
                _request(run, run_id, plan, selected, specification, copied)
                execution = _run_process(command, run, selected.timeout_seconds)
                if execution["exit_code"] != 0:
                    raise RuntimeError(
                        f"TRA run-{index:02d} failed: "
                        f"{execution['stderr'].strip()}"
                    )
            summary = _evaluate_run(run, run_id, plan, copied)
            if index == 1:
                _scientific_gate(run, execution)
                if selected.resume_completed_run_one:
                    after = {
                        name: fingerprint_file(run / name)
                        for name in runner_artifacts
                    }
                    if after != before:
                        raise RuntimeError(
                            "resume changed official run-01 artifacts"
                        )
                    execution["runner_artifact_hashes_after_resume"] = after
                    write_canonical_json(execution, run / "execution_report.json")
            _finalize_run(run, run_id, plan)
            results.append(QlibTRARunResult(
                run_id=run_id, directory=run,
                execution_report=execution, evaluation_summary=summary,
            ))
        reproducibility = compare_tra_runs(
            results[0].directory, results[1].directory,
            selected.reproducibility_tolerance,
        )
        write_canonical_json(
            reproducibility,
            plan.output_directory / "reproducibility_report.json",
        )
        if reproducibility["status"] != "passed":
            raise RuntimeError("TRA two-run reproducibility failed")
        write_canonical_json({
            "schema_version": "1.0", "status": "completed",
            "batch_id": plan.batch_id, "run_count": 2,
            "registry_source_mutated_at_runtime": False,
            "reproducibility_status": "passed",
        }, plan.output_directory / "batch_execution_report.json")
        write_canonical_json({
            "schema_version": "1.0",
            "proposed_changes": [{
                "registry_id": "qlib_tra",
                "adoption_status": "synthetic_reproduced",
            }],
            "runtime_registry_mutation": False,
            "scope": "offline frozen synthetic sequence reproduction only",
        }, plan.output_directory / "proposed_registry_status_update.json")
    except Exception as exc:
        write_canonical_json({
            "schema_version": "1.0", "status": "blocked",
            "batch_id": plan.batch_id,
            "attempted_run_count": len(list(plan.output_directory.glob("run-*"))),
            "accepted_run_count": len(results),
            "failure_reason": f"{type(exc).__name__}: {exc}",
            "registry_promotion_permitted": False,
            "registry_source_mutated_at_runtime": False,
        }, plan.output_directory / "batch_execution_report.json")
        write_canonical_json({
            "schema_version": "1.0", "proposed_changes": [],
            "qlib_tra_status": "adoption_specified",
            "promotion_blocked": True,
            "reason": f"{type(exc).__name__}: {exc}",
        }, plan.output_directory / "proposed_registry_status_update.json")
        raise
    return QlibTRABatchResult(
        batch_id=plan.batch_id, directory=plan.output_directory,
        runs=tuple(results), reproducibility=reproducibility,
    )
