"""Common, model-neutral research data and execution contracts.

This module deliberately contains no Qlib, LightGBM, Torch, or provider imports.
Every feature carries its own evidence clock; a single row-level date is not
enough to establish point-in-time safety for heterogeneous model inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from stock_research.errors import Diagnostic, ResearchValidationError
from stock_research.fingerprints import fingerprint_dataframe


FEATURE_EVIDENCE_COLUMNS = (
    "as_of_date", "ticker", "sector", "feature", "value", "available_at",
    "availability_status", "source_id", "evidence_fingerprint",
)
DATASET_MODES = {"current", "historical_train", "historical_evaluation"}
AVAILABILITY_STATUSES = {"pit_verified", "current_only"}
MODEL_STATUSES = {
    "specified", "adapter_ready", "synthetic_reproduced", "blocked", "verified"
}


def _fail(rule: str, message: str, row: int | None = None) -> None:
    raise ResearchValidationError(Diagnostic(rule, message, row))


@dataclass(frozen=True, slots=True)
class FeatureRequirement:
    name: str
    max_age_days: int | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("feature name must not be blank")
        if self.max_age_days is not None and (
            isinstance(self.max_age_days, bool) or self.max_age_days < 0
        ):
            raise ValueError("max_age_days must be a nonnegative integer")


@dataclass(frozen=True, slots=True)
class ModelSpecification:
    model_id: str
    implementation_kind: str
    required_features: tuple[FeatureRequirement, ...]
    optional_features: tuple[str, ...] = ()
    training_required: bool = False
    supported_frequencies: tuple[str, ...] = ("daily",)
    status: str = "specified"
    upstream_reference: str = ""

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ValueError("model_id must not be blank")
        names = [item.name for item in self.required_features]
        if not names or len(names) != len(set(names)):
            raise ValueError("required feature names must be nonempty and unique")
        if set(names) & set(self.optional_features):
            raise ValueError("required and optional features overlap")
        if self.status not in MODEL_STATUSES:
            raise ValueError(f"invalid model status: {self.status}")


@dataclass(frozen=True, slots=True)
class ModelDataset:
    model_id: str
    mode: str
    features: pd.DataFrame
    eligibility: pd.DataFrame
    evidence: pd.DataFrame
    feature_fingerprint: str


def validate_feature_evidence(
    data: pd.DataFrame,
    *,
    mode: str,
    cutoff_time: time = time(15, 30),
    timezone_name: str = "Asia/Kolkata",
) -> pd.DataFrame:
    """Validate per-feature clocks and canonicalize a long evidence panel."""

    if mode not in DATASET_MODES:
        _fail("dataset_mode", f"unsupported dataset mode: {mode}")
    missing = sorted(set(FEATURE_EVIDENCE_COLUMNS) - set(data.columns))
    if missing:
        _fail("feature_evidence_columns", f"missing columns: {missing}")
    if data.empty:
        _fail("empty_dataset", "feature evidence must not be empty")
    frame = data.loc[:, FEATURE_EVIDENCE_COLUMNS].copy()
    for column in ("ticker", "sector", "feature", "availability_status", "source_id", "evidence_fingerprint"):
        invalid = frame[column].isna() | frame[column].astype(str).str.strip().eq("")
        if invalid.any():
            _fail("blank_evidence_identifier", f"{column} must not be blank", int(np.flatnonzero(invalid)[0]))
        frame[column] = frame[column].astype(str).str.strip()
    if frame.duplicated(["as_of_date", "ticker", "feature"]).any():
        _fail("duplicate_feature_evidence", "duplicate as_of_date/ticker/feature")
    statuses = set(frame["availability_status"])
    if not statuses <= AVAILABILITY_STATUSES:
        _fail("availability_status", f"unknown statuses: {sorted(statuses - AVAILABILITY_STATUSES)}")
    if mode != "current" and "current_only" in statuses:
        _fail("current_only_historical_leakage", "current-only evidence cannot enter historical datasets")
    date_text = frame["as_of_date"]
    exact = date_text.map(lambda value: isinstance(value, str)) & date_text.astype(str).str.fullmatch(r"\d{4}-\d{2}-\d{2}")
    dates = pd.to_datetime(date_text, format="%Y-%m-%d", errors="coerce")
    if not (exact & dates.notna()).all():
        _fail("malformed_date", "as_of_date must be ISO YYYY-MM-DD")
    available = pd.to_datetime(frame["available_at"], errors="coerce", utc=True)
    if available.isna().any():
        _fail("availability_timestamp", "available_at must be an explicit timezone-aware timestamp")
    # pandas accepts naive strings with utc=True, so reject them independently.
    aware = frame["available_at"].astype(str).str.contains(r"(?:Z|[+-]\d{2}:\d{2})$", regex=True)
    if not aware.all():
        _fail("availability_timestamp", "available_at must include a timezone offset")
    zone = ZoneInfo(timezone_name)
    decisions = pd.Series([
        pd.Timestamp.combine(value.date(), cutoff_time).tz_localize(zone).tz_convert("UTC")
        for value in dates
    ], index=frame.index)
    future = available > decisions
    if future.any():
        _fail("future_feature_availability", "feature became public after the decision cutoff", int(np.flatnonzero(future)[0]))
    numeric = pd.to_numeric(frame["value"], errors="coerce")
    if numeric.isna().any() or not np.isfinite(numeric.to_numpy(dtype=float)).all():
        _fail("nonfinite_feature", "feature values must be finite numeric")
    frame["value"] = numeric.astype(float)
    frame["available_at"] = available.dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return frame.sort_values(["as_of_date", "ticker", "feature"], kind="mergesort").reset_index(drop=True)


def build_model_dataset(
    evidence: pd.DataFrame,
    specification: ModelSpecification,
    *,
    mode: str,
    frequency: str = "daily",
) -> ModelDataset:
    """Create a deterministic complete-case matrix for one model specification."""

    if frequency not in specification.supported_frequencies:
        _fail("model_frequency", f"{specification.model_id} does not support {frequency}")
    canonical = validate_feature_evidence(evidence, mode=mode)
    required = [item.name for item in specification.required_features]
    selected = canonical.loc[canonical["feature"].isin(required)].copy()
    for requirement in specification.required_features:
        if requirement.max_age_days is None:
            continue
        mask = selected["feature"].eq(requirement.name)
        age = (
            pd.to_datetime(selected.loc[mask, "as_of_date"])
            - pd.to_datetime(selected.loc[mask, "available_at"], utc=True).dt.tz_localize(None).dt.normalize()
        ).dt.days
        selected = selected.drop(index=age.index[age > requirement.max_age_days])
    keys = canonical[["as_of_date", "ticker", "sector"]].drop_duplicates()
    if keys.duplicated(["as_of_date", "ticker"]).any():
        _fail("conflicting_sector", "same-date ticker has conflicting sectors")
    present = selected.pivot_table(
        index=["as_of_date", "ticker", "sector"], columns="feature", values="value", aggfunc="first"
    ).reset_index()
    present.columns.name = None
    for name in required:
        if name not in present:
            present[name] = np.nan
    merged = keys.merge(present, on=["as_of_date", "ticker", "sector"], how="left", validate="one_to_one")
    missing_rows = []
    for row in merged.itertuples(index=False):
        absent = [name for name in required if pd.isna(getattr(row, name, np.nan))]
        missing_rows.append({
            "as_of_date": row.as_of_date, "ticker": row.ticker,
            "eligible": not absent,
            "reason": "ELIGIBLE" if not absent else "MISSING_REQUIRED_FEATURES",
            "missing_features": ";".join(absent),
        })
    eligibility = pd.DataFrame(missing_rows).sort_values(["as_of_date", "ticker"], kind="mergesort").reset_index(drop=True)
    eligible_keys = eligibility.loc[eligibility["eligible"], ["as_of_date", "ticker"]]
    features = merged.merge(eligible_keys, on=["as_of_date", "ticker"], how="inner", validate="one_to_one")
    features = features[["as_of_date", "ticker", "sector", *required]].sort_values(
        ["as_of_date", "ticker"], kind="mergesort"
    ).reset_index(drop=True)
    return ModelDataset(
        specification.model_id, mode, features, eligibility, canonical,
        fingerprint_dataframe(canonical),
    )


def specifications_from_registry(entries: Iterable[Mapping[str, Any]]) -> tuple[ModelSpecification, ...]:
    return tuple(ModelSpecification(
        model_id=str(item["id"]), implementation_kind=str(item["implementation_kind"]),
        required_features=tuple(FeatureRequirement(**feature) for feature in item["required_features"]),
        optional_features=tuple(item.get("optional_features", ())),
        training_required=bool(item.get("training_required", False)),
        supported_frequencies=tuple(item.get("supported_frequencies", ("daily",))),
        status=str(item["status"]), upstream_reference=str(item.get("upstream_reference", "")),
    ) for item in entries)
