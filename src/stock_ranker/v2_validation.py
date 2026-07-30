"""Structural validation for Research V2 point-in-time inputs."""

from __future__ import annotations

import re

import pandas as pd

from stock_ranker.v2_contracts import (
    FUNDAMENTAL_COLUMNS,
    PRICE_HISTORY_COLUMNS,
    UNIVERSE_COLUMNS,
)

ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _require_columns(
    data: pd.DataFrame, required: tuple[str, ...], label: str
) -> pd.DataFrame:
    if not isinstance(data, pd.DataFrame):
        raise TypeError(f"{label} must be a pandas DataFrame")
    missing = set(required).difference(data.columns)
    if missing:
        raise ValueError(
            f"{label} missing required columns: " + ", ".join(sorted(missing))
        )
    if data.empty:
        raise ValueError(f"{label} must contain at least one row")
    return data.loc[:, list(required)].copy()


def _validate_identifiers(data: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    for column in columns:
        if data[column].isna().any():
            raise ValueError(f"{label}.{column} must not contain missing values")
        data[column] = data[column].astype(str).str.strip()
        if data[column].eq("").any():
            raise ValueError(f"{label}.{column} must not contain blank values")


def _parse_iso_date_column(
    data: pd.DataFrame, column: str, label: str
) -> None:
    if data[column].isna().any():
        raise ValueError(f"{label}.{column} must not contain missing values")
    raw = data[column].astype(str)
    if (~raw.str.fullmatch(ISO_DATE_PATTERN)).any():
        raise ValueError(f"{label}.{column} must use ISO YYYY-MM-DD format")
    try:
        data[column] = pd.to_datetime(raw, format="%Y-%m-%d", errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}.{column} contains an invalid calendar date") from exc


def validate_v2_structures(
    universe: pd.DataFrame,
    prices: pd.DataFrame,
    fundamentals: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Validate schemas, identifiers, dates, and natural keys.

    Numeric values intentionally remain unvalidated until point-in-time
    filtering has removed future observations.
    """

    clean_universe = _require_columns(universe, UNIVERSE_COLUMNS, "universe")
    clean_prices = _require_columns(prices, PRICE_HISTORY_COLUMNS, "prices")
    clean_fundamentals = _require_columns(
        fundamentals, FUNDAMENTAL_COLUMNS, "fundamentals"
    )

    _validate_identifiers(
        clean_universe, ("ticker", "company", "sector"), "universe"
    )
    _validate_identifiers(clean_prices, ("ticker",), "prices")
    _validate_identifiers(clean_fundamentals, ("ticker",), "fundamentals")

    if clean_universe.duplicated(["ticker"]).any():
        raise ValueError("universe contains duplicate ticker records")

    _parse_iso_date_column(clean_prices, "date", "prices")
    _parse_iso_date_column(clean_fundamentals, "period_end", "fundamentals")
    _parse_iso_date_column(
        clean_fundamentals, "available_date", "fundamentals"
    )

    if clean_prices.duplicated(["ticker", "date"]).any():
        raise ValueError("prices contains duplicate (ticker, date) records")
    if clean_fundamentals.duplicated(
        ["ticker", "period_end", "available_date"]
    ).any():
        raise ValueError(
            "fundamentals contains duplicate "
            "(ticker, period_end, available_date) records"
        )

    return clean_universe, clean_prices, clean_fundamentals
