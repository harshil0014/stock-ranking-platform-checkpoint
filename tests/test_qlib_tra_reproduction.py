from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.cli import main
from stock_research.qlib_tra_reproduction import (
    DATASET_CONFIG,
    MODEL_CONFIG,
    MODEL_PARAMETERS,
    SUBPROCESS_CONTROLS,
    TRA_CONFIG,
    QlibTRAReproductionConfig,
    build_tra_subprocess_environment,
    compare_tra_runs,
    plan_qlib_tra_reproduction,
)


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "research/runners/qlib_tra_runner.py"
VERIFIER = ROOT / "research/runners/verify_qlib_tra_integration.py"
PRODUCT = ROOT / "src/stock_research/qlib_tra_reproduction.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("qlib_tra_runner_test", RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_configuration_is_exact() -> None:
    assert MODEL_CONFIG == {
        "input_size": 10, "hidden_size": 64, "num_layers": 2,
        "rnn_arch": "LSTM", "use_attn": True, "dropout": 0.0,
    }
    assert TRA_CONFIG["num_states"] == 3
    assert TRA_CONFIG["src_info"] == "LR_TPE"
    assert MODEL_PARAMETERS["pretrain"] is True
    assert MODEL_PARAMETERS["eval_test"] is False
    assert MODEL_PARAMETERS["logdir"] is None


def test_dataset_configuration_uses_real_sequences() -> None:
    assert DATASET_CONFIG == {
        "seq_len": 60, "horizon": 1, "input_size": None,
        "num_states": 3, "batch_size": 1024, "n_samples": None,
        "memory_mode": "sample", "shuffle": True, "drop_last": True,
    }
    assert MODEL_CONFIG["input_size"] == 10


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("seed", 1), ("reruns", 1), ("reproducibility_tolerance", 1e-8),
        ("timeout_seconds", 1),
    ],
)
def test_config_rejects_nonfrozen_values(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        QlibTRAReproductionConfig(**{field: value})


def test_subprocess_controls_are_isolated(tmp_path: Path) -> None:
    parent = {"PATH": "example", "OMP_NUM_THREADS": "99"}
    child, audit = build_tra_subprocess_environment(tmp_path, parent)
    assert parent["OMP_NUM_THREADS"] == "99"
    assert {name: child[name] for name in SUBPROCESS_CONTROLS} == SUBPROCESS_CONTROLS
    assert child["MPLCONFIGDIR"].endswith("matplotlib-cache")
    assert audit["OMP_NUM_THREADS"] is True


def test_remote_environment_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="prohibited inherited"):
        build_tra_subprocess_environment(
            tmp_path, {"MLFLOW_TRACKING_URI": "https://example.invalid"}
        )


def test_plan_is_two_processes_and_write_free(tmp_path: Path) -> None:
    output = tmp_path / "generated"
    plan = plan_qlib_tra_reproduction(
        QlibTRAReproductionConfig(output_root=output, batch_id="fresh")
    )
    assert len(plan.commands) == 2
    assert plan.commands[0] != plan.commands[1]
    assert plan.dataset_config["input_size"] is None
    assert plan.model_config["input_size"] == 10
    assert not output.exists()


def test_resume_requires_completed_runner_evidence(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="resume requires"):
        plan_qlib_tra_reproduction(QlibTRAReproductionConfig(
            output_root=tmp_path, batch_id="missing",
            resume_completed_run_one=True,
        ))


