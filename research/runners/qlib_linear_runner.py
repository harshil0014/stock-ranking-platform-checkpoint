"""Standalone Python 3.12 Qlib Linear runner.

This file deliberately does not import the product package.  It is invoked only
with the verified ``.venv-qlib`` interpreter.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd
import qlib
import lightgbm
from qlib.contrib.model.linear import LinearModel
from qlib.data.dataset import DatasetH
from qlib.data.dataset.handler import DataHandlerLP


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(value: Any, path: Path) -> None:
    path.write_text(
        json.dumps(
            value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
        ) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _csv(data: pd.DataFrame, path: Path) -> None:
    data.to_csv(
        path, index=False, encoding="utf-8", lineterminator="\n",
        float_format="%.17g",
    )


def run(request_path: Path) -> int:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    required_threads = request["thread_controls"]
    actual_threads = {name: os.environ.get(name) for name in required_threads}
    if actual_threads != required_threads:
        raise RuntimeError(
            f"numerical thread controls mismatch: {actual_threads}"
        )
    environment_report = Path(request["environment_report"])
    lock_path = Path(request["resolved_lock"])
    if _sha256(environment_report) != request["environment_report_sha256"]:
        raise RuntimeError("environment report fingerprint mismatch")
    if _sha256(lock_path) != request["resolved_lock_sha256"]:
        raise RuntimeError("resolved dependency lock fingerprint mismatch")
    environment = json.loads(environment_report.read_text(encoding="utf-8"))
    if environment.get("status") != "verified":
        raise RuntimeError("Qlib environment is not verified")
    if environment.get("environment_fingerprint") != request[
        "environment_fingerprint"
    ]:
        raise RuntimeError("Qlib environment fingerprint mismatch")
    expected_versions = {
        name: environment.get("import_results", {}).get(name, {}).get("version")
        for name in ("qlib", "lightgbm", "numpy", "pandas")
    }
    actual_versions = {
        "qlib": qlib.__version__,
        "lightgbm": lightgbm.__version__,
        "numpy": np.__version__,
        "pandas": pd.__version__,
    }
    if actual_versions != expected_versions:
        raise RuntimeError(
            f"installed dependency versions differ from report: {actual_versions}"
        )
    if Path(sys.executable).resolve() != Path(environment["interpreter"]).resolve():
        raise RuntimeError("runner interpreter differs from verified environment")

    panel_path = Path(request["panel_path"])
    if _sha256(panel_path) != request["panel_sha256"]:
        raise RuntimeError("Qlib panel fingerprint mismatch")
    outputs = {name: Path(path) for name, path in request["outputs"].items()}
    preexisting = [str(path) for path in outputs.values() if path.exists()]
    if preexisting:
        raise RuntimeError(f"refusing stale output artifacts: {preexisting}")
    for path in outputs.values():
        path.parent.mkdir(parents=True, exist_ok=True)

    panel = pd.read_csv(panel_path, header=[0, 1], index_col=[0, 1])
    panel.index = pd.MultiIndex.from_arrays(
        [
            pd.to_datetime(panel.index.get_level_values(0), format="%Y-%m-%d"),
            panel.index.get_level_values(1).astype(str),
        ],
        names=["datetime", "instrument"],
    )
    panel = panel.astype(float).sort_index()
    if panel.isna().any().any() or not np.isfinite(panel.to_numpy()).all():
        raise RuntimeError("panel contains missing or nonfinite values")
    expected_features = [
        ("feature", name) for name in request["feature_columns"]
    ]
    expected_label = [("label", request["label_name"])]
    if list(panel.columns) != expected_features + expected_label:
        raise RuntimeError("panel columns do not match the canonical request")

    segments = request["segments"]
    handler = DataHandlerLP.from_df(panel)
    dataset = DatasetH(
        handler=handler,
        segments={
            name: (values["start"], values["end"])
            for name, values in segments.items()
        },
    )
    parameters = request["model_parameters"]
    model = LinearModel(**parameters)
    model.fit(dataset)
    predictions = model.predict(dataset, segment="test")
    if not isinstance(predictions, pd.Series):
        predictions = pd.Series(predictions)
    predictions = predictions.rename("score").sort_index()
    raw = predictions.reset_index()
    raw.columns = ["datetime", "instrument", "score"]
    raw["datetime"] = pd.to_datetime(raw["datetime"]).dt.strftime("%Y-%m-%d")
    raw = raw.sort_values(
        ["datetime", "instrument"], kind="mergesort"
    ).reset_index(drop=True)
    if len(raw) != request["expected_test_rows"]:
        raise RuntimeError(
            f"expected {request['expected_test_rows']} predictions; got {len(raw)}"
        )
    if not np.isfinite(raw["score"].to_numpy(dtype=float)).all():
        raise RuntimeError("predictions contain nonfinite values")

    coefficients = np.asarray(model.coef_, dtype=float).reshape(-1)
    if len(coefficients) != len(request["feature_columns"]):
        raise RuntimeError("unexpected coefficient count")
    coefficient_frame = pd.DataFrame({
        "feature": request["feature_columns"],
        "coefficient": coefficients,
    })
    intercept_status = "not_applicable"
    intercept: float | None = None
    if hasattr(model, "intercept_"):
        raw_intercept = getattr(model, "intercept_")
        if raw_intercept is not None:
            array = np.asarray(raw_intercept, dtype=float).reshape(-1)
            if len(array) != 1 or not np.isfinite(array[0]):
                raise RuntimeError("upstream estimator exposes an invalid intercept")
            intercept = float(array[0])
            intercept_status = "extracted_zero_verified"
            if abs(intercept) > request["intercept_tolerance"]:
                raise RuntimeError(
                    f"fit_intercept=false but extracted intercept is {intercept}"
                )

    _csv(raw, outputs["predictions"])
    _csv(coefficient_frame, outputs["coefficients"])
    metadata = {
        "schema_version": "1.0",
        "run_id": request["run_id"],
        "model_id": request["model_id"],
        "qlib_version": qlib.__version__,
        "dependency_versions": actual_versions,
        "model_class": f"{type(model).__module__}.{type(model).__name__}",
        "model_parameters": parameters,
        "model_configuration_fingerprint":
            request["model_configuration_fingerprint"],
        "dataset_fingerprints": request["dataset_fingerprints"],
        "environment_fingerprint": request["environment_fingerprint"],
        "resolved_lock_sha256": request["resolved_lock_sha256"],
        "thread_controls": actual_threads,
        "training_segment": "train",
        "prediction_segment": "test",
        "include_valid": parameters["include_valid"],
        "prediction_count": len(raw),
        "coefficient_count": len(coefficients),
        "intercept": intercept,
        "intercept_status": intercept_status,
        "intercept_tolerance": request["intercept_tolerance"],
        "provider_initialized": False,
        "network_used": False,
        "pickle_written": False,
    }
    _json(metadata, outputs["metadata"])
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: qlib_linear_runner.py REQUEST.json", file=sys.stderr)
        return 2
    try:
        return run(Path(sys.argv[1]))
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
