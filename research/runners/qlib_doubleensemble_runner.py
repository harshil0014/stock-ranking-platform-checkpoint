"""Standalone verified Python 3.12 runner for official Qlib DoubleEnsemble."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(value: Any, path: Path) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False,
                   allow_nan=False) + "\n",
        encoding="utf-8", newline="\n",
    )


def _preflight(request_path: Path) -> dict[str, Any]:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    required = request["subprocess_environment_controls"]
    actual = {name: os.environ.get(name) for name in required}
    if actual != required:
        raise RuntimeError(f"deterministic process controls mismatch: {actual}")
    prohibited = [
        "MLFLOW_ALLOW_FILE_STORE", "MLFLOW_TRACKING_URI",
        "MLFLOW_REGISTRY_URI", "MLFLOW_TRACKING_USERNAME",
        "MLFLOW_TRACKING_PASSWORD", "MLFLOW_TRACKING_TOKEN",
        "DATABRICKS_HOST", "DATABRICKS_TOKEN", "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
        "AZURE_STORAGE_CONNECTION_STRING", "GOOGLE_APPLICATION_CREDENTIALS",
    ]
    present = sorted(name for name in prohibited if os.environ.get(name))
    if present:
        raise RuntimeError(f"prohibited inherited environment variables: {present}")
    for key, hash_key in (
        ("panel_path", "panel_sha256"),
        ("environment_report", "environment_report_sha256"),
        ("resolved_lock", "resolved_lock_sha256"),
        ("doubleensemble_source", "doubleensemble_source_sha256"),
    ):
        path = Path(request[key])
        if not path.is_file() or _sha256(path) != request[hash_key]:
            raise RuntimeError(f"{key} hash mismatch")
    outputs = {name: Path(path) for name, path in request["outputs"].items()}
    stale = [str(path) for path in outputs.values() if path.exists()]
    if stale:
        raise RuntimeError(f"refusing stale output artifacts: {stale}")
    return request


def run(request_path: Path) -> int:
    request = _preflight(request_path)

    import lightgbm
    import numpy as np
    import pandas as pd
    import qlib
    from qlib.contrib.model.double_ensemble import DEnsembleModel
    from qlib.data.dataset import DatasetH
    from qlib.data.dataset.handler import DataHandlerLP

    environment = json.loads(
        Path(request["environment_report"]).read_text(encoding="utf-8")
    )
    versions = {
        "qlib": qlib.__version__, "lightgbm": lightgbm.__version__,
        "numpy": np.__version__, "pandas": pd.__version__,
    }
    expected = {
        name: environment["import_results"][name]["version"]
        for name in versions
    }
    if versions != expected or qlib.__version__ != "0.9.7":
        raise RuntimeError(f"dependency versions differ: {versions}")
    if Path(sys.executable).resolve() != Path(environment["interpreter"]).resolve():
        raise RuntimeError("runner interpreter differs from verified environment")
    if (
        f"{DEnsembleModel.__module__}.{DEnsembleModel.__name__}"
        != "qlib.contrib.model.double_ensemble.DEnsembleModel"
    ):
        raise RuntimeError("unexpected upstream DoubleEnsemble class")

    panel = pd.read_csv(
        request["panel_path"], header=[0, 1], index_col=[0, 1],
        float_precision="round_trip",
    )
    panel.index = pd.MultiIndex.from_arrays(
        [
            pd.to_datetime(panel.index.get_level_values(0), format="%Y-%m-%d"),
            panel.index.get_level_values(1).astype(str),
        ], names=["datetime", "instrument"],
    )
    panel = panel.astype(float).sort_index()
    if panel.isna().any().any() or not np.isfinite(panel.to_numpy()).all():
        raise RuntimeError("panel contains missing or nonfinite values")
    expected_columns = (
        [("feature", name) for name in request["feature_columns"]]
        + [("label", request["label_name"])]
    )
    if list(panel.columns) != expected_columns:
        raise RuntimeError("panel columns differ from frozen feature order")
    segments = request["segments"]
    dataset = DatasetH(
        handler=DataHandlerLP.from_df(panel),
        segments={
            name: (value["start"], value["end"])
            for name, value in segments.items()
        },
    )

    np.random.seed(request["numpy_seed"])
    model = DEnsembleModel(**request["model_parameters"])
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
        raise RuntimeError("unexpected prediction count")
    if not np.isfinite(raw["score"].to_numpy(float)).all():
        raise RuntimeError("predictions contain nonfinite values")
    if len(model.ensemble) != 3 or len(model.sub_features) != 3:
        raise RuntimeError("official model did not expose three submodels")

    outputs = {name: Path(path) for name, path in request["outputs"].items()}
    for path in outputs.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    raw.to_csv(
        outputs["predictions"], index=False, encoding="utf-8",
        lineterminator="\n", float_format="%.17g",
    )
    feature_order = request["feature_columns"]
    selected: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    per_gain: list[dict[str, Any]] = []
    per_split: list[dict[str, Any]] = []
    normalized_hashes: list[str] = []
    for index, (booster, features) in enumerate(
        zip(model.ensemble, model.sub_features), start=1
    ):
        names = [str(name) for name in features]
        selected.append({"submodel": index, "features": names})
        summary.append({
            "submodel": index, "tree_count": int(booster.num_trees()),
            "selected_feature_count": len(names),
        })
        gain_map = dict(zip(
            booster.feature_name(),
            booster.feature_importance(importance_type="gain").astype(float),
        ))
        split_map = dict(zip(
            booster.feature_name(),
            booster.feature_importance(importance_type="split").astype(float),
        ))
        for feature in feature_order:
            per_gain.append({
                "submodel": index, "feature": feature,
                "importance_gain": float(gain_map.get(feature, 0.0)),
            })
            per_split.append({
                "submodel": index, "feature": feature,
                "importance_split": float(split_map.get(feature, 0.0)),
            })
        dump_path = outputs[f"model_dump_{index}"]
        _json(booster.dump_model(), dump_path)
        normalized_hashes.append(_sha256(dump_path))

    combined_gain = model.get_feature_importance(
        importance_type="gain"
    ).reindex(feature_order, fill_value=0.0)
    combined_split = model.get_feature_importance(
        importance_type="split"
    ).reindex(feature_order, fill_value=0.0)
    pd.DataFrame({
        "feature": feature_order,
        "importance_gain": combined_gain.to_numpy(float),
    }).to_csv(
        outputs["combined_gain"], index=False, encoding="utf-8",
        lineterminator="\n", float_format="%.17g",
    )
    pd.DataFrame({
        "feature": feature_order,
        "importance_split": combined_split.to_numpy(float),
    }).to_csv(
        outputs["combined_split"], index=False, encoding="utf-8",
        lineterminator="\n", float_format="%.17g",
    )
    pd.DataFrame(per_gain).to_csv(
        outputs["per_gain"], index=False, encoding="utf-8",
        lineterminator="\n", float_format="%.17g",
    )
    pd.DataFrame(per_split).to_csv(
        outputs["per_split"], index=False, encoding="utf-8",
        lineterminator="\n", float_format="%.17g",
    )
    _json(summary, outputs["submodel_summary"])
    _json(selected, outputs["selected_features"])
    _json({
        "schema_version": "1.0",
        "status": "completed",
        "run_id": request["run_id"],
        "model_id": request["model_id"],
        "model_class": f"{type(model).__module__}.{type(model).__name__}",
        "qlib_version": qlib.__version__,
        "dependency_versions": versions,
        "source_sha256": request["doubleensemble_source_sha256"],
        "model_parameters": request["model_parameters"],
        "model_configuration_fingerprint":
            request["model_configuration_fingerprint"],
        "dataset_fingerprints": request["dataset_fingerprints"],
        "evaluation_protocol_fingerprint":
            request["evaluation_protocol_fingerprint"],
        "subprocess_environment_controls":
            request["subprocess_environment_controls"],
        "numpy_seed_policy": f"np.random.seed({request['numpy_seed']})",
        "feature_order": feature_order,
        "training_segments": ["train", "valid"],
        "prediction_segment": "test",
        "validation_use": "official_internal_validation_no_early_stopping",
        "prediction_count": len(raw),
        "submodel_count": len(model.ensemble),
        "tree_counts": [item["tree_count"] for item in summary],
        "normalized_model_dump_sha256": normalized_hashes,
        "provider_initialized": False,
        "workflow_initialized": False,
        "network_used": False,
        "pickle_written": False,
        "direct_lightgbm_fit_by_runner": False,
    }, outputs["metadata"])
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: qlib_doubleensemble_runner.py REQUEST.json", file=sys.stderr)
        return 2
    try:
        return run(Path(sys.argv[1]))
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
