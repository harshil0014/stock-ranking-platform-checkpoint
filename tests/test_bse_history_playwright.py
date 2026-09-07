from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from zipfile import ZipFile

import pytest


SCRIPT = Path(__file__).parents[1] / "marketdata/runners/download_bse_history_playwright.py"
SPEC = importlib.util.spec_from_file_location("bse_history_playwright", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_extracts_only_exact_six_digit_codes_from_folder_and_zip(tmp_path: Path) -> None:
    folder = tmp_path / "BSE_2025_2026"
    folder.mkdir()
    (folder / "500500.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    (folder / "BSE_500051_latest.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    (folder / "bad_500371_notes.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    assert MODULE.extract_codes(folder) == ["500051", "500500"]
    archive = tmp_path / "BSE_2025_2026.zip"
    with ZipFile(archive, "w") as output:
        output.writestr("nested/501270.csv", "x,y\n1,2\n")
    assert MODULE.extract_codes(archive) == ["501270"]


def test_queue_has_exact_code_window_keys_and_required_folders() -> None:
    tasks = MODULE.build_tasks(["500500"], MODULE.WINDOWS)
    assert len(tasks) == 4
    assert tasks[0].key == "500500|05/09/2024|04/09/2025"
    assert [task.year_folder for task in tasks] == [
        "2024-2025", "2023-2024", "2022-2023", "2021-2022",
    ]


def test_progress_is_atomic_resumable_and_terminal_tasks_are_preserved(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "500500.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    tasks = MODULE.build_tasks(["500500"], MODULE.WINDOWS)
    store = MODULE.ProgressStore(tmp_path / "out", source, ["500500"], tasks)
    store.load_or_initialize()
    store.tasks[0].status = "DOWNLOADED"
    store.tasks[1].status = "NO_RECORD"
    store.tasks[2].status = "RUNNING"
    store.tasks[2].attempts = 1
    store.persist()
    restored = MODULE.ProgressStore(
        tmp_path / "out", source, ["500500"], MODULE.build_tasks(["500500"], MODULE.WINDOWS)
    )
    restored.load_or_initialize()
    assert [task.status for task in restored.tasks[:3]] == ["DOWNLOADED", "NO_RECORD", "PENDING"]
    assert not list((tmp_path / "out").glob("*.pending"))
    payload = json.loads((tmp_path / "out/bse_history_progress.json").read_text())
    assert payload["source_code_count"] == 1


def test_csv_validation_rejects_html_wrong_codes_and_out_of_window_dates() -> None:
    task = MODULE.build_tasks(["500500"], [MODULE.WINDOWS[0]])[0]
    header = (
        b"Scrip Code,Date,Open Price,High Price,Low Price,Close Price,WAP,"
        b"No.of Shares,No. of Trades,Total Turnover (Rs.)\r\n"
    )
    valid, rows = MODULE.validate_csv_bytes(
        b"Scrip Code,Date,Open Price,High Price,Low Price,Close Price,WAP,No.of Shares,No. of Trades,Total Turnover (Rs.)\r\n500500,05/09/2024,100,101,99,100,100,10,2,1000\r\n500500,04/09/2025,120,121,119,120,120,20,3,2400\r\n", task
    )
    assert rows == 2
    assert b"\r" not in valid
    with pytest.raises(ValueError, match="HTML"):
        MODULE.validate_csv_bytes(b"<html><body>Access Denied</body></html>", task)
    with pytest.raises(ValueError, match="different scrip code"):
        MODULE._validate_csv_request_url(
            "https://api.bseindia.com/example?scripcode=500051", task
        )
    with pytest.raises(ValueError, match="outside"):
        MODULE.validate_csv_bytes(
            header + b"500500,01/09/2024,100,101,99,100,100,10,2,1000\r\n",
            task,
        )


def test_full_output_filename_is_deterministic(tmp_path: Path) -> None:
    task = MODULE.build_tasks(["500500"], [MODULE.WINDOWS[0]])[0]
    assert MODULE.output_path(tmp_path, task) == (
        tmp_path / "2024-2025/BSE_500500_05-09-2024_to_04-09-2025.csv"
    )
