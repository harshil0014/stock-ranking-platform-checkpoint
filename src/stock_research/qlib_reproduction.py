"""Offline orchestration for the pinned Qlib Linear synthetic reproduction."""

from __future__ import annotations

from dataclasses import asdict, dataclass
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

from stock_ranker.research_v2 import ResearchV2Inputs, calculate_research_v2
from stock_ranker.v2_config import ResearchV2Config
from stock_research.adapters import convert_qlib_predictions, research_v2_to_signals
from stock_research.comparison import compare_evaluations
from stock_research.evaluation import EvaluationProtocol, evaluate_signals
from stock_research.fingerprints import (
    fingerprint_config,
    fingerprint_dataframe,
    fingerprint_file,
    model_configuration_fingerprint,
)
from stock_research.synthetic_qlib import (
    DEFAULT_SEED,
    FEATURE_COLUMNS,
    LABEL_NAME,
    THREAD_CONTROLS,
    SyntheticDatasetBundle,
    generate_synthetic_qlib_data,
    write_canonical_csv,
    write_canonical_json,
)


MODEL_ID = "qlib_linear_ols_v0_9_7"
RESEARCH_V2_MODEL_ID = "research_v2_baseline"
MODEL_PARAMETERS = {
    "estimator": "ols",
    "alpha": 0.0,
    "fit_intercept": False,
    "include_valid": False,
}
DEFAULT_OUTPUT_ROOT = Path("research/generated/qlib-linear")
DEFAULT_INTERPRETER = Path(".venv-qlib/Scripts/python.exe")
DEFAULT_ENVIRONMENT_REPORT = Path(
    "research/generated/qlib-environment-verified.json"
)
RUNNER_PATH = Path("research/runners/qlib_linear_runner.py")


@dataclass(frozen=True, slots=True)
class QlibLinearReproductionConfig:
    seed: int = DEFAULT_SEED
    output_root: Path = DEFAULT_OUTPUT_ROOT
    qlib_interpreter: Path = DEFAULT_INTERPRETER
    environment_report: Path = DEFAULT_ENVIRONMENT_REPORT
    reruns: int = 2
    keep_failed_artifacts: bool = True
    reproducibility_tolerance: float = 1e-12
    batch_id: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        if isinstance(self.reruns, bool) or self.reruns != 2:
            raise ValueError("reruns must be exactly 2 for acceptance")
        tolerance = float(self.reproducibility_tolerance)
        if not np.isfinite(tolerance) or tolerance <= 0:
            raise ValueError("reproducibility_tolerance must be positive")
        object.__setattr__(self, "output_root", Path(self.output_root))
        object.__setattr__(self, "qlib_interpreter", Path(self.qlib_interpreter))
        object.__setattr__(self, "environment_report", Path(self.environment_report))


@dataclass(frozen=True, slots=True)
class ReproductionPlan:
    batch_id: str
    output_directory: Path
    commands: tuple[tuple[str, ...], ...]
    environment_fingerprint: str
    dataset_fingerprints: dict[str, str]
    model_configuration_fingerprint: str
    evaluation_protocol_fingerprint: str
    row_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class ReproductionRunResult:
    run_id: str
    directory: Path
    execution_report: dict[str, Any]
    qlib_evaluation: dict[str, Any]
    research_v2_evaluation: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ReproductionBatchResult:
    batch_id: str
    directory: Path
    runs: tuple[ReproductionRunResult, ...]
    reproducibility: dict[str, Any]


