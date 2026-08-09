"""Read-only presentation adapter for the prepared LIVE MARKET bundle."""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from stock_ranker.live_market import LiveMarketBundle, load_live_market_bundle
from stock_ranker.v2_config import ResearchV2Weights


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LIVE_BUNDLE_ROOT = PROJECT_ROOT / "data/live_market/current"
LIVE_HISTORY_ROOT = PROJECT_ROOT / "data/live_market/history_cache"
SAFE_TICKER = re.compile(r"^[A-Z0-9&.-]{1,32}$")
V2_FACTORS = (
    "return_1y", "cagr_3y", "cagr_5y", "days_since_recorded_high",
    "annualized_volatility_1y", "max_drawdown_3y", "roce",
    "debt_to_equity", "profit_growth_yoy",
)
BASELINE_FACTOR_COLUMNS = {
    "yoy_growth": "baseline_yoy_growth",
    "cagr_3y": "baseline_cagr_3y",
    "cagr_5y": "baseline_cagr_5y",
    "days_since_recorded_high": "baseline_days_since_recorded_high",
}
V2_CATEGORIES = {
    "return_1y": "PRICE / GROWTH", "cagr_3y": "PRICE / GROWTH",
    "cagr_5y": "PRICE / GROWTH", "days_since_recorded_high": "PRICE / GROWTH",
    "annualized_volatility_1y": "RISK", "max_drawdown_3y": "RISK",
    "roce": "FUNDAMENTALS", "debt_to_equity": "FUNDAMENTALS",
    "profit_growth_yoy": "FUNDAMENTALS",
}
V2_DIRECTIONS = {
    "return_1y": "Higher preferred", "cagr_3y": "Higher preferred",
    "cagr_5y": "Higher preferred", "days_since_recorded_high": "Lower preferred",
    "annualized_volatility_1y": "Lower preferred",
    "max_drawdown_3y": "Higher (nearer zero) preferred", "roce": "Higher preferred",
    "debt_to_equity": "Lower preferred", "profit_growth_yoy": "Higher preferred",
}
HISTORY_RANGES = {"1m": 1, "6m": 6, "1y": 12, "3y": 36, "5y": 60}


class LiveWebsiteError(ValueError):
    """Controlled request or prepared-bundle error."""


@lru_cache(maxsize=4)
def _cached_bundle(path: str, manifest_mtime_ns: int) -> LiveMarketBundle:
    del manifest_mtime_ns
    return load_live_market_bundle(path)


def _bundle() -> LiveMarketBundle:
    try:
        manifest = LIVE_BUNDLE_ROOT / "bundle_manifest.json"
        return _cached_bundle(str(LIVE_BUNDLE_ROOT.resolve()), manifest.stat().st_mtime_ns)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise LiveWebsiteError(
            "Prepared LIVE MARKET bundle is unavailable. Run marketdata/runners/prepare_live_market.py."
        ) from exc


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records", double_precision=15))


def format_price(value: Any) -> str:
    return "Unavailable" if value is None or pd.isna(value) else f"₹{float(value):,.2f}"


def format_percent_points(value: Any) -> str:
    if value is None or pd.isna(value):
        return "Unavailable"
    number = float(value)
    return f"{number:+.2f}%"


