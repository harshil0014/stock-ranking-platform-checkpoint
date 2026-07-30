from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).parents[1]
VERIFIER_PATH = (
    ROOT / "research/runners/verify_qlib_linear_integration.py"
)


@pytest.fixture
def verifier():
    spec = importlib.util.spec_from_file_location(
        "qlib_integration_verifier_cli_fixture", VERIFIER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    before = sys.modules.get("qlib")
    spec.loader.exec_module(module)
    assert sys.modules.get("qlib") is before
    return module


@pytest.mark.parametrize("option", ["--help", "-h"])
def test_help_exits_zero_with_useful_usage(verifier, option, capsys):
    with pytest.raises(SystemExit) as exit_info:
        verifier.main([option])
    captured = capsys.readouterr()
    assert exit_info.value.code == 0
    assert "usage:" in captured.out
    assert "batch_directory" in captured.out
    assert "offline two-run Qlib Linear reproduction batch" in captured.out
    assert captured.err == ""


def test_missing_positional_argument_is_argparse_error(verifier, capsys):
    with pytest.raises(SystemExit) as exit_info:
        verifier.main([])
    captured = capsys.readouterr()
    assert exit_info.value.code != 0
    assert "usage:" in captured.err
    assert "batch_directory" in captured.err
    assert "Traceback" not in captured.err


def test_nonexistent_batch_directory_is_argparse_error(
    verifier, tmp_path, capsys
):
    missing = tmp_path / "missing"
    with pytest.raises(SystemExit) as exit_info:
        verifier.main([str(missing)])
    captured = capsys.readouterr()
    assert exit_info.value.code != 0
    assert "batch directory does not exist" in captured.err
    assert "Traceback" not in captured.err


def test_file_is_not_accepted_as_batch_directory(
    verifier, tmp_path, capsys
):
    file_path = tmp_path / "batch.txt"
    file_path.write_text("not a directory", encoding="utf-8")
    with pytest.raises(SystemExit) as exit_info:
        verifier.main([str(file_path)])
    captured = capsys.readouterr()
    assert exit_info.value.code != 0
    assert "batch directory is not a directory" in captured.err


def test_missing_and_malformed_artifacts_fail_concisely(
    verifier, tmp_path, capsys
):
    assert verifier.main([str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert (
        "Verification failed: missing required artifact: "
        "reproducibility_report.json"
    ) in captured.err
    assert "Traceback" not in captured.err

    report = tmp_path / "reproducibility_report.json"
    report.write_text("{", encoding="utf-8")
    assert verifier.main([str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert "Verification failed: invalid JSON artifact" in captured.err
    assert "Traceback" not in captured.err


def test_valid_directory_reaches_verifier_without_importing_qlib(
    verifier, tmp_path, monkeypatch, capsys
):
    received = []
    monkeypatch.setattr(verifier, "verify", received.append)
    before = sys.modules.get("qlib")
    assert verifier.main([str(tmp_path)]) == 0
    assert received == [tmp_path]
    assert sys.modules.get("qlib") is before
    assert (
        "Qlib Linear integration verification passed."
        in capsys.readouterr().out
    )
