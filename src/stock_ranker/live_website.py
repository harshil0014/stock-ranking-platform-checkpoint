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
from stock_ranker.data_state import data_state_status, resolve_accepted_bundle_root
from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_ranker.screener_statements import load_screener_statement_history
from stock_ranker.product_evidence import enrich_presentation
from stock_ranker.v2_config import ResearchV2Weights


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LIVE_STATE_ROOT = PROJECT_ROOT / "data/live_market"
LIVE_BUNDLE_ROOT = LIVE_STATE_ROOT / "current"
LIVE_HISTORY_ROOT = PROJECT_ROOT / "data/live_market/history_cache"
COMPANY_FACT_STATE_ROOT = PROJECT_ROOT / "data/company_facts"
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
SEGMENTS = {"", "ALL", "ALL NSE", "LARGE", "MID", "SMALL", "MICRO", "OTHER NSE", "OTHER BSE"}


class LiveWebsiteError(ValueError):
    """Controlled request or prepared-bundle error."""


@lru_cache(maxsize=4)
def _cached_bundle(path: str, manifest_mtime_ns: int) -> LiveMarketBundle:
    del manifest_mtime_ns
    return load_live_market_bundle(path)


def _bundle() -> LiveMarketBundle:
    try:
        resolved = resolve_accepted_bundle_root(LIVE_STATE_ROOT)
        manifest = resolved / "bundle_manifest.json"
        return _cached_bundle(str(resolved), manifest.stat().st_mtime_ns)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise LiveWebsiteError(
            "No validated market snapshot is available. Autonomous refresh evidence is shown in Data Status."
        ) from exc


@lru_cache(maxsize=4)
def _cached_company_facts(path: str, manifest_mtime_ns: int):
    del manifest_mtime_ns
    return load_company_fact_snapshot(path)


def _company_facts():
    try:
        root = resolve_company_fact_snapshot(COMPANY_FACT_STATE_ROOT)
        manifest = root / "manifest.json"
        return _cached_company_facts(str(root), manifest.stat().st_mtime_ns)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise LiveWebsiteError(
            "No validated company-fact snapshot is available; the accepted market snapshot remains usable."
        ) from exc


def company_facts_coverage() -> dict[str, Any]:
    """Expose measured accepted fact coverage, not provider marketing claims."""

    result = _company_facts()
    return {
        "available": True, "coverage": result.coverage,
        "manifest": result.manifest,
        "warning": "Accepted user-exported Screener data enriches current company pages. Historical research still requires the separate official publication clock.",
    }


def live_data_status() -> dict[str, Any]:
    """Expose accepted-state, freshness and last-known-good behavior without acquisition."""

    try:
        status = data_state_status(LIVE_STATE_ROOT)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise LiveWebsiteError("Validated data-state status is unavailable.") from exc
    status["available"] = True
    status["mode"] = "OFFLINE-FIRST ACCEPTED STATE"
    status["refresh_policy"] = (
        "The local website starts a bounded background refresh. Only complete validated snapshots "
        "are accepted; failures leave the prior snapshot active."
    )
    return status


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records", double_precision=15))