def format_decimal_percent(value: Any, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "Unavailable"
    return f"{float(value) * 100:+.{digits}f}%"


def format_ist_timestamp(value: str) -> str:
    """Format an aware canonical timestamp for display without changing it."""

    timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise LiveWebsiteError("acquisition timestamp must include a timezone")
    local = timestamp.astimezone(ZoneInfo("Asia/Kolkata"))
    return local.strftime("%d %b %Y, ") + str(int(local.strftime("%I"))) + local.strftime(":%M %p IST")


def validate_v2_detail_invariants(frame: pd.DataFrame) -> int:
    """Require every eligible detail row to expose its canonical V2 inputs."""

    eligible = frame.loc[frame["v2_eligible"].astype(bool)]
    required = [*V2_FACTORS, "research_v2_score", "research_v2_sector_rank"]
    missing_columns = [column for column in required if column not in eligible.columns]
    if missing_columns:
        raise LiveWebsiteError("eligible Research V2 detail data is missing: " + ", ".join(missing_columns))
    numeric = eligible[required].apply(pd.to_numeric, errors="coerce")
    invalid = numeric.isna() | ~numeric.map(lambda value: bool(pd.notna(value) and float("-inf") < value < float("inf")))
    if invalid.any(axis=None):
        ticker = str(eligible.loc[invalid.any(axis=1), "ticker"].iloc[0])
        columns = ", ".join(invalid.columns[invalid.loc[eligible.index[invalid.any(axis=1)][0]]].tolist())
        raise LiveWebsiteError(f"eligible Research V2 detail data is invalid for {ticker}: {columns}")
    return len(eligible)


def _model_status(row: pd.Series, model: str) -> tuple[bool, str, str, Any, Any]:
    if model == "baseline_v1":
        return (
            bool(row["baseline_eligible"]), str(row["baseline_reason_code"]),
            str(row["baseline_reason"]), row.get("baseline_score"), row.get("baseline_sector_rank"),
        )
    if model == "research_v2":
        return (
            bool(row["v2_eligible"]), str(row["v2_reason_code"]),
            str(row["v2_reason"]), row.get("research_v2_score"), row.get("research_v2_sector_rank"),
        )
    raise LiveWebsiteError("model must be baseline_v1 or research_v2")


def _sector_peer_count(frame: pd.DataFrame, row: pd.Series, eligibility_column: str) -> int:
    if pd.isna(row.get("sector")):
        return 0
    return int((frame[eligibility_column].astype(bool) & frame["sector"].eq(row["sector"])).sum())


@lru_cache(maxsize=128)
def _cached_history(path: str, mtime_ns: int) -> pd.DataFrame:
    del mtime_ns
    frame = pd.read_csv(path, usecols=["date", "adjusted_close"])
    frame["date"] = pd.to_datetime(frame["date"], format="%Y-%m-%d", errors="coerce")
    frame["adjusted_close"] = pd.to_numeric(frame["adjusted_close"], errors="coerce")
    frame = frame.dropna().loc[lambda item: item["adjusted_close"].gt(0)]
    return frame.drop_duplicates("date", keep="last").sort_values("date", kind="stable")


def live_history(ticker_value: str, range_value: str = "1y") -> dict[str, Any]:
    """Read one safe cached adjusted-price series without provider access."""

    ticker = str(ticker_value).strip().upper()
    if not SAFE_TICKER.fullmatch(ticker):
        raise LiveWebsiteError("ticker is not a recognized safe identifier")
    selected_range = str(range_value).strip().lower()
    if selected_range not in HISTORY_RANGES:
        raise LiveWebsiteError("range must be one of 1m, 6m, 1y, 3y, or 5y")
    bundle = _bundle()
    if not bundle.market["ticker"].eq(ticker).any():
        raise LiveWebsiteError("stock is not present in the prepared ALL NSE universe")
    path = LIVE_HISTORY_ROOT / f"{ticker}.csv"
    if not path.is_file():
        return {
            "available": False, "ticker": ticker, "range": selected_range,
            "status": "HISTORICAL CHART UNAVAILABLE",
            "message": "Historical chart unavailable for this stock.",
        }
    frame = _cached_history(str(path.resolve()), path.stat().st_mtime_ns).copy()
    trade_date = pd.Timestamp(str(bundle.manifest["snapshot"]["trade_date"]))
    frame = frame.loc[frame["date"].le(trade_date)]
    start = trade_date - pd.DateOffset(months=HISTORY_RANGES[selected_range])
    frame = frame.loc[frame["date"].ge(start)]
    if frame.empty:
        return {
            "available": False, "ticker": ticker, "range": selected_range,
            "status": "HISTORICAL CHART UNAVAILABLE",
            "message": "Historical chart unavailable for this stock in the selected range.",
        }
    points = [{"date": item.date.date().isoformat(), "adjusted_price": float(item.adjusted_close)}
              for item in frame.itertuples(index=False)]
    return {
        "available": True, "ticker": ticker, "range": selected_range,
        "price_basis": "Adjusted price from the prepared current-product history cache",
        "start_date": points[0]["date"], "end_date": points[-1]["date"],
        "point_count": len(points), "points": points,
        "warning": "Historical display only; no forecast or trading signal.",
    }


def live_overview(model: str = "baseline_v1") -> dict[str, Any]:
    """Return the prepared current market; no ranking is recalculated per request."""

    bundle = _bundle()
    validate_v2_detail_invariants(bundle.market)
    frame = bundle.market.copy()
    eligible, codes, reasons, scores, ranks = [], [], [], [], []
    for _, row in frame.iterrows():
        item = _model_status(row, model)
        eligible.append(item[0]); codes.append(item[1]); reasons.append(item[2]); scores.append(item[3]); ranks.append(item[4])
    view = frame[[
        "ticker", "company", "series", "isin", "listing_date", "size_segment",
        "sector", "industry", "basic_industry", "classification_status",
        "trade_date", "snapshot_status", "latest_price", "previous_close",
        "day_change", "day_change_pct", "open", "high", "low", "volume",
    ]].copy()
    view["eligible"] = eligible
    view["reason_code"] = codes
    view["reason"] = reasons
    view["score"] = scores
    view["sector_rank"] = ranks
    view = view.sort_values(
        ["eligible", "sector", "score", "ticker"],
        ascending=[False, True, True if model == "baseline_v1" else False, True],
        na_position="last", kind="stable",
    )
    manifest = bundle.manifest
    return {
        "available": True, "mode": "LIVE MARKET", "model": model,
        "title": "Latest Market Snapshot", "changing_snapshot": True,
        "summary": {
            "all_nse_equities": manifest["universe_count"],
            "price_ready": manifest["snapshot"]["matched_count"],
            "baseline_eligible": manifest["baseline_eligible_count"],
            "research_v2_eligible": manifest["research_v2_eligible_count"],
        },
        "snapshot": manifest["snapshot"],
        "segments": ["ALL NSE", "LARGE", "MID", "SMALL", "MICRO", "OTHER NSE"],
        "segment_counts": manifest["size_segment_counts"],
        "sectors": sorted(frame["sector"].dropna().astype(str).unique().tolist()),
        "industries": sorted(frame["industry"].dropna().astype(str).unique().tolist()),
        "rows": _records(view),
        "bundle_fingerprint": bundle.fingerprint,
        "provenance": {
            "universe_source": manifest["universe_source"],
            "classification_source": manifest["size_membership_source"],
            "price_history": manifest["price_history"],
            "v2_contract": manifest["research_v2_contract"],
            "acquisition_completed_at": manifest["acquisition_completed_at"],
            "acquisition_completed_display": format_ist_timestamp(manifest["acquisition_completed_at"]),
        },
        "warnings": [
            "Latest available EOD snapshot; not a licensed real-time NSE feed.",
            "Scores and ranks are sector-relative, not universal market ranks.",
            "Research screening only; not investment advice or a recommendation.",
        ],
    }


def live_stock(ticker_value: str) -> dict[str, Any]:
    ticker = str(ticker_value).strip().upper()
    if not SAFE_TICKER.fullmatch(ticker):
        raise LiveWebsiteError("ticker is not a recognized safe identifier")
    bundle = _bundle()
    validate_v2_detail_invariants(bundle.market)
    matches = bundle.market.loc[bundle.market["ticker"].eq(ticker)]
    if matches.empty:
        raise LiveWebsiteError("stock is not present in the prepared ALL NSE universe")
    row = matches.iloc[0]
    baseline = {
        "eligible": bool(row["baseline_eligible"]), "score": row.get("baseline_score"),
        "sector_rank": row.get("baseline_sector_rank"), "reason_code": row["baseline_reason_code"],
        "reason": row["baseline_reason"],
        "factors": {name: row.get(column) for name, column in BASELINE_FACTOR_COLUMNS.items()},
        "peer_count": _sector_peer_count(bundle.market, row, "baseline_eligible"),
        "plain_label": "Price-history ranking",
    }
    weights = {name: float(value) for name, value in ResearchV2Weights().as_dict().items()}
    factor_details = [{
        "metric": name, "category": V2_CATEGORIES[name], "value": row.get(name),
        "direction": V2_DIRECTIONS[name], "weight_percent": weights[name],
        "component_score": row.get(f"{name}_score"),
        "contribution": row.get(f"{name}_contribution"),
    } for name in V2_FACTORS]
    v2 = {
        "eligible": bool(row["v2_eligible"]), "score": row.get("research_v2_score"),
        "sector_rank": row.get("research_v2_sector_rank"), "reason_code": row["v2_reason_code"],
        "reason": row["v2_reason"],
        "factors": {name: row.get(name) for name in V2_FACTORS},
        "factor_details": factor_details,
        "peer_count": _sector_peer_count(bundle.market, row, "v2_eligible"),
        "plain_label": "Price + risk + fundamentals",
    }
    identity_columns = (
        "ticker", "company", "series", "isin", "listing_date", "size_segment",
        "sector", "industry", "basic_industry", "classification_status",
        "trade_date", "snapshot_status", "latest_price", "previous_close",
        "day_change", "day_change_pct", "open", "high", "low", "volume",
        "snapshot_source", "classification_source", "universe_source",
    )
    identity = {name: row.get(name) for name in identity_columns}
    identity = _records(pd.DataFrame([identity]))[0]
    baseline = _records(pd.DataFrame([baseline]))[0]
    v2 = _records(pd.DataFrame([v2]))[0]
    return {
        "available": True, "mode": "LIVE MARKET", "stock": identity,
        "baseline_v1": baseline, "research_v2": v2,
        "display": {"price": format_price(row.get("latest_price")), "day_change_pct": format_percent_points(row.get("day_change_pct"))},
        "rank_scope": f"Ranks are within the full eligible {row.get('sector')} sector.",
        "simple_explanation": (
            "Research V2 ranks this company relative to eligible companies in the same sector "
            "using price performance, risk and audited fundamentals."
        ),
        "bundle_fingerprint": bundle.fingerprint,
        "warning": "Latest available research snapshot; not investment advice.",
    }
