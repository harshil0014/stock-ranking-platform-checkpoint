"""Strict bridge from structured accounting exports to official PIT filings.

Structured vendors accelerate extraction, but do not supply an historical
availability date merely because a value is labelled with an old financial
period.  Admission therefore requires exact identity/basis/period matching and
either contemporaneous archived structured evidence or a numeric match to the
original official filing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from typing import Final

import pandas as pd


JOIN_KEY: Final = ("isin", "period_end", "reporting_basis")
VALUE_COLUMNS: Final = ("roce", "debt_to_equity", "current_pat", "prior_pat")
STRUCTURED_COLUMNS: Final = JOIN_KEY + VALUE_COLUMNS + (
    "source_observed_at", "source_name", "source_record_id",
)
FILING_COLUMNS: Final = JOIN_KEY + (
    "official_available_at", "filing_id", "filing_url", "filing_sha256",
)


@dataclass(frozen=True, slots=True)
class StructuredPITBridgeResult:
    accepted: pd.DataFrame
    rejected: pd.DataFrame


def _dates(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    result = frame.copy(deep=True)
    for column in columns:
        parsed = pd.to_datetime(result[column], format="mixed", errors="coerce", utc=True)
        if parsed.isna().any():
            rows = result.index[parsed.isna()].tolist()
            raise ValueError(f"{column}: malformed date at rows {rows}")
        result[column] = parsed
    return result


def bridge_structured_fundamentals(
    structured: pd.DataFrame,
    official_filings: pd.DataFrame,
    *,
    ranking_date: date,
) -> StructuredPITBridgeResult:
    """Admit only structured values with an independently valid PIT chain.

    ``evidence_mode`` must be one of:
    ``CONTEMPORANEOUS_ARCHIVED_EXPORT`` (the structured export existed by the
    ranking date) or ``EXACT_ORIGINAL_FILING_MATCH`` (all values were matched
    to the original official attachment).  A present-day export cannot be
    backdated using an older filing timestamp.
    """

    required_structured = set(STRUCTURED_COLUMNS) | {"evidence_mode"}
    missing = sorted(required_structured - set(structured.columns))
    if missing:
        raise ValueError(f"structured fundamentals missing columns: {missing}")
    missing = sorted(set(FILING_COLUMNS) - set(official_filings.columns))
    if missing:
        raise ValueError(f"official filings missing columns: {missing}")
    left = _dates(structured, ("period_end", "source_observed_at"))
    right = _dates(official_filings, ("period_end", "official_available_at"))
    for name, frame in (("structured", left), ("official", right)):
        if frame.duplicated(list(JOIN_KEY)).any():
            keys = frame.loc[frame.duplicated(list(JOIN_KEY), keep=False), list(JOIN_KEY)].to_dict("records")
            raise ValueError(f"duplicate {name} natural keys: {keys}")
    for column in VALUE_COLUMNS:
        values = pd.to_numeric(left[column], errors="coerce")
        bad = values.isna() | ~values.map(math.isfinite)
        if bad.any():
            raise ValueError(f"{column}: invalid numeric values at rows {left.index[bad].tolist()}")
        left[column] = values
    merged = left.merge(right, on=list(JOIN_KEY), how="left", validate="one_to_one", indicator=True)
    cutoff = pd.Timestamp(ranking_date, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    reasons: list[str] = []
    for row in merged.to_dict("records"):
        if row["_merge"] != "both":
            reasons.append("NO_EXACT_OFFICIAL_FILING_MATCH")
        elif row["reporting_basis"] not in {"STANDALONE", "CONSOLIDATED"}:
            reasons.append("UNSUPPORTED_REPORTING_BASIS")
        elif row["period_end"] > row["official_available_at"]:
            reasons.append("OFFICIAL_AVAILABILITY_PRECEDES_PERIOD_END")
        elif row["official_available_at"] > cutoff:
            reasons.append("OFFICIAL_FILING_NOT_AVAILABLE_AT_RANKING_DATE")
        elif row["evidence_mode"] == "CONTEMPORANEOUS_ARCHIVED_EXPORT" and row["source_observed_at"] > cutoff:
            reasons.append("STRUCTURED_EXPORT_OBSERVED_AFTER_RANKING_DATE")
        elif row["evidence_mode"] == "EXACT_ORIGINAL_FILING_MATCH" and not str(row.get("filing_value_match_sha256", "")).strip():
            reasons.append("MISSING_ORIGINAL_FILING_VALUE_MATCH")
        elif row["evidence_mode"] not in {"CONTEMPORANEOUS_ARCHIVED_EXPORT", "EXACT_ORIGINAL_FILING_MATCH"}:
            reasons.append("UNSUPPORTED_EVIDENCE_MODE")
        elif float(row["debt_to_equity"]) < 0 or float(row["prior_pat"]) == 0:
            reasons.append("V2_NUMERIC_POLICY_FAILURE")
        else:
            reasons.append("ACCEPTED")
    merged["bridge_status"] = reasons
    stable = merged.drop(columns=["_merge"]).sort_values(list(JOIN_KEY), kind="stable").reset_index(drop=True)
    return StructuredPITBridgeResult(
        accepted=stable.loc[stable["bridge_status"] == "ACCEPTED"].reset_index(drop=True),
        rejected=stable.loc[stable["bridge_status"] != "ACCEPTED"].reset_index(drop=True),
    )

