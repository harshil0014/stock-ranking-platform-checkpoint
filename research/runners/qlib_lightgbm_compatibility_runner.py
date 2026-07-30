"""One-attempt compatibility proof for Qlib v0.9.7 ``LGBModel``.

This standalone file is executed only by the isolated Python 3.12 Qlib
environment.  It intentionally does not import the product package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
from typing import Any

import numpy as np
import pandas as pd


class CompatibilityBlocked(RuntimeError):
    """The official model trained but its mandatory workflow logging failed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
        ) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _csv(data: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(
        path, index=False, encoding="utf-8", lineterminator="\n",
        float_format="%.17g",
    )


def _existing_file(value: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"request file does not exist: {path}")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one official Qlib LGBModel compatibility proof without "
            "initializing a workflow recorder."
        )
    )
    parser.add_argument("request", type=_existing_file)
    return parser


def _load_and_validate_request(path: Path) -> dict[str, Any]:
    try:
        request = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid request JSON: {exc}") from exc
    required = {
        "run_id", "model_id", "panel_path", "panel_sha256",
        "environment_report", "environment_report_sha256",
        "environment_fingerprint", "resolved_lock", "resolved_lock_sha256",
        "qlib_gbdt_source", "qlib_gbdt_source_sha256", "feature_columns",
        "label_name", "segments", "model_construction", "fit_configuration",
        "model_configuration_fingerprint", "dataset_fingerprints",
        "evaluation_protocol_fingerprint", "thread_controls", "outputs",
    }
    missing = sorted(required.difference(request))
    if missing:
        raise ValueError(f"request is missing fields: {missing}")
    expected_threads = request["thread_controls"]
    actual_threads = {name: os.environ.get(name) for name in expected_threads}
    if actual_threads != expected_threads:
        raise ValueError(f"numerical thread controls mismatch: {actual_threads}")
    for field, hash_field in (
        ("panel_path", "panel_sha256"),
        ("environment_report", "environment_report_sha256"),
        ("resolved_lock", "resolved_lock_sha256"),
        ("qlib_gbdt_source", "qlib_gbdt_source_sha256"),
    ):
        source = Path(request[field])
        if not source.is_file():
            raise ValueError(f"required file does not exist: {source}")
        if _sha256(source) != request[hash_field]:
            raise ValueError(f"{field} fingerprint mismatch")
    outputs = {name: Path(value) for name, value in request["outputs"].items()}
    stale = sorted(str(path) for path in outputs.values() if path.exists())
    if stale:
        raise ValueError(f"refusing stale output artifacts: {stale}")
    required_outputs = {
        "runner_metadata", "training_history", "feature_importance_gain",
        "feature_importance_split", "model_dump", "failure_diagnostics",
    }
    if set(outputs) != required_outputs:
        raise ValueError("runner output contract mismatch")
    request["_output_paths"] = outputs
    request["_actual_threads"] = actual_threads
    return request


def _load_panel(request: dict[str, Any]) -> pd.DataFrame:
    panel = pd.read_csv(
        request["panel_path"], header=[0, 1], index_col=[0, 1]
    )
    panel.index = pd.MultiIndex.from_arrays(
        [
            pd.to_datetime(panel.index.get_level_values(0), format="%Y-%m-%d"),
            panel.index.get_level_values(1).astype(str),
        ],
        names=["datetime", "instrument"],
    )
    panel = panel.astype(float).sort_index()
    expected_columns = [
        *(("feature", name) for name in request["feature_columns"]),
        ("label", request["label_name"]),
    ]
    if list(panel.columns) != expected_columns:
        raise ValueError("panel columns do not match the frozen feature order")
    if panel.isna().any().any() or not np.isfinite(panel.to_numpy()).all():
        raise ValueError("panel contains missing or nonfinite values")
    expected_rows = {"train": 3600, "valid": 900, "test": 1200}
    for name, boundaries in request["segments"].items():
        selected = panel.loc[
            panel.index.get_level_values("datetime").to_series(index=panel.index)
            .between(boundaries["start"], boundaries["end"])
            .to_numpy()
        ]
        if len(selected) != expected_rows[name]:
            raise ValueError(
                f"frozen {name} row count mismatch: {len(selected)}"
            )
    return panel


