"""Standalone Python 3.12 runner for the official Qlib TRA implementation."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import sys
from typing import Any


EXPECTED_CLASS = "qlib.contrib.model.pytorch_tra.TRAModel"
EXPECTED_DATASET = "qlib.contrib.data.dataset.MTSDatasetH"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _write_json(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical(value))


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def _static_panel_audit(request: dict[str, Any]) -> dict[str, Any]:
    """Audit sequence boundaries without importing NumPy, Torch, or Qlib."""

    panel_path = Path(request["panel_path"])
    feature_columns = request["feature_columns"]
    observations: dict[str, list[str]] = {}
    ordered_keys: list[tuple[str, str]] = []
    with panel_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        group_header = next(reader)
        name_header = next(reader)
        index_header = next(reader)
        if (
            group_header[:2] != ["", ""]
            or name_header[2:-1] != feature_columns
            or name_header[-1] != request["label_name"]
            or index_header[:2] != ["datetime", "instrument"]
            or len(feature_columns) != 10
        ):
            raise RuntimeError("frozen panel header or feature width mismatch")
        previous: tuple[str, str] | None = None
        for row_number, row in enumerate(reader, start=4):
            if len(row) != len(feature_columns) + 3:
                raise RuntimeError(f"panel width mismatch at row {row_number}")
            date_value, instrument = row[0], row[1]
            _parse_date(date_value)
            if not instrument.strip():
                raise RuntimeError(f"blank instrument at row {row_number}")
            key = (date_value, instrument)
            if previous is not None and key <= previous:
                raise RuntimeError("panel keys are not strictly date/instrument ordered")
            previous = key
            ordered_keys.append(key)
            observations.setdefault(instrument, []).append(date_value)
            for raw in row[2:]:
                try:
                    value = float(raw)
                except ValueError as exc:
                    raise RuntimeError(
                        f"nonnumeric panel value at row {row_number}"
                    ) from exc
                if not (-float("inf") < value < float("inf")):
                    raise RuntimeError(
                        f"nonfinite panel value at row {row_number}"
                    )
    if len(ordered_keys) != request["expected_panel_rows"]:
        raise RuntimeError("frozen panel row count mismatch")
    instruments = sorted(observations)
    if len(instruments) != request["expected_instrument_count"]:
        raise RuntimeError("frozen instrument count mismatch")
    dates = sorted({date for date, _ in ordered_keys})
    if any(observations[name] != dates for name in instruments):
        raise RuntimeError("instruments do not share the frozen date grid")

    endpoints: list[dict[str, Any]] = []
    segments = request["segments"]
    for instrument in instruments:
        instrument_dates = observations[instrument]
        for index, endpoint in enumerate(instrument_dates):
            start_index = max(0, index - request["dataset_config"]["seq_len"] + 1)
            history = instrument_dates[start_index : index + 1]
            segment = next(
                (
                    name
                    for name, bounds in segments.items()
                    if bounds["start"] <= endpoint <= bounds["end"]
                ),
                None,
            )
            endpoints.append({
                "instrument": instrument,
                "endpoint": endpoint,
                "earliest_feature_date": history[0],
                "latest_feature_date": history[-1],
                "observed_steps": len(history),
                "left_padding_steps":
                    request["dataset_config"]["seq_len"] - len(history),
                "label_horizon": request["dataset_config"]["horizon"],
                "segment": segment,
            })
    fingerprint = hashlib.sha256(_canonical(endpoints)).hexdigest()
    return {
        "schema_version": "1.0",
        "status": "passed",
        "stage": "pre_import_independent",
        "panel_rows": len(ordered_keys),
        "instrument_count": len(instruments),
        "date_count": len(dates),
        "feature_width": len(feature_columns),
        "label_horizon": request["dataset_config"]["horizon"],
        "ordered_key_sha256": hashlib.sha256(
            _canonical(ordered_keys)
        ).hexdigest(),
        "sequence_boundary_fingerprint": fingerprint,
        "endpoints": endpoints,
        "future_feature_use": False,
        "cross_instrument_mixing": False,
    }


def _preflight(request_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    request = _read_json(request_path)
    required = request["subprocess_environment_controls"]
    observed = {name: os.environ.get(name) for name in required}
    if observed != required:
        raise RuntimeError(f"deterministic process controls mismatch: {observed}")
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
        ("labels_path", "labels_sha256"),
        ("environment_report", "environment_report_sha256"),
        ("resolved_lock", "resolved_lock_sha256"),
        ("tra_source", "tra_source_sha256"),
        ("dataset_source", "dataset_source_sha256"),
    ):
        path = Path(request[key])
        if not path.is_file() or _sha256(path) != request[hash_key]:
            raise RuntimeError(f"{key} hash mismatch")
    stale = [
        str(path)
        for path in map(Path, request["outputs"].values())
        if path.exists()
    ]
    if stale:
        raise RuntimeError(f"refusing stale output artifacts: {stale}")
    audit = _static_panel_audit(request)
    return request, audit


def _actual_dataset_audit(
    dataset: Any,
    independent: dict[str, Any],
    request: dict[str, Any],
    torch: Any,
) -> dict[str, Any]:
    expected = {
        (item["instrument"], item["endpoint"]): item
        for item in independent["endpoints"]
        if item["segment"] is not None
    }
    actual_keys: list[tuple[str, str]] = []
    segment_rows: dict[str, int] = {}
    segment_batches: dict[str, int] = {}
    for segment_name in ("train", "valid", "test"):
        view = dataset.prepare(segment_name)
        view.eval()
        rows = 0
        batches = 0
        for batch in view:
            batches += 1
            data = batch["data"]
            state = batch["state"]
            if tuple(data.shape[1:]) != (60, 10):
                raise RuntimeError(
                    f"official {segment_name} data shape mismatch: {tuple(data.shape)}"
                )
            if tuple(state.shape[1:]) != (59, 3):
                raise RuntimeError(
                    f"official {segment_name} state shape mismatch: {tuple(state.shape)}"
                )
            if not torch.isfinite(data).all() or not torch.isfinite(state).all():
                raise RuntimeError("official dataset emitted nonfinite tensors")
            restored = view.restore_index(batch["index"])
            for instrument, timestamp in restored.tolist():
                key = (str(instrument), timestamp.strftime("%Y-%m-%d"))
                reference = expected.get(key)
                if reference is None or reference["segment"] != segment_name:
                    raise RuntimeError(
                        f"official dataset key disagrees with audit: {key}"
                    )
                actual_keys.append(key)
            rows += len(restored)
        segment_rows[segment_name] = rows
        segment_batches[segment_name] = batches
    expected_keys = sorted(expected)
    if sorted(actual_keys) != expected_keys or len(actual_keys) != len(set(actual_keys)):
        raise RuntimeError("official dataset keys disagree with independent audit")
    expected_counts = request["segment_row_counts"]
    if segment_rows != expected_counts:
        raise RuntimeError(
            f"official segment counts mismatch: {segment_rows} != {expected_counts}"
        )
    return {
        "schema_version": "1.0",
        "status": "passed",
        "stage": "post_import_official_dataset",
        "dataset_class": EXPECTED_DATASET,
        "feature_tensor_suffix": [60, 10],
        "memory_state_tensor_suffix": [59, 3],
        "segment_rows": segment_rows,
        "segment_daily_batches": segment_batches,
        "actual_key_sha256": hashlib.sha256(
            _canonical(sorted(actual_keys))
        ).hexdigest(),
        "independent_sequence_boundary_fingerprint":
            independent["sequence_boundary_fingerprint"],
        "official_matches_independent": True,
        "evaluation_mode": {
            "batch_size": "daily_sampling",
            "shuffle": False,
            "drop_last": False,
        },
    }


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.buffer = io.StringIO()
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        self.buffer.write(self.format(record) + "\n")


def _phase_evidence(log_text: str, history: dict[str, list[Any]]) -> dict[str, Any]:
    best_matches = list(
        re.finditer(
            r"best score:\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*@\s*(\d+)",
            log_text,
        )
    )
    if len(best_matches) != 2:
        raise RuntimeError("official logs do not contain two phase best scores")
    first_end, second_end = best_matches[0].end(), best_matches[1].end()
    pretrain_count = log_text[:first_end].count("valid metrics:")
    routed_count = log_text[first_end:second_end].count("valid metrics:")
    valid_history = history.get("valid", [])
    if (
        pretrain_count <= 0
        or routed_count <= 0
        or pretrain_count + routed_count != len(valid_history)
    ):
        raise RuntimeError("official phase lengths disagree with evals_result")
    phases = []
    offset = 0
    for name, match, count in (
        ("pretraining", best_matches[0], pretrain_count),
        ("routed_training", best_matches[1], routed_count),
    ):
        metrics = valid_history[offset : offset + count]
        scores = [float(item["IC"]) for item in metrics]
        best_score = float(match.group(1))
        best_epoch = int(match.group(2))
        if (
            not scores
            or not all(-float("inf") < value < float("inf") for value in scores)
            or abs(scores[best_epoch] - best_score) > 5e-6
            or best_epoch != max(range(len(scores)), key=scores.__getitem__)
        ):
            raise RuntimeError(f"{name} best-score evidence mismatch")
        phase_text = (
            log_text[:first_end] if name == "pretraining"
            else log_text[first_end:second_end]
        )
        stop = re.findall(r"early stop @\s*(\d+)", phase_text)
        phases.append({
            "name": name,
            "history_offset": offset,
            "history_length": count,
            "best_score": best_score,
            "best_epoch": best_epoch,
            "stopping_epoch": int(stop[-1]) if stop else count - 1,
            "official_best_score_log":
                f"best score: {match.group(1)} @ {match.group(2)}",
        })
        offset += count
    return {
        "schema_version": "1.0",
        "pretrain_enabled": True,
        "phases": phases,
        "final_selected_phase": "routed_training",
        "final_selected_epoch": phases[1]["best_epoch"],
        "final_selected_score": phases[1]["best_score"],
    }


def _tensor_manifest(module: Any, torch: Any) -> dict[str, Any]:
    tensors = []
    for name, value in sorted(module.state_dict().items()):
        tensor = value.detach().cpu().contiguous()
        raw = tensor.numpy().tobytes(order="C")
        tensors.append({
            "name": name,
            "dtype": str(tensor.dtype),
            "shape": list(tensor.shape),
            "element_count": tensor.numel(),
            "finite": bool(torch.isfinite(tensor).all()),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    return {
        "schema_version": "1.0",
        "tensor_count": len(tensors),
        "all_finite": all(item["finite"] for item in tensors),
        "tensors": tensors,
        "state_fingerprint": hashlib.sha256(_canonical(tensors)).hexdigest(),
    }


def run(request_path: Path) -> int:
    request, independent_audit = _preflight(request_path)

    import numpy as np
    import pandas as pd
    import qlib
    import torch
    from qlib.contrib.data.dataset import MTSDatasetH
    from qlib.contrib.model.pytorch_tra import TRAModel
    from qlib.data.dataset.handler import DataHandlerLP

    if torch.__version__ != "2.4.1+cpu" or qlib.__version__ != "0.9.7":
        raise RuntimeError(
            f"unexpected Qlib/Torch versions: {qlib.__version__}, {torch.__version__}"
        )
    if (
        f"{TRAModel.__module__}.{TRAModel.__name__}" != EXPECTED_CLASS
        or f"{MTSDatasetH.__module__}.{MTSDatasetH.__name__}" != EXPECTED_DATASET
    ):
        raise RuntimeError("official class identity mismatch")

    np.random.seed(20260730)
    torch.manual_seed(20260730)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    if not torch.are_deterministic_algorithms_enabled():
        raise RuntimeError("Torch deterministic algorithms are not enabled")

    panel = pd.read_csv(
        request["panel_path"], header=[0, 1], index_col=[0, 1],
        float_precision="round_trip",
    )
    panel.index = pd.MultiIndex.from_arrays(
        [
            pd.to_datetime(panel.index.get_level_values(0), format="%Y-%m-%d"),
            panel.index.get_level_values(1).astype(str),
        ],
        names=["datetime", "instrument"],
    )
    panel = panel.astype(float).sort_index()
    columns = (
        [("feature", name) for name in request["feature_columns"]]
        + [("label", request["label_name"])]
    )
    if list(panel.columns) != columns:
        raise RuntimeError("official panel columns differ from frozen order")
    dataset = MTSDatasetH(
        handler=DataHandlerLP.from_df(panel),
        segments={
            name: (bounds["start"], bounds["end"])
            for name, bounds in request["segments"].items()
        },
        seq_len=60,
        horizon=1,
        input_size=None,
        num_states=3,
        batch_size=1024,
        n_samples=None,
        memory_mode="sample",
        shuffle=True,
        drop_last=True,
    )
    actual_audit = _actual_dataset_audit(
        dataset, independent_audit, request, torch
    )

    np.random.seed(20260730)
    torch.manual_seed(20260730)
    model = TRAModel(
        model_config=request["model_config"],
        tra_config=request["tra_config"],
        **request["model_parameters"],
    )
    capture = _Capture()
    model.logger.addHandler(capture)
    history: dict[str, list[Any]] = {}
    fit_return = model.fit(dataset, evals_result=history)
    model.logger.removeHandler(capture)
    if fit_return is not None:
        raise RuntimeError("official public fit unexpectedly returned a value")
    phase = _phase_evidence(capture.buffer.getvalue(), history)
    if not (-float("inf") < phase["final_selected_score"] < float("inf")):
        raise RuntimeError("routed selected validation score is nonfinite")

    backbone = _tensor_manifest(model.model, torch)
    tra = _tensor_manifest(model.tra, torch)
    if not backbone["all_finite"] or not tra["all_finite"]:
        raise RuntimeError("fitted model contains nonfinite tensors")

    predictions = model.predict(dataset, segment="test")
    required_prediction_columns = {
        "score", "label", "score_0", "score_1", "score_2"
    }
    if set(predictions.columns) != required_prediction_columns:
        raise RuntimeError(
            f"unexpected public prediction columns: {list(predictions.columns)}"
        )
    predictions = predictions.sort_index()
    raw = predictions.reset_index()
    raw["datetime"] = pd.to_datetime(raw["datetime"]).dt.strftime("%Y-%m-%d")
    raw = raw.sort_values(
        ["datetime", "instrument"], kind="mergesort"
    ).reset_index(drop=True)
    if (
        len(raw) != 1200
        or raw.duplicated(["datetime", "instrument"]).any()
        or not np.isfinite(
            raw[["score", "score_0", "score_1", "score_2"]].to_numpy(float)
        ).all()
    ):
        raise RuntimeError("public predictions fail count/key/finite checks")

    outputs = {name: Path(path) for name, path in request["outputs"].items()}
    for path in outputs.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    raw[["datetime", "instrument", "score"]].to_csv(
        outputs["predictions"], index=False, encoding="utf-8",
        lineterminator="\n", float_format="%.17g",
    )
    raw[[
        "datetime", "instrument", "score_0", "score_1", "score_2"
    ]].to_csv(
        outputs["state_scores"], index=False, encoding="utf-8",
        lineterminator="\n", float_format="%.17g",
    )
    raw[["datetime", "instrument", "label"]].to_csv(
        outputs["audit_labels"], index=False, encoding="utf-8",
        lineterminator="\n", float_format="%.17g",
    )
    _write_json(independent_audit, outputs["independent_audit"])
    _write_json(actual_audit, outputs["official_audit"])
    _write_json(history, outputs["training_history"])
    _write_json(phase, outputs["phase_summary"])
    _write_json(backbone, outputs["backbone_state"])
    _write_json(tra, outputs["tra_state"])
    _write_json({
        "schema_version": "1.0",
        "backbone_state_fingerprint": backbone["state_fingerprint"],
        "tra_state_fingerprint": tra["state_fingerprint"],
        "combined_state_fingerprint": hashlib.sha256(
            _canonical({
                "backbone": backbone["state_fingerprint"],
                "tra": tra["state_fingerprint"],
            })
        ).hexdigest(),
    }, outputs["combined_state"])
    _write_json({
        "schema_version": "1.0",
        "status": "completed",
        "run_id": request["run_id"],
        "model_id": request["model_id"],
        "model_class": EXPECTED_CLASS,
        "dataset_class": EXPECTED_DATASET,
        "qlib_version": qlib.__version__,
        "torch_version": torch.__version__,
        "device": "cpu",
        "cuda_available": torch.cuda.is_available(),
        "deterministic_algorithms_enabled":
            torch.are_deterministic_algorithms_enabled(),
        "subprocess_environment_controls":
            request["subprocess_environment_controls"],
        "model_config": request["model_config"],
        "tra_config": request["tra_config"],
        "model_parameters": request["model_parameters"],
        "dataset_config": request["dataset_config"],
        "model_input_size": 10,
        "dataset_input_size": None,
        "prediction_count": len(raw),
        "state_score_columns": ["score_0", "score_1", "score_2"],
        "fit_call_count": 1,
        "predict_call_count": 1,
        "fit_returned_normally": True,
        "fit_public_return": None,
        "final_selected_score": phase["final_selected_score"],
        "final_selected_epoch": phase["final_selected_epoch"],
        "logdir": None,
        "pickle_written": False,
        "torch_save_used": False,
        "provider_initialized": False,
        "workflow_initialized": False,
        "network_used": False,
        "upstream_final_test_label_access": True,
        "test_access_after_checkpoint_selection": True,
        "test_used_for_tuning": False,
        "current_loss_excluded_from_routing_state": True,
        "historical_realized_loss_memory_permitted": True,
        "model_parameter_count": sum(
            value.numel() for value in model.model.parameters()
        ),
        "tra_parameter_count": sum(
            value.numel() for value in model.tra.parameters()
        ),
        "model_configuration_fingerprint":
            request["model_configuration_fingerprint"],
        "evaluation_protocol_fingerprint":
            request["evaluation_protocol_fingerprint"],
        "environment_fingerprint": request["environment_fingerprint"],
        "sequence_boundary_fingerprint":
            independent_audit["sequence_boundary_fingerprint"],
        "tra_source_sha256": request["tra_source_sha256"],
        "dataset_source_sha256": request["dataset_source_sha256"],
    }, outputs["metadata"])
    outputs["official_log"].write_text(
        capture.buffer.getvalue(), encoding="utf-8", newline="\n"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run official Qlib TRA against one verified request."
    )
    parser.add_argument("request", type=Path)
    args = parser.parse_args(argv)
    try:
        return run(args.request)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
