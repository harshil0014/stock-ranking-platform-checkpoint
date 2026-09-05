"""Fail-closed Screener-methodology reconstruction from official XBRL facts.

This is a candidate evidence bridge, not an accepted value source.  It applies
the formula calibrated from Screener's standalone workbook only when the
official fact store contains every exact line item for both the current and
prior annual periods.  Missing comparative facts and differences between an
issuer taxonomy line and Screener's normalized line are never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Final, Iterable

import pandas as pd

from .screener_historical_fundamentals import (
    REPORTING_BASIS,
    SCREENER_HISTORICAL_CONTRACT_VERSION,
)


XBRL_CANDIDATE_VALUE_METHOD: Final = "official_xbrl_screener_formula_candidate_v1"
XBRL_REQUIRED_CONCEPTS: Final = (
    "pbt",
    "finance_costs",
    "pat",
    "equity_share_capital",
    "unknown:OtherEquity",
    "unknown:BorrowingsCurrent",
    "unknown:BorrowingsNoncurrent",
)


@dataclass(frozen=True, slots=True)
class XBRLScreenerReconstructionResult:
    candidates: pd.DataFrame
    rejected: pd.DataFrame
    coverage: pd.DataFrame


def audit_xbrl_component_alignment(
    workbook_history: pd.DataFrame,
    facts: pd.DataFrame,
) -> pd.DataFrame:
    """Compare latest calibration-workbook inputs with exact-period XBRL facts."""

    required_workbook = {
        "ticker", "isin", "period_end", "current_pbt", "current_interest",
        "current_pat", "current_equity_capital", "current_reserves",
        "current_borrowings", "prior_period_end",
    }
    missing = sorted(required_workbook - set(workbook_history.columns))
    if missing:
        raise ValueError(f"workbook history missing component columns: {missing}")
    filtered = facts.loc[
        facts["statement_basis"].eq(REPORTING_BASIS)
        & facts["canonical_concept"].isin(XBRL_REQUIRED_CONCEPTS)
    ].copy()
    filtered["period_end"] = pd.to_datetime(filtered["period_end"], errors="coerce", utc=True)
    latest = workbook_history.copy(deep=True)
    latest["period_end"] = pd.to_datetime(latest["period_end"], errors="coerce", utc=True)
    latest["prior_period_end"] = pd.to_datetime(latest["prior_period_end"], errors="coerce", utc=True)
    latest = latest.sort_values(["isin", "period_end"], kind="stable").groupby("isin", as_index=False).tail(1)
    rows: list[dict[str, object]] = []
    mappings = {
        "pbt": "current_pbt",
        "interest": "current_interest",
        "pat": "current_pat",
        "equity_capital": "current_equity_capital",
        "reserves": "current_reserves",
    }
    for workbook in latest.to_dict("records"):
        current_group = filtered.loc[
            filtered["isin"].eq(workbook["isin"])
            & filtered["period_end"].eq(workbook["period_end"])
        ]
        values, missing_current = _period_record(current_group)
        prior_group = filtered.loc[
            filtered["isin"].eq(workbook["isin"])
            & filtered["period_end"].eq(workbook["prior_period_end"])
        ]
        prior_values, _ = _period_record(prior_group)
        prior_required = {
            "pat", "equity_capital", "reserves",
            "borrowings_current", "borrowings_noncurrent",
        }
        missing_prior = sorted(prior_required - set(prior_values))
        record: dict[str, object] = {
            "ticker": workbook["ticker"], "isin": workbook["isin"],
            "period_end": workbook["period_end"],
            "prior_period_end": workbook["prior_period_end"],
            "xbrl_current_complete": not missing_current,
            "xbrl_prior_complete": not missing_prior,
            "missing_current_components": ";".join(missing_current),
            "missing_prior_components": ";".join(missing_prior),
        }
        for xbrl_name, workbook_name in mappings.items():
            xbrl_value = values.get(xbrl_name)
            workbook_value = float(workbook[workbook_name])
            record[f"workbook_{xbrl_name}"] = workbook_value
            record[f"xbrl_{xbrl_name}"] = xbrl_value
            record[f"{xbrl_name}_delta"] = None if xbrl_value is None else xbrl_value - workbook_value
            record[f"{xbrl_name}_matches_workbook_precision"] = (
                False if xbrl_value is None else abs(xbrl_value - workbook_value) <= 0.0050001
            )
        xbrl_borrowings = None
        if "borrowings_current" in values and "borrowings_noncurrent" in values:
            xbrl_borrowings = values["borrowings_current"] + values["borrowings_noncurrent"]
        workbook_borrowings = float(workbook["current_borrowings"])
        record.update({
            "workbook_borrowings": workbook_borrowings,
            "xbrl_borrowings": xbrl_borrowings,
            "borrowings_delta": None if xbrl_borrowings is None else xbrl_borrowings - workbook_borrowings,
            "borrowings_matches_workbook_precision": (
                False if xbrl_borrowings is None else abs(xbrl_borrowings - workbook_borrowings) <= 0.0050001
            ),
            "prior_xbrl_pat": prior_values.get("pat"),
        })
        rows.append(record)
    return pd.DataFrame(rows).sort_values("ticker", kind="stable").reset_index(drop=True)


def _finite_unique(group: pd.DataFrame, concept: str) -> float | None:
    values = pd.to_numeric(
        group.loc[group["canonical_concept"].eq(concept), "value"], errors="coerce"
    ).dropna()
    values = values[values.map(math.isfinite)].drop_duplicates()
    if len(values) != 1:
        return None
    return float(values.iloc[0]) / 10_000_000.0


def _period_record(group: pd.DataFrame) -> tuple[dict[str, float], list[str]]:
    annual = group.loc[group["period_type"].eq("ANNUAL")]
    instant = group.loc[group["period_type"].eq("INSTANT")]
    values = {
        "pbt": _finite_unique(annual, "pbt"),
        "interest": _finite_unique(annual, "finance_costs"),
        "pat": _finite_unique(annual, "pat"),
        "equity_capital": _finite_unique(instant, "equity_share_capital"),
        "reserves": _finite_unique(instant, "unknown:OtherEquity"),
        "borrowings_current": _finite_unique(instant, "unknown:BorrowingsCurrent"),
        "borrowings_noncurrent": _finite_unique(instant, "unknown:BorrowingsNoncurrent"),
    }
    missing = sorted(name for name, value in values.items() if value is None)
    return {name: float(value) for name, value in values.items() if value is not None}, missing


def reconstruct_screener_methodology_from_xbrl(
    facts: pd.DataFrame,
    *,
    target_isins: Iterable[str] | None = None,
) -> XBRLScreenerReconstructionResult:
    """Build candidates only from complete same-basis, exact-period fact sets."""

    required = {
        "ticker", "isin", "statement_basis", "period_type", "period_end",
        "available_at", "filing_id", "canonical_concept", "value", "unit",
        "source_url", "source_sha256",
    }
    missing_columns = sorted(required - set(facts.columns))
    if missing_columns:
        raise ValueError(f"official XBRL facts missing columns: {missing_columns}")
    frame = facts.copy(deep=True)
    frame = frame.loc[
        frame["statement_basis"].eq(REPORTING_BASIS)
        & frame["canonical_concept"].isin(XBRL_REQUIRED_CONCEPTS)
    ].copy()
    if target_isins is not None:
        frame = frame.loc[frame["isin"].isin({str(value) for value in target_isins})]
    frame["period_end"] = pd.to_datetime(frame["period_end"], errors="coerce", utc=True)
    frame["available_at"] = pd.to_datetime(frame["available_at"], errors="coerce", utc=True)
    if frame[["period_end", "available_at"]].isna().any().any():
        raise ValueError("official XBRL facts contain malformed period/availability dates")
    if (~frame["unit"].eq("INR")).any():
        raise ValueError("official XBRL candidate facts must use INR")

    # A filing is the atomic evidence unit.  Never combine current components
    # from two revisions merely to make a period complete.
    records: dict[tuple[str, pd.Timestamp], list[tuple[pd.Timestamp, dict[str, object]]]] = {}
    for keys, group in frame.groupby(
        ["ticker", "isin", "period_end", "available_at", "filing_id"], sort=True
    ):
        ticker, isin, period_end, available_at, filing_id = keys
        values, missing = _period_record(group)
        record: dict[str, object] = {
            "ticker": ticker,
            "isin": isin,
            "period_end": period_end,
            "available_at": available_at,
            "filing_id": str(filing_id),
            "source_url": sorted(group["source_url"].astype(str).unique())[0],
            "source_sha256": sorted(group["source_sha256"].astype(str).unique())[0],
            **values,
            "missing_current_components": ";".join(missing),
        }
        records.setdefault((str(isin), period_end), []).append((available_at, record))

    def earliest_complete(
        isin: str,
        period: pd.Timestamp,
        required_names: set[str],
    ) -> dict[str, object] | None:
        choices = records.get((isin, period), [])
        complete = [record for _, record in choices if required_names.issubset(record)]
        return sorted(complete, key=lambda row: (row["available_at"], row["filing_id"]))[0] if complete else None

    candidate_rows: list[dict[str, object]] = []
    rejection_rows: list[dict[str, object]] = []
    all_periods = sorted(records, key=lambda item: (item[0], item[1]))
    for isin, period_end in all_periods:
        current_required = {
            "pbt", "interest", "pat", "equity_capital", "reserves",
            "borrowings_current", "borrowings_noncurrent",
        }
        current = earliest_complete(isin, period_end, current_required)
        if current is None:
            choices = records[(isin, period_end)]
            missing_sets = sorted({str(record["missing_current_components"]) for _, record in choices})
            rejection_rows.append({
                "isin": isin,
                "ticker": choices[0][1]["ticker"],
                "period_end": period_end,
                "status": "INCOMPLETE_CURRENT_XBRL_COMPONENTS",
                "missing_components": " | ".join(missing_sets),
            })
            continue
        prior_period = period_end - pd.DateOffset(years=1)
        prior_required = {
            "pat", "equity_capital", "reserves",
            "borrowings_current", "borrowings_noncurrent",
        }
        prior = earliest_complete(isin, prior_period, prior_required)
        if prior is None:
            rejection_rows.append({
                "isin": isin,
                "ticker": current["ticker"],
                "period_end": period_end,
                "status": "MISSING_PRIOR_ANNUAL_XBRL_COMPONENTS",
                "missing_components": "prior_pat;prior_equity_capital;prior_reserves;prior_borrowings",
            })
            continue
        current_equity = float(current["equity_capital"]) + float(current["reserves"])
        current_borrowings = float(current["borrowings_current"]) + float(current["borrowings_noncurrent"])
        prior_capital = (
            float(prior["equity_capital"]) + float(prior["reserves"])
            + float(prior["borrowings_current"]) + float(prior["borrowings_noncurrent"])
        )
        denominator = prior_capital + current_equity + current_borrowings
        if current_equity == 0 or denominator <= 0:
            rejection_rows.append({
                "isin": isin, "ticker": current["ticker"], "period_end": period_end,
                "status": "INVALID_XBRL_DENOMINATOR", "missing_components": "",
            })
            continue
        candidate_rows.append({
            "ticker": current["ticker"],
            "isin": isin,
            "period_end": period_end,
            "prior_period_end": prior_period,
            "reporting_basis": REPORTING_BASIS,
            "roce": (float(current["pbt"]) + float(current["interest"])) * 2.0 / denominator,
            "debt_to_equity": current_borrowings / current_equity,
            "current_pat": current["pat"],
            "prior_pat": prior["pat"],
            "current_pbt": current["pbt"],
            "current_interest": current["interest"],
            "current_equity_capital": current["equity_capital"],
            "current_reserves": current["reserves"],
            "current_borrowings": current_borrowings,
            "prior_equity_capital": prior["equity_capital"],
            "prior_reserves": prior["reserves"],
            "prior_borrowings": float(prior["borrowings_current"]) + float(prior["borrowings_noncurrent"]),
            "official_available_at": current["available_at"],
            "official_filing_url": current["source_url"],
            "source_sha256": current["source_sha256"],
            "source_value_method": XBRL_CANDIDATE_VALUE_METHOD,
            "contract_version": SCREENER_HISTORICAL_CONTRACT_VERSION,
            "promotion_status": "CANDIDATE_REQUIRES_CALIBRATION",
        })

    candidates = pd.DataFrame(candidate_rows)
    rejected = pd.DataFrame(rejection_rows)
    if len(candidates):
        candidates = candidates.sort_values(["isin", "period_end"], kind="stable").reset_index(drop=True)
    if len(rejected):
        rejected = rejected.sort_values(["isin", "period_end"], kind="stable").reset_index(drop=True)
    statuses = rejected["status"].value_counts().sort_index().rename_axis("status").reset_index(name="count") if len(rejected) else pd.DataFrame(columns=["status", "count"])
    coverage = pd.concat([
        pd.DataFrame([{"status": "COMPLETE_CANDIDATE", "count": len(candidates)}]),
        statuses,
    ], ignore_index=True)
    return XBRLScreenerReconstructionResult(candidates, rejected, coverage)
