from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

from stock_ranker.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_INPUT = PROJECT_ROOT / "data" / "input" / "synthetic_stocks.csv"


def test_cli_main_success_creates_full_and_top_outputs(
    tmp_path, capsys
) -> None:
    exit_code = main(
        [
            "rank",
            "--input",
            str(SAMPLE_INPUT),
            "--output-dir",
            str(tmp_path),
            "--top-n",
            "5",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Processed 18 stocks across 3 sectors." in captured.out
    assert "Selected 15 stocks" in captured.out
    assert (tmp_path / "full_rankings.csv").is_file()
    assert (tmp_path / "top_5_rankings.csv").is_file()
    assert len(pd.read_csv(tmp_path / "full_rankings.csv")) == 18
    assert len(pd.read_csv(tmp_path / "top_5_rankings.csv")) == 15


def test_cli_main_failure_is_concise_and_nonzero(tmp_path, capsys) -> None:
    bad_input = tmp_path / "bad.csv"
    pd.DataFrame({"ticker": ["BAD"]}).to_csv(bad_input, index=False)

    exit_code = main(
        [
            "rank",
            "--input",
            str(bad_input),
            "--output-dir",
            str(tmp_path / "output"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.out == ""
    assert captured.err.startswith("Error: Missing required columns:")
    assert "Traceback" not in captured.err


def test_cli_main_rejects_invalid_top_n(tmp_path, capsys) -> None:
    exit_code = main(
        [
            "rank",
            "--input",
            str(SAMPLE_INPUT),
            "--output-dir",
            str(tmp_path),
            "--top-n",
            "0",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.err == "Error: top_n must be a positive integer\n"
    assert not (tmp_path / "full_rankings.csv").exists()


def _installed_console_command() -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    command = Path(sys.executable).with_name(f"stock-ranker{suffix}")
    assert command.is_file(), (
        "Install the project with 'python -m pip install -e .' before tests"
    )
    return command


def test_installed_console_command_success(tmp_path) -> None:
    completed = subprocess.run(
        [
            str(_installed_console_command()),
            "rank",
            "--input",
            str(SAMPLE_INPUT),
            "--output-dir",
            str(tmp_path),
            "--top-n",
            "2",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Processed 18 stocks across 3 sectors." in completed.stdout
    assert (tmp_path / "full_rankings.csv").is_file()
    assert len(pd.read_csv(tmp_path / "top_2_rankings.csv")) == 6


def test_installed_console_command_failure(tmp_path) -> None:
    completed = subprocess.run(
        [
            str(_installed_console_command()),
            "rank",
            "--input",
            str(tmp_path / "missing.csv"),
            "--output-dir",
            str(tmp_path / "output"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert completed.stderr.startswith("Error:")
    assert "Traceback" not in completed.stderr
