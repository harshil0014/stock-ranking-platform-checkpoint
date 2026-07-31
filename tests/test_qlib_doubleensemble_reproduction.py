from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.cli import main
from stock_research.qlib_doubleensemble_reproduction import (
    MODEL_PARAMETERS,
    SUBPROCESS_CONTROLS,
    QlibDoubleEnsembleReproductionConfig,
    build_doubleensemble_subprocess_environment,
    compare_doubleensemble_runs,
    finalize_doubleensemble_failed_batch,
    plan_qlib_doubleensemble_reproduction,
)


def test_frozen_configuration_is_exact() -> None:
    assert MODEL_PARAMETERS == {
        "base_model": "gbm", "loss": "mse", "num_models": 3,
        "enable_sr": True, "enable_fs": True, "alpha1": 1.0,
        "alpha2": 1.0, "bins_sr": 10, "bins_fs": 5, "decay": 0.5,
        "sample_ratios": [0.8, 0.7, 0.6, 0.5, 0.4],
        "sub_weights": [1.0, 1.0, 1.0], "epochs": 28,
        "early_stopping_rounds": None, "colsample_bytree": 0.8879,
        "learning_rate": 0.2, "subsample": 0.8789,
        "lambda_l1": 205.6999, "lambda_l2": 580.9768,
        "max_depth": 8, "num_leaves": 210, "num_threads": 1,
        "verbosity": -1, "seed": 20260730,
        "feature_fraction_seed": 20260730,
        "bagging_seed": 20260730, "data_random_seed": 20260730,
        "deterministic": True, "force_col_wise": True,
    }


@pytest.mark.parametrize("field,value", [
    ("seed", 1), ("reruns", 1), ("reproducibility_tolerance", 1e-8),
])
def test_config_rejects_relaxation(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        QlibDoubleEnsembleReproductionConfig(**{field: value})


def test_subprocess_controls_are_isolated() -> None:
    parent = {"PATH": "example"}
    child, audit = build_doubleensemble_subprocess_environment(parent)
    assert parent == {"PATH": "example"}
    assert {key: child[key] for key in SUBPROCESS_CONTROLS} == SUBPROCESS_CONTROLS
    assert audit == {key: False for key in SUBPROCESS_CONTROLS}
    assert "MLFLOW_ALLOW_FILE_STORE" not in child


@pytest.mark.parametrize("name", [
    "MLFLOW_ALLOW_FILE_STORE", "MLFLOW_TRACKING_URI",
    "DATABRICKS_HOST", "AWS_ACCESS_KEY_ID",
])
def test_subprocess_rejects_remote_or_workflow_environment(name: str) -> None:
    with pytest.raises(ValueError, match="prohibited"):
        build_doubleensemble_subprocess_environment({name: "present"})


def test_plan_validates_frozen_inputs_and_two_commands(tmp_path: Path) -> None:
    plan = plan_qlib_doubleensemble_reproduction(
        QlibDoubleEnsembleReproductionConfig(
            output_root=tmp_path, batch_id="dry-run",
        )
    )
    assert len(plan.commands) == 2
    assert [Path(command[2]).parent.name for command in plan.commands] == [
        "run-01", "run-02",
    ]
    assert plan.model_parameters == MODEL_PARAMETERS
    assert plan.doubleensemble_source_sha256 == (
        "780d60f334bcac2e2d0b07f97022f4b9fa40b6a570befe6fa690094a52eaf462"
    )
    assert plan.evaluation_protocol_fingerprint.startswith("210bca5c")
    assert not plan.output_directory.exists()


def test_plan_rejects_stale_batch(tmp_path: Path) -> None:
    (tmp_path / "stale").mkdir()
    with pytest.raises(ValueError, match="preexisting"):
        plan_qlib_doubleensemble_reproduction(
            QlibDoubleEnsembleReproductionConfig(
                output_root=tmp_path, batch_id="stale",
            )
        )


def _write_run(directory: Path, delta: float = 0.0) -> None:
    directory.mkdir()
    pd.DataFrame({
        "datetime": ["2026-01-01"], "instrument": ["SYN001"],
        "score": [1.0 + delta],
    }).to_csv(directory / "doubleensemble_predictions_raw.csv", index=False)
    for name, column in (
        ("combined_feature_importance_gain.csv", "importance_gain"),
        ("combined_feature_importance_split.csv", "importance_split"),
    ):
        pd.DataFrame({"feature": ["a"], column: [1.0 + delta]}).to_csv(
            directory / name, index=False
        )
    for name, column in (
        ("per_submodel_feature_importance_gain.csv", "importance_gain"),
        ("per_submodel_feature_importance_split.csv", "importance_split"),
    ):
        pd.DataFrame({
            "submodel": [1], "feature": ["a"], column: [1.0 + delta],
        }).to_csv(directory / name, index=False)
    (directory / "submodel_selected_features.json").write_text(
        json.dumps([{"submodel": 1, "features": ["a"]}]), encoding="utf-8"
    )
    (directory / "submodel_summary.json").write_text(
        json.dumps([{"submodel": 1, "tree_count": 28}]), encoding="utf-8"
    )
    metadata = {
        "normalized_model_dump_sha256": ["x"],
        "dataset_fingerprints": {"x": "y"},
        "model_configuration_fingerprint": "model",
        "evaluation_protocol_fingerprint": "protocol",
        "subprocess_environment_controls": SUBPROCESS_CONTROLS,
    }
    (directory / "doubleensemble_runner_metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )


def test_reproducibility_compares_all_required_outputs(tmp_path: Path) -> None:
    one, two = tmp_path / "one", tmp_path / "two"
    _write_run(one)
    _write_run(two)
    result = compare_doubleensemble_runs(one, two)
    assert result["passed"] is True
    assert result["maximum_prediction_difference"] == 0
    assert result["maximum_per_submodel_gain_difference"] == 0


def test_reproducibility_never_relaxes_tolerance(tmp_path: Path) -> None:
    one, two = tmp_path / "one", tmp_path / "two"
    _write_run(one)
    _write_run(two, delta=1e-10)
    with pytest.raises(RuntimeError, match="acceptance failed"):
        compare_doubleensemble_runs(one, two)


def test_cli_dry_run_is_write_free(tmp_path: Path, capsys) -> None:
    code = main([
        "reproduce-qlib-doubleensemble", "--dry-run",
        "--output-root", str(tmp_path), "--batch-id", "planned",
    ])
    assert code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["dry_run"] is True
    assert output["training_performed"] is False
    assert len(output["commands"]) == 2
    assert not (tmp_path / "planned").exists()


def test_static_algorithm_and_import_boundaries() -> None:
    product = Path(
        "src/stock_research/qlib_doubleensemble_reproduction.py"
    ).read_text(encoding="utf-8")
    runner = Path(
        "research/runners/qlib_doubleensemble_runner.py"
    ).read_text(encoding="utf-8")
    for forbidden in ("import qlib", "import lightgbm", "import torch"):
        assert forbidden not in product
    assert "stock_research" not in runner
    assert "lightgbm.train" not in runner
    assert "R.start" not in runner
    assert "MLflowExpManager" not in runner
    assert "class DEnsemble" not in runner
    assert "DEnsembleModel(**request[\"model_parameters\"])" in runner
    assert "model.fit(dataset)" in runner
    assert 'model.predict(dataset, segment="test")' in runner


def test_failure_finalizer_rejects_missing_evidence(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires only run-01"):
        finalize_doubleensemble_failed_batch(tmp_path)
