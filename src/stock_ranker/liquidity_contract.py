"""Point-in-time liquidity evidence contract; not a transaction-cost model."""

from __future__ import annotations

import re
from typing import Iterable

import numpy as np
import pandas as pd


LIQUIDITY_COLUMNS = (
    "ticker", "isin", "exchange", "trade_date", "available_date",
    "close", "volume", "traded_value", "trade_count", "source",
)
_ISIN = re.compile(r"^INE[A-Z0-9]{9}$")


def validate_liquidity_panel(data: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in LIQUIDITY_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError(f"liquidity panel missing columns: {', '.join(missing)}")
    result = data.loc[:, LIQUIDITY_COLUMNS].copy(deep=True)
    for column in ("ticker", "isin", "exchange", "source"):
        result[column] = result[column].astype("string").str.strip()
        if result[column].isna().any() or result[column].eq("").any():
            raise ValueError(f"liquidity panel has blank {column}")
    if not result["isin"].map(lambda value: bool(_ISIN.fullmatch(str(value)))).all():
        raise ValueError("liquidity panel contains invalid ISIN")
    if not result["exchange"].isin(("NSE", "BSE")).all():
        raise ValueError("liquidity panel exchange must be NSE or BSE")
    for column in ("trade_date", "available_date"):
        result[column] = pd.to_datetime(result[column], format="%Y-%m-%d", errors="raise")
    if result["available_date"].lt(result["trade_date"]).any():
        raise ValueError("liquidity evidence cannot be available before its trade date")
    if result.duplicated(["ticker", "exchange", "trade_date"]).any():
        raise ValueError("liquidity panel contains duplicate natural keys")
    for column in ("close", "volume", "traded_value", "trade_count"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
        if not np.isfinite(result[column]).all():
            raise ValueError(f"liquidity panel has non-finite {column}")
    if result["close"].le(0).any():
        raise ValueError("liquidity close must be positive")
    if result[["volume", "traded_value", "trade_count"]].lt(0).any(axis=None):
        raise ValueError("liquidity activity fields must be nonnegative")
    return result.sort_values(["ticker", "trade_date"], kind="mergesort").reset_index(drop=True)


def calculate_point_in_time_liquidity(
    panel: pd.DataFrame, ranking_dates: Iterable[str], *, window: int = 20,
) -> pd.DataFrame:
    """Calculate trailing observations available by each cutoff, without costs."""

    if window <= 0:
        raise ValueError("window must be positive")
    data = validate_liquidity_panel(panel)
    rows = []
    for raw_cutoff in sorted(set(ranking_dates)):
        cutoff = pd.to_datetime(raw_cutoff, format="%Y-%m-%d", errors="raise")
        eligible = data.loc[
            data["trade_date"].le(cutoff) & data["available_date"].le(cutoff)
        ]
        for ticker, history in eligible.groupby("ticker", sort=True):
            trailing = history.sort_values("trade_date", kind="mergesort").tail(window)
            latest = trailing.iloc[-1]
            rows.append({
                "ranking_date": cutoff.strftime("%Y-%m-%d"), "ticker": ticker,
                "isin": latest["isin"], "exchange": latest["exchange"],
                "observation_count": len(trailing), "window": window,
                "latest_trade_date": latest["trade_date"].strftime("%Y-%m-%d"),
                "average_daily_volume": float(trailing["volume"].mean()),
                "median_daily_traded_value": float(trailing["traded_value"].median()),
                "average_daily_trade_count": float(trailing["trade_count"].mean()),
                "zero_trade_day_count": int(trailing["trade_count"].eq(0).sum()),
                "liquidity_status": "COMPLETE_WINDOW" if len(trailing) == window else "PARTIAL_WINDOW",
                "source": latest["source"],
            })
    return pd.DataFrame(rows).sort_values(
        ["ranking_date", "ticker"], kind="mergesort"
    ).reset_index(drop=True) if rows else pd.DataFrame(columns=(
        "ranking_date", "ticker", "isin", "exchange", "observation_count", "window",
        "latest_trade_date", "average_daily_volume", "median_daily_traded_value",
        "average_daily_trade_count", "zero_trade_day_count", "liquidity_status", "source",
    ))
