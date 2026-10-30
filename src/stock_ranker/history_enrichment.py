"""Leakage-safe current-history enrichment with explicit provenance.

This module does not mutate accepted market state. It derives auditable history
features from an accepted price cache plus an optional research recovery overlay.
Observed horizon returns remain distinct from estimates and secondary-provider
cross-checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

FRESH_TERMINAL_LAG_DAYS = 7
MAX_TERMINAL_LAG_DAYS = 21
ANCHOR_TOLERANCE_DAYS = 7
DAYS_PER_YEAR = 365.0
DAYS_PER_MONTH = 30.4375


class HistoryEnrichmentError(ValueError):
    """Raised when a candidate history violates the enrichment contract."""


@dataclass(frozen=True, slots=True)
class HistorySource:
    path: Path
    source: str
    quality: str


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def load_history(
    path: str | Path,
    *,
    cutoff: str | pd.Timestamp | None = None,
    allow_official_raw_close: bool = False,
) -> pd.DataFrame:
    """Load one positive, unique, chronologically ordered price history.

    The normal contract accepts only adjusted_close/raw_close. The official BSE
    recovery evidence uses a close column; that column is accepted only when
    explicitly requested for risk-only diagnostics and must never silently
    become an adjusted-return series.
    """
    source = Path(path)
    frame = pd.read_csv(source)
    required = {"date"}
    if not required.issubset(frame.columns):
        raise HistoryEnrichmentError(f"{source.name}: history is missing date")
    if "adjusted_close" in frame.columns:
        price_column = "adjusted_close"
    elif "raw_close" in frame.columns:
        price_column = "raw_close"
    elif allow_official_raw_close and "close" in frame.columns:
        price_column = "close"
    else:
        raise HistoryEnrichmentError(f"{source.name}: history has no usable price column")
    result = pd.DataFrame({
        "date": pd.to_datetime(frame["date"], errors="coerce"),
        "price": pd.to_numeric(frame[price_column], errors="coerce"),
    })
    result = result.dropna().loc[lambda x: x["price"].gt(0)].copy()
    result = result.drop_duplicates("date", keep="last").sort_values("date", kind="stable")
    if cutoff is not None:
        result = result.loc[result["date"].le(pd.Timestamp(cutoff))].copy()
    if result.empty:
        raise HistoryEnrichmentError(f"{source.name}: no positive prices through cutoff")
    if result["date"].duplicated().any() or not result["date"].is_monotonic_increasing:
        raise HistoryEnrichmentError(f"{source.name}: history ordering is invalid")
    return result.reset_index(drop=True)


def _strict_cagr(dates: np.ndarray, prices: np.ndarray, cutoff: pd.Timestamp, years: int) -> float | None:
    anchor = np.datetime64((cutoff - pd.DateOffset(years=years)).date(), "D")
    index = np.searchsorted(dates, anchor, side="right") - 1
    if index < 0 or index >= len(dates) - 1:
        return None
    gap = int((anchor - dates[index]).astype(int))
    span = int((dates[-1] - dates[index]).astype(int))
    if not 0 <= gap <= ANCHOR_TOLERANCE_DAYS or span <= 0:
        return None
    return float(np.expm1(np.log(prices[-1] / prices[index]) * DAYS_PER_YEAR / span))


def compute_history_metrics(
    frame: pd.DataFrame,
    *,
    cutoff: str | pd.Timestamp,
    listing_date: Any = None,
) -> dict[str, Any]:
    """Derive current, point-in-time features from one accepted history."""
    cutoff_ts = pd.Timestamp(cutoff).normalize()
    work = frame.loc[frame["date"].le(cutoff_ts)].copy()
    if work.empty:
        raise HistoryEnrichmentError("history has no row through cutoff")
    terminal_lag = int((cutoff_ts - work.iloc[-1]["date"]).days)
    if terminal_lag < 0 or terminal_lag > MAX_TERMINAL_LAG_DAYS:
        raise HistoryEnrichmentError(f"terminal history lag is {terminal_lag} days")

    dates = work["date"].to_numpy(dtype="datetime64[D]")
    prices = work["price"].to_numpy(dtype=float)
    if len(prices) < 1 or not np.isfinite(prices).all() or np.any(prices <= 0):
        raise HistoryEnrichmentError("history contains invalid prices")

    span_days = int((dates[-1] - dates[0]).astype(int)) if len(dates) > 1 else 0
    history_months = span_days / DAYS_PER_MONTH
    history_start_cagr = (
        float(np.expm1(np.log(prices[-1] / prices[0]) * DAYS_PER_YEAR / span_days))
        if span_days > 0 else None
    )

    peak_index = int(np.argmax(prices))
    running_peak = np.maximum.accumulate(prices)
    drawdowns = prices / running_peak - 1.0
    deepest_index = int(np.argmin(drawdowns))

    underwater = prices < running_peak * (1 - 1e-10)
    last_peak_marker = np.where(~underwater, np.arange(len(prices)), 0)
    last_peak_index = np.maximum.accumulate(last_peak_marker)
    underwater_days = (dates - dates[last_peak_index]).astype(int)

    year_start = np.searchsorted(dates, np.datetime64((cutoff_ts - pd.Timedelta(days=365)).date(), "D"))
    year_prices = prices[year_start:]
    daily_log_returns = np.diff(np.log(year_prices))
    volatility = (
        float(np.std(daily_log_returns, ddof=1) * np.sqrt(252))
        if len(daily_log_returns) > 5 else None
    )
    downside = (
        float(np.sqrt(np.mean(np.minimum(daily_log_returns, 0) ** 2)) * np.sqrt(252))
        if len(daily_log_returns) > 5 else None
    )

    listing = pd.to_datetime(listing_date, errors="coerce")
    first_date = pd.Timestamp(dates[0])
    listing_available = bool(pd.notna(listing))
    listing_consistent = bool(
        listing_available and abs((first_date.normalize() - listing.normalize()).days) <= 31
    )
    listing_age_months = (
        float((cutoff_ts - listing.normalize()).days / DAYS_PER_MONTH)
        if listing_available and listing.normalize() <= cutoff_ts else None
    )

    result: dict[str, Any] = {
        "history_start_date": first_date.date().isoformat(),
        "history_end_date": pd.Timestamp(dates[-1]).date().isoformat(),
        "history_observation_count": int(len(prices)),
        "history_span_days": span_days,
        "history_months": float(history_months),
        "history_age_basis": "OBSERVED_PRICE_HISTORY_SPAN",
        "listing_date_available": listing_available,
        "listing_age_months": listing_age_months,
        "terminal_lag_days": terminal_lag,
        "terminal_history_quality": (
            "CURRENT_0_7D" if terminal_lag <= FRESH_TERMINAL_LAG_DAYS
            else "ACCEPTED_STALE_8_21D"
        ),
        "history_start_cagr": history_start_cagr,
        "listing_date_consistent_with_history_start": listing_consistent,
        "strict_cagr_1y": _strict_cagr(dates, prices, cutoff_ts, 1),
        "strict_cagr_3y": _strict_cagr(dates, prices, cutoff_ts, 3),
        "strict_cagr_5y": _strict_cagr(dates, prices, cutoff_ts, 5),
        "recorded_high_price": float(prices[peak_index]),
        "recorded_high_date": pd.Timestamp(dates[peak_index]).date().isoformat(),
        "days_since_recorded_high": int((np.datetime64(cutoff_ts.date(), "D") - dates[peak_index]).astype(int)),
        "distance_from_recorded_high": float(prices[-1] / prices[peak_index] - 1.0),
        "distance_from_52w_high": float(prices[-1] / np.max(year_prices) - 1.0),
        "full_history_max_drawdown": float(np.min(drawdowns)),
        "current_drawdown_duration_days": int(underwater_days[-1]),
        "max_drawdown_duration_days": int(np.max(underwater_days)),
        "recovery_from_worst_trough": float(prices[-1] / prices[deepest_index] - 1.0),
        "realized_volatility_1y": volatility,
        "downside_volatility_1y": downside,
    }
    return result


def resolve_history(
    ticker: str,
    *,
    primary_root: str | Path,
    recovery_root: str | Path | None = None,
) -> HistorySource | None:
    """Prefer accepted history unless a validated recovery is strictly newer."""
    primary = Path(primary_root) / f"{ticker}.csv"
    recovered = (
        Path(recovery_root) / f"{ticker}.csv"
        if recovery_root is not None else None
    )
    if primary.is_file() and recovered is not None and recovered.is_file():
        try:
            primary_last = pd.to_datetime(
                pd.read_csv(primary, usecols=["date"])["date"], errors="coerce"
            ).max()
            recovered_last = pd.to_datetime(
                pd.read_csv(recovered, usecols=["date"])["date"], errors="coerce"
            ).max()
            if pd.notna(recovered_last) and (
                pd.isna(primary_last) or recovered_last > primary_last
            ):
                return HistorySource(
                    recovered, "RECOVERY_OVERLAY_REFRESH", "RECOVERED_VALIDATED"
                )
        except (OSError, ValueError, pd.errors.ParserError):
            pass
    if primary.is_file():
        return HistorySource(primary, "ACCEPTED_HISTORY_CACHE", "ACCEPTED")
    if recovered is not None and recovered.is_file():
        return HistorySource(recovered, "RECOVERY_OVERLAY", "RECOVERED_VALIDATED")
    return None


def build_current_history_enrichment(
    facts: pd.DataFrame,
    *,
    primary_root: str | Path,
    recovery_root: str | Path | None,
    cutoff: str,
    raw_risk_root: str | Path | None = None,
) -> pd.DataFrame:
    """Build one provenance-rich current enrichment row per accepted identity."""
    required = {"isin", "ticker"}
    missing = required.difference(facts.columns)
    if missing:
        raise HistoryEnrichmentError("facts missing: " + ", ".join(sorted(missing)))

    records: list[dict[str, Any]] = []
    for row in facts.to_dict("records"):
        ticker = str(row["ticker"])
        source = resolve_history(
            ticker, primary_root=primary_root, recovery_root=recovery_root
        )
        record: dict[str, Any] = {
            "isin": row["isin"],
            "ticker": ticker,
            "sector": row.get("derived_research_sector"),
            "history_source": source.source if source else "NO_VALID_PRICE_HISTORY",
            "history_quality": source.quality if source else "MISSING",
            "history_path": str(source.path) if source else "",
            "adjusted_history_available": bool(source is not None),
            "return_metric_source": source.source if source else "UNAVAILABLE",
            "risk_metric_source": source.source if source else "UNAVAILABLE",
            "screener_return_3y_pct": _finite_number(row.get("screener_return_3y_pct")),
            "screener_return_5y_pct": _finite_number(row.get("screener_return_5y_pct")),
            "screener_all_time_high_price": _finite_number(row.get("screener_all_time_high_price")),
        }
        if source is not None:
            try:
                history = load_history(source.path, cutoff=cutoff)
                record.update(compute_history_metrics(
                    history, cutoff=cutoff, listing_date=row.get("listing_date")
                ))
            except (OSError, ValueError, pd.errors.ParserError) as exc:
                record["history_quality"] = "INVALID"
                record["adjusted_history_available"] = False
                record["return_metric_source"] = "UNAVAILABLE_INVALID_ADJUSTED_HISTORY"
                record["risk_metric_source"] = "UNAVAILABLE_INVALID_ADJUSTED_HISTORY"
                record["history_error"] = f"{type(exc).__name__}: {exc}"

        # For the tiny residual set where official BSE closes exist but a
        # corporate-action-adjusted history cannot be defended, use the raw
        # closes only for price-path/risk diagnostics. Never populate strict
        # CAGR or history-start return fields from this fallback.
        raw_risk_path = (
            Path(raw_risk_root) / f"{ticker}.csv" if raw_risk_root is not None else None
        )
        if (
            not record["adjusted_history_available"]
            and raw_risk_path is not None
            and raw_risk_path.is_file()
        ):
            try:
                raw_history = load_history(
                    raw_risk_path, cutoff=cutoff, allow_official_raw_close=True
                )
                raw_metrics = compute_history_metrics(
                    raw_history, cutoff=cutoff, listing_date=row.get("listing_date")
                )
                risk_only_fields = {
                    "history_start_date", "history_end_date", "history_observation_count",
                    "history_span_days", "history_months", "history_age_basis",
                    "listing_date_available", "listing_age_months",
                    "listing_date_consistent_with_history_start", "terminal_lag_days",
                    "terminal_history_quality", "recorded_high_price", "recorded_high_date",
                    "days_since_recorded_high", "distance_from_recorded_high",
                    "distance_from_52w_high", "full_history_max_drawdown",
                    "current_drawdown_duration_days", "max_drawdown_duration_days",
                    "recovery_from_worst_trough", "realized_volatility_1y",
                    "downside_volatility_1y",
                }
                for key in risk_only_fields:
                    if key in raw_metrics:
                        record[key] = raw_metrics[key]
                record["history_age_basis"] = "OBSERVED_RAW_PRICE_HISTORY_SPAN"
                record["history_source"] = "OFFICIAL_BSE_RAW_RISK_FALLBACK"
                record["history_quality"] = "RAW_RISK_ONLY"
                record["history_path"] = str(raw_risk_path)
                record["risk_metric_source"] = "OFFICIAL_BSE_RAW_CLOSE"
                record["return_metric_source"] = "UNAVAILABLE_UNADJUSTED_CORPORATE_ACTIONS"
                record["raw_risk_fallback_used"] = True
            except (OSError, ValueError, pd.errors.ParserError) as exc:
                record["raw_risk_fallback_error"] = f"{type(exc).__name__}: {exc}"

        if record.get("days_since_recorded_high") is None:
            high_date = pd.to_datetime(row.get("recorded_high_date"), errors="coerce")
            high_price = _finite_number(row.get("recorded_high"))
            if pd.notna(high_date) and high_date <= pd.Timestamp(cutoff) and high_price is not None:
                record["recorded_high_date"] = high_date.date().isoformat()
                record["recorded_high_price"] = high_price
                record["days_since_recorded_high"] = int(
                    (pd.Timestamp(cutoff).normalize() - high_date.normalize()).days
                )
                record["high_metric_source"] = "ACCEPTED_FACT_SNAPSHOT"
            elif record.get("recorded_high_date") is not None:
                record["high_metric_source"] = record["history_source"]
        else:
            record["high_metric_source"] = record["history_source"]
        records.append(record)

    result = pd.DataFrame(records)
    observed = (
        pd.to_numeric(result["strict_cagr_5y"], errors="coerce")
        if "strict_cagr_5y" in result
        else pd.Series(np.nan, index=result.index, dtype=float)
    )
    result["cagr_5y_observed"] = observed.notna().astype(int)

    sector_key = result["sector"].astype("string")
    sector_median = observed.groupby(sector_key).transform("median")
    global_median = float(observed.median()) if observed.notna().any() else 0.0
    result["sector_median_observed_cagr_5y"] = sector_median.fillna(global_median).clip(-0.5, 0.5)

    months = (
        pd.to_numeric(result["history_months"], errors="coerce")
        if "history_months" in result
        else pd.Series(0.0, index=result.index, dtype=float)
    ).fillna(0).clip(lower=0)
    own_growth = (
        pd.to_numeric(result["history_start_cagr"], errors="coerce")
        if "history_start_cagr" in result
        else pd.Series(np.nan, index=result.index, dtype=float)
    )
    weight = (months / 60.0).clip(0, 1)
    estimate = (
        weight * own_growth.clip(-0.75, 1.0)
        + (1 - weight) * result["sector_median_observed_cagr_5y"]
    )
    estimate = estimate.where(own_growth.notna(), result["sector_median_observed_cagr_5y"])

    result["long_term_growth_value"] = observed.where(observed.notna(), estimate)
    result["long_term_growth_source"] = np.where(
        observed.notna(),
        "OBSERVED_ADJUSTED_5Y_CAGR",
        np.where(
            own_growth.notna(),
            "ESTIMATED_HISTORY_SECTOR_SHRUNK",
            "ESTIMATED_SECTOR_MEDIAN_ONLY",
        ),
    )
    result["long_term_growth_is_observed"] = observed.notna()

    # Keep observed volatility separate from a complete model-ready proxy so
    # sparse/young histories cannot turn NaN routing into another shortcut.
    for metric in ("realized_volatility_1y", "downside_volatility_1y"):
        metric_observed = (
            pd.to_numeric(result[metric], errors="coerce")
            if metric in result
            else pd.Series(np.nan, index=result.index, dtype=float)
        )
        metric_sector_median = metric_observed.groupby(sector_key).transform("median")
        metric_global_median = (
            float(metric_observed.median()) if metric_observed.notna().any() else 0.0
        )
        metric_estimate = metric_sector_median.fillna(metric_global_median).clip(lower=0)
        result[f"{metric}_value"] = metric_observed.where(
            metric_observed.notna(), metric_estimate
        )
        result[f"{metric}_is_observed"] = metric_observed.notna()
        result[f"{metric}_source"] = np.where(
            metric_observed.notna(),
            "OBSERVED_PRICE_HISTORY",
            "ESTIMATED_SECTOR_MEDIAN",
        )

    scr5 = pd.to_numeric(result["screener_return_5y_pct"], errors="coerce") / 100.0
    result["screener_5y_crosscheck"] = scr5
    result["screener_5y_minus_observed_cagr"] = scr5 - observed

    return result