def test_cli_help_and_dry_run(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as help_exit:
        main(["reproduce-qlib-tra", "--help"])
    assert help_exit.value.code == 0
    assert "reproduce-qlib-tra" in capsys.readouterr().out
    output = tmp_path / "output"
    code = main([
        "reproduce-qlib-tra", "--dry-run", "--output-root", str(output),
        "--batch-id", "dry-run",
    ])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["artifacts_written"] is False
    assert payload["training_performed"] is False
    assert len(payload["commands"]) == 2
    assert not output.exists()


def test_phase_history_is_split_at_official_best_logs() -> None:
    runner = _load_runner()
    log = "\n".join([
        "pretraining...", "valid metrics: {'IC': 0.1}",
        "valid metrics: {'IC': 0.2}", "best score: 0.200000 @ 1",
        "training...", "valid metrics: {'IC': 0.3}",
        "valid metrics: {'IC': 0.4}", "early stop @ 1",
        "best score: 0.400000 @ 1",
    ])
    history = {
        "valid": [{"IC": 0.1}, {"IC": 0.2}, {"IC": 0.3}, {"IC": 0.4}]
    }
    evidence = runner._phase_evidence(log, history)
    assert [item["history_length"] for item in evidence["phases"]] == [2, 2]
    assert evidence["final_selected_epoch"] == 1
    assert evidence["final_selected_score"] == pytest.approx(0.4)


def test_static_sequence_audit_uses_frozen_panel() -> None:
    runner = _load_runner()
    panel = (
        ROOT / "research/generated/qlib-linear/final-locked-20260731/"
        "run-01/synthetic_qlib_panel.csv"
    )
    specification = json.loads(
        (ROOT / "research/specifications/qlib_tra_frozen_protocol.json")
        .read_text(encoding="utf-8")
    )
    split = json.loads(
        (ROOT / "research/generated/qlib-linear/final-locked-20260731/"
         "run-01/split.json").read_text(encoding="utf-8")
    )
    audit = runner._static_panel_audit({
        "panel_path": str(panel), "feature_columns": specification["feature_list"],
        "label_name": "forward_1d_return", "expected_panel_rows": 6000,
        "expected_instrument_count": 30, "dataset_config": DATASET_CONFIG,
        "segments": {
            "train": split["train"], "valid": split["validation"],
            "test": split["test"],
        },
    })
    assert audit["status"] == "passed"
    assert audit["feature_width"] == 10
    first = next(
        item for item in audit["endpoints"]
        if item["instrument"] == "SYN001"
    )
    assert first["left_padding_steps"] == 59
    assert first["latest_feature_date"] == first["endpoint"]


def _write_run(directory: Path, offset: float = 0.0) -> None:
    directory.mkdir()
    keys = pd.DataFrame({
        "datetime": ["2026-05-05", "2026-05-05"],
        "instrument": ["SYN001", "SYN002"],
    })
    keys.assign(score=[1.0 + offset, 2.0]).to_csv(
        directory / "tra_predictions_raw.csv", index=False
    )
    keys.assign(
        score_0=[1.0 + offset, 2.0], score_1=[2.0, 3.0],
        score_2=[3.0, 4.0],
    ).to_csv(directory / "tra_state_scores.csv", index=False)
    metadata = {
        "sequence_boundary_fingerprint": "sequence",
        "environment_fingerprint": "environment",
        "model_configuration_fingerprint": "model",
        "evaluation_protocol_fingerprint": "protocol",
        "subprocess_environment_controls": SUBPROCESS_CONTROLS,
    }
    (directory / "tra_runner_metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    phase = {
        "final_selected_epoch": 2,
        "phases": [
            {"history_length": 3, "stopping_epoch": 2},
            {"history_length": 4, "stopping_epoch": 3},
        ],
    }
    (directory / "phase_summary.json").write_text(
        json.dumps(phase), encoding="utf-8"
    )
    state = {
        "backbone_state_fingerprint": "backbone",
        "tra_state_fingerprint": "tra",
    }
    (directory / "combined_state_fingerprint.json").write_text(
        json.dumps(state), encoding="utf-8"
    )


def test_reproducibility_checks_all_four_scores(tmp_path: Path) -> None:
    one, two = tmp_path / "one", tmp_path / "two"
    _write_run(one)
    _write_run(two)
    report = compare_tra_runs(one, two)
    assert report["status"] == "passed"
    assert set(report["maximum_differences"]) == {
        "score", "score_0", "score_1", "score_2"
    }


def test_reproducibility_fails_without_relaxing_tolerance(tmp_path: Path) -> None:
    one, two = tmp_path / "one", tmp_path / "two"
    _write_run(one)
    _write_run(two, offset=1e-10)
    assert compare_tra_runs(one, two)["status"] == "failed"
    with pytest.raises(ValueError):
        compare_tra_runs(one, two, tolerance=1e-8)


def test_product_and_runner_import_boundaries() -> None:
    product_tree = ast.parse(PRODUCT.read_text(encoding="utf-8"))
    product_imports = {
        alias.name.split(".")[0]
        for node in ast.walk(product_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(product_tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert {"qlib", "torch", "lightgbm"}.isdisjoint(product_imports)
    runner_text = RUNNER.read_text(encoding="utf-8")
    for forbidden in (
        "torch.save(", ".to_pickle(", "pickle.dump(", "joblib.dump(", "backward(",
        "MLflowExpManager", "qlib.init(", "lightgbm.train",
    ):
        assert forbidden not in runner_text


def test_environment_lock_contains_only_expected_torch_package() -> None:
    lock = (
        ROOT / "research/environment/tra_dependency_lock.txt"
    ).read_text(encoding="utf-8").splitlines()
    torch_lines = [line for line in lock if line.lower().startswith("torch")]
    assert torch_lines == ["torch==2.4.1+cpu"]
    assert not any(line.lower().startswith("torchvision") for line in lock)
    assert not any(line.lower().startswith("torchaudio") for line in lock)


def test_verifier_help_and_missing_directory(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    spec = importlib.util.spec_from_file_location("qlib_tra_verifier_test", VERIFIER)
    assert spec and spec.loader
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    with pytest.raises(SystemExit) as help_exit:
        verifier.main(["--help"])
    assert help_exit.value.code == 0
    assert "batch_directory" in capsys.readouterr().out
    assert verifier.main([str(tmp_path / "missing")]) == 1
    captured = capsys.readouterr()
    assert "batch directory does not exist" in captured.err
    assert "Traceback" not in captured.err