def _product_market_view(market: pd.DataFrame, facts: pd.DataFrame) -> pd.DataFrame:
    """Overlay current-product grouping/ranks without mutating frozen market rows."""

    columns = [
        "ticker", "product_sector", "product_industry", "product_basic_industry",
        "product_classification_evidence", "product_classification_source",
        "product_baseline_yoy_growth", "product_baseline_cagr_3y",
        "product_baseline_cagr_5y", "product_baseline_days_since_recorded_high",
        "product_baseline_score", "product_baseline_sector_rank",
        "product_baseline_eligible", "product_baseline_reason_code",
        "product_baseline_reason",
        "product_price_reference", "product_price_date", "product_price_exchange",
        "product_price_status", "product_price_source", "product_price_source_sha256",
    ]
    available = [column for column in columns if column in facts]
    view = market.merge(facts[available], on="ticker", how="left", validate="one_to_one")
    mapping = {
        "sector": "product_sector", "industry": "product_industry",
        "basic_industry": "product_basic_industry",
        "classification_status": "product_classification_evidence",
        "classification_source": "product_classification_source",
        "baseline_yoy_growth": "product_baseline_yoy_growth",
        "baseline_cagr_3y": "product_baseline_cagr_3y",
        "baseline_cagr_5y": "product_baseline_cagr_5y",
        "baseline_days_since_recorded_high": "product_baseline_days_since_recorded_high",
        "baseline_score": "product_baseline_score",
        "baseline_sector_rank": "product_baseline_sector_rank",
        "baseline_eligible": "product_baseline_eligible",
        "baseline_reason_code": "product_baseline_reason_code",
        "baseline_reason": "product_baseline_reason",
    }
    for target, source in mapping.items():
        if source in view:
            view[target] = view[source]
    if "product_price_reference" in view and view["product_price_reference"].notna().any():
        prior = view["latest_price"].isna() & view["product_price_reference"].notna()
        view.loc[prior, "latest_price"] = view.loc[prior, "product_price_reference"]
        view.loc[prior, "trade_date"] = view.loc[prior, "product_price_date"]
        view.loc[prior, "price_exchange"] = view.loc[prior, "product_price_exchange"]
        view.loc[prior, "snapshot_status"] = view.loc[prior, "product_price_status"]
        view.loc[prior, "snapshot_source"] = view.loc[prior, "product_price_source"]
        view.loc[prior, "price_identity_status"] = "EXACT_IDENTITY_OFFICIAL_PRIOR_TRADE"
    return view


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
            "message": (
                "Exact BSE identity and official EOD price are available, but a defensible "
                "corporate-action-aware adjusted history has not yet been accepted."
                if ticker.startswith("BSE-") else "Historical chart unavailable for this stock."
            ),
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
    fact_result = _company_facts()
    frame = _product_market_view(bundle.market, fact_result.facts) if model == "baseline_v1" else bundle.market.copy()
    for column, default in (
        ("primary_exchange", "NSE"), ("exchange_security_id", pd.NA),
        ("identity_status", "OFFICIAL_NSE_MASTER"),
    ):
        if column not in frame:
            frame[column] = default
    eligible, codes, reasons, scores, ranks = [], [], [], [], []
    for _, row in frame.iterrows():
        item = _model_status(row, model)
        eligible.append(item[0]); codes.append(item[1]); reasons.append(item[2]); scores.append(item[3]); ranks.append(item[4])
    view = frame[[
        "ticker", "company", "series", "isin", "listing_date", "primary_exchange",
        "exchange_security_id", "identity_status", "size_segment",
        "sector", "industry", "basic_industry", "classification_status",
        "trade_date", "snapshot_status", "latest_price", "previous_close",
        "day_change", "day_change_pct", "open", "high", "low", "volume",
    ]].copy()
    view["eligible"] = eligible
    view["reason_code"] = codes
    view["reason"] = reasons
    view["score"] = scores
    view["sector_rank"] = ranks
    screening_columns = [
        "ticker", "market_cap", "pe_ratio", "pb_ratio", "trailing_eps",
        "dividend_yield", "return_on_equity", "roce", "debt_to_equity",
        "profit_growth_yoy", "revenue_growth", "secondary_high_52w",
        "secondary_low_52w", "quarterly_results_status",
        "screener_roce_pct", "screener_roe_pct", "screener_debt_to_equity",
        "screener_profit_growth_pct", "screener_sales_growth_pct",
        "screener_market_cap_crore", "screener_workbook_available",
        "screener_bundle_fingerprint",
    ]
    view = view.merge(fact_result.facts[screening_columns], on="ticker", how="left", validate="one_to_one")
    view = view.sort_values(
        ["eligible", "sector", "score", "ticker"],
        ascending=[False, True, True if model == "baseline_v1" else False, True],
        na_position="last", kind="stable",
    )
    manifest = bundle.manifest
    state = live_data_status()
    return {
        "available": True, "mode": "LIVE MARKET", "model": model,
        "title": "Latest Market Snapshot", "changing_snapshot": True,
        "summary": {
            "all_nse_equities": manifest.get("nse_universe_count", manifest["universe_count"]),
            "supported_equities": manifest["universe_count"],
            "nse_equities": manifest.get("nse_universe_count", manifest["universe_count"]),
            "bse_only_equities": manifest.get("bse_only_count", 0),
            "price_ready": manifest["snapshot"]["matched_count"],
            "baseline_eligible": int(frame["baseline_eligible"].astype(bool).sum()) if model == "baseline_v1" else int(fact_result.facts["product_baseline_eligible"].fillna(False).astype(bool).sum()),
            "research_v2_eligible": manifest["research_v2_eligible_count"],
        },
        "snapshot": manifest["snapshot"],
        "segments": ["ALL", "ALL NSE", "LARGE", "MID", "SMALL", "MICRO", "OTHER NSE", "OTHER BSE"],
        "segment_counts": manifest["size_segment_counts"],
        "sectors": sorted(frame["sector"].dropna().astype(str).unique().tolist()),
        "industries": sorted(frame["industry"].dropna().astype(str).unique().tolist()),
        "rows": _records(view),
        "bundle_fingerprint": bundle.fingerprint,
        "data_state": state,
        "provenance": {
            "universe_source": manifest["universe_source"],
            "ranking_universe_contract": manifest.get("ranking_universe_contract"),
            "excluded_instrument_count": manifest.get("ranking_universe_exclusion_count", 0),
            "excluded_instrument_counts": manifest.get("ranking_universe_exclusion_counts", {}),
            "classification_source": manifest["size_membership_source"],
            "price_history": manifest["price_history"],
            "v2_contract": manifest["research_v2_contract"],
            "acquisition_completed_at": manifest["acquisition_completed_at"],
            "acquisition_completed_display": format_ist_timestamp(manifest["acquisition_completed_at"]),
        },
        "warnings": [
            "Latest available EOD snapshot; not a licensed real-time NSE feed.",
            "Baseline V1 current-product coverage uses Product Classification v1: official evidence first, then exact-identity secondary reference evidence.",
            "Scores and ranks are sector-relative, not universal market ranks.",
            "Research screening only; not investment advice or a recommendation.",
        ],
    }


