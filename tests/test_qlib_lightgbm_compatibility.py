from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

import stock_research.qlib_lightgbm_compatibility as compatibility
from stock_research.fingerprints import fingerprint_file
from stock_research.manifests import load_manifest
from stock_research.cli import main
from stock_research.qlib_lightgbm_compatibility import (
    FIT_CONFIGURATION,
    MODEL_CONSTRUCTION,
    QlibLightGBMCompatibilityConfig,
    build_qlib_lightgbm_plan,
    run_qlib_lightgbm_compatibility_proof,
    validate_frozen_lightgbm_inputs,
)


ROOT = Path(__file__).parents[1]


def _json(value, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _fixture(tmp_path: Path) -> QlibLightGBMCompatibilityConfig:
    environment_root = tmp_path / "environment"
    interpreter = environment_root / "Scripts/python.exe"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_bytes(b"fixture interpreter")
    gbdt = (
        environment_root
        / "Lib/site-packages/qlib/contrib/model/gbdt.py"
    )
    gbdt.parent.mkdir(parents=True)
    gbdt.write_text("class LGBModel: pass\n", encoding="utf-8")
    lock = tmp_path / "freeze.txt"
    lock.write_text("lightgbm==4.6.0\npyqlib==0.9.7\n", encoding="utf-8")
    report = tmp_path / "environment.json"
    _json({
        "status": "verified",
        "environment_fingerprint": "e" * 64,
        "interpreter": str(interpreter),
        "resolved_lock": str(lock),
        "import_results": {
            "qlib": {"ok": True, "version": "0.9.7"},
            "lightgbm": {"ok": True, "version": "4.6.0"},
            "qlib.contrib.model.gbdt": {"ok": True, "version": None},
        },
    }, report)

    batch = tmp_path / "linear-batch"
    canonical_names = (
        "data_generation_metadata.json",
        "dataset_fingerprints.json",
        "evaluation_protocol.json",
        "qlib_instrument_mapping.csv",
        "split.json",
        "synthetic_features.csv",
        "synthetic_labels.csv",
        "synthetic_qlib_panel.csv",
        "synthetic_v2_fundamentals.csv",
        "synthetic_v2_prices.csv",
        "synthetic_v2_universe.csv",
    )
    dataset_fingerprints = {
        "features": "features", "labels": "labels", "prices": "prices",
        "fundamentals": "fundamentals", "universe": "universe",
        "mapping": "mapping", "generation_metadata": "metadata",
    }
    for number in (1, 2):
        run = batch / f"run-{number:02d}"
        run.mkdir(parents=True)
        for name in canonical_names:
            (run / name).write_text(f"frozen:{name}\n", encoding="utf-8")
        _json(dataset_fingerprints, run / "dataset_fingerprints.json")
        _json({
            "label_dataset_fingerprint": "label-fingerprint"
        }, run / "evaluation_protocol.json")
        _json({
            "status": "completed",
            "evaluation_protocol_fingerprint": "protocol-fingerprint",
        }, run / "experiment_manifest.json")
        _json({
            "evaluation_protocol_fingerprint": "protocol-fingerprint",
            "dataset_fingerprints": dataset_fingerprints,
        }, run / "qlib_model_metadata.json")
        pd.DataFrame({
            "model_id": ["qlib_linear_ols_v0_9_7"] * 1200
        }).to_csv(run / "qlib_signals.csv", index=False)
        pd.DataFrame({
            "model_id": ["research_v2_baseline"] * 1160
        }).to_csv(run / "research_v2_signals.csv", index=False)
        pd.DataFrame({
            "eligible": [False] * 40,
            "ticker": ["SYN030"] * 40,
        }).to_csv(run / "research_v2_eligibility_report.csv", index=False)

    selected = batch / "run-01"
    canonical_hashes = {
        name: fingerprint_file(selected / name) for name in canonical_names
    }
    baseline_names = (
        "qlib_signals.csv",
        "research_v2_signals.csv",
        "research_v2_eligibility_report.csv",
    )
    specification = tmp_path / "frozen.json"
    _json({
        "accepted_source_batch": batch.as_posix(),
        "selected_source_run": "run-01",
        "source_selection_rule":
            "lexicographically first valid completed run",
        "seed": 20260730,
        "feature_list": [f"feature_{number}" for number in range(10)],
        "label_name": "forward_1d_return",
        "splits": {
            "train": {"start": "2025-09-23", "end": "2026-03-09"},
            "validation": {"start": "2026-03-17", "end": "2026-04-27"},
            "test": {"start": "2026-05-05", "end": "2026-06-29"},
        },
        "canonical_file_hashes": canonical_hashes,
        "accepted_baseline_hashes": {
            name: fingerprint_file(selected / name)
            for name in baseline_names
        },
        "accepted_baseline_counts": {
            "qlib_linear_signals": 1200,
            "research_v2_signals": 1160,
            "research_v2_ineligible": 40,
        },
        "dataset_fingerprints": dataset_fingerprints,
        "label_dataset_fingerprint": "label-fingerprint",
        "evaluation_protocol_fingerprint": "protocol-fingerprint",
        "environment_fingerprint": "e" * 64,
        "environment_report_sha256": fingerprint_file(report),
        "resolved_lock_sha256": fingerprint_file(lock),
        "qlib_gbdt_source_sha256": fingerprint_file(gbdt),
        "evidence_scope": "fictional compatibility fixture",
    }, specification)
    return QlibLightGBMCompatibilityConfig(
        output_root=tmp_path / "output",
        frozen_linear_batch=batch,
        qlib_interpreter=interpreter,
        environment_report=report,
        frozen_specification=specification,
        batch_id="fixture-batch",
    )


def test_frozen_inputs_select_first_run_and_validate_hashes(tmp_path):
    config = _fixture(tmp_path)
    specification, selected, environment = validate_frozen_lightgbm_inputs(
        config
    )
    assert selected.name == "run-01"
    assert specification["seed"] == 20260730
    assert environment["lock_sha256"] == specification[
        "resolved_lock_sha256"
    ]


def test_frozen_hash_mismatch_is_rejected(tmp_path):
    config = _fixture(tmp_path)
    source = config.frozen_linear_batch / "run-02/synthetic_features.csv"
    source.write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="accepted input hash mismatch"):
        validate_frozen_lightgbm_inputs(config)


