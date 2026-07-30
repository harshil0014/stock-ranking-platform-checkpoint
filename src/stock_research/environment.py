"""Read-only environment inspection for the isolated Qlib specification."""

from __future__ import annotations

import importlib.util
import json
import platform
from pathlib import Path
import subprocess
import sys
from typing import Any

from stock_research.fingerprints import fingerprint_environment


PROHIBITED_MAIN_PACKAGES = ("qlib", "lightgbm", "torch")


def python_312_command() -> list[str] | None:
    try:
        result = subprocess.run(
            ["py", "-3.12", "-c", "import sys; print(sys.executable)"],
            check=False, capture_output=True, text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    executable = result.stdout.strip()
    return [executable] if executable else None


def inspect_environment() -> dict[str, Any]:
    available = python_312_command()
    imports = {
        name: importlib.util.find_spec(name) is not None
        for name in PROHIBITED_MAIN_PACKAGES
    }
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "python_3_12_available" if available else "specified_blocked",
        "status_code": (
            "python_3_12_available" if available else "python_3_12_missing"
        ),
        "python_3_12_executable": available[0] if available else None,
        "current_interpreter": sys.executable,
        "current_python_version": platform.python_version(),
        "platform": platform.platform(),
        "qlib_specification": {
            "package": "pyqlib==0.9.7",
            "upstream_tag": "v0.9.7",
            "upstream_commit": "da920b7",
            "candidate_constraints": [
                "lightgbm==4.6.0",
                "numpy==2.0.2",
                "pandas==2.2.3",
            ],
            "constraints_status": "specified_not_verified",
        },
        "main_environment_imports": imports,
        "resolved_lock": None,
        "import_results": None,
    }
    result["environment_fingerprint"] = fingerprint_environment(result)
    return result


def write_environment_report(path: str | Path) -> Path:
    report = inspect_environment()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target
