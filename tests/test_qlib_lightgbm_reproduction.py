from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from stock_research.qlib_lightgbm_compatibility import (
    QlibLightGBMCompatibilityConfig,
)
from stock_research.qlib_lightgbm_reproduction import (
    LIGHTGBM_SUBPROCESS_CONTROLS,
    QlibLightGBMReproductionConfig,
    build_lightgbm_subprocess_environment,
    compare_lightgbm_reproduction_runs,
    finalize_failed_lightgbm_batch,
    plan_qlib_lightgbm_reproduction,
    validate_local_recorder_paths,
)
from stock_research.contracts import validate_labels
from stock_research.fingerprints import fingerprint_dataframe

from test_qlib_lightgbm_compatibility import _fixture


ROOT = Path(__file__).parents[1]


def _config(tmp_path: Path) -> QlibLightGBMReproductionConfig:
    source: QlibLightGBMCompatibilityConfig = _fixture(tmp_path)
    return QlibLightGBMReproductionConfig(
        output_root=source.output_root,
        frozen_linear_batch=source.frozen_linear_batch,
        qlib_interpreter=source.qlib_interpreter,
        environment_report=source.environment_report,
        frozen_specification=source.frozen_specification,
        batch_id="fixture-local-recorder",
    )


def test_local_recorder_plan_is_write_free_and_has_two_commands(tmp_path):
    config = _config(tmp_path)
    plan = plan_qlib_lightgbm_reproduction(config)
    assert not plan.output_directory.exists()
    assert len(plan.commands) == 2
    assert len(plan.tracking_uris) == 2
    assert all(uri.startswith("file:///") for uri in plan.tracking_uris)
    assert (
        plan.subprocess_environment_controls
        == LIGHTGBM_SUBPROCESS_CONTROLS
    )
    assert plan.parent_mlflow_allow_file_store is None
    assert plan.commands[0][0] == str(config.qlib_interpreter)
    assert plan.commands[0][1].endswith(
        "qlib_lightgbm_local_runner.py"
    )
    assert Path(plan.commands[0][2]).parts[-2:] == (
        "run-01", "runner_request.json"
    )
    assert Path(plan.commands[1][2]).parts[-2:] == (
        "run-02", "runner_request.json"
    )


def test_reproduction_configuration_is_frozen():
    with pytest.raises(ValueError, match="seed is frozen"):
        QlibLightGBMReproductionConfig(seed=7)
    with pytest.raises(ValueError, match="exactly 2"):
        QlibLightGBMReproductionConfig(reruns=1)
    with pytest.raises(ValueError, match="frozen at 1e-12"):
        QlibLightGBMReproductionConfig(
            reproducibility_tolerance=1e-9
        )


def test_local_recorder_path_rejects_unignored_directory(tmp_path):
    target = ROOT / "not-ignored-recorder-path"
    with pytest.raises(ValueError, match="not ignored"):
        validate_local_recorder_paths(target)


def test_child_opt_in_is_explicit_without_mutating_parent():
    parent = {"PATH": "fixture"}
    child, audit = build_lightgbm_subprocess_environment(parent)
    assert parent == {"PATH": "fixture"}
    assert child["PATH"] == "fixture"
    assert {
        name: child[name] for name in LIGHTGBM_SUBPROCESS_CONTROLS
    } == LIGHTGBM_SUBPROCESS_CONTROLS
    assert audit["parent_mlflow_allow_file_store"] is None
    assert "MLFLOW_ALLOW_FILE_STORE" not in parent


def test_parent_opt_in_and_remote_mlflow_environment_are_rejected():
    with pytest.raises(ValueError, match="must be absent"):
        build_lightgbm_subprocess_environment({
            "MLFLOW_ALLOW_FILE_STORE": "true"
        })
    with pytest.raises(ValueError, match="remote MLflow"):
        build_lightgbm_subprocess_environment({
            "MLFLOW_TRACKING_URI": "https://example.invalid"
        })


def test_frozen_labels_require_round_trip_csv_parsing():
    path = (
        ROOT
        / "research/generated/qlib-linear/final-locked-20260731/"
        "run-01/synthetic_labels.csv"
    )
    labels = pd.read_csv(
        path,
        dtype={"as_of_date": str, "label_end_date": str},
        float_precision="round_trip",
    )
    assert fingerprint_dataframe(validate_labels(labels)) == (
        "7412fc79f8af0acf87b1cb22209842d153e8a6b6e9370e147b43e454ca247f2d"
    )