def test_plan_is_write_free_fixed_and_does_not_import_model_packages(tmp_path):
    config = _fixture(tmp_path)
    before = set(sys.modules)
    plan = build_qlib_lightgbm_plan(config)
    added = set(sys.modules).difference(before)
    assert "qlib" not in added
    assert "lightgbm" not in added
    assert not plan.output_directory.exists()
    assert plan.expected_status == "blocked"
    assert plan.selected_source_run.name == "run-01"
    assert plan.command[0] == str(config.qlib_interpreter)
    assert MODEL_CONSTRUCTION["num_boost_round"] == 200
    assert MODEL_CONSTRUCTION["early_stopping_rounds"] == 20
    assert MODEL_CONSTRUCTION["deterministic"] is True
    assert FIT_CONFIGURATION["test_labels_used"] is False


def test_configuration_rejects_retry_or_changed_seed():
    with pytest.raises(ValueError, match="exactly one attempt"):
        QlibLightGBMCompatibilityConfig(attempts=2)
    with pytest.raises(ValueError, match="frozen"):
        QlibLightGBMCompatibilityConfig(seed=7)


def test_cli_dry_run_is_write_free(tmp_path, capsys):
    config = _fixture(tmp_path)
    assert main([
        "reproduce-qlib-lightgbm",
        "--output-root", str(config.output_root),
        "--frozen-linear-batch", str(config.frozen_linear_batch),
        "--qlib-interpreter", str(config.qlib_interpreter),
        "--environment-report", str(config.environment_report),
        "--frozen-specification", str(config.frozen_specification),
        "--batch-id", "fixture-batch",
        "--dry-run",
    ]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["dry_run"] is True
    assert response["training_performed"] is False
    assert response["artifacts_written"] is False
    assert len(response["commands"]) == 2
    assert len(response["tracking_uris"]) == 2
    assert all(uri.startswith("file:") for uri in response["tracking_uris"])
    assert response["subprocess_environment_controls"] == {
        "MKL_NUM_THREADS": "1",
        "MLFLOW_ALLOW_FILE_STORE": "true",
        "NUMEXPR_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
    }
    assert response["parent_mlflow_allow_file_store"] is None
    assert not config.output_root.exists()


def test_runner_help_does_not_require_qlib_import():
    completed = subprocess.run(
        [
            sys.executable,
            str(
                ROOT
                / "research/runners/qlib_lightgbm_compatibility_runner.py"
            ),
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "request" in completed.stdout


def test_compatibility_verifier_help_and_missing_path_are_concise(tmp_path):
    verifier = (
        ROOT
        / "research/runners/verify_qlib_lightgbm_compatibility.py"
    )
    help_result = subprocess.run(
        [sys.executable, str(verifier), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "batch_directory" in help_result.stdout

    missing_result = subprocess.run(
        [sys.executable, str(verifier), str(tmp_path / "missing")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing_result.returncode != 0
    assert "batch directory does not exist" in missing_result.stderr
    assert "Traceback" not in missing_result.stderr


def test_compatibility_verifier_reports_missing_evidence(tmp_path):
    verifier = (
        ROOT
        / "research/runners/verify_qlib_lightgbm_compatibility.py"
    )
    batch = tmp_path / "batch"
    (batch / "attempt-01").mkdir(parents=True)
    completed = subprocess.run(
        [sys.executable, str(verifier), str(batch)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    assert "missing required artifact" in completed.stderr
    assert "Traceback" not in completed.stderr


def test_expected_blocker_writes_failed_evidence(tmp_path, monkeypatch):
    config = _fixture(tmp_path)

    def blocked(command, **kwargs):
        request = json.loads(Path(command[2]).read_text(encoding="utf-8"))
        outputs = {
            name: Path(path) for name, path in request["outputs"].items()
        }
        _json({
            "status": "blocked",
            "model_class": "qlib.contrib.model.gbdt.LGBModel",
            "model_configuration_fingerprint":
                request["model_configuration_fingerprint"],
            "evaluation_protocol_fingerprint":
                request["evaluation_protocol_fingerprint"],
            "best_iteration": 17,
            "tree_count": 17,
            "predictions_written": False,
        }, outputs["runner_metadata"])
        _json({
            "train": {"l2": [1.0, 0.8]},
            "valid": {"l2": [1.1, 0.9]},
        }, outputs["training_history"])
        features = request["feature_columns"]
        pd.DataFrame({
            "feature": features,
            "importance_gain": range(len(features)),
        }).to_csv(outputs["feature_importance_gain"], index=False)
        pd.DataFrame({
            "feature": features,
            "importance_split": range(len(features)),
        }).to_csv(outputs["feature_importance_split"], index=False)
        _json({"tree_info": [{"tree_index": 0}]}, outputs["model_dump"])
        _json({
            "blocker_matched": True,
            "predictions_attempted": False,
            "failure_message": "Please run qlib.init() first using qlib",
        }, outputs["failure_diagnostics"])
        return subprocess.CompletedProcess(
            command, 1, stdout="official fit attempted\n",
            stderr="CompatibilityBlocked\n",
        )

    monkeypatch.setattr(compatibility.subprocess, "run", blocked)
    result = run_qlib_lightgbm_compatibility_proof(config)
    assert result.status == "blocked"
    assert result.exit_code == 1
    assert (result.attempt_directory / "failed_manifest.json").is_file()
    assert (result.attempt_directory / "artifact_inventory.json").is_file()
    assert not (result.attempt_directory / "qlib_lightgbm_signals.csv").exists()
    proposed = json.loads(
        (result.directory / "proposed_registry_status_update.json").read_text()
    )
    assert proposed["proposed_changes"] == []
    assert proposed["qlib_lightgbm_status"] == "adoption_specified"


def test_malformed_runner_metadata_is_not_accepted(tmp_path, monkeypatch):
    config = _fixture(tmp_path)

    def malformed(command, **kwargs):
        request = json.loads(Path(command[2]).read_text(encoding="utf-8"))
        for name, path in request["outputs"].items():
            target = Path(path)
            if target.suffix == ".csv":
                pd.DataFrame({"wrong": [1]}).to_csv(target, index=False)
            else:
                _json(
                    {
                        "blocker_matched": True,
                        "predictions_attempted": False,
                    },
                    target,
                )
        return subprocess.CompletedProcess(command, 1, "", "blocked")

    monkeypatch.setattr(compatibility.subprocess, "run", malformed)
    with pytest.raises(RuntimeError, match="did not produce the expected"):
        run_qlib_lightgbm_compatibility_proof(config)
    failed = json.loads(
        (
            config.output_root
            / "fixture-batch/attempt-01/failed_manifest.json"
        ).read_text()
    )
    assert failed["status"] == "failed"


def test_runner_source_has_no_forbidden_execution_paths():
    runner = (
        ROOT / "research/runners/qlib_lightgbm_compatibility_runner.py"
    ).read_text(encoding="utf-8")
    product = (
        ROOT / "src/stock_research/qlib_lightgbm_compatibility.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "lightgbm.train", "LGBMRegressor", "GridSearch", "RandomizedSearch",
        "R.register(", "mlflow.", "requests.", "urllib.",
        "stock_research", "stock_ranker",
    ):
        assert forbidden not in runner
    tree = ast.parse(runner)
    calls = {
        ast.unparse(node.func) for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert "qlib.init" not in calls
    assert "R.register" not in calls
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "mlflow" not in imported
    assert "from qlib.contrib.model.gbdt import LGBModel" in runner
    assert "model.fit(" in runner
    assert "import qlib" not in product
    assert "import lightgbm" not in product


def test_planned_manifest_and_generated_output_ignore():
    manifest = load_manifest(
        ROOT / "research/manifests/qlib_lightgbm_compatibility_planned.json"
    )
    assert manifest["status"] == "planned"
    assert "blocked" in manifest["notes"].lower()
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "research/generated/" in gitignore
