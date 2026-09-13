"""Current-product classification and Baseline coverage expansion.

This module deliberately does not alter the frozen research classifications.
It applies an explicit evidence precedence to the current company-fact view and
uses the unchanged Baseline V1 metric/ranking implementation.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from stock_ranker.config import BaselineConfig
from stock_ranker.ranking import rank_stocks_by_sector


PRODUCT_CLASSIFICATION_VERSION = "product_classification_v1"
PRODUCT_BASELINE_METHOD_VERSION = "baseline_v1_equal_rank_mean"

PRODUCT_COLUMNS = (
    "product_classification_version", "product_sector", "product_industry",
    "product_basic_industry", "product_classification_evidence",
    "product_classification_source", "product_classification_as_of",
    "product_baseline_yoy_growth", "product_baseline_cagr_3y",
    "product_baseline_cagr_5y", "product_baseline_days_since_recorded_high",
    "product_baseline_score", "product_baseline_sector_rank",
    "product_baseline_eligible", "product_baseline_reason_code",
    "product_baseline_reason",
)


def _present(value: Any) -> bool:
    return value is not None and not pd.isna(value) and str(value).strip() != ""


def _select_prior(frame: pd.DataFrame, target: pd.Timestamp, tolerance_days: int = 7) -> pd.Series | None:
    eligible = frame.loc[frame["date"].le(target)].tail(1)
    if eligible.empty or (target - eligible.iloc[0]["date"]).days > tolerance_days:
        return None
    return eligible.iloc[0]


def _secondary_metrics(row: dict[str, Any], history_root: Path) -> tuple[dict[str, Any] | None, str, str]:
    path = history_root / f"{row['ticker']}.csv"
    if not path.is_file():
        return None, "PRICE_HISTORY_UNAVAILABLE", "No accepted adjusted history exists for this exact security identity."
    try:
        frame = pd.read_csv(path, usecols=["date", "adjusted_close"])
    except (OSError, ValueError):
        return None, "PRICE_HISTORY_UNAVAILABLE", "The accepted adjusted-history file is unreadable."
    frame["date"] = pd.to_datetime(frame["date"], format="%Y-%m-%d", errors="coerce")
    frame["adjusted_close"] = pd.to_numeric(frame["adjusted_close"], errors="coerce")
    frame = frame.dropna().loc[lambda value: value["adjusted_close"].gt(0)]
    frame = frame.drop_duplicates("date", keep="last").sort_values("date", kind="stable")
    as_of = pd.Timestamp(str(row["trade_date"]))
    frame = frame.loc[frame["date"].le(as_of)]
    if frame.empty:
        return None, "PRICE_HISTORY_UNAVAILABLE", "No accepted adjusted-history observation exists through the trade date."
    selected: dict[str, pd.Series] = {}
    for name, years in (("close_1y", 1), ("close_3y", 3), ("close_5y", 5)):
        target = as_of - pd.DateOffset(years=years)
        observation = _select_prior(frame, target)
        if observation is None:
            return None, f"INSUFFICIENT_{years}Y_HISTORY", f"No prior adjusted-close observation exists within seven days of the {name} target."
        selected[name] = observation
    listing = pd.to_datetime(row.get("listing_date"), format="%Y-%m-%d", errors="coerce")
    high_frame = frame if pd.isna(listing) else frame.loc[frame["date"].ge(listing)]
    if high_frame.empty:
        return None, "RECORDED_HIGH_HISTORY_UNAVAILABLE", "No adjusted history remains after the documented listing boundary."
    terminal = frame.iloc[-1]
    terminal_lag_days = int((as_of - terminal["date"]).days)
    provider_current = float(terminal["adjusted_close"])
    prior_reference = not _present(row.get("latest_price"))
    official_current = float(row["product_price_reference"] if prior_reference else row["latest_price"])
    relative_difference = abs(provider_current - official_current) / official_current
    current = official_current
    current_price_reason = (
        "Accepted exchange current price and exact-identity adjusted history satisfy "
        "the Product Classification v1 continuity gate."
    )
    accepted_screener = str(row.get("screener_current_status")) in {
        "ACCEPTED_EXACT_ISIN_CURRENT_REFERENCE",
        "ACCEPTED_UNIQUE_EXCHANGE_CODE_CURRENT_REFERENCE",
    }
    if terminal_lag_days > 7 or relative_difference > 0.02:
        if prior_reference:
            return None, "CURRENT_PRICE_MISMATCH", (
                "Official prior-trade price is available, but differs from the accepted "
                "adjusted-history terminal by more than 2% or history is stale; "
                "cross-exchange continuity remains unresolved."
            )
        screener_current = pd.to_numeric(row.get("screener_current_price"), errors="coerce")
        if not accepted_screener or pd.isna(screener_current) or float(screener_current) <= 0:
            code = "CURRENT_PRICE_UNAVAILABLE" if terminal_lag_days > 7 else "CURRENT_PRICE_MISMATCH"
            return None, code, (
                "The exact-identity provider history does not supply a current continuity "
                "observation and no accepted Screener Premium current/reference price is available."
            )
        current = float(screener_current)
        current_price_reason = (
            "Provider terminal staleness or exchange-price conflict is retained as provenance; "
            "Screener Premium is authoritative for current/reference price and the "
            "accepted exact-identity adjusted history supplies historical anchors."
        )
    maximum = max(float(high_frame["adjusted_close"].max()), current)
    if current >= float(high_frame["adjusted_close"].max()):
        high_date = pd.Timestamp(row['product_price_date']) if prior_reference else as_of
    else:
        high_date = high_frame.loc[high_frame["adjusted_close"].eq(maximum)].iloc[-1]["date"]
    if prior_reference:
        current_price_reason = (
            f"Official {row['product_price_exchange']} prior-trade price from {row['product_price_date']}; "
            "historical anchors retain the snapshot date and existing continuity rules."
        )
    return ({
        "ticker": str(row["ticker"]), "company": str(row["company"]),
        "sector": str(row["product_sector"]), "as_of_date": as_of,
        "current_price": current,
        "close_1y_ago": float(selected["close_1y"]["adjusted_close"]),
        "close_3y_ago": float(selected["close_3y"]["adjusted_close"]),
        "close_5y_ago": float(selected["close_5y"]["adjusted_close"]),
        "ath_date": high_date,
        "yoy_growth": current / float(selected["close_1y"]["adjusted_close"]) - 1,
        "cagr_3y": (current / float(selected["close_3y"]["adjusted_close"])) ** (1 / 3) - 1,
        "cagr_5y": (current / float(selected["close_5y"]["adjusted_close"])) ** (1 / 5) - 1,
        "days_since_recorded_high": int((as_of - high_date).days),
    }, "ELIGIBLE", current_price_reason)


def add_product_classification_and_baseline(
    facts: pd.DataFrame,
    *,
    history_root: str | Path,
) -> pd.DataFrame:
    """Add current-product grouping and rankings while preserving frozen fields."""

    result = facts.copy()
    for column in PRODUCT_COLUMNS:
        result[column] = None
    result["product_classification_version"] = PRODUCT_CLASSIFICATION_VERSION
    metric_rows: list[dict[str, Any]] = []
    reasons: dict[str, tuple[str, str]] = {}
    for index, source in result.iterrows():
        ticker = str(source["ticker"])
        official = _present(source.get("official_sector"))
        secondary = (
            str(source.get("secondary_identity_status")) == "EXCHANGE_SYMBOL_MATCH"
            and _present(source.get("secondary_sector"))
        )
        bulk_secondary = (
            str(source.get("bulk_classification_status")) == "ACCEPTED"
            and _present(source.get("bulk_classification_sector"))
        )
        screener_status = str(source.get("screener_current_status"))
        screener_secondary = (
            screener_status in {
                "ACCEPTED_EXACT_ISIN_CURRENT_REFERENCE",
                "ACCEPTED_UNIQUE_EXCHANGE_CODE_CURRENT_REFERENCE",
            }
            and _present(source.get("screener_industry_group"))
        )
        if official:
            result.at[index, "product_sector"] = source["official_sector"]
            result.at[index, "product_industry"] = source.get("official_industry")
            result.at[index, "product_basic_industry"] = source.get("official_basic_industry")
            result.at[index, "product_classification_evidence"] = "OFFICIAL"
            result.at[index, "product_classification_source"] = source.get("official_classification_source")
            result.at[index, "product_classification_as_of"] = source.get("trade_date")
        elif secondary:
            result.at[index, "product_sector"] = source["secondary_sector"]
            result.at[index, "product_industry"] = source.get("secondary_industry")
            result.at[index, "product_classification_evidence"] = "EXACT_IDENTITY_SECONDARY_REFERENCE"
            result.at[index, "product_classification_source"] = source.get("secondary_source")
            result.at[index, "product_classification_as_of"] = source.get("secondary_source_as_of")
        elif bulk_secondary:
            result.at[index, "product_sector"] = source["bulk_classification_sector"]
            result.at[index, "product_industry"] = source.get("bulk_classification_industry")
            result.at[index, "product_classification_evidence"] = "EXACT_IDENTITY_SECONDARY_REFERENCE"
            result.at[index, "product_classification_source"] = source.get("bulk_classification_source")
            result.at[index, "product_classification_as_of"] = source.get("bulk_classification_retrieved_at")
        elif screener_secondary:
            result.at[index, "product_sector"] = source["screener_industry_group"]
            result.at[index, "product_industry"] = source.get("screener_industry")
            result.at[index, "product_classification_evidence"] = (
                "EXACT_ISIN_SCREENER_CURRENT_REFERENCE"
                if screener_status == "ACCEPTED_EXACT_ISIN_CURRENT_REFERENCE"
                else "UNIQUE_EXCHANGE_CODE_SCREENER_CURRENT_REFERENCE"
            )
            result.at[index, "product_classification_source"] = "Accepted Screener market-wide export"
            result.at[index, "product_classification_as_of"] = source.get("screener_source_observed_at")
        else:
            result.at[index, "product_classification_evidence"] = "UNCLASSIFIED"
            reasons[ticker] = ("UNCLASSIFIED", "No official or exact-identity secondary sector evidence is accepted.")
            continue

        row = result.loc[index].to_dict()
        if not _present(row.get("latest_price")):
            if row.get("product_price_status") == "OFFICIAL_PRIOR_TRADE" and _present(row.get("product_price_reference")):
                metrics, code, reason = _secondary_metrics(row, Path(history_root))
                reasons[ticker] = (code, reason)
                if metrics is not None:
                    metric_rows.append(metrics)
            elif row.get("product_price_status") == "OFFICIAL_LAST_TRADE_STALE":
                reasons[ticker] = ("CURRENT_PRICE_STALE", f"Last verified official trade is {row.get('product_price_date')}; outside the existing seven-day continuity window.")
            elif row.get("product_price_status") == "OFFICIAL_PRIOR_TRADE_ACTION_REVIEW_REQUIRED":
                reasons[ticker] = ("CURRENT_PRICE_ACTION_REVIEW_REQUIRED", "An official corporate action follows the last verified trade; its price basis requires review.")
            else:
                reasons[ticker] = ("PRICE_UNAVAILABLE", "No accepted current exchange price exists.")
            continue
        frozen_metrics = (
            "baseline_yoy_growth", "baseline_cagr_3y", "baseline_cagr_5y",
            "baseline_days_since_recorded_high",
        )
        if official and bool(row.get("baseline_eligible")) and all(_present(row.get(name)) for name in frozen_metrics):
            metric_rows.append({
                "ticker": ticker, "company": str(row["company"]),
                "sector": str(row["product_sector"]), "as_of_date": pd.Timestamp(str(row["trade_date"])),
                "current_price": float(row["latest_price"]), "close_1y_ago": 1.0,
                "close_3y_ago": 1.0, "close_5y_ago": 1.0,
                "ath_date": pd.Timestamp(str(row["trade_date"])) - pd.Timedelta(days=int(row["baseline_days_since_recorded_high"])),
                "yoy_growth": float(row["baseline_yoy_growth"]),
                "cagr_3y": float(row["baseline_cagr_3y"]),
                "cagr_5y": float(row["baseline_cagr_5y"]),
                "days_since_recorded_high": int(row["baseline_days_since_recorded_high"]),
            })
            reasons[ticker] = ("ELIGIBLE", "Accepted official classification and frozen current Baseline inputs are reused unchanged.")
        elif official and bool(row.get("baseline_eligible")):
            reasons[ticker] = ("BASELINE_METRICS_UNAVAILABLE", "The source row is eligible but does not expose its canonical metric inputs.")
        elif official and str(row.get("baseline_reason_code")) == "CURRENT_PRICE_MISMATCH":
            metrics, code, reason = _secondary_metrics(row, Path(history_root))
            reasons[ticker] = (code, reason)
            if metrics is not None:
                reasons[ticker] = ("ELIGIBLE", reason)
                metric_rows.append(metrics)
        elif official:
            reasons[ticker] = (str(row.get("baseline_reason_code")), str(row.get("history_reason") or "Accepted current Baseline eligibility reason applies."))
        else:
            metrics, code, reason = _secondary_metrics(row, Path(history_root))
            reasons[ticker] = (code, reason)
            if metrics is not None:
                metric_rows.append(metrics)

    if metric_rows:
        metrics = pd.DataFrame(metric_rows)
        ranked = rank_stocks_by_sector(metrics, BaselineConfig(method_version=PRODUCT_BASELINE_METHOD_VERSION))
        by_ticker = ranked.set_index("ticker")
        for index, ticker in result["ticker"].astype(str).items():
            if ticker not in by_ticker.index:
                continue
            ranked_row = by_ticker.loc[ticker]
            for target, source in (
                ("product_baseline_yoy_growth", "yoy_growth"),
                ("product_baseline_cagr_3y", "cagr_3y"),
                ("product_baseline_cagr_5y", "cagr_5y"),
                ("product_baseline_days_since_recorded_high", "days_since_recorded_high"),
                ("product_baseline_score", "baseline_score"),
                ("product_baseline_sector_rank", "sector_rank"),
            ):
                result.at[index, target] = ranked_row[source]
    for index, ticker in result["ticker"].astype(str).items():
        code, reason = reasons[ticker]
        result.at[index, "product_baseline_reason_code"] = code
        result.at[index, "product_baseline_reason"] = reason
        result.at[index, "product_baseline_eligible"] = code == "ELIGIBLE"
    result["product_baseline_eligible"] = result["product_baseline_eligible"].astype(bool)
    return result