def _write_reproduction_run(
    directory: Path,
    *,
    prediction_delta: float = 0.0,
    gain_delta: float = 0.0,
) -> None:
    directory.mkdir(parents=True)
    pd.DataFrame({
        "datetime": ["2026-05-05", "2026-05-05"],
        "instrument": ["SYN001", "SYN002"],
        "score": [1.0 + prediction_delta, 2.0],
    }).to_csv(
        directory / "qlib_lightgbm_predictions.csv", index=False
    )
    pd.DataFrame({
        "feature": ["one", "two"],
        "importance_gain": [3.0 + gain_delta, 4.0],
    }).to_csv(
        directory / "lightgbm_feature_importance_gain.csv",
        index=False,
    )
    pd.DataFrame({
        "feature": ["one", "two"],
        "importance_split": [5, 6],
    }).to_csv(
        directory / "lightgbm_feature_importance_split.csv",
        index=False,
    )
    (directory / "evaluation_lightgbm").mkdir()
    pd.DataFrame({"status": ["valid", "valid"]}).to_csv(
        directory / "evaluation_lightgbm/daily_ic.csv", index=False
    )
    (directory / "qlib_lightgbm_metadata.json").write_text(
        json.dumps({
            "dataset_fingerprints": {"labels": "frozen"},
            "model_configuration_fingerprint": "model",
            "evaluation_protocol_fingerprint": "protocol",
            "best_iteration": 53,
            "tree_count": 53,
            "thread_controls": {
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
            },
            "subprocess_environment_controls":
                LIGHTGBM_SUBPROCESS_CONTROLS,
        }),
        encoding="utf-8",
    )


def test_reproducibility_compares_predictions_and_both_importances(
    tmp_path,
):
    first, second = tmp_path / "one", tmp_path / "two"
    _write_reproduction_run(first)
    _write_reproduction_run(second)
    report = compare_lightgbm_reproduction_runs(first, second)
    assert report["passed"] is True
    assert report["maximum_prediction_difference"] == 0
    assert report["maximum_gain_importance_difference"] == 0
    assert report["maximum_split_importance_difference"] == 0

    changed = tmp_path / "changed"
    _write_reproduction_run(changed, prediction_delta=1e-8)
    with pytest.raises(RuntimeError, match="reproducibility acceptance"):
        compare_lightgbm_reproduction_runs(first, changed)


def test_failed_local_recorder_batch_is_terminal_and_not_promoted(
    tmp_path,
):
    batch = tmp_path / "batch"
    run = batch / "run-01"
    run.mkdir(parents=True)
    (run / "runner_request.json").write_text(json.dumps({
        "run_id": "run-id",
        "model_configuration_fingerprint": "model",
        "evaluation_protocol_fingerprint": "protocol",
    }), encoding="utf-8")
    (run / "execution_report.json").write_text(json.dumps({
        "exit_code": 1,
        "stderr": (
            "qlib successfully initialized\n"
            "The filesystem tracking backend is in maintenance mode; "
            "set MLFLOW_ALLOW_FILE_STORE=true"
        ),
    }), encoding="utf-8")
    diagnostics = finalize_failed_lightgbm_batch(batch)
    assert diagnostics["qlib_initialization_succeeded"] is True
    assert diagnostics["lgbmodel_fit_started"] is False
    report = json.loads((batch / "batch_report.json").read_text())
    assert report["attempted_run_count"] == 1
    assert report["second_run_attempted"] is False
    proposed = json.loads(
        (batch / "proposed_registry_status_update.json").read_text()
    )
    assert proposed["proposed_changes"] == []


def test_local_runner_uses_only_official_qllib_workflow():
    runner = (
        ROOT / "research/runners/qlib_lightgbm_local_runner.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(runner)
    calls = {
        ast.unparse(node.func) for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert "qlib.init" in calls
    assert "R.start" in calls
    assert "model.fit" in calls
    assert "model.predict" in calls
    assert "lightgbm.train" not in calls
    assert "mlflow.start_server" not in calls
    for forbidden in (
        "LGBMRegressor", "requests.", "urllib.request",
        "DatasetD", "D.features", "D.calendar",
    ):
        assert forbidden not in runner
    product = (
        ROOT
        / "src/stock_research/qlib_lightgbm_reproduction.py"
    ).read_text(encoding="utf-8")
    product_tree = ast.parse(product)
    imports = {
        alias.name
        for node in ast.walk(product_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "qlib" not in imports
    assert "lightgbm" not in imports


def test_local_runner_help_does_not_initialize_qlib():
    completed = subprocess.run(
        [
            sys.executable,
            str(
                ROOT
                / "research/runners/qlib_lightgbm_local_runner.py"
            ),
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "local file-backed" in completed.stdout


def test_local_integration_verifier_help_is_qlib_free():
    completed = subprocess.run(
        [
            sys.executable,
            str(
                ROOT
                / "research/runners/"
                "verify_qlib_lightgbm_local_integration.py"
            ),
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "batch_directory" in completed.stdout
    assert "Traceback" not in completed.stderr


def test_planned_local_recorder_manifest_is_valid():
    from stock_research.manifests import load_manifest

    manifest = load_manifest(
        ROOT
        / "research/manifests/"
        "qlib_lightgbm_local_reproduction_planned.json"
    )
    assert manifest["status"] == "planned"
    assert manifest["parameters"]["reruns"] == 2
