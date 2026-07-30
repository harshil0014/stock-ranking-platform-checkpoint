"""Strict validation and normalization for Baseline V1 inputs."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from stock_ranker.contracts import (
    DATE_COLUMNS,
    IDENTITY_COLUMNS,
    PRICE_COLUMNS,
    REQUIRED_COLUMNS,
)

ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_baseline_input(data: pd.DataFrame) -> pd.DataFrame:
    """Return a validated canonical copy of ``data``.

    Extra input columns are allowed but intentionally omitted from the
    canonical result. Required names are exact and case-sensitive.
    """

    if not isinstance(data, pd.DataFrame):
        raise TypeError("data must be a pandas DataFrame")

    missing = set(REQUIRED_COLUMNS).difference(data.columns)
    if missing:
        raise ValueError(
            "Missing required columns: " + ", ".join(sorted(missing))
        )

    validated = data.loc[:, list(REQUIRED_COLUMNS)].copy()
    missing_counts = validated.isna().sum()
    missing_columns = [
        f"{column} ({int(count)} row(s))"
        for column, count in missing_counts.items()
        if count
    ]
    if missing_columns:
        raise ValueError(
            "Missing values in required columns: " + ", ".join(missing_columns)
        )

    for column in IDENTITY_COLUMNS:
        validated[column] = validated[column].astype(str).str.strip()
        blank_rows = validated.index[validated[column].eq("")].tolist()
        if blank_rows:
            raise ValueError(
                f"{column} must not be blank; invalid row(s): {blank_rows}"
            )

    for column in DATE_COLUMNS:
        if isinstance(validated[column].dtype, pd.DatetimeTZDtype):
            raise ValueError(f"{column} must not contain timezone information")
        if pd.api.types.is_datetime64_any_dtype(validated[column]):
            parsed_dates = validated[column]
            has_time = parsed_dates.ne(parsed_dates.dt.normalize())
            if has_time.any():
                rows = validated.index[has_time].tolist()
                raise ValueError(
                    f"{column} must contain dates without times; "
                    f"invalid row(s): {rows}"
                )
            validated[column] = parsed_dates
        else:
            raw_dates = validated[column].astype(str)
            invalid_format = ~raw_dates.str.fullmatch(ISO_DATE_PATTERN)
            if invalid_format.any():
                rows = validated.index[invalid_format].tolist()
                raise ValueError(
                    f"{column} must use ISO YYYY-MM-DD format; "
                    f"invalid row(s): {rows}"
                )
            try:
                validated[column] = pd.to_datetime(
                    raw_dates, format="%Y-%m-%d", errors="raise"
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{column} contains an invalid calendar date"
                ) from exc

    for column in PRICE_COLUMNS:
        try:
            numeric = pd.to_numeric(validated[column], errors="raise")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{column} must contain numeric values") from exc

        values = numeric.to_numpy(dtype=float)
        invalid_rows = validated.index[
            ~np.isfinite(values) | (values <= 0)
        ].tolist()
        if invalid_rows:
            raise ValueError(
                f"{column} must contain finite positive values; "
                f"invalid row(s): {invalid_rows}"
            )
        validated[column] = numeric.astype(float)

    future_high = validated["ath_date"] > validated["as_of_date"]
    if future_high.any():
        rows = validated.index[future_high].tolist()
        raise ValueError(
            "ath_date (recorded high date) cannot be later than as_of_date; "
            f"invalid row(s): {rows}"
        )

    duplicates = validated.duplicated(
        subset=["ticker", "as_of_date"], keep=False
    )
    if duplicates.any():
        keys = (
            validated.loc[duplicates, ["ticker", "as_of_date"]]
            .assign(
                as_of_date=lambda frame: frame["as_of_date"].dt.strftime(
                    "%Y-%m-%d"
                )
            )
            .drop_duplicates()
            .to_dict("records")
        )
        raise ValueError(
            "Duplicate (ticker, as_of_date) record(s): "
            + ", ".join(
                f"({key['ticker']}, {key['as_of_date']})" for key in keys
            )
        )

    return validated
