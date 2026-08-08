"""Canonical import and presentation boundary for the local research website."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from io import StringIO
import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_ranker.baseline import (
    calculate_baseline_rankings,
    get_top_stocks_by_sector,
)
from stock_ranker.config import BaselineConfig
from stock_ranker.contracts import METRIC_COLUMNS, RANK_COLUMNS
from stock_ranker.nse_snapshot import parse_nse_snapshot
from stock_ranker.research_v2 import (
    ResearchV2Inputs,
    calculate_research_v2,
    get_top_research_v2_by_sector,
)
from stock_ranker.v2_config import ResearchV2Config
from stock_ranker.v2_contracts import (
    V2_CONTRIBUTION_COLUMNS,
    V2_METRIC_COLUMNS,
    V2_SCORE_COLUMNS,
)


METHOD_BASELINE = "baseline_v1"
METHOD_RESEARCH_V2 = "research_v2"
METHODS = (METHOD_BASELINE, METHOD_RESEARCH_V2)
INPUT_OFFICIAL_NSE_SNAPSHOT = "official_nse_snapshot"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

DATA_MODE_LABELS = {
    "real_current_snapshot": "REAL CURRENT SNAPSHOT",
    "real_historical_point_in_time": "REAL HISTORICAL / POINT-IN-TIME",
    "synthetic_research_test": "SYNTHETIC RESEARCH TEST",
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_FILES = {
    METHOD_BASELINE: {"baseline": PROJECT_ROOT / "data/input/synthetic_stocks.csv"},
    METHOD_RESEARCH_V2: {
        "universe": PROJECT_ROOT / "data/input/v2_universe.csv",
        "prices": PROJECT_ROOT / "data/input/v2_prices.csv",
        "fundamentals": PROJECT_ROOT / "data/input/v2_fundamentals.csv",
    },
}


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must not be blank")
    return value.strip()


def _parse_csv_text(value: Any, label: str) -> pd.DataFrame:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} CSV is required and must not be empty")
    try:
        frame = pd.read_csv(StringIO(value))
    except (pd.errors.ParserError, UnicodeError, ValueError) as exc:
        raise ValueError(f"Could not parse {label} CSV: {exc}") from exc
    if frame.empty:
        raise ValueError(f"{label} CSV must contain at least one row")
    return frame


def _iso_date(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must use valid ISO YYYY-MM-DD format")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field} must use valid ISO YYYY-MM-DD format") from exc
    return parsed.isoformat()


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    normalized = frame.copy()
    for column in normalized.select_dtypes(include=["datetime", "datetimetz"]):
        normalized[column] = normalized[column].dt.strftime("%Y-%m-%d")
    return json.loads(normalized.to_json(orient="records", double_precision=15))


def _decode_upload(files: dict[str, Any], field: str) -> bytes:
    value = files.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} is required")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"{field} must be valid base64 data") from exc
    if not decoded:
        raise ValueError(f"{field} must not be empty")
    if len(decoded) > MAX_UPLOAD_BYTES:
        raise ValueError(f"{field} exceeds the 25 MiB decoded upload limit")
    return decoded


def _official_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    files = payload.get("files")
    if not isinstance(files, dict):
        raise ValueError("files must be supplied for the official snapshot")
    nifty_name = _required_text(files, "nifty_filename")
    bhavcopy_name = _required_text(files, "bhavcopy_filename")
    result = parse_nse_snapshot(
        _decode_upload(files, "nifty_base64"),
        _decode_upload(files, "bhavcopy_base64"),
        nifty_filename=nifty_name,
        bhavcopy_filename=bhavcopy_name,
    )
    trade_date = result.provenance["trade_date"]
    return {
        "mode": "real_snapshot",
        "analysis_available": False,
        "ranking_notice": (
            "Ranking unavailable for this snapshot alone. Historical price "
            "data is required for Baseline V1. Historical point-in-time prices "
            "and fundamentals are required for Research V2."
        ),
        "snapshot": _records(result.snapshot),
        "export_csv": result.snapshot.to_csv(index=False, lineterminator="\n"),
        "export_filename": f"nifty50_nse_snapshot_{trade_date}.csv",
        "provenance": result.provenance,
    }


def _common_provenance(
    *, source_label: str, data_mode: str, as_of_date: str, method: str,
    universe: str, company_count: int, eligible_count: int, ineligible_count: int,
) -> dict[str, Any]:
    warnings = [
        "Research screening only; not investment advice or a recommendation.",
        "Inputs are processed locally. No live market data is fetched.",
    ]
    if data_mode == "synthetic_research_test":
        warnings.append(
            "Synthetic research test: all companies and values are fictional."
        )
    elif data_mode == "real_current_snapshot":
        warnings.append(
            "Current-snapshot mode is not a point-in-time historical claim."
        )
    else:
        warnings.append(
            "Point-in-time behavior relies on supplied availability dates and source accuracy."
        )
    if method == METHOD_BASELINE:
        warnings.append(
            "Baseline V1 uses the project's equal-rank-mean approximation; it is not claimed as the paper's exact final formula."
        )
    else:
        warnings.append(
            "Research V2 scores are relative within sectors and are not comparable across sectors."
        )
    return {
        "source_label": source_label,
        "data_mode": DATA_MODE_LABELS[data_mode],
        "data_mode_key": data_mode,
        "as_of_date": as_of_date,
        "methodology": (
            "Baseline V1 / Original Paper signals (project approximation)"
            if method == METHOD_BASELINE
            else "Research V2 point-in-time weighted scoring"
        ),
        "universe": universe,
        "company_count": company_count,
        "eligible_count": eligible_count,
        "ineligible_count": ineligible_count,
        "warnings": warnings,
    }


def _baseline(payload: dict[str, Any], files: dict[str, Any]) -> dict[str, Any]:
    data = _parse_csv_text(files.get("baseline"), "Baseline V1 input")
    rankings = calculate_baseline_rankings(data, BaselineConfig(top_n=5))
    dates = sorted(rankings["as_of_date"].unique().tolist())
    if len(dates) != 1:
        raise ValueError(
            "Website Baseline V1 input must contain exactly one as_of_date"
        )
    requested_date = payload.get("ranking_date")
    if requested_date and _iso_date(requested_date, "ranking_date") != dates[0]:
        raise ValueError("ranking_date does not match the Baseline V1 as_of_date")

    top = get_top_stocks_by_sector(rankings, 5)
    selected = set(top["ticker"].tolist())
    rows: list[dict[str, Any]] = []
    for row in _records(rankings):
        rows.append({
            "ticker": row["ticker"],
            "company": row["company"],
            "sector": row["sector"],
            "rank": row["sector_rank"],
            "score": row["baseline_score"],
            "eligible": True,
            "status": "Eligible",
            "selected_top_5": row["ticker"] in selected,
            "reason": "Ranked from the four accepted Baseline V1 signals.",
            "explanation": {
                "metrics": {name: row[name] for name in METRIC_COLUMNS},
                "metric_ranks": {name: row[name] for name in RANK_COLUMNS},
                "combined_score": row["baseline_score"],
                "method_version": row["method_version"],
                "interpretation": "Lower Baseline V1 score and sector rank are better.",
            },
        })

    export = rankings.copy()
    export.insert(len(export.columns) - 1, "eligible", True)
    export.insert(len(export.columns) - 1, "status", "Eligible")
    source = _required_text(payload, "source_label")
    universe = str(payload.get("universe") or "Uploaded Baseline V1 universe").strip()
    return {
        "method": METHOD_BASELINE,
        "results": rows,
        "export_csv": export.to_csv(index=False, lineterminator="\n"),
        "export_filename": f"baseline_v1_rankings_{dates[0]}.csv",
        "provenance": _common_provenance(
            source_label=source, data_mode=payload["data_mode"],
            as_of_date=dates[0], method=METHOD_BASELINE, universe=universe,
            company_count=len(rankings), eligible_count=len(rankings),
            ineligible_count=0,
        ),
    }


def _research_v2(payload: dict[str, Any], files: dict[str, Any]) -> dict[str, Any]:
    ranking_date = _iso_date(payload.get("ranking_date"), "ranking_date")
    config = ResearchV2Config(
        ranking_date=datetime.strptime(ranking_date, "%Y-%m-%d").date(), top_n=5
    )
    inputs = ResearchV2Inputs(
        universe=_parse_csv_text(files.get("universe"), "universe"),
        prices=_parse_csv_text(files.get("prices"), "prices"),
        fundamentals=_parse_csv_text(files.get("fundamentals"), "fundamentals"),
    )
    result = calculate_research_v2(inputs, config)
    top = get_top_research_v2_by_sector(result.rankings, 5)
    selected = set(top["ticker"].tolist())
    ranked = {row["ticker"]: row for row in _records(result.rankings)}
    eligibility = _records(result.eligibility)
    rows: list[dict[str, Any]] = []
    export_rows: list[dict[str, Any]] = []
    for status_row in eligibility:
        row = ranked.get(status_row["ticker"])
        if row:
            explanation = {
                "metrics": {name: row[name] for name in V2_METRIC_COLUMNS},
                "component_scores": {name: row[name] for name in V2_SCORE_COLUMNS},
                "contributions": {
                    name: row[name] for name in V2_CONTRIBUTION_COLUMNS
                },
                "combined_score": row["research_v2_score"],
                "method_version": row["method_version"],
                "interpretation": "Higher Research V2 score is better within this sector.",
            }
            display = {
                "ticker": row["ticker"], "company": row["company"],
                "sector": row["sector"], "rank": row["sector_rank"],
                "score": row["research_v2_score"], "eligible": True,
                "status": "Eligible", "reason": status_row["reason"],
                "selected_top_5": row["ticker"] in selected,
                "explanation": explanation,
            }
            export_rows.append({**row, "status": "Eligible", "reason_code": "ELIGIBLE", "reason": status_row["reason"]})
        else:
            display = {
                "ticker": status_row["ticker"],
                "company": status_row["company"],
                "sector": status_row["sector"],
                "rank": None, "score": None, "eligible": False,
                "status": "Ineligible", "reason": status_row["reason"],
                "selected_top_5": False,
                "explanation": {
                    "reason_code": status_row["reason_code"],
                    "reason": status_row["reason"],
                    "interpretation": "No score was fabricated for an ineligible company.",
                },
            }
            export_rows.append({
                **status_row, "status": "Ineligible", "sector_rank": None,
                "research_v2_score": None,
            })
        rows.append(display)
    rows.sort(key=lambda item: (
        item["sector"], not item["eligible"],
        item["score"] is None, -(item["score"] or 0), item["ticker"],
    ))

    source = _required_text(payload, "source_label")
    universe_label = str(payload.get("universe") or "Uploaded Research V2 universe").strip()
    ineligible = sum(not row["eligible"] for row in rows)
    return {
        "method": METHOD_RESEARCH_V2,
        "results": rows,
        "export_csv": pd.DataFrame(export_rows).to_csv(
            index=False, lineterminator="\n"
        ),
        "export_filename": f"research_v2_rankings_{ranking_date}.csv",
        "provenance": _common_provenance(
            source_label=source, data_mode=payload["data_mode"],
            as_of_date=ranking_date, method=METHOD_RESEARCH_V2,
            universe=universe_label, company_count=len(rows),
            eligible_count=len(rows) - ineligible, ineligible_count=ineligible,
        ),
    }


def analyze_website_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a website request and dispatch to an accepted ranking engine."""

    if not isinstance(payload, dict):
        raise TypeError("request must be a JSON object")
    if payload.get("input_source") == INPUT_OFFICIAL_NSE_SNAPSHOT:
        return _official_snapshot(payload)
    method = payload.get("method")
    if method not in METHODS:
        raise ValueError("method must be baseline_v1 or research_v2")

    if payload.get("use_synthetic_sample") is True:
        files = {
            name: path.read_text(encoding="utf-8")
            for name, path in SYNTHETIC_FILES[method].items()
        }
        payload = {
            **payload,
            "source_label": "Committed fictional research sample",
            "data_mode": "synthetic_research_test",
            "universe": "Fictional companies committed for automated research tests",
        }
        if method == METHOD_RESEARCH_V2:
            payload["ranking_date"] = "2026-06-30"
    else:
        raw_files = payload.get("files")
        if not isinstance(raw_files, dict):
            raise ValueError("files must be supplied for an uploaded dataset")
        files = raw_files

    data_mode = payload.get("data_mode")
    if data_mode not in DATA_MODE_LABELS:
        raise ValueError("data_mode is invalid")
    if method == METHOD_BASELINE and data_mode == "real_historical_point_in_time":
        raise ValueError(
            "Baseline V1 snapshot input cannot be labelled point-in-time historical"
        )
    return _baseline(payload, files) if method == METHOD_BASELINE else _research_v2(payload, files)
