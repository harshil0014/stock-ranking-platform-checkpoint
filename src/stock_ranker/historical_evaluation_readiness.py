"""Outcome-blind readiness audit for the Screener historical V2 extension."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Any

import pandas as pd

from stock_ranker.baseline import calculate_baseline_rankings
from stock_ranker.research_v2 import ResearchV2Inputs, calculate_research_v2
from stock_ranker.v2_config import ResearchV2Config
from stock_ranker.walk_forward_blind import assert_outcome_blind


READINESS_SCHEMA_VERSION = "screener_historical_evaluation_readiness_v1"
RANKING_DATES = ("2022-08-05", "2023-08-07", "2024-08-07", "2025-08-07")
REQUIRED_PERIOD_END = {
    "2022-08-05": "2022-03-31",
    "2023-08-07": "2023-03-31",
    "2024-08-07": "2024-03-31",
    "2025-08-07": "2025-03-31",
}


@dataclass(frozen=True, slots=True)
class HistoricalReadinessResult:
    cohort_membership: pd.DataFrame
    exclusions: pd.DataFrame
    cohort_summary: pd.DataFrame
    sector_distribution: pd.DataFrame
    report: dict[str, Any]


def sha256_file(path: str | Path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _name_key(value: object) -> str:
    text = str(value).upper().replace("&", " AND ")
    aliases = {
        "LIMITED": "LTD", "COMPANY": "CO", "CORPORATION": "CORP",
        "CORPN": "CORP", "INDUSTRIES": "INDS", "TECHNOLOGIES": "TECH",
    }
    tokens = re.findall(r"[A-Z0-9]+", text)
    return "".join(aliases.get(token, token) for token in tokens if token != "THE")


def _cutoff(ranking_date: str) -> pd.Timestamp:
    return (
        pd.Timestamp(ranking_date, tz="Asia/Kolkata")
        + pd.Timedelta(hours=15, minutes=30)
    ).tz_convert("UTC")


def _outcome_key_availability(
    outcome_dates: pd.DataFrame,
    ranking_date: str,
    tickers: set[str],
) -> set[str]:
    """Check 12-month endpoint availability without reading prices or returns."""

    required = {"ranking_date", "ticker", "date"}
    if required.difference(outcome_dates.columns):
        raise ValueError("outcome availability input lacks key/date columns")
    frame = outcome_dates.loc[
        outcome_dates["ranking_date"].astype(str).eq(ranking_date)
        & outcome_dates["ticker"].astype(str).isin(tickers)
    ].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    if frame["date"].isna().any():
        raise ValueError("outcome availability contains malformed dates")
    if frame.duplicated(["ticker", "date"]).any():
        raise ValueError("outcome availability contains duplicate ticker/date keys")
    start = pd.Timestamp(ranking_date)
    target = start + pd.DateOffset(months=12)
    valid: set[str] = set()
    for ticker, rows in frame.groupby("ticker", sort=True):
        dates = rows["date"]
        has_start = bool(dates.eq(start).any())
        endpoints = dates.loc[(dates > start) & (dates <= target)]
        if has_start and not endpoints.empty:
            valid.add(str(ticker))
    return valid


def _validate_latest_filing_first(selected: pd.DataFrame) -> None:
    if selected.duplicated(["ranking_date", "isin"]).any():
        raise ValueError("selected fundamentals contain duplicate ranking-date/ISIN keys")
    for row in selected.to_dict("records"):
        if str(row.get("period_status")) != "ELIGIBLE_PERIOD":
            raise ValueError("selected fundamental was not eligible after latest-period selection")
        if not bool(row.get("selected_for_ranking_date")):
            raise ValueError("selected fundamental lacks latest-filing selection attestation")
        available = pd.to_datetime(row["official_available_at"], utc=True, errors="coerce")
        if pd.isna(available) or available > _cutoff(str(row["ranking_date"])):
            raise ValueError("selected fundamental violates the official PIT cutoff")


def audit_historical_evaluation_readiness(
    *,
    screener_selected: pd.DataFrame,
    identity_master: pd.DataFrame,
    prospective_counts: pd.DataFrame,
    blind_root: str | Path,
    outcome_dates: pd.DataFrame,
    protocol: dict[str, Any],
) -> HistoricalReadinessResult:
    """Build same-cohort readiness evidence without calculating an outcome."""

    selected = screener_selected.copy(deep=True)
    _validate_latest_filing_first(selected)
    assert_outcome_blind(selected)
    identities = identity_master.copy(deep=True)
    identities["ticker"] = identities["ticker"].astype(str).str.upper().str.strip()
    identities["isin"] = identities["isin"].astype(str).str.upper().str.strip()
    if identities.duplicated("ticker").any() or identities.duplicated("isin").any():
        raise ValueError("identity master ticker and ISIN keys must be unique")
    identity_by_ticker = identities.set_index("ticker")
    prospective = prospective_counts.set_index("ranking_date")
    blind = Path(blind_root)
    member_rows: list[dict[str, Any]] = []
    exclusion_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    sector_rows: list[dict[str, Any]] = []

    for ranking_date in RANKING_DATES:
        snapshot = blind / ranking_date
        universe = pd.read_csv(snapshot / "historical_universe.csv", dtype=str)
        universe["investable"] = universe["investable"].astype(str).str.lower().eq("true")
        universe = universe.loc[universe["investable"]].copy()
        if len(universe) != 50 or universe["historical_symbol"].duplicated().any():
            raise ValueError(f"{ranking_date}: official historical universe is not 50 unique securities")
        if universe["historical_sector"].isna().any() or universe["historical_sector"].eq("").any():
            raise ValueError(f"{ranking_date}: historical sector is missing")

        baseline_full = pd.read_csv(snapshot / "baseline_full.csv")
        prices = pd.read_csv(snapshot / "predictor_prices.csv")
        assert_outcome_blind(baseline_full, ranking_date)
        assert_outcome_blind(prices, ranking_date)
        if pd.to_datetime(prices["date"], errors="coerce").max() > pd.Timestamp(ranking_date):
            raise ValueError(f"{ranking_date}: predictor prices extend past ranking date")

        day_fundamentals = selected.loc[
            selected["ranking_date"].astype(str).eq(ranking_date)
        ].copy()
        fundamental_by_ticker = day_fundamentals.set_index("ticker")
        investable_tickers = set(universe["historical_symbol"].astype(str))
        outcome_available = _outcome_key_availability(
            outcome_dates, ranking_date, investable_tickers
        )
        clean_fundamentals: list[dict[str, Any]] = []

        for row in universe.sort_values("historical_symbol", kind="stable").to_dict("records"):
            ticker = str(row["historical_symbol"])
            reasons: list[str] = []
            if ticker not in identity_by_ticker.index:
                reasons.append("NO_EXACT_CURRENT_ISIN_IDENTITY")
            if ticker not in fundamental_by_ticker.index:
                reasons.append("NO_SCREENER_PIT_FUNDAMENTALS")
            if ticker not in set(baseline_full["ticker"].astype(str)):
                reasons.append("BASELINE_PRICE_INELIGIBLE")
            if reasons:
                exclusion_rows.append({
                    "ranking_date": ranking_date, "ticker": ticker,
                    "company": row["company"], "sector": row["historical_sector"],
                    "reason_code": reasons[0],
                })
                continue

            identity = identity_by_ticker.loc[ticker]
            fundamental = fundamental_by_ticker.loc[ticker]
            if isinstance(fundamental, pd.DataFrame):
                raise ValueError("multiple selected fundamentals for one historical ticker")
            if str(fundamental["isin"]) != str(identity["isin"]):
                exclusion_rows.append({
                    "ranking_date": ranking_date, "ticker": ticker,
                    "company": row["company"], "sector": row["historical_sector"],
                    "reason_code": "ISIN_IDENTITY_MISMATCH",
                })
                continue
            if _name_key(fundamental["company"]) != _name_key(identity["company"]):
                exclusion_rows.append({
                    "ranking_date": ranking_date, "ticker": ticker,
                    "company": row["company"], "sector": row["historical_sector"],
                    "reason_code": "COMPANY_IDENTITY_MISMATCH",
                })
                continue
            clean_fundamentals.append({
                "ticker": ticker,
                "period_end": str(fundamental["period_end"])[:10],
                "available_date": str(fundamental["official_available_at"])[:10],
                "roce": float(fundamental["roce"]),
                "debt_to_equity": float(fundamental["debt_to_equity"]),
                "profit_growth_yoy": float(fundamental["current_pat"])
                / float(fundamental["prior_pat"]) - 1,
            })

        v2_universe = universe.rename(columns={
            "historical_symbol": "ticker", "historical_sector": "sector",
        })[["ticker", "company", "sector"]]
        v2_prices = prices[["ticker", "date", "pit_adjusted_price"]].rename(
            columns={"pit_adjusted_price": "adjusted_close"}
        )
        fundamentals = pd.DataFrame(clean_fundamentals, columns=[
            "ticker", "period_end", "available_date", "roce",
            "debt_to_equity", "profit_growth_yoy",
        ])
        if fundamentals.empty:
            eligible = pd.DataFrame(columns=[
                "ticker", "company", "sector", "research_v2_score", "sector_rank",
            ])
        else:
            v2 = calculate_research_v2(
                ResearchV2Inputs(v2_universe, v2_prices, fundamentals),
                ResearchV2Config(ranking_date=date.fromisoformat(ranking_date)),
            )
            for item in v2.eligibility.loc[~v2.eligibility["eligible"]].to_dict("records"):
                if item["ticker"] in {entry["ticker"] for entry in clean_fundamentals}:
                    exclusion_rows.append({
                        "ranking_date": ranking_date, "ticker": item["ticker"],
                        "company": item["company"], "sector": item["sector"],
                        "reason_code": "V2_" + str(item["reason_code"]),
                    })
            eligible = v2.rankings.copy()
        eligible_tickers = set(eligible["ticker"].astype(str))
        baseline_inputs = baseline_full.loc[
            baseline_full["ticker"].astype(str).isin(eligible_tickers),
            [
                "ticker", "company", "sector", "as_of_date", "current_price",
                "close_1y_ago", "close_3y_ago", "close_5y_ago", "ath_date",
            ],
        ].copy()
        matched_baseline = (
            calculate_baseline_rankings(baseline_inputs)
            if not baseline_inputs.empty else pd.DataFrame()
        )
        baseline_by_ticker = (
            matched_baseline.set_index("ticker")
            if not matched_baseline.empty else pd.DataFrame()
        )
        for item in eligible.sort_values(["sector", "ticker"], kind="stable").to_dict("records"):
            ticker = str(item["ticker"])
            has_outcome = ticker in outcome_available
            member_rows.append({
                "ranking_date": ranking_date,
                "ticker": ticker,
                "company": item["company"],
                "isin": str(identity_by_ticker.loc[ticker, "isin"]),
                "sector": item["sector"],
                "fundamental_period_end": str(
                    fundamental_by_ticker.loc[ticker, "period_end"]
                )[:10],
                "official_available_at": str(
                    fundamental_by_ticker.loc[ticker, "official_available_at"]
                ),
                "baseline_score": float(baseline_by_ticker.loc[ticker, "baseline_score"]),
                "baseline_sector_rank": int(baseline_by_ticker.loc[ticker, "sector_rank"]),
                "research_v2_score": float(item["research_v2_score"]),
                "research_v2_sector_rank": int(item["sector_rank"]),
                "primary_outcome_key_available": has_outcome,
                "comparison_cohort_member": has_outcome,
            })
            if not has_outcome:
                exclusion_rows.append({
                    "ranking_date": ranking_date, "ticker": ticker,
                    "company": item["company"], "sector": item["sector"],
                    "reason_code": "PRIMARY_OUTCOME_ENDPOINT_UNAVAILABLE",
                })

        selected_members = [
            row for row in member_rows
            if row["ranking_date"] == ranking_date and row["comparison_cohort_member"]
        ]
        sector_counts: dict[str, int] = {}
        for item in selected_members:
            sector_counts[item["sector"]] = sector_counts.get(item["sector"], 0) + 1
        for sector, count in sorted(sector_counts.items()):
            sector_rows.append({
                "ranking_date": ranking_date, "sector": sector,
                "same_cohort_count": count,
                "rank_ic_eligible": count >= 3,
                "pairwise_eligible": count >= 2,
            })
        prospective_count = int(prospective.loc[ranking_date, "prospective_union_count"])
        v2_count = int(len(eligible))
        outcome_count = sum(bool(row["primary_outcome_key_available"]) for row in member_rows if row["ranking_date"] == ranking_date)
        summary_rows.append({
            "ranking_date": ranking_date,
            "starting_prospective_v2_count": prospective_count,
            "official_historical_universe_count": len(universe),
            "final_identity_pit_clean_count": v2_count,
            "primary_outcome_key_available_count": outcome_count,
            "final_same_cohort_count": len(selected_members),
            "sector_count": len(sector_counts),
            "rank_ic_eligible_sector_count": sum(count >= 3 for count in sector_counts.values()),
            "largest_sector_count": max(sector_counts.values(), default=0),
        })

    membership = pd.DataFrame(member_rows).sort_values(
        ["ranking_date", "sector", "ticker"], kind="stable"
    ).reset_index(drop=True)
    exclusions = pd.DataFrame(exclusion_rows).drop_duplicates().sort_values(
        ["ranking_date", "reason_code", "ticker"], kind="stable"
    ).reset_index(drop=True)
    summary = pd.DataFrame(summary_rows)
    sectors = pd.DataFrame(sector_rows)
    valid_sector_dates = int(summary["rank_ic_eligible_sector_count"].sum())
    execution_gates = {
        "minimum_same_cohort_each_date": 10,
        "minimum_rank_ic_eligible_sectors_each_date": 2,
        "minimum_total_rank_ic_sector_dates": 12,
    }
    gate_results = {
        "same_cohort_each_date": bool((summary["final_same_cohort_count"] >= 10).all()),
        "rank_ic_sectors_each_date": bool((summary["rank_ic_eligible_sector_count"] >= 2).all()),
        "total_rank_ic_sector_dates": valid_sector_dates >= 12,
    }
    report = {
        "schema_version": READINESS_SCHEMA_VERSION,
        "protocol_identifier": protocol["protocol_identifier"],
        "protocol_fingerprint": sha256(canonical_json_bytes(protocol)).hexdigest(),
        "outcomes_calculated_or_inspected": False,
        "prospective_union_is_historical_cohort": False,
        "prospective_union_limitation": (
            "The headline union combines official historical NIFTY-50 predictions with "
            "Screener records selected from a later broad issuer population; it is not a "
            "ranking-date membership universe."
        ),
        "execution_gates": execution_gates,
        "execution_gate_results": gate_results,
        "valid_rank_ic_sector_dates": valid_sector_dates,
        "verdict": (
            "READY_RUN_FINAL_EVALUATION" if all(gate_results.values())
            else "TARGETED_DATA_FIX_REQUIRED"
        ),
        "data_collection_decision": "STOP_GENERAL_CHECKLIST_COLLECTION",
        "scientific_boundary": (
            "No return, IC, rank-correlation, portfolio, turnover, or transaction-cost "
            "value was calculated or inspected."
        ),
    }
    return HistoricalReadinessResult(membership, exclusions, summary, sectors, report)