def live_dashboard(
    sector_value: str = "", model: str = "baseline_v1",
    segment_value: str = "", *, fingerprint_only: bool = False,
) -> dict[str, Any]:
    """Aggregate canonical live and frozen-research views without reranking."""

    bundle = _bundle()
    if model not in {"baseline_v1", "research_v2"}:
        raise LiveWebsiteError("model must be baseline_v1 or research_v2")
    sector = str(sector_value).strip()
    segment = str(segment_value).strip().upper()
    if segment not in SEGMENTS:
        raise LiveWebsiteError("segment must be All, Large, Mid, Small, Micro, or Other NSE")
    if fingerprint_only:
        return {
            "available": True, "bundle_fingerprint": bundle.fingerprint,
            "snapshot": bundle.manifest["snapshot"],
        }
    validate_v2_detail_invariants(bundle.market)
    fact_result = _company_facts()
    frame = _product_market_view(bundle.market, fact_result.facts) if model == "baseline_v1" else bundle.market.copy()
    sectors = sorted(frame["sector"].dropna().astype(str).unique().tolist())
    if sector and sector not in sectors:
        raise LiveWebsiteError("sector is not present in the prepared live bundle")
    eligibility_column = "baseline_eligible" if model == "baseline_v1" else "v2_eligible"
    score_column = "baseline_score" if model == "baseline_v1" else "research_v2_score"
    rank_column = "baseline_sector_rank" if model == "baseline_v1" else "research_v2_sector_rank"

    def card(row: pd.Series) -> dict[str, Any]:
        def numeric(value: Any) -> float | None:
            return None if value is None or pd.isna(value) else float(value)

        peer_count = _sector_peer_count(frame, row, eligibility_column)
        rank = float(row[rank_column])
        item: dict[str, Any] = {
            "ticker": row["ticker"], "company": row["company"],
            "sector": row["sector"], "size_segment": row["size_segment"],
            "latest_price": numeric(row["latest_price"]), "day_change_pct": numeric(row["day_change_pct"]),
            "trade_date": row["trade_date"], "eligible": True,
            "canonical_sector_rank": rank, "canonical_score": float(row[score_column]),
            "eligible_peer_count": peer_count,
            "rank_percentile": 100.0 * rank / peer_count,
            "displayed_leader": False,
        }
        if model == "baseline_v1":
            item["baseline_factors"] = {
                name: numeric(row[column]) for name, column in BASELINE_FACTOR_COLUMNS.items()
            }
        else:
            details = [{
                "metric": name, "category": V2_CATEGORIES[name], "value": numeric(row[name]),
                "direction": V2_DIRECTIONS[name],
                "weight_percent": float(ResearchV2Weights().as_dict()[name]),
                "component_score": numeric(row[f"{name}_score"]),
                "contribution": numeric(row[f"{name}_contribution"]),
            } for name in V2_FACTORS]
            grouped = {
                category: sum(float(detail["contribution"]) for detail in details if detail["category"] == category)
                for category in ("PRICE / GROWTH", "RISK", "FUNDAMENTALS")
            }
            item["factor_details"] = details
            item["strongest_contributions"] = sorted(
                details, key=lambda detail: (-float(detail["contribution"]), detail["metric"])
            )[:3]
            item["grouped_contributions"] = grouped
            item["grouped_contribution_total"] = sum(grouped.values())
        history = live_history(str(row["ticker"]), "6m")
        item["sparkline"] = history if not history.get("available") else {
            key: history[key] for key in ("available", "ticker", "range", "price_basis", "start_date", "end_date", "point_count", "points", "warning")
        }
        return item

    top_four: list[dict[str, Any]] = []
    leaders: list[dict[str, Any]] = []
    sector_frame = frame.loc[frame["sector"].eq(sector)] if sector else frame.iloc[0:0]
    if sector:
        displayed = sector_frame.loc[sector_frame[eligibility_column].astype(bool)]
        if segment not in {"", "ALL", "ALL NSE"}:
            displayed = displayed.loc[displayed["size_segment"].eq(segment)]
        displayed = displayed.sort_values([rank_column, "ticker"], kind="stable").head(4)
        top_four = [card(row) for _, row in displayed.iterrows()]
        if top_four:
            top_four[0]["displayed_leader"] = True
    else:
        eligible = frame.loc[frame[eligibility_column].astype(bool)].sort_values(
            ["sector", rank_column, "ticker"], kind="stable"
        )
        for _, row in eligible.groupby("sector", sort=True).head(1).iterrows():
            leaders.append({
                "sector": row["sector"], "ticker": row["ticker"], "company": row["company"],
                "canonical_sector_rank": float(row[rank_column]), "size_segment": row["size_segment"],
            })

    prepared_count = int(len(sector_frame)) if sector else 0
    baseline_count = int(sector_frame["baseline_eligible"].astype(bool).sum()) if sector else 0
    v2_count = int(sector_frame["v2_eligible"].astype(bool).sum()) if sector else 0
    selected_eligible = baseline_count if model == "baseline_v1" else v2_count
    from stock_ranker.research_website import quant_lab, validation
    evaluation = validation()
    quant = quant_lab()
    primary = evaluation["primary"]
    manifest = bundle.manifest
    return {
        "available": True, "mode": "LATEST PREPARED MARKET SNAPSHOT",
        "model": model, "selected_sector": sector or None,
        "selected_segment": segment or "ALL",
        "sectors": sectors, "segments": ["ALL", "LARGE", "MID", "SMALL", "MICRO", "OTHER NSE", "OTHER BSE"],
        "snapshot": manifest["snapshot"],
        "snapshot_display": {
            "acquired": format_ist_timestamp(manifest["acquisition_completed_at"]),
            "freshness": manifest["snapshot"].get("freshness", "Latest prepared snapshot"),
        },
        "sector_summary": {
            "prepared_companies": prepared_count, "baseline_eligible": baseline_count,
            "research_v2_eligible": v2_count, "selected_model_eligible_peers": selected_eligible,
            "displayed_companies": len(top_four),
            "v2_coverage_ratio": (v2_count / prepared_count) if prepared_count else None,
        },
        "top_four": top_four, "sector_leaders": leaders,
        "selection_warning": (
            "Choose a sector. Sector-relative scores are not compared across sectors."
            if not sector else
            "Research V2 coverage is intentionally strict because missing audited fundamentals are not guessed."
            if model == "research_v2" and selected_eligible < 4 else None
        ),
        "rank_scope": "Filters select displayed companies but never recompute canonical sector ranks.",
        "research_summary": {
            "baseline": "Original-paper price-history methodology operationalized in software.",
            "research_v2": "Adds risk and audited fundamentals.",
            "historical_evaluation": "2022–2025", "primary_horizon": "12 months",
            "research_v2_mean_rank_ic": primary["research_v2_rank_ic"]["mean"],
            "matched_baseline_mean_rank_ic": primary["matched_baseline_rank_ic"]["mean"],
            "primary_sample": f"{primary['rank_ic_observation_count']} sector-date observations",
            "interpretation": evaluation["interpretation"],
            "alphalens_exact_matches": quant["alphalens"]["exact_ic_matches"],
            "alphalens_total_checks": quant["alphalens"]["ic_rows"],
            "empyrical_passes": quant["empyrical"]["passes"],
            "empyrical_metric_summary": quant["empyrical_metric_summary"],
            "empyrical_explained_differences": quant["empyrical"]["explained_differences"],
            "empyrical_failures": quant["empyrical"]["failures"],
        },
        "bundle_fingerprint": bundle.fingerprint,
        "warnings": [
            "Sector Rank is canonical across the full eligible sector; dashboard filters do not rerank.",
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
    fact_result = _company_facts()
    fact_matches = fact_result.facts.loc[fact_result.facts["ticker"].eq(ticker)]
    if fact_matches.empty:
        raise LiveWebsiteError("stock is missing from the accepted company-fact layer")
    fact = fact_matches.iloc[0]
    product = _product_market_view(bundle.market, fact_result.facts)
    row = product.loc[product["ticker"].eq(ticker)].iloc[0]
    baseline = {
        "eligible": bool(row["baseline_eligible"]), "score": row.get("baseline_score"),
        "sector_rank": row.get("baseline_sector_rank"), "reason_code": row["baseline_reason_code"],
        "reason": row["baseline_reason"],
        "factors": {name: row.get(column) for name, column in BASELINE_FACTOR_COLUMNS.items()},
        "peer_count": _sector_peer_count(bundle.market, row, "baseline_eligible"),
        "plain_label": "Baseline V1 — Current Product Coverage",
        "classification_scope": "Product Classification v1; historical research classifications remain frozen",
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
        "primary_exchange", "exchange_security_id", "identity_status",
        "sector", "industry", "basic_industry", "classification_status",
        "trade_date", "snapshot_status", "latest_price", "previous_close",
        "day_change", "day_change_pct", "open", "high", "low", "volume",
        "snapshot_source", "price_exchange", "price_identity_status",
        "classification_source", "universe_source",
    )
    identity = {name: row.get(name) for name in identity_columns}
    identity = _records(pd.DataFrame([identity]))[0]
    baseline = _records(pd.DataFrame([baseline]))[0]
    v2 = _records(pd.DataFrame([v2]))[0]
    def clean(value: Any) -> Any:
        if value is None or pd.isna(value):
            return None
        return value.item() if hasattr(value, "item") else value

    def values(*names: str) -> dict[str, Any]:
        return {name: clean(fact.get(name)) for name in names}

    is_financial = str(fact.get("official_sector", "")).strip().lower() in {
        "financial services", "banking", "insurance",
    }
    has_screener_current = clean(fact.get("screener_current_status")) is not None
    has_screener_workbook = bool(fact.get("screener_workbook_available"))
    has_screener_ownership = any(clean(fact.get(name)) is not None for name in (
        "screener_promoter_holding_pct", "screener_public_holding_pct",
        "screener_fii_holding_pct", "screener_dii_holding_pct",
    ))
    same = fact_result.facts.loc[fact_result.facts["ticker"].ne(ticker)].copy()
    peer_basis = None
    for column, label in (("product_basic_industry", "product basic industry"),
                          ("product_industry", "product industry"),
                          ("product_sector", "product sector")):
        if not pd.isna(fact.get(column)):
            candidates = same.loc[same[column].eq(fact[column])]
            if not candidates.empty:
                same, peer_basis = candidates, label
                break
    peer_rows = same.sort_values(["product_baseline_eligible", "product_baseline_sector_rank", "ticker"],
                                 ascending=[False, True, True], na_position="last", kind="stable").head(12)
    peer_view = peer_rows[[
        "ticker", "company", "product_sector", "product_industry",
        "latest_price", "product_baseline_eligible", "product_baseline_sector_rank", "v2_eligible",
        "research_v2_sector_rank",
    ]].rename(columns={"product_sector": "official_sector", "product_industry": "official_industry", "product_baseline_eligible": "baseline_eligible", "product_baseline_sector_rank": "baseline_sector_rank"})
    peers = _records(peer_view) if peer_basis else []
    for peer in peers:
        if peer.get('latest_price') is None:
            evidence = peer_rows.loc[peer_rows.ticker.eq(peer['ticker'])].iloc[0]
            peer['latest_price'] = clean(evidence.get('product_price_reference'))
            peer['price_date'] = clean(evidence.get('product_price_date'))
            peer['price_status'] = clean(evidence.get('product_price_status'))
    facts = {
        "schema_version": fact_result.manifest["schema_version"],
        "fingerprint": fact_result.manifest["fingerprint"],
        "overview": {
            "status": "CANONICAL_IDENTITY_VERIFIED",
            "values": values("ticker", "company", "isin", "primary_exchange", "exchange_security_id", "series", "listing_date", "identity_status"),
        },
        "classification": {
            "status": clean(fact.get("product_classification_evidence")),
            "reason": clean(fact.get("classification_reason")),
            "values": values("product_classification_version", "product_sector", "product_industry", "product_basic_industry", "product_classification_evidence", "product_classification_source", "product_classification_as_of", "official_sector", "official_industry", "official_basic_industry", "official_classification_source", "secondary_sector", "secondary_industry", "screener_industry_group", "screener_industry", "size_segment"),
            "professor_taxonomy_is_separate": True,
        },
        "market_data": {
            "status": "LATEST_ACCEPTED_EOD" if clean(fact.get("latest_price")) is not None else (clean(fact.get("product_price_status")) or "NO_ACCEPTED_CURRENT_TRADE"),
            "reason": f"Latest accepted official trade date: {row.get('trade_date')}; market snapshot date: {fact.get('trade_date')}",
            "values": {**values("trade_date", "latest_price", "previous_close", "day_change", "day_change_pct", "open", "high", "low", "volume", "traded_value", "transaction_count"),
                       "trade_date": clean(row.get("trade_date")), "latest_price": clean(row.get("latest_price")),
                       **values("product_price_source", "product_price_source_sha256", "product_price_identity_evidence")},
        },
        "price_history": {
            "status": clean(fact.get("history_status")), "reason": clean(fact.get("history_reason")),
            "values": values("history_start_date", "history_end_date", "history_observation_count", "history_1y_usable", "history_3y_usable", "history_5y_usable", "high_52w", "high_52w_date", "low_52w", "low_52w_date", "recorded_high", "recorded_high_date", "history_price_basis", "corporate_action_history_status"),
        },
        "valuation": {
            "status": clean(fact.get("valuation_status")), "reason": clean(fact.get("valuation_reason")),
            "values": values("market_cap", "shares_outstanding", "pe_ratio", "pb_ratio", "trailing_eps", "book_value", "dividend_yield", "beta", "official_market_cap", "official_pe_ratio", "official_pb_ratio", "screener_market_cap_crore", "screener_current_price", "screener_pe_ratio", "screener_pb_ratio", "screener_dividend_yield_pct", "screener_eps", "official_ratio_formula_version", "official_ratio_reporting_basis"),
        },
        "company_profile_secondary_reference": {
            "status": clean(fact.get("secondary_identity_status")),
            "reason": clean(fact.get("secondary_reason")),
            "values": values("company_profile", "secondary_sector", "secondary_industry", "secondary_source", "secondary_source_as_of", "secondary_freshness_status"),
        },
        "quarterly_results": {
            "status": "SCREENER_STANDALONE_HISTORY_AVAILABLE" if has_screener_workbook else clean(fact.get("quarterly_results_status")),
            "reason": "Official exchange XBRL facts remain first; accepted exact-ISIN Screener current and standalone history are separately labelled and do not alter historical PIT eligibility.",
            "values": values("official_quarterly_period_end", "official_quarterly_reporting_basis", "official_quarterly_revenue", "official_quarterly_pat", "screener_latest_quarter_sales_crore", "screener_latest_quarter_pat_crore", "screener_quarterly_sales_growth_pct", "screener_quarterly_profit_growth_pct", "secondary_quarterly_period_end", "secondary_quarterly_revenue", "secondary_quarterly_net_income", "secondary_reporting_basis"),
        },
        "annual_financials": {
            "status": "NORMALIZED_OFFICIAL_FACTS_AVAILABLE" if clean(fact.get("official_annual_period_end")) else ("SCREENER_STANDALONE_HISTORY_AVAILABLE" if bool(fact.get("screener_historical_financials_available")) else clean(fact.get("annual_report_status"))),
            "reason": "Accepted official exchange XBRL facts are shown with their period and standalone/consolidated basis; audited annual-report and secondary evidence remain separately identified." if clean(fact.get("official_annual_period_end")) else clean(fact.get("annual_report_reason")),
            "values": values("official_annual_period_end", "official_annual_reporting_basis", "official_annual_revenue", "official_annual_pat", "official_annual_eps", "annual_profit_current", "annual_profit_prior", "annual_profit_unit", "annual_profit_label", "annual_report_financial_year", "annual_report_reporting_basis", "fundamental_contract", "screener_sales_crore", "screener_profit_after_tax_crore", "screener_eps", "screener_historical_financials_available", "screener_workbook_available", "secondary_annual_period_end", "secondary_annual_revenue", "secondary_annual_ebitda", "secondary_annual_net_income", "secondary_annual_eps", "secondary_reporting_basis"),
        },
        "balance_sheet": {"status": clean(fact.get("balance_sheet_status")), "reason": "Official exchange XBRL balance-sheet facts are shown first; secondary-provider fields retain their separate unspecified reporting basis.", "values": values("official_balance_period_end", "official_total_assets", "official_borrowings", "official_equity", "official_cash", "secondary_balance_period_end", "secondary_total_assets", "secondary_total_debt", "secondary_stockholders_equity", "secondary_cash_balance", "secondary_reporting_basis")},
        "cash_flow": {"status": clean(fact.get("cash_flow_status")), "reason": "Official exchange XBRL operating cash flow is shown with its period; secondary-provider fields remain separately labelled.", "values": values("official_cash_flow_period_end", "official_operating_cash_flow", "secondary_cash_flow_period_end", "secondary_operating_cash_flow", "secondary_free_cash_flow", "secondary_capital_expenditure", "secondary_reporting_basis")},
        "ratios_quality": {
            "status": "STRICT_V2_FACTS_AVAILABLE" if bool(fact.get("v2_eligible")) else ("SCREENER_CURRENT_REFERENCE_AVAILABLE" if has_screener_current else ("FINANCIAL_INSTITUTION_CONVENTIONAL_RATIO_NOT_ASSUMED" if is_financial else "STRICT_RATIO_EVIDENCE_INCOMPLETE")),
            "reason": "Accepted values use the audited standalone V2 contract; definitions are shown in Source Evidence." if bool(fact.get("v2_eligible")) else ("Accepted Screener current ratios are available for company research, but do not become historical PIT evidence without an official dissemination clock." if has_screener_current else ("Conventional industrial ROCE and leverage definitions are not silently imposed on a financial institution." if is_financial else "Missing ratios are not estimated from incompatible or unaudited evidence.")),
            "values": values("roce", "debt_to_equity", "profit_growth_yoy", "screener_roce_pct", "screener_roe_pct", "screener_debt_to_equity", "screener_profit_growth_pct", "screener_sales_growth_pct", "screener_operating_margin_pct", "screener_return_on_assets_pct", "screener_current_ratio", "screener_interest_coverage", "screener_cash_conversion_quality", "screener_working_capital_days", "screener_debtor_days", "screener_inventory_days", "screener_asset_turnover", "official_return_on_equity", "official_debt_to_equity", "official_revenue_growth", "official_profit_growth_yoy", "official_net_margin", "official_ratio_formula_version", "official_ratio_reporting_basis", "return_on_equity", "secondary_debt_to_equity", "revenue_growth", "secondary_profit_growth", "operating_margin", "profit_margin"),
        },
        "screener_current_reference": {
            "status": "SCREENER_CURRENT_REFERENCE_AVAILABLE" if has_screener_current else "NO_SCREENER_CURRENT_REFERENCE",
            "reason": "User-supplied Screener Premium export matched to the accepted Screener bundle. These are current/reference observations only and do not alter frozen historical PIT research.",
            "values": values(
                "screener_match_method", "screener_source_isin",
                "screener_company_name", "screener_nse_code", "screener_bse_code",
                "screener_industry_group", "screener_industry",
                "screener_market_cap_crore", "screener_current_price",
                "screener_pe_ratio", "screener_pb_ratio", "screener_dividend_yield_pct",
                "screener_eps", "screener_profit_after_tax_crore", "screener_sales_crore",
                "screener_roce_pct", "screener_roe_pct", "screener_debt_to_equity",
                "screener_profit_growth_pct", "screener_sales_growth_pct",
                "screener_operating_margin_pct", "screener_return_on_assets_pct",
                "screener_current_ratio", "screener_interest_coverage",
                "screener_cash_conversion_quality", "screener_operating_cash_flow_crore",
                "screener_free_cash_flow_crore", "screener_working_capital_days",
                "screener_debtor_days", "screener_inventory_days",
                "screener_asset_turnover", "screener_latest_quarter_sales_crore",
                "screener_latest_quarter_pat_crore", "screener_quarterly_sales_growth_pct",
                "screener_quarterly_profit_growth_pct", "screener_promoter_holding_pct",
                "screener_public_holding_pct", "screener_fii_holding_pct",
                "screener_dii_holding_pct", "screener_pledged_pct",
                "screener_total_debt_crore", "screener_cash_conversion_cycle_days",
                "screener_roce_3y_avg_pct", "screener_roic_pct", "screener_croic_pct",
                "screener_sales_growth_3y_pct", "screener_sales_growth_5y_pct",
                "screener_profit_growth_3y_pct", "screener_profit_growth_5y_pct",
                "screener_roe_3y_avg_pct", "screener_roe_5y_avg_pct",
                "screener_return_3m_pct", "screener_return_6m_pct",
                "screener_return_1y_pct", "screener_return_3y_pct",
                "screener_return_5y_pct", "screener_peg_ratio",
                "screener_enterprise_value_crore", "screener_ev_ebitda",
                "screener_price_to_free_cash_flow", "screener_price_to_sales",
                "screener_industry_pe", "screener_earnings_yield_pct",
                "screener_fii_holding_change_pct", "screener_dii_holding_change_pct",
                "screener_promoter_holding_change_pct",
                "screener_historical_financials_available", "screener_workbook_available",
                "screener_source_observed_at", "screener_bundle_fingerprint",
            ),
        },
        "shareholding": {"status": clean(fact.get("shareholding_status")) if clean(fact.get("shareholding_as_of")) else ("SCREENER_CURRENT_REFERENCE_AVAILABLE" if has_screener_ownership else clean(fact.get("shareholding_status"))), "reason": "Official Regulation 31 values are shown when present; accepted Screener ownership is a separately named current/reference fallback.", "values": values("shareholding_as_of", "promoter_holding_pct", "public_holding_pct", "fii_holding_pct", "dii_holding_pct", "promoter_pledge_pct", "official_total_shares", "screener_promoter_holding_pct", "screener_public_holding_pct", "screener_fii_holding_pct", "screener_dii_holding_pct", "screener_pledged_pct")},
        "peers": {"status": "EVIDENCE_MATCHED_PEERS" if peers else "NO_CLASSIFIED_PEER_SET", "reason": f"Peers share this security's {peer_basis}. Canonical ranks are not recalculated." if peer_basis else "No authoritative classification exists from which to form peers.", "basis": peer_basis, "rows": peers},
        "corporate_actions_announcements_documents": {
            "status": clean(fact.get("documents_status")),
            "reason": "Official exchange actions and document metadata are indexed without downloading every linked document; all displayed links retain their source provenance.",
            "values": values("corporate_actions_status", "official_action_count", "latest_corporate_action_date", "announcements_status", "latest_document_type", "latest_document_date", "latest_document_url", "latest_document_source_sha256", "annual_report_source_url", "annual_report_pdf_sha256"),
        },
        "professor_reference": {
            "status": "PROFESSOR_COHORT_EVIDENCE" if bool(fact.get("professor_cohort")) else "NOT_IN_PROFESSOR_COHORT",
            "reason": "Professor taxonomy and ranks are displayed separately and never replace model sectors or ranks.",
            "values": values("professor_supplied_rank", "workbook_strategy_rank", "professor_industry", "professor_workbook_current_price", "professor_workbook_market_cap", "professor_workbook_cagr_10y", "professor_workbook_cagr_5y", "professor_workbook_cagr_3y", "professor_workbook_cagr_1y", "professor_evidence_status"),
        },
        "source_evidence": {
            "status": "PROVENANCE_PRESERVED",
            "values": values("snapshot_source", "official_classification_source", "classification_evidence_status", "ranking_classification_grade", "official_evidence_freshness", "latest_document_url", "annual_report_source_url", "annual_report_pdf_sha256", "fundamental_contract", "secondary_source", "secondary_source_as_of", "secondary_freshness_status", "screener_current_status", "screener_source_observed_at", "screener_bundle_fingerprint", "screener_company_name", "screener_nse_code", "screener_bse_code"),
        },
        "historical_validation": {
            "status": "FROZEN_RESEARCH_SEPARATE",
            "reason": "Current fact refreshes do not modify frozen point-in-time experiments or their fingerprints.",
            "values": {},
        },
    }
    enrich_presentation(facts, fact)
    screener_history = load_screener_statement_history(
        ticker,
        str(row.get("isin") or ""),
    )
    return {
        "available": True, "mode": "LIVE MARKET", "stock": identity,
        "baseline_v1": baseline, "research_v2": v2,
        "company_facts": facts,
        "screener_financial_history": screener_history,
        "display": {"price": format_price(row.get("latest_price")), "day_change_pct": format_percent_points(row.get("day_change_pct"))},
        "rank_scope": f"Ranks are within the full eligible {row.get('sector')} sector.",
        "simple_explanation": (
            "Research V2 ranks this company relative to eligible companies in the same sector "
            "using price performance, risk and audited fundamentals."
            if bool(row["v2_eligible"])
            else (
                "Research V2 requires price, risk and audited fundamental evidence. "
                f"This company is not currently eligible: {row['v2_reason']}"
            )
        ),
        "bundle_fingerprint": bundle.fingerprint,
        "warning": "Latest available research snapshot; not investment advice.",
    }
