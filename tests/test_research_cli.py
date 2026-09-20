from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stock_research.cli import main


ROOT = Path(__file__).parents[1]


def test_registry_contract_manifest_and_environment_commands(tmp_path, capsys):
    assert main([
        "registry-validate", "--registry",
        str(ROOT / "research/registry/open_source_registry.json"),
    ]) == 0
    assert main([
        "model-registry-validate", "--registry",
        str(ROOT / "research/registry/model_execution_registry.json"),
    ]) == 0
    assert main([
        "contract-validate", "--kind", "features", "--input",
        str(ROOT / "research/examples/features.csv"),
    ]) == 0
    assert main([
        "contract-validate", "--kind", "split", "--input",
        str(ROOT / "research/examples/split.json"),
    ]) == 0
    assert main([
        "manifest-validate", "--manifest",
        str(ROOT / "research/manifests/planned_qlib_linear.json"),
    ]) == 0
    report = tmp_path / "environment.json"
    assert main(["environment-inspect", "--output", str(report)]) == 0
    environment = json.loads(report.read_text())
    assert environment["status"] in {
        "specified_blocked", "python_3_12_available"
    }
    assert not any(environment["main_environment_imports"].values())


def test_qlib_conversion_cli(tmp_path):
    output = tmp_path / "signals.csv"
    assert main([
        "signal-convert-qlib",
        "--input", str(ROOT / "research/examples/qlib_predictions.csv"),
        "--mapping", str(ROOT / "research/examples/qlib_instrument_mapping.csv"),
        "--output", str(output),
        "--model-id", "qlib_linear",
        "--run-id", "run",
    ]) == 0
    assert output.is_file()


def test_current_feature_export_is_current_only(tmp_path):
    output = tmp_path / "current.csv"
    assert main([
        "current-feature-export", "--state-root", str(ROOT / "data/company_facts"),
        "--output", str(output),
    ]) == 0
    frame = pd.read_csv(output)
    assert not frame.empty
    assert set(frame["availability_status"]) == {"current_only"}
    assert main([
        "contract-validate", "--kind", "feature-evidence", "--mode",
        "current", "--input", str(output),
    ]) == 0
    # The generic contract refuses this exact export in historical mode.
    assert main([
        "contract-validate", "--kind", "feature-evidence", "--mode",
        "historical_evaluation", "--input", str(output),
    ]) != 0


def test_invalid_cli_returns_nonzero(tmp_path, capsys):
    invalid = tmp_path / "invalid.csv"
    invalid.write_text("wrong\nvalue\n")
    assert main([
        "contract-validate", "--kind", "labels", "--input", str(invalid)
    ]) != 0
    assert "Error:" in capsys.readouterr().err


def test_evaluate_writes_derived_completed_manifest(tmp_path):
    signals = pd.read_csv(ROOT / "research/examples/signals_linear.csv")
    signals["run_id"] = "33333333-3333-4333-8333-333333333333"
    signal_path = tmp_path / "signals.csv"
    signals.to_csv(signal_path, index=False)
    output = tmp_path / "evaluation"
    assert main([
        "evaluate",
        "--signals", str(signal_path),
        "--labels", str(ROOT / "research/examples/labels.csv"),
        "--protocol", str(ROOT / "research/examples/evaluation_protocol.json"),
        "--model-configuration-fingerprint",
        "0f12fa31205aec98248e46325cc8fe3c5700d9d3a02d76bca3d29e7bc7f0af03",
        "--manifest",
        str(ROOT / "research/manifests/planned_qlib_linear.json"),
        "--output-dir", str(output),
    ]) == 0
    derived = json.loads((output / "experiment_manifest.json").read_text())
    assert derived["status"] == "completed"
    assert len(derived["evaluation_artifacts"]) == 4


def test_reproduce_qlib_linear_dry_run_is_write_free(tmp_path, capsys):
    interpreter = tmp_path / "python.exe"
    interpreter.write_bytes(b"not executed")
    lock = tmp_path / "freeze.txt"
    lock.write_text("pyqlib==0.9.7\n", encoding="utf-8")
    environment = tmp_path / "environment.json"
    environment.write_text(json.dumps({
        "status": "verified",
        "environment_fingerprint": "b" * 64,
        "resolved_lock": str(lock),
        "interpreter": str(interpreter),
        "packages": ["pyqlib==0.9.7"],
        "import_results": {
            "qlib": {"ok": True, "version": "0.9.7"},
            "lightgbm": {"ok": True, "version": "4.6.0"},
            "numpy": {"ok": True, "version": "2.0.2"},
            "pandas": {"ok": True, "version": "2.2.3"},
            "qlib.contrib.data.handler": {"ok": True, "version": None},
            "qlib.contrib.model.linear": {"ok": True, "version": None},
        },
    }), encoding="utf-8")
    output = tmp_path / "output"
    assert main([
        "reproduce-qlib-linear",
        "--qlib-interpreter", str(interpreter),
        "--environment-report", str(environment),
        "--output-root", str(output),
        "--batch-id", "dry-run",
        "--dry-run",
    ]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["dry_run"] is True
    assert response["training_performed"] is False
    assert response["artifacts_written"] is False
    assert not output.exists()


def test_reproduce_qlib_linear_invalid_environment_returns_nonzero(
    tmp_path, capsys
):
    interpreter = tmp_path / "python.exe"
    interpreter.write_bytes(b"not executed")
    environment = tmp_path / "environment.json"
    environment.write_text(json.dumps({
        "status": "specified_blocked",
        "environment_fingerprint": "b" * 64,
        "resolved_lock": str(tmp_path / "missing.txt"),
    }), encoding="utf-8")
    assert main([
        "reproduce-qlib-linear",
        "--qlib-interpreter", str(interpreter),
        "--environment-report", str(environment),
        "--dry-run",
    ]) != 0
    assert "not verified" in capsys.readouterr().err
