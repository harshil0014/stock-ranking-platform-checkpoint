from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

from stock_ranker.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = PROJECT_ROOT / "data" / "input"


def _arguments(output_dir: Path) -> list[str]:
    return [
        "research-v2",
        "--universe",
        str(INPUT_DIR / "v2_universe.csv"),
        "--prices",
        str(INPUT_DIR / "v2_prices.csv"),
        "--fundamentals",
        str(INPUT_DIR / "v2_fundamentals.csv"),
        "--ranking-date",
        "2026-06-30",
        "--output-dir",
        str(output_dir),
        "--top-n",
        "5",
    ]


def test_v2_cli_success_creates_all_outputs(tmp_path, capsys) -> None:
    exit_code = main(_arguments(tmp_path))
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "17 eligible, 1 ineligible" in captured.out
    assert (tmp_path / "full_research_v2_rankings.csv").is_file()
    assert (tmp_path / "top_5_research_v2_rankings.csv").is_file()
    assert (tmp_path / "research_v2_eligibility_report.csv").is_file()
    assert len(pd.read_csv(tmp_path / "full_research_v2_rankings.csv")) == 17
    assert len(pd.read_csv(tmp_path / "top_5_research_v2_rankings.csv")) == 15


def test_v2_cli_rejects_bad_ranking_date(tmp_path, capsys) -> None:
    arguments = _arguments(tmp_path)
    arguments[arguments.index("2026-06-30")] = "30/06/2026"
    exit_code = main(arguments)
    assert exit_code != 0
    assert "ranking_date must use valid ISO" in capsys.readouterr().err


def test_installed_v2_console_command_succeeds(tmp_path) -> None:
    suffix = ".exe" if os.name == "nt" else ""
    executable = Path(sys.executable).with_name(f"stock-ranker{suffix}")
    assert executable.is_file()
    completed = subprocess.run(
        [str(executable), *_arguments(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "Evaluated 18 stocks" in completed.stdout
