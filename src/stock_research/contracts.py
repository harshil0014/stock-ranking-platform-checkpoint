"""Point-in-time research data contracts and split leakage controls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from stock_research.errors import Diagnostic, ResearchValidationError


FEATURE_ID_COLUMNS = (
    "as_of_date", "ticker", "sector", "max_feature_available_date"
)
LABEL_COLUMNS = (
    "as_of_date", "ticker", "label_end_date", "forward_return", "label_name"
)
SIGNAL_COLUMNS = ("as_of_date", "ticker", "score", "model_id", "run_id")
OPTIONAL_SIGNAL_COLUMNS = ("sector", "rank", "method_version")
FORBIDDEN_FEATURE_COLUMNS = {
    "forward_return", "label", "label_end_date", "label_name", "target"
}


def _raise(rule_id: str, message: str, row: int | None = None,
           key: dict | None = None) -> None:
    raise ResearchValidationError(Diagnostic(rule_id, message, row, key))


def _columns(data: pd.DataFrame, required: Iterable[str], kind: str) -> None:
    if data.columns.has_duplicates:
        duplicates = sorted(set(data.columns[data.columns.duplicated()]))
        _raise("duplicate_columns", f"{kind} has duplicate columns: {duplicates}")
    missing = sorted(set(required).difference(data.columns))
    if missing:
        _raise("missing_columns", f"{kind} missing required columns: {missing}")


def _identifiers(data: pd.DataFrame, columns: Iterable[str]) -> None:
    for column in columns:
        invalid = data[column].isna() | data[column].astype(str).str.strip().eq("")
        if invalid.any():
            row = int(np.flatnonzero(invalid.to_numpy())[0])
            _raise("blank_identifier", f"{column} must not be blank", row)


def _iso_dates(data: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    result = data.copy(deep=True)
    for column in columns:
        source = result[column]
        if not source.map(lambda value: isinstance(value, str)).all():
            row = int(np.flatnonzero(
                ~source.map(lambda value: isinstance(value, str)).to_numpy()
            )[0])
            _raise(
                "mixed_date_representation",
                f"{column} must contain ISO YYYY-MM-DD strings only",
                row,
            )
        exact = source.str.fullmatch(r"\d{4}-\d{2}-\d{2}", na=False)
        parsed = pd.to_datetime(source, format="%Y-%m-%d", errors="coerce")
        invalid = ~exact | parsed.isna()
        if invalid.any():
            row = int(np.flatnonzero(invalid.to_numpy())[0])
            _raise("malformed_date", f"{column} has an invalid ISO date", row)
        result[column] = parsed
    return result


def _finite(data: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    result = data.copy(deep=True)
    for column in columns:
        numeric = pd.to_numeric(result[column], errors="coerce")
        valid = numeric.notna() & np.isfinite(numeric.to_numpy(dtype=float))
        if not valid.all():
            row = int(np.flatnonzero(~valid.to_numpy())[0])
            _raise("nonfinite_numeric", f"{column} must be finite numeric", row)
        result[column] = numeric.astype(float)
    return result


def _unique(data: pd.DataFrame, key_columns: list[str], rule: str) -> None:
    duplicates = data.duplicated(key_columns, keep=False)
    if duplicates.any():
        row = int(np.flatnonzero(duplicates.to_numpy())[0])
        key = {column: str(data.iloc[row][column]) for column in key_columns}
        _raise(rule, f"duplicate key {tuple(key_columns)}", row, key)


def _canonical_dates(data: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    result = data.copy()
    for column in columns:
        result[column] = result[column].dt.strftime("%Y-%m-%d")
    return result


def validate_feature_panel(data: pd.DataFrame) -> pd.DataFrame:
    """Validate and canonicalize a leakage-safe extensible feature panel."""

    _columns(data, FEATURE_ID_COLUMNS, "feature panel")
    if data.empty:
        _raise("empty_dataset", "feature panel must not be empty")
    feature_columns = [name for name in data.columns if name not in FEATURE_ID_COLUMNS]
    forbidden = sorted(set(feature_columns).intersection(FORBIDDEN_FEATURE_COLUMNS))
    if forbidden:
        _raise("label_feature_leakage", f"label columns cannot be features: {forbidden}")
    if not feature_columns:
        _raise("missing_features", "feature panel requires at least one feature")
    _identifiers(data, ("ticker", "sector"))
    parsed = _iso_dates(data, ("as_of_date", "max_feature_available_date"))
    conflicts = (
        parsed.groupby(["as_of_date", "ticker"])["sector"].nunique().gt(1)
    )
    if conflicts.any():
        _raise("conflicting_sector", "same-date ticker has conflicting sectors")
    _unique(parsed, ["as_of_date", "ticker"], "duplicate_feature_key")
    future = parsed["max_feature_available_date"] > parsed["as_of_date"]
    if future.any():
        row = int(np.flatnonzero(future.to_numpy())[0])
        _raise("future_feature_availability",
               "max_feature_available_date exceeds as_of_date", row)
    parsed = _finite(parsed, feature_columns)
    ordered = [*FEATURE_ID_COLUMNS, *sorted(feature_columns)]
    return _canonical_dates(parsed[ordered], (
        "as_of_date", "max_feature_available_date"
    )).sort_values(["as_of_date", "ticker"], kind="mergesort").reset_index(drop=True)


def validate_labels(data: pd.DataFrame) -> pd.DataFrame:
    _columns(data, LABEL_COLUMNS, "labels")
    if data.empty:
        _raise("empty_dataset", "labels must not be empty")
    _identifiers(data, ("ticker", "label_name"))
    parsed = _iso_dates(data, ("as_of_date", "label_end_date"))
    _unique(parsed, ["as_of_date", "ticker", "label_name"], "duplicate_label_key")
    invalid = parsed["label_end_date"] <= parsed["as_of_date"]
    if invalid.any():
        row = int(np.flatnonzero(invalid.to_numpy())[0])
        _raise("invalid_label_horizon",
               "label_end_date must be after as_of_date", row)
    parsed = _finite(parsed, ("forward_return",))
    return _canonical_dates(
        parsed[list(LABEL_COLUMNS)], ("as_of_date", "label_end_date")
    ).sort_values(
        ["as_of_date", "ticker", "label_name"], kind="mergesort"
    ).reset_index(drop=True)


def validate_signals(
    data: pd.DataFrame, known_model_ids: Iterable[str] | None = None
) -> pd.DataFrame:
    _columns(data, SIGNAL_COLUMNS, "signals")
    if data.empty:
        _raise("empty_dataset", "signals must not be empty")
    _identifiers(data, ("ticker", "model_id", "run_id"))
    parsed = _iso_dates(data, ("as_of_date",))
    _unique(parsed, ["as_of_date", "ticker", "model_id", "run_id"],
            "duplicate_signal_key")
    parsed = _finite(parsed, ("score",))
    if "rank" in parsed:
        parsed = _finite(parsed, ("rank",))
    if known_model_ids is not None:
        known = set(known_model_ids)
        unknown = sorted(set(parsed["model_id"]).difference(known))
        if unknown:
            _raise("unknown_model_id", f"unknown model IDs: {unknown}")
    extras = sorted(set(parsed.columns).difference(
        {*SIGNAL_COLUMNS, *OPTIONAL_SIGNAL_COLUMNS}
    ))
    ordered = [*SIGNAL_COLUMNS, *[
        name for name in OPTIONAL_SIGNAL_COLUMNS if name in parsed
    ], *extras]
    return _canonical_dates(parsed[ordered], ("as_of_date",)).sort_values(
        ["as_of_date", "ticker", "model_id", "run_id"], kind="mergesort"
    ).reset_index(drop=True)


def _as_date(value: str | date, field: str) -> date:
    if isinstance(value, datetime):
        _raise("invalid_split_date", f"{field} must be a date, not datetime")
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        _raise("invalid_split_date", f"{field} must be ISO YYYY-MM-DD")
    raise AssertionError


@dataclass(frozen=True, slots=True)
class DateRange:
    start: date
    end: date

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _as_date(self.start, "start"))
        object.__setattr__(self, "end", _as_date(self.end, "end"))
        if self.start > self.end:
            _raise("invalid_split_range", "split start must not exceed end")

    def as_dict(self) -> dict[str, str]:
        return {"start": self.start.isoformat(), "end": self.end.isoformat()}


@dataclass(frozen=True, slots=True)
class ChronologicalSplit:
    train: DateRange
    validation: DateRange
    test: DateRange
    purge_days: int = 0
    embargo_days: int = 0

    def __post_init__(self) -> None:
        for name in ("purge_days", "embargo_days"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                _raise("invalid_gap", f"{name} must be a nonnegative integer")
        required_gap = self.purge_days + self.embargo_days
        validation_gap = (self.validation.start - self.train.end).days - 1
        test_gap = (self.test.start - self.validation.end).days - 1
        if self.train.end >= self.validation.start or self.validation.end >= self.test.start:
            _raise("split_overlap", "train, validation, and test must be chronological")
        if validation_gap < required_gap or test_gap < required_gap:
            _raise(
                "split_gap_violation",
                f"each split boundary requires at least {required_gap} calendar gap days",
            )

    def as_dict(self) -> dict:
        return {
            "train": self.train.as_dict(),
            "validation": self.validation.as_dict(),
            "test": self.test.as_dict(),
            "purge_days": self.purge_days,
            "embargo_days": self.embargo_days,
        }


def validate_split(value: ChronologicalSplit | Mapping) -> ChronologicalSplit:
    if isinstance(value, ChronologicalSplit):
        return value
    try:
        return ChronologicalSplit(
            train=DateRange(**value["train"]),
            validation=DateRange(**value["validation"]),
            test=DateRange(**value["test"]),
            purge_days=value.get("purge_days", 0),
            embargo_days=value.get("embargo_days", 0),
        )
    except KeyError as exc:
        _raise("missing_split_field", f"missing split field: {exc.args[0]}")
    raise AssertionError


def reject_test_contamination(
    fitting_dates: Iterable[str | date], split: ChronologicalSplit
) -> None:
    for index, raw in enumerate(fitting_dates):
        value = _as_date(raw, "fitting_date")
        if value >= split.test.start:
            _raise("test_contamination", "fitting data reaches test period", index)
