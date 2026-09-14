"""PIT-safe normalization for Upstox Company Fundamentals responses.

Upstox is a structured extraction source, not the historical availability
clock. A response fetched today remains a present-day observation even when it
contains older financial periods. This module therefore emits candidates only;
Research V2 promotion still requires an exact official exchange filing match
and exchange dissemination timestamp through the existing PIT bridge.

The Upstox key-ratios endpoint is deliberately excluded because its ROCE and
other ratios are documented as current values, not historical PIT values.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import math
import re
from typing import Any, Final

import pandas as pd


UPSTOX_API_BASE: Final = "https://api.upstox.com/v2/fundamentals"
UPSTOX_SOURCE_NAME: Final = "UPSTOX_COMPANY_FUNDAMENTALS_V2"
PIT_CANDIDATE_STATUS: Final = "REQUIRES_EXACT_OFFICIAL_FILING_MATCH"
SUPPORTED_BASES: Final = {"STANDALONE": "standalone", "CONSOLIDATED": "consolidated"}
ISIN_RE: Final = re.compile(r"^IN[A-Z0-9]{10}$")

FACT_COLUMNS: Final = (
    "isin", "reporting_basis", "period_end", "metric", "particular", "value",
    "unit", "source_observed_at", "source_name", "source_record_id",
    "source_endpoint", "raw_sha256", "pit_candidate_status",
)
PROFIT_PAIR_COLUMNS: Final = (
    "isin", "period_end", "reporting_basis", "current_pat", "prior_pat",
    "source_observed_at", "source_name", "source_record_id", "source_endpoint",
    "raw_sha256", "pit_candidate_status",
)


@dataclass(frozen=True, slots=True)
class UpstoxNormalizedBundle:
    income_facts: pd.DataFrame
    balance_facts: pd.DataFrame
    profit_pairs: pd.DataFrame


def canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ) + "\n").encode("utf-8")


def payload_sha256(payload: Any) -> str:
    return sha256(canonical_json_bytes(payload)).hexdigest()


def validate_isin(isin: str) -> str:
    value = str(isin).strip().upper()
    if not ISIN_RE.fullmatch(value):
        raise ValueError(f"invalid Indian ISIN: {isin!r}")
    return value


def normalize_basis(reporting_basis: str) -> tuple[str, str]:
    canonical = str(reporting_basis).strip().upper()
    if canonical not in SUPPORTED_BASES:
        raise ValueError(f"unsupported reporting basis: {reporting_basis!r}")
    return canonical, SUPPORTED_BASES[canonical]


def normalize_observed_at(value: str | datetime) -> str:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        raise ValueError("source_observed_at must be timezone-aware")
    return parsed.tz_convert("UTC").isoformat()


def period_label_to_end(label: str) -> str:
    text = str(label).strip()
    try:
        parsed = datetime.strptime(text, "%b %Y")
    except ValueError as exc:
        raise ValueError(f"unsupported Upstox period label: {label!r}") from exc
    day = monthrange(parsed.year, parsed.month)[1]
    return f"{parsed.year:04d}-{parsed.month:02d}-{day:02d}"


def _finite(value: Any, *, field: str) -> float:
    if value is None or isinstance(value, bool):
        raise ValueError(f"{field}: missing numeric value")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}: invalid numeric value {value!r}") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field}: non-finite numeric value")
    return result


def _response_data(
    payload: dict[str, Any], *, expected_basis: str,
    expected_time_period: str | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("status") != "success":
        raise ValueError("Upstox response is not a successful payload")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Upstox response has no data object")
    actual_basis = str(data.get("type", "")).strip().lower()
    if actual_basis != expected_basis:
        raise ValueError(
            f"Upstox reporting basis mismatch: expected {expected_basis}, got {actual_basis or 'blank'}"
        )
    if expected_time_period is not None:
        actual_period = str(data.get("time_period", "")).strip().lower()
        if actual_period != expected_time_period:
            raise ValueError(
                f"Upstox time-period mismatch: expected {expected_time_period}, got {actual_period or 'blank'}"
            )
    unit = str(data.get("units_in", "")).strip().lower()
    if unit != "crore":
        raise ValueError(f"unsupported Upstox monetary unit: {unit or 'blank'}")
    return data


def _row(
    *, isin: str, basis: str, period_end: str, metric: str, particular: str,
    value: float, observed_at: str, endpoint: str, digest: str,
) -> dict[str, Any]:
    return {
        "isin": isin, "reporting_basis": basis, "period_end": period_end,
        "metric": metric, "particular": particular, "value": value,
        "unit": "INR_CRORE", "source_observed_at": observed_at,
        "source_name": UPSTOX_SOURCE_NAME,
        "source_record_id": f"{isin}:{basis}:{period_end}:{metric}",
        "source_endpoint": endpoint, "raw_sha256": digest,
        "pit_candidate_status": PIT_CANDIDATE_STATUS,
    }


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def normalize_income_statement(
    payload: dict[str, Any], *, isin: str, reporting_basis: str,
    source_observed_at: str | datetime,
) -> pd.DataFrame:
    exact_isin = validate_isin(isin)
    basis, api_basis = normalize_basis(reporting_basis)
    observed = normalize_observed_at(source_observed_at)
    data = _response_data(payload, expected_basis=api_basis, expected_time_period="yearly")
    digest = payload_sha256(payload)
    endpoint = f"/fundamentals/{exact_isin}/income-statement"
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    categories = data.get("income_statement")
    if not isinstance(categories, list):
        raise ValueError("Upstox income_statement must be a list")
    for category in categories:
        if not isinstance(category, dict):
            raise ValueError("Upstox income category must be an object")
        name = str(category.get("category", "")).strip().lower()
        history = category.get("history")
        if not name or not isinstance(history, list):
            raise ValueError("Upstox income category is malformed")
        metric = {
            "revenue": "revenue", "operating_profit": "operating_profit",
            "net_profit": "net_profit",
        }.get(name, f"category:{name}")
        for item in history:
            if not isinstance(item, dict):
                raise ValueError("Upstox income history item must be an object")
            end = period_label_to_end(item.get("period"))
            key = (metric, end)
            if key in seen:
                raise ValueError(f"duplicate Upstox income fact: {key}")
            seen.add(key)
            rows.append(_row(
                isin=exact_isin, basis=basis, period_end=end, metric=metric,
                particular=name, value=_finite(item.get("value"), field=f"{metric}/{end}"),
                observed_at=observed, endpoint=endpoint, digest=digest,
            ))

    full = data.get("full_statement", [])
    if full is None:
        full = []
    if not isinstance(full, list):
        raise ValueError("Upstox income full_statement must be a list")
    for line in full:
        if not isinstance(line, dict):
            raise ValueError("Upstox income full-statement row must be an object")
        particular = str(line.get("particular", "")).strip()
        history = line.get("history")
        if not particular or not isinstance(history, list):
            raise ValueError("Upstox income full-statement row is malformed")
        metric = f"income_line:{_slug(particular)}"
        for item in history:
            if not isinstance(item, dict):
                raise ValueError("Upstox income line history item must be an object")
            end = period_label_to_end(item.get("period"))
            key = (metric, end)
            if key in seen:
                raise ValueError(f"duplicate Upstox income fact: {key}")
            seen.add(key)
            rows.append(_row(
                isin=exact_isin, basis=basis, period_end=end, metric=metric,
                particular=particular,
                value=_finite(item.get("value"), field=f"{metric}/{end}"),
                observed_at=observed, endpoint=endpoint, digest=digest,
            ))
    return pd.DataFrame(rows, columns=FACT_COLUMNS).sort_values(
        ["period_end", "metric"], kind="stable"
    ).reset_index(drop=True)


def normalize_balance_sheet(
    payload: dict[str, Any], *, isin: str, reporting_basis: str,
    source_observed_at: str | datetime,
) -> pd.DataFrame:
    exact_isin = validate_isin(isin)
    basis, api_basis = normalize_basis(reporting_basis)
    observed = normalize_observed_at(source_observed_at)
    data = _response_data(payload, expected_basis=api_basis)
    digest = payload_sha256(payload)
    endpoint = f"/fundamentals/{exact_isin}/balance-sheet"
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    history = data.get("history")
    if not isinstance(history, list):
        raise ValueError("Upstox balance-sheet history must be a list")
    for item in history:
        if not isinstance(item, dict):
            raise ValueError("Upstox balance-sheet history item must be an object")
        end = period_label_to_end(item.get("period"))
        for metric, field in (("total_assets", "total_asset"), ("total_liabilities", "total_liability")):
            key = (metric, end)
            if key in seen:
                raise ValueError(f"duplicate Upstox balance fact: {key}")
            seen.add(key)
            rows.append(_row(
                isin=exact_isin, basis=basis, period_end=end, metric=metric,
                particular=field, value=_finite(item.get(field), field=f"{metric}/{end}"),
                observed_at=observed, endpoint=endpoint, digest=digest,
            ))

    full = data.get("full_statement", [])
    if full is None:
        full = []
    if not isinstance(full, list):
        raise ValueError("Upstox balance-sheet full_statement must be a list")
    for line in full:
        if not isinstance(line, dict):
            raise ValueError("Upstox balance-sheet full-statement row must be an object")
        particular = str(line.get("particular", "")).strip()
        history = line.get("history")
        if not particular or not isinstance(history, list):
            raise ValueError("Upstox balance-sheet full-statement row is malformed")
        metric = f"balance_line:{_slug(particular)}"
        for item in history:
            if not isinstance(item, dict):
                raise ValueError("Upstox balance line history item must be an object")
            end = period_label_to_end(item.get("period"))
            key = (metric, end)
            if key in seen:
                raise ValueError(f"duplicate Upstox balance fact: {key}")
            seen.add(key)
            rows.append(_row(
                isin=exact_isin, basis=basis, period_end=end, metric=metric,
                particular=particular,
                value=_finite(item.get("value"), field=f"{metric}/{end}"),
                observed_at=observed, endpoint=endpoint, digest=digest,
            ))
    return pd.DataFrame(rows, columns=FACT_COLUMNS).sort_values(
        ["period_end", "metric"], kind="stable"
    ).reset_index(drop=True)


def build_profit_pairs(income_facts: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in FACT_COLUMNS if column not in income_facts.columns]
    if missing:
        raise ValueError(f"income facts missing columns: {missing}")
    net = income_facts.loc[income_facts["metric"].eq("net_profit")].copy()
    if net.empty:
        return pd.DataFrame(columns=PROFIT_PAIR_COLUMNS)
    if net.duplicated(["isin", "reporting_basis", "period_end"]).any():
        raise ValueError("duplicate Upstox net-profit natural key")
    net["parsed_period_end"] = pd.to_datetime(net["period_end"], format="%Y-%m-%d", errors="raise")
    lookup = {
        (str(row["isin"]), str(row["reporting_basis"]), row["parsed_period_end"]): row
        for row in net.to_dict("records")
    }
    rows: list[dict[str, Any]] = []
    for row in net.sort_values(
        ["isin", "reporting_basis", "parsed_period_end"], kind="stable"
    ).to_dict("records"):
        prior_end = row["parsed_period_end"] - pd.DateOffset(years=1)
        prior = lookup.get((str(row["isin"]), str(row["reporting_basis"]), prior_end))
        if prior is None:
            continue
        rows.append({
            "isin": str(row["isin"]),
            "period_end": row["parsed_period_end"].date().isoformat(),
            "reporting_basis": str(row["reporting_basis"]),
            "current_pat": float(row["value"]), "prior_pat": float(prior["value"]),
            "source_observed_at": str(row["source_observed_at"]),
            "source_name": str(row["source_name"]),
            "source_record_id": f"{row['source_record_id']}|prior={prior['source_record_id']}",
            "source_endpoint": str(row["source_endpoint"]),
            "raw_sha256": str(row["raw_sha256"]),
            "pit_candidate_status": PIT_CANDIDATE_STATUS,
        })
    return pd.DataFrame(rows, columns=PROFIT_PAIR_COLUMNS).sort_values(
        ["isin", "reporting_basis", "period_end"], kind="stable"
    ).reset_index(drop=True)


def normalize_bundle(
    income_payload: dict[str, Any], balance_payload: dict[str, Any], *, isin: str,
    reporting_basis: str, source_observed_at: str | datetime,
) -> UpstoxNormalizedBundle:
    income = normalize_income_statement(
        income_payload, isin=isin, reporting_basis=reporting_basis,
        source_observed_at=source_observed_at,
    )
    balance = normalize_balance_sheet(
        balance_payload, isin=isin, reporting_basis=reporting_basis,
        source_observed_at=source_observed_at,
    )
    return UpstoxNormalizedBundle(income, balance, build_profit_pairs(income))
