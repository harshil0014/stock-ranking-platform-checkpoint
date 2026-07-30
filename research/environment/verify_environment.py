"""Run inside .venv-qlib after installation; no project import is required."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import platform
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    modules = (
        "qlib", "lightgbm", "numpy", "pandas",
        "qlib.contrib.model.linear", "qlib.contrib.model.gbdt",
        "qlib.contrib.model.double_ensemble", "qlib.contrib.data.handler",
    )
    imports = {}
    for name in modules:
        try:
            module = importlib.import_module(name)
            imports[name] = {
                "ok": True, "version": getattr(module, "__version__", None)
            }
        except Exception as exc:
            imports[name] = {
                "ok": False, "error": f"{type(exc).__name__}: {exc}"
            }
    lock = args.lock.read_text(encoding="utf-8-sig").splitlines()
    report = {
        "schema_version": "1.0",
        "status": "verified" if all(item["ok"] for item in imports.values()) else "failed",
        "interpreter": sys.executable,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "packages": sorted(line for line in lock if line.strip()),
        "import_results": imports,
        "resolved_lock": args.lock.as_posix(),
    }
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["environment_fingerprint"] = hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if report["status"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
