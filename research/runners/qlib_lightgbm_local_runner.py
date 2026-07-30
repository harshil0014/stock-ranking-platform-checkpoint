"""Standalone official Qlib LightGBM runner with a local file recorder.

This file is executed only by the isolated Python 3.12 Qlib environment and
deliberately does not import the product package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse

import numpy as np
import pandas as pd


EXPERIMENT_NAME = "qlib-lightgbm-offline-synthetic"
FORBIDDEN_MLFLOW_ENVIRONMENT = (
    "MLFLOW_TRACKING_URI",
    "MLFLOW_REGISTRY_URI",
    "MLFLOW_TRACKING_USERNAME",
    "MLFLOW_TRACKING_PASSWORD",
    "MLFLOW_TRACKING_TOKEN",
)


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
            value, indent=2, sort_keys=True, ensure_ascii=False,
            allow_nan=False,
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
            "Run official Qlib LGBModel with Qlib's local file-backed "
            "MLflowExpManager."
        )
    )
    parser.add_argument("request", type=_existing_file)
    return parser


def _beneath(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _validate_local_paths(request: dict[str, Any]) -> dict[str, Path]:
    run_directory = Path(request["run_directory"]).resolve()
    provider_path = Path(request["provider_path"]).resolve()
    tracking_path = Path(request["tracking_path"]).resolve()
    tracking_uri = request["tracking_uri"]
    parsed = urlparse(tracking_uri)
    if parsed.scheme != "file" or parsed.netloc:
        raise ValueError("tracking URI must be a local file URI without a host")
    if provider_path.as_posix().startswith("//") or (
        tracking_path.as_posix().startswith("//")
    ):
        raise ValueError("UNC or network paths are prohibited")
    if not _beneath(provider_path, run_directory):
        raise ValueError("provider path must be beneath the run directory")
    if not _beneath(tracking_path, run_directory):
        raise ValueError("tracking path must be beneath the run directory")
    if tracking_path.as_uri() != tracking_uri:
        raise ValueError("tracking URI does not match the resolved local path")
    repository = Path(subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()).resolve()
    for path in (provider_path, tracking_path):
        if _beneath(path, repository):
            ignored = subprocess.run(
                ["git", "check-ignore", "-q", str(path)],
                check=False,
                capture_output=True,
            )
            if ignored.returncode != 0:
                raise ValueError(
                    f"recorder path is not ignored by Git: {path}"
                )
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path)],
            check=False,
            capture_output=True,
        )
        if tracked.returncode == 0:
            raise ValueError(f"recorder path is source-controlled: {path}")
    return {
        "run_directory": run_directory,
        "provider_path": provider_path,
        "tracking_path": tracking_path,
    }


def _load_request(path: Path) -> dict[str, Any]:
    try:
        request = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid request JSON: {exc}") from exc
    required = {
        "run_id", "model_id", "run_directory", "panel_path",
        "panel_sha256", "environment_report",
        "environment_report_sha256", "environment_fingerprint",
        "resolved_lock", "resolved_lock_sha256", "qlib_gbdt_source",
        "qlib_gbdt_source_sha256", "feature_columns", "label_name",
        "segments", "model_construction", "fit_configuration",
        "model_configuration_fingerprint", "dataset_fingerprints",
        "evaluation_protocol_fingerprint", "thread_controls",
        "provider_path", "tracking_path", "tracking_uri",
        "experiment_name", "recorder_name", "expected_test_rows",
        "subprocess_environment_controls", "parent_environment",
        "subprocess_only_file_store_opt_in", "outputs",
    }
    missing = sorted(required.difference(request))
    if missing:
        raise ValueError(f"request is missing fields: {missing}")
    if request["experiment_name"] != EXPERIMENT_NAME:
        raise ValueError("experiment name differs from the frozen workflow")
    if request["recorder_name"] != request["run_id"]:
        raise ValueError("recorder name must equal the run ID")
    actual_threads = {
        name: os.environ.get(name) for name in request["thread_controls"]
    }
    if actual_threads != request["thread_controls"]:
        raise ValueError(
            f"numerical thread controls mismatch: {actual_threads}"
        )
    actual_controls = {
        name: os.environ.get(name)
        for name in request["subprocess_environment_controls"]
    }
    if actual_controls != request["subprocess_environment_controls"]:
        raise ValueError(
            f"subprocess environment controls mismatch: {actual_controls}"
        )
    if actual_controls.get("MLFLOW_ALLOW_FILE_STORE") != "true":
        raise ValueError("MLFLOW_ALLOW_FILE_STORE must equal exactly true")
    if request["parent_environment"].get(
        "MLFLOW_ALLOW_FILE_STORE"
    ) is not None:
        raise ValueError("file-store opt-in was inherited from the parent")
    if request["subprocess_only_file_store_opt_in"] is not True:
        raise ValueError("subprocess-only opt-in assertion is missing")
    remote = {
        name: os.environ[name]
        for name in FORBIDDEN_MLFLOW_ENVIRONMENT if name in os.environ
    }
    if remote:
        raise ValueError(
            f"remote MLflow environment is prohibited: {sorted(remote)}"
        )
    for field, hash_field in (
        ("panel_path", "panel_sha256"),
        ("environment_report", "environment_report_sha256"),
        ("resolved_lock", "resolved_lock_sha256"),
        ("qlib_gbdt_source", "qlib_gbdt_source_sha256"),
    ):
        source = Path(request[field])
        if not source.is_file() or _sha256(source) != request[hash_field]:
            raise ValueError(f"{field} fingerprint mismatch")
    paths = _validate_local_paths(request)
    outputs = {name: Path(value) for name, value in request["outputs"].items()}
    required_outputs = {
        "predictions", "runner_metadata", "training_history",
        "feature_importance_gain", "feature_importance_split",
        "model_dump", "recorder_audit",
    }
    if set(outputs) != required_outputs:
        raise ValueError("runner output contract mismatch")
    stale = sorted(str(item) for item in outputs.values() if item.exists())
    if stale:
        raise ValueError(f"refusing stale output artifacts: {stale}")
    if any(not _beneath(item.resolve(), paths["run_directory"])
           for item in outputs.values()):
        raise ValueError("every output must remain beneath the run directory")
    request["_paths"] = paths
    request["_outputs"] = outputs
    request["_actual_threads"] = actual_threads
    request["_actual_controls"] = actual_controls
    return request


def _load_panel(request: dict[str, Any]) -> pd.DataFrame:
    panel = pd.read_csv(
        request["panel_path"], header=[0, 1], index_col=[0, 1]
    )
    panel.index = pd.MultiIndex.from_arrays(
        [
            pd.to_datetime(
                panel.index.get_level_values(0), format="%Y-%m-%d"
            ),
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
        dates = panel.index.get_level_values("datetime")
        selected = panel.loc[
            (dates >= pd.Timestamp(boundaries["start"]))
            & (dates <= pd.Timestamp(boundaries["end"]))
        ]
        if len(selected) != expected_rows[name]:
            raise ValueError(
                f"frozen {name} row count mismatch: {len(selected)}"
            )
    return panel


def run(request_path: Path) -> int:
    request = _load_request(request_path)
    panel = _load_panel(request)
    paths = request["_paths"]
    outputs = request["_outputs"]
    paths["provider_path"].mkdir(parents=True, exist_ok=False)
    paths["tracking_path"].mkdir(parents=True, exist_ok=False)

    environment = json.loads(
        Path(request["environment_report"]).read_text(encoding="utf-8")
    )
    if (
        environment.get("status") != "verified"
        or environment.get("environment_fingerprint")
        != request["environment_fingerprint"]
    ):
        raise ValueError("Qlib environment report mismatch")

    import lightgbm
    import mlflow
    import qlib
    from qlib.contrib.model.gbdt import LGBModel
    from qlib.data.dataset import DatasetH
    from qlib.data.dataset.handler import DataHandlerLP
    from qlib.workflow import R

    versions = {
        "qlib": qlib.__version__,
        "lightgbm": lightgbm.__version__,
        "mlflow": mlflow.__version__,
        "numpy": np.__version__,
        "pandas": pd.__version__,
    }
    if versions["qlib"] != "0.9.7" or versions["lightgbm"] != "4.6.0":
        raise ValueError(f"unexpected dependency versions: {versions}")
    if f"{LGBModel.__module__}.{LGBModel.__name__}" != (
        "qlib.contrib.model.gbdt.LGBModel"
    ):
        raise ValueError("official Qlib LGBModel class identity mismatch")

    initialization = {
        "provider_uri": str(paths["provider_path"]),
        "dataset_cache": None,
        "expression_cache": None,
        "auto_mount": False,
        "exp_manager": {
            "class": "MLflowExpManager",
            "module_path": "qlib.workflow.expm",
            "kwargs": {
                "uri": request["tracking_uri"],
                "default_exp_name": EXPERIMENT_NAME,
            },
        },
    }
    qlib.init(**initialization)

    handler = DataHandlerLP.from_df(panel)
    dataset = DatasetH(
        handler=handler,
        segments={
            name: (values["start"], values["end"])
            for name, values in request["segments"].items()
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
    recorder = None
    with R.start(
        experiment_name=EXPERIMENT_NAME,
        recorder_name=request["run_id"],
        uri=request["tracking_uri"],
    ) as experiment:
        recorder = experiment.active_recorder
        model.fit(
            dataset,
            evals_result=history,
            verbose_eval=request["fit_configuration"]["verbose_eval"],
        )
    if recorder is None:
        raise RuntimeError("Qlib workflow did not expose an active recorder")

    predictions = model.predict(dataset, segment="test")
    if not isinstance(predictions, pd.Series):
        predictions = pd.Series(predictions)
    predictions = predictions.rename("score").sort_index()
    raw = predictions.reset_index()
    raw.columns = ["datetime", "instrument", "score"]
    raw["datetime"] = pd.to_datetime(raw["datetime"]).dt.strftime(
        "%Y-%m-%d"
    )
    raw = raw.sort_values(
        ["datetime", "instrument"], kind="mergesort"
    ).reset_index(drop=True)
    if len(raw) != request["expected_test_rows"]:
        raise RuntimeError(
            f"expected {request['expected_test_rows']} predictions; "
            f"got {len(raw)}"
        )
    if not np.isfinite(raw["score"].to_numpy(dtype=float)).all():
        raise RuntimeError("predictions contain nonfinite values")

    booster = model.model
    if booster is None:
        raise RuntimeError("official Qlib model did not expose its Booster")
    features = list(request["feature_columns"])
    gain = pd.DataFrame({
        "feature": features,
        "importance_gain": booster.feature_importance(
            importance_type="gain"
        ),
    })
    split = pd.DataFrame({
        "feature": features,
        "importance_split": booster.feature_importance(
            importance_type="split"
        ),
    })
    _csv(raw, outputs["predictions"])
    _csv(gain, outputs["feature_importance_gain"])
    _csv(split, outputs["feature_importance_split"])
    _json(history, outputs["training_history"])
    _json(booster.dump_model(), outputs["model_dump"])

    workflow_files = sorted(
        path.relative_to(paths["run_directory"]).as_posix()
        for path in paths["tracking_path"].rglob("*") if path.is_file()
    )
    recorder_audit = {
        "schema_version": "1.0",
        "implementation": (
            f"{type(R._provider.exp_manager).__module__}."
            f"{type(R._provider.exp_manager).__name__}"
        ),
        "recorder_implementation":
            f"{type(recorder).__module__}.{type(recorder).__name__}",
        "tracking_uri": request["tracking_uri"],
        "tracking_uri_local_file_only": True,
        "provider_directory": str(paths["provider_path"]),
        "tracking_directory": str(paths["tracking_path"]),
        "experiment_name": EXPERIMENT_NAME,
        "recorder_name": request["run_id"],
        "recorder_id": recorder.id,
        "recorder_final_status": recorder.status,
        "workflow_files": workflow_files,
        "mlflow_server_started": False,
        "provider_data_api_called": False,
        "network_uri_configured": False,
        "file_store_opt_in_observed":
            request["_actual_controls"]["MLFLOW_ALLOW_FILE_STORE"],
        "subprocess_environment_controls":
            request["_actual_controls"],
    }
    _json(recorder_audit, outputs["recorder_audit"])
    _json({
        "schema_version": "1.0",
        "run_id": request["run_id"],
        "model_id": request["model_id"],
        "status": "completed",
        "model_class": f"{type(model).__module__}.{type(model).__name__}",
        "versions": versions,
        "qlib_initialization": initialization,
        "recorder": recorder_audit,
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
        "thread_controls": request["_actual_threads"],
        "subprocess_environment_controls":
            request["_actual_controls"],
        "parent_mlflow_allow_file_store":
            request["parent_environment"]["MLFLOW_ALLOW_FILE_STORE"],
        "subprocess_only_file_store_opt_in": True,
        "best_iteration": int(booster.best_iteration),
        "tree_count": int(booster.num_trees()),
        "feature_names": features,
        "prediction_count": len(raw),
        "training_completed": True,
        "prediction_completed": True,
        "official_fit_used": True,
        "official_predict_used": True,
        "direct_lightgbm_fit_used": False,
        "provider_data_api_called": False,
        "network_used": False,
        "mlflow_server_started": False,
        "monkeypatch_used": False,
        "fallback_used": False,
        "pickle_written": False,
    }, outputs["runner_metadata"])
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args.request)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