def run(request_path: Path) -> int:
    request = _load_and_validate_request(request_path)
    panel = _load_panel(request)
    environment = json.loads(
        Path(request["environment_report"]).read_text(encoding="utf-8")
    )
    if environment.get("status") != "verified":
        raise ValueError("Qlib environment report is not verified")
    if environment.get("environment_fingerprint") != request[
        "environment_fingerprint"
    ]:
        raise ValueError("Qlib environment fingerprint mismatch")

    import lightgbm
    import qlib
    from qlib.contrib.model.gbdt import LGBModel
    from qlib.data.dataset import DatasetH
    from qlib.data.dataset.handler import DataHandlerLP
    from qlib.workflow import R

    versions = {
        "qlib": qlib.__version__,
        "lightgbm": lightgbm.__version__,
        "numpy": np.__version__,
        "pandas": pd.__version__,
    }
    if versions["qlib"] != "0.9.7" or versions["lightgbm"] != "4.6.0":
        raise ValueError(f"unexpected dependency versions: {versions}")
    if f"{LGBModel.__module__}.{LGBModel.__name__}" != (
        "qlib.contrib.model.gbdt.LGBModel"
    ):
        raise ValueError("official Qlib LGBModel class identity mismatch")
    if R._provider is not None:
        raise ValueError("workflow provider is unexpectedly initialized")

    handler = DataHandlerLP.from_df(panel)
    dataset = DatasetH(
        handler=handler,
        segments={
            name: (boundaries["start"], boundaries["end"])
            for name, boundaries in request["segments"].items()
        },
    )
    construction = request["model_construction"]
    model = LGBModel(
        loss=construction["loss"],
        early_stopping_rounds=construction["early_stopping_rounds"],
        num_boost_round=construction["num_boost_round"],
        **construction["parameters"],
    )
    history: dict[str, Any] = {}
    caught: Exception | None = None
    try:
        model.fit(
            dataset,
            evals_result=history,
            verbose_eval=request["fit_configuration"]["verbose_eval"],
        )
    except Exception as exc:
        caught = exc

    outputs = request["_output_paths"]
    booster = model.model
    if booster is not None:
        feature_names = list(request["feature_columns"])
        _csv(pd.DataFrame({
            "feature": feature_names,
            "importance_gain": booster.feature_importance(
                importance_type="gain"
            ),
        }), outputs["feature_importance_gain"])
        _csv(pd.DataFrame({
            "feature": feature_names,
            "importance_split": booster.feature_importance(
                importance_type="split"
            ),
        }), outputs["feature_importance_split"])
        _json(booster.dump_model(), outputs["model_dump"])
        best_iteration = int(booster.best_iteration)
        tree_count = int(booster.num_trees())
        booster_feature_names = list(booster.feature_name())
    else:
        best_iteration = None
        tree_count = None
        booster_feature_names = []
    _json(history, outputs["training_history"])

    blocker_matched = (
        isinstance(caught, AttributeError)
        and "Please run qlib.init() first using qlib" in str(caught)
        and booster is not None
    )
    diagnostics = {
        "schema_version": "1.0",
        "status": "blocked" if blocker_matched else "failed",
        "blocker_matched": blocker_matched,
        "failure_type": type(caught).__name__ if caught is not None else None,
        "failure_message": str(caught) if caught is not None else (
            "official fit unexpectedly returned without the known blocker"
        ),
        "traceback": (
            "".join(traceback.format_exception(caught))
            if caught is not None else None
        ),
        "training_completed_before_workflow_failure": booster is not None,
        "predictions_attempted": False,
        "workflow_provider_initialized": R._provider is not None,
        "fallback_used": False,
        "parameters_relaxed": False,
    }
    _json(diagnostics, outputs["failure_diagnostics"])
    _json({
        "schema_version": "1.0",
        "run_id": request["run_id"],
        "model_id": request["model_id"],
        "status": diagnostics["status"],
        "model_class": f"{LGBModel.__module__}.{LGBModel.__name__}",
        "versions": versions,
        "qlib_gbdt_source": request["qlib_gbdt_source"],
        "qlib_gbdt_source_sha256": request["qlib_gbdt_source_sha256"],
        "environment_fingerprint": request["environment_fingerprint"],
        "resolved_lock_sha256": request["resolved_lock_sha256"],
        "dataset_fingerprints": request["dataset_fingerprints"],
        "evaluation_protocol_fingerprint":
            request["evaluation_protocol_fingerprint"],
        "model_configuration_fingerprint":
            request["model_configuration_fingerprint"],
        "model_construction": construction,
        "fit_configuration": request["fit_configuration"],
        "segments": request["segments"],
        "row_counts": {"train": 3600, "valid": 900, "test": 1200},
        "requested_boosting_rounds": construction["num_boost_round"],
        "best_iteration": best_iteration,
        "tree_count": tree_count,
        "feature_names": list(request["feature_columns"]),
        "booster_feature_names": booster_feature_names,
        "thread_controls": request["_actual_threads"],
        "provider_initialized": False,
        "mlflow_initialized": False,
        "network_used": False,
        "predictions_written": False,
        "pickle_written": False,
    }, outputs["runner_metadata"])
    if blocker_matched:
        raise CompatibilityBlocked(
            "official Qlib LGBModel.fit trained, then failed at mandatory "
            "R.log_metrics because qlib.init() was not permitted"
        )
    if caught is not None:
        raise caught
    raise RuntimeError("expected Qlib workflow compatibility blocker was absent")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args.request)
    except Exception as exc:
        print(f"Compatibility proof failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