def build_qlib_subprocess_environment(
    base: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return a subprocess environment with deterministic numerical threading."""

    environment = dict(os.environ if base is None else base)
    environment.update(THREAD_CONTROLS)
    return environment


def _load_environment(config: QlibLinearReproductionConfig) -> dict[str, Any]:
    if not config.qlib_interpreter.is_file():
        raise ValueError(f"Qlib interpreter does not exist: {config.qlib_interpreter}")
    try:
        report = json.loads(config.environment_report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Qlib environment report: {exc}") from exc
    if report.get("status") != "verified":
        raise ValueError("Qlib environment report is not verified")
    reported_interpreter = Path(report.get("interpreter", ""))
    if not reported_interpreter.is_file() or (
        reported_interpreter.resolve() != config.qlib_interpreter.resolve()
    ):
        raise ValueError("Qlib interpreter does not match the verified report")
    import_results = report.get("import_results")
    if not isinstance(import_results, dict) or any(
        not import_results.get(name, {}).get("ok")
        for name in (
            "qlib", "lightgbm", "numpy", "pandas",
            "qlib.contrib.data.handler", "qlib.contrib.model.linear",
        )
    ):
        raise ValueError("Qlib environment import smoke checks are incomplete")
    if import_results["qlib"].get("version") != "0.9.7":
        raise ValueError("verified Qlib version must be 0.9.7")
    packages = report.get("packages")
    if not isinstance(packages, list) or "pyqlib==0.9.7" not in packages:
        raise ValueError("verified environment lock does not contain pyqlib==0.9.7")
    if not RUNNER_PATH.is_file():
        raise ValueError(f"standalone Qlib runner is missing: {RUNNER_PATH}")
    fingerprint = report.get("environment_fingerprint")
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise ValueError("Qlib environment fingerprint is missing")
    lock_path = Path(report.get("resolved_lock", ""))
    if not lock_path.is_file():
        raise ValueError(f"resolved Qlib dependency lock is missing: {lock_path}")
    return {
        "report": report,
        "report_sha256": fingerprint_file(config.environment_report),
        "lock_path": lock_path,
        "lock_sha256": fingerprint_file(lock_path),
    }


def _model_configuration() -> dict[str, Any]:
    return {
        "model_id": MODEL_ID,
        "upstream_package": "pyqlib==0.9.7",
        "upstream_class": "qlib.contrib.model.linear.LinearModel",
        "parameters": MODEL_PARAMETERS,
        "features": list(FEATURE_COLUMNS),
        "seed": DEFAULT_SEED,
        "implementation_release": {"tag": "v0.9.7", "commit": "da920b7"},
    }


def _protocol(bundle: SyntheticDatasetBundle) -> EvaluationProtocol:
    return EvaluationProtocol(
        label_name=LABEL_NAME,
        label_definition=bundle.metadata["label_definition"],
        label_dataset_fingerprint=fingerprint_dataframe(bundle.labels),
        train_start=bundle.split.train.start.isoformat(),
        train_end=bundle.split.train.end.isoformat(),
        validation_start=bundle.split.validation.start.isoformat(),
        validation_end=bundle.split.validation.end.isoformat(),
        test_start=bundle.split.test.start.isoformat(),
        test_end=bundle.split.test.end.isoformat(),
        purge_days=bundle.split.purge_days,
        embargo_days=bundle.split.embargo_days,
        evaluation_frequency="daily",
        metric_definitions={
            "ic": "per-date Pearson correlation",
            "rank_ic": "per-date Spearman correlation using average ranks",
            "icir": "mean divided by sample standard deviation",
            "coverage": "usable matched observations divided by label observations",
        },
        annualization_factor=252.0,
        minimum_cross_sectional_observations=2,
        test_universe_policy="all 30 fictional instruments in the frozen test panel",
    )


def _dataset_fingerprints(bundle: SyntheticDatasetBundle) -> dict[str, str]:
    return {
        "features": fingerprint_dataframe(bundle.features),
        "labels": fingerprint_dataframe(bundle.labels),
        "prices": fingerprint_dataframe(bundle.prices),
        "fundamentals": fingerprint_dataframe(bundle.fundamentals),
        "universe": fingerprint_dataframe(bundle.universe),
        "mapping": fingerprint_dataframe(bundle.mapping),
        "generation_metadata": fingerprint_config(bundle.metadata),
    }


def plan_qlib_linear_reproduction(
    config: QlibLinearReproductionConfig | None = None,
) -> ReproductionPlan:
    """Validate and plan a batch without writing or training."""

    selected = config or QlibLinearReproductionConfig()
    environment = _load_environment(selected)
    bundle = generate_synthetic_qlib_data(selected.seed)
    protocol = _protocol(bundle)
    batch_id = selected.batch_id or str(uuid4())
    directory = selected.output_root / batch_id
    commands = tuple(
        (
            str(selected.qlib_interpreter),
            str(RUNNER_PATH),
            str(directory / f"run-{number:02d}" / "runner_request.json"),
        )
        for number in range(1, selected.reruns + 1)
    )
    test_rows = int(
        bundle.features["as_of_date"].between(
            bundle.split.test.start.isoformat(), bundle.split.test.end.isoformat()
        ).sum()
    )
    return ReproductionPlan(
        batch_id=batch_id,
        output_directory=directory,
        commands=commands,
        environment_fingerprint=environment["report"]["environment_fingerprint"],
        dataset_fingerprints=_dataset_fingerprints(bundle),
        model_configuration_fingerprint=model_configuration_fingerprint(
            _model_configuration()
        ),
        evaluation_protocol_fingerprint=protocol.fingerprint,
        row_counts={
            "features": len(bundle.features),
            "labels": len(bundle.labels),
            "test": test_rows,
        },
    )


def _write_inputs(bundle: SyntheticDatasetBundle, directory: Path) -> dict[str, Path]:
    paths = {
        "features": directory / "synthetic_features.csv",
        "labels": directory / "synthetic_labels.csv",
        "panel": directory / "synthetic_qlib_panel.csv",
        "universe": directory / "synthetic_v2_universe.csv",
        "prices": directory / "synthetic_v2_prices.csv",
        "fundamentals": directory / "synthetic_v2_fundamentals.csv",
        "mapping": directory / "qlib_instrument_mapping.csv",
        "split": directory / "split.json",
        "metadata": directory / "data_generation_metadata.json",
        "latent": directory / "latent_coefficients.json",
    }
    write_canonical_csv(bundle.features, paths["features"])
    write_canonical_csv(bundle.labels, paths["labels"])
    write_canonical_csv(bundle.qlib_panel, paths["panel"], index=True)
    write_canonical_csv(bundle.universe, paths["universe"])
    write_canonical_csv(bundle.prices, paths["prices"])
    write_canonical_csv(bundle.fundamentals, paths["fundamentals"])
    write_canonical_csv(bundle.mapping, paths["mapping"])
    write_canonical_json(bundle.split.as_dict(), paths["split"])
    write_canonical_json(bundle.metadata, paths["metadata"])
    write_canonical_json(bundle.latent_coefficients, paths["latent"])
    return paths


def _run_research_v2(
    bundle: SyntheticDatasetBundle, run_id: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rankings: list[pd.DataFrame] = []
    diagnostics: list[pd.DataFrame] = []
    for ranking_date in pd.bdate_range(
        bundle.split.test.start, bundle.split.test.end
    ):
        result = calculate_research_v2(
            ResearchV2Inputs(
                universe=bundle.universe,
                prices=bundle.prices,
                fundamentals=bundle.fundamentals,
            ),
            ResearchV2Config(ranking_date=ranking_date.date()),
        )
        rankings.append(result.rankings)
        diagnostics.append(result.eligibility)
    combined = pd.concat(rankings, ignore_index=True)
    signals = research_v2_to_signals(combined, run_id=run_id)
    eligibility = pd.concat(diagnostics, ignore_index=True).sort_values(
        ["ranking_date", "ticker"], kind="mergesort"
    ).reset_index(drop=True)
    return signals, eligibility


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
            "timestamp": datetime.fromtimestamp(
                path.stat().st_mtime, timezone.utc
            ).isoformat(),
            "role": relative.split("/", 1)[0],
            "producing_environment": (
                "qlib-python-3.12" if relative.startswith("qlib_")
                else "product-python-3.13"
            ),
        })
    return rows


def _request(
    *,
    run_id: str,
    paths: dict[str, Path],
    outputs: dict[str, Path],
    bundle: SyntheticDatasetBundle,
    config: QlibLinearReproductionConfig,
    environment: dict[str, Any],
    fingerprints: dict[str, str],
    model_fp: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "model_id": MODEL_ID,
        "panel_path": str(paths["panel"].resolve()),
        "panel_sha256": fingerprint_file(paths["panel"]),
        "feature_columns": list(FEATURE_COLUMNS),
        "label_name": LABEL_NAME,
        "segments": {
            name: bundle.split.as_dict()[name]
            for name in ("train", "validation", "test")
        },
        "model_parameters": MODEL_PARAMETERS,
        "model_configuration_fingerprint": model_fp,
        "dataset_fingerprints": fingerprints,
        "environment_report": str(config.environment_report.resolve()),
        "environment_report_sha256": environment["report_sha256"],
        "environment_fingerprint":
            environment["report"]["environment_fingerprint"],
        "resolved_lock": str(environment["lock_path"].resolve()),
        "resolved_lock_sha256": environment["lock_sha256"],
        "thread_controls": THREAD_CONTROLS,
        "expected_test_rows": 1200,
        "intercept_tolerance": 1e-12,
        "outputs": {name: str(path.resolve()) for name, path in outputs.items()},
    }


def _execute_run(
    *,
    number: int,
    batch_directory: Path,
    config: QlibLinearReproductionConfig,
    bundle: SyntheticDatasetBundle,
    environment: dict[str, Any],
    fingerprints: dict[str, str],
    protocol: EvaluationProtocol,
    model_fp: str,
) -> ReproductionRunResult:
    run_id = str(uuid4())
    directory = batch_directory / f"run-{number:02d}"
    if directory.exists():
        raise ValueError(f"refusing preexisting run directory: {directory}")
    directory.mkdir(parents=True)
    started = datetime.now(timezone.utc).isoformat()
    paths = _write_inputs(bundle, directory)
    write_canonical_json(
        fingerprints, directory / "dataset_fingerprints.json"
    )
    write_canonical_json(
        _model_configuration(), directory / "model_configuration.json"
    )
    write_canonical_json(protocol.as_dict(), directory / "evaluation_protocol.json")
    outputs = {
        "predictions": directory / "qlib_indexed_predictions.csv",
        "coefficients": directory / "qlib_coefficients.csv",
        "metadata": directory / "qlib_model_metadata.json",
    }
    request = _request(
        run_id=run_id, paths=paths, outputs=outputs, bundle=bundle,
        config=config, environment=environment, fingerprints=fingerprints,
        model_fp=model_fp,
    )
    request_path = directory / "runner_request.json"
    write_canonical_json(request, request_path)
    command = [
        str(config.qlib_interpreter.resolve()),
        str(RUNNER_PATH.resolve()),
        str(request_path.resolve()),
    ]
    process_environment = build_qlib_subprocess_environment()
    start = time.perf_counter()
    completed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8",
        env=process_environment, check=False,
    )
    duration = time.perf_counter() - start
    execution = {
        "schema_version": "1.0",
        "run_id": run_id,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "thread_controls": THREAD_CONTROLS,
        "exit_code": completed.returncode,
        "duration_seconds": duration,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "status": "completed" if completed.returncode == 0 else "failed",
    }
    if completed.returncode != 0:
        write_canonical_json(execution, directory / "execution_report.json")
        if not config.keep_failed_artifacts:
            shutil.rmtree(directory)
        raise RuntimeError(
            f"Qlib run {number} failed with exit code {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    for path in outputs.values():
        if not path.is_file():
            raise RuntimeError(f"Qlib runner did not create {path}")
    qlib_metadata = json.loads(outputs["metadata"].read_text(encoding="utf-8"))
    if qlib_metadata["run_id"] != run_id:
        raise RuntimeError("Qlib output run ID mismatch")
    if qlib_metadata["thread_controls"] != THREAD_CONTROLS:
        raise RuntimeError("Qlib thread controls were not preserved")

    qlib_signals, dropped = convert_qlib_predictions(
        outputs["predictions"], bundle.mapping,
        model_id=MODEL_ID, run_id=run_id,
        upstream_model_id=MODEL_ID, upstream_run_id=run_id,
    )
    if not dropped.empty or len(qlib_signals) != 1200:
        raise RuntimeError("Qlib signal conversion count mismatch")
    write_canonical_csv(qlib_signals, directory / "qlib_signals.csv")
    write_canonical_csv(dropped, directory / "qlib_unmapped_report.csv")

    v2_run_id = str(uuid4())
    v2_signals, eligibility = _run_research_v2(bundle, v2_run_id)
    if len(v2_signals) != 1160:
        raise RuntimeError(f"expected 1160 Research V2 signals; got {len(v2_signals)}")
    ineligible = eligibility.loc[~eligibility["eligible"]]
    if len(ineligible) != 40 or set(ineligible["ticker"]) != {"SYN030"}:
        raise RuntimeError("Research V2 ineligibility diagnostics mismatch")
    write_canonical_csv(v2_signals, directory / "research_v2_signals.csv")
    write_canonical_csv(
        eligibility, directory / "research_v2_eligibility_report.csv"
    )

    qlib_eval = evaluate_signals(
        qlib_signals, bundle.labels, protocol,
        model_configuration_fingerprint=model_fp,
        dataset_fingerprints=fingerprints,
        provenance={
            "implementation": "Qlib v0.9.7 LinearModel",
            "evidence_scope": "offline synthetic-only reproduction",
        },
        output_dir=directory / "evaluation_qlib",
    )
    v2_model_fp = model_configuration_fingerprint({
        "model_id": RESEARCH_V2_MODEL_ID,
        "method_version": "research_v2_point_in_time_weighted",
        "implementation": "stock_ranker.research_v2",
    })
    v2_eval = evaluate_signals(
        v2_signals, bundle.labels, protocol,
        model_configuration_fingerprint=v2_model_fp,
        dataset_fingerprints=fingerprints,
        provenance={
            "implementation": "Research V2 non-ML baseline",
            "evidence_scope": "offline synthetic-only comparison",
        },
        output_dir=directory / "evaluation_research_v2",
    )
    comparison_path = directory / "model_comparison.csv"
    comparison = compare_evaluations(
        [qlib_eval.summary, v2_eval.summary], output_path=comparison_path
    )
    write_canonical_json({
        "schema_version": "1.0",
        "evaluation_protocol_fingerprint": protocol.fingerprint,
        "model_count": len(comparison),
        "coverage_differences_reported": True,
        "models": comparison.to_dict("records"),
    }, directory / "model_comparison.json")
    write_canonical_json({
        "schema_version": "1.0",
        "proposed_changes": [
            {
                "registry_id": "qlib_framework",
                "proposed_status": "environment_verified",
            },
            {
                "registry_id": "qlib_linear",
                "proposed_status": "synthetic_reproduced",
            },
        ],
        "evidence_scope": (
            "Offline synthetic-only reproduction; not real-market validation, "
            "investment evidence, or upstream benchmark reproduction."
        ),
        "runtime_mutated_registry": False,
    }, directory / "proposed_registry_status_update.json")
    write_canonical_json(execution, directory / "execution_report.json")
    write_canonical_json({
        "schema_version": "1.0",
        "self_referential_exclusions": [
            "artifact_inventory.json",
            "execution_report.json",
            "experiment_manifest.json",
        ],
        "artifacts": _inventory(directory),
    }, directory / "artifact_inventory.json")
    write_canonical_json({
        "schema_version": "1.0",
        "run_id": run_id,
        "model_id": MODEL_ID,
        "status": "completed",
        "created_at": started,
        "source_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True,
            text=True, check=True,
        ).stdout.strip(),
        "worktree_status": subprocess.run(
            ["git", "status", "--short"], capture_output=True,
            text=True, check=True,
        ).stdout.strip(),
        "model_configuration": _model_configuration(),
        "source_manifest": "research/manifests/qlib_linear_synthetic_planned.json",
        "evaluation_protocol_fingerprint": protocol.fingerprint,
        "evaluation_protocol": protocol.as_dict(),
        "model_configuration_fingerprint": model_fp,
        "datasets": {
            name: {"fingerprint": value, "provenance": "offline fictional generator"}
            for name, value in fingerprints.items()
        },
        "splits": bundle.split.as_dict(),
        "seeds": {"generator": config.seed},
        "parameters": MODEL_PARAMETERS,
        "paths": {name: str(path) for name, path in paths.items()},
        "evaluation_artifacts": [
            {
                "path": str(path),
                "sha256": fingerprint_file(path),
            }
            for path in (
                directory / "evaluation_qlib/evaluation_summary.json",
                directory / "evaluation_research_v2/evaluation_summary.json",
                directory / "model_comparison.csv",
            )
        ],
        "notes": "Offline synthetic-only reproduction.",
        "evidence_scope": "offline synthetic-only reproduction",
    }, directory / "experiment_manifest.json")
    return ReproductionRunResult(
        run_id=run_id,
        directory=directory,
        execution_report=execution,
        qlib_evaluation=qlib_eval.summary,
        research_v2_evaluation=v2_eval.summary,
    )


def compare_reproduction_runs(
    first: Path, second: Path, *, tolerance: float = 1e-12
) -> dict[str, Any]:
    """Compare the two independent Qlib runs without relaxing tolerance."""

    first_predictions = pd.read_csv(first / "qlib_indexed_predictions.csv")
    second_predictions = pd.read_csv(second / "qlib_indexed_predictions.csv")
    key_columns = ["datetime", "instrument"]
    if not first_predictions[key_columns].equals(second_predictions[key_columns]):
        raise RuntimeError("prediction key/order differs between Qlib runs")
    prediction_difference = float(np.max(np.abs(
        first_predictions["score"].to_numpy(dtype=float)
        - second_predictions["score"].to_numpy(dtype=float)
    )))
    first_coefficients = pd.read_csv(first / "qlib_coefficients.csv")
    second_coefficients = pd.read_csv(second / "qlib_coefficients.csv")
    if not first_coefficients["feature"].equals(second_coefficients["feature"]):
        raise RuntimeError("coefficient feature order differs between Qlib runs")
    coefficient_difference = float(np.max(np.abs(
        first_coefficients["coefficient"].to_numpy(dtype=float)
        - second_coefficients["coefficient"].to_numpy(dtype=float)
    )))
    first_metadata = json.loads(
        (first / "qlib_model_metadata.json").read_text(encoding="utf-8")
    )
    second_metadata = json.loads(
        (second / "qlib_model_metadata.json").read_text(encoding="utf-8")
    )
    checks = {
        "dataset_fingerprints_identical":
            first_metadata["dataset_fingerprints"]
            == second_metadata["dataset_fingerprints"],
        "model_configuration_fingerprint_identical":
            first_metadata["model_configuration_fingerprint"]
            == second_metadata["model_configuration_fingerprint"],
        "coefficient_shape_identical":
            len(first_coefficients) == len(second_coefficients),
        "prediction_order_identical": True,
        "thread_controls_identical":
            first_metadata["thread_controls"] == second_metadata["thread_controls"],
        "status_counts_identical": (
            pd.read_csv(first / "evaluation_qlib/daily_ic.csv")["status"]
            .value_counts().to_dict()
            == pd.read_csv(second / "evaluation_qlib/daily_ic.csv")["status"]
            .value_counts().to_dict()
        ),
    }
    passed = (
        all(checks.values())
        and prediction_difference <= tolerance
        and coefficient_difference <= tolerance
    )
    report = {
        "schema_version": "1.0",
        "tolerance": tolerance,
        "maximum_prediction_difference": prediction_difference,
        "maximum_coefficient_difference": coefficient_difference,
        "checks": checks,
        "passed": passed,
        "tolerance_relaxed": False,
    }
    if not passed:
        raise RuntimeError(f"Qlib reproducibility acceptance failed: {report}")
    return report


def run_qlib_linear_reproduction(
    config: QlibLinearReproductionConfig | None = None,
) -> ReproductionBatchResult:
    """Execute two isolated runs and verify deterministic reproduction."""

    selected = config or QlibLinearReproductionConfig()
    plan = plan_qlib_linear_reproduction(selected)
    if plan.output_directory.exists():
        raise ValueError(f"refusing preexisting batch directory: {plan.output_directory}")
    environment = _load_environment(selected)
    bundle = generate_synthetic_qlib_data(selected.seed)
    fingerprints = _dataset_fingerprints(bundle)
    protocol = _protocol(bundle)
    model_fp = model_configuration_fingerprint(_model_configuration())
    plan.output_directory.mkdir(parents=True)
    completed_runs: list[ReproductionRunResult] = []
    for number in range(1, selected.reruns + 1):
        try:
            completed_runs.append(_execute_run(
                number=number, batch_directory=plan.output_directory,
                config=selected, bundle=bundle, environment=environment,
                fingerprints=fingerprints, protocol=protocol, model_fp=model_fp,
            ))
        except Exception as exc:
            failed_directory = plan.output_directory / f"run-{number:02d}"
            if selected.keep_failed_artifacts and failed_directory.exists():
                request_path = failed_directory / "runner_request.json"
                failed_run_id = None
                if request_path.is_file():
                    try:
                        failed_run_id = json.loads(
                            request_path.read_text(encoding="utf-8")
                        ).get("run_id")
                    except (OSError, json.JSONDecodeError):
                        pass
                failure = f"{type(exc).__name__}: {exc}"
                write_canonical_json({
                    "schema_version": "1.0",
                    "run_id": failed_run_id,
                    "status": "failed",
                    "failure_reason": failure,
                    "failed_artifacts_retained": True,
                }, failed_directory / "experiment_manifest.json")
                report_path = failed_directory / "execution_report.json"
                existing_report: dict[str, Any] = {}
                if report_path.is_file():
                    try:
                        existing_report = json.loads(
                            report_path.read_text(encoding="utf-8")
                        )
                    except (OSError, json.JSONDecodeError):
                        existing_report = {}
                write_canonical_json({
                    **existing_report,
                    "schema_version": "1.0",
                    "run_id": failed_run_id,
                    "status": "failed",
                    "failure_reason": failure,
                }, report_path)
            raise
    runs = tuple(completed_runs)
    reproducibility = compare_reproduction_runs(
        runs[0].directory, runs[1].directory,
        tolerance=selected.reproducibility_tolerance,
    )
    reproducibility["evaluation_protocol_fingerprint"] = protocol.fingerprint
    reproducibility["batch_id"] = plan.batch_id
    write_canonical_json(
        reproducibility, plan.output_directory / "reproducibility_report.json"
    )
    write_canonical_json({
        "schema_version": "1.0",
        "batch_id": plan.batch_id,
        "status": "completed",
        "run_ids": [run.run_id for run in runs],
        "registry_source_mutated_at_runtime": False,
        "evidence_scope": (
            "Offline synthetic-only reproduction; not real-market validation, "
            "investment evidence, or upstream benchmark reproduction."
        ),
    }, plan.output_directory / "batch_report.json")
    return ReproductionBatchResult(
        batch_id=plan.batch_id,
        directory=plan.output_directory,
        runs=runs,
        reproducibility=reproducibility,
    )
