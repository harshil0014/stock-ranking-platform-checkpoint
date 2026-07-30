"""Deterministic SHA-256 fingerprints for research provenance."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


def _json_value(value: Any) -> Any:
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_value(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return value.as_posix()
    if hasattr(value, "item"):
        return value.item()
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _json_value(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )


def fingerprint_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fingerprint_file(path: str | Path) -> str:
    file_path = Path(path)
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint_config(configuration: Any) -> str:
    return fingerprint_bytes(canonical_json(configuration).encode("utf-8"))


def fingerprint_dataframe(data: pd.DataFrame) -> str:
    """Fingerprint exact canonical content, including column order and dtypes."""

    payload = {
        "columns": list(data.columns),
        "dtypes": [str(dtype) for dtype in data.dtypes],
        "records": [
            [_json_value(value) for value in row]
            for row in data.itertuples(index=False, name=None)
        ],
    }
    return fingerprint_config(payload)


def fingerprint_environment(environment: Mapping[str, Any]) -> str:
    filtered = {
        key: value for key, value in environment.items()
        if key != "environment_fingerprint"
    }
    return fingerprint_config(filtered)


def model_configuration_fingerprint(configuration: Mapping[str, Any]) -> str:
    return fingerprint_config(configuration)


def evaluation_protocol_fingerprint(protocol: Mapping[str, Any] | Any) -> str:
    payload = protocol.as_dict() if hasattr(protocol, "as_dict") else protocol
    return fingerprint_config(payload)
