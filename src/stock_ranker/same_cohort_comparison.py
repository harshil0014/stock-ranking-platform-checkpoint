"""Fair, deterministic Baseline V1 versus Research V2 comparison.

This module consumes frozen blind rankings and one shared outcome table.  It
does not calculate either model and deliberately has no data-acquisition path.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from stock_ranker.walk_forward_evaluation import (
    AMENDMENT_SHA256,
    BLIND_FINGERPRINT,
    PROTOCOL_SHA256,
    RANKING_DATES,
)


COMPARISON_PROTOCOL = "same_cohort_baseline_v1_vs_research_v2_v1"
PRIMARY_HORIZON_MONTHS = 12
MODEL_VERSIONS = {
    "baseline_v1": "baseline_v1_equal_rank_mean",
    "research_v2": "research_v2_point_in_time_weighted",
}
FORMATION_FORBIDDEN = {
    "future_return", "forward_return", "future_adjusted_return", "label",
    "label_end_date", "target_date", "actual_endpoint_date", "endpoint_adjusted_close",
}


@dataclass(frozen=True, slots=True)
class SameCohortComparison:
    cohorts: pd.DataFrame
    evaluated_rows: pd.DataFrame
    outcome_exclusions: pd.DataFrame
    date_metrics: pd.DataFrame
    sector_metrics: pd.DataFrame
    top_k_metrics: pd.DataFrame
    report: dict[str, Any]


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _finite_or_none(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    return number if np.isfinite(number) else None


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for row in frame.to_dict("records"):
        values.append({
            key: (_finite_or_none(value) if isinstance(value, (float, np.floating)) else value)
            for key, value in row.items()
        })
    return values


def _rank_correlation(left: pd.Series, right: pd.Series) -> float | None:
    if len(left) < 2 or left.nunique() < 2 or right.nunique() < 2:
        return None
    result = left.rank(method="average").corr(right.rank(method="average"))
    return _finite_or_none(result)


def _kendall_tau_b(left: pd.Series, right: pd.Series) -> float | None:
    """Small-sample Kendall tau-b without adding SciPy."""

    concordant = discordant = left_ties = right_ties = 0
    pairs = list(zip(left.astype(float), right.astype(float), strict=True))
    for index, (left_a, right_a) in enumerate(pairs):
        for left_b, right_b in pairs[index + 1:]:
            left_delta, right_delta = left_a - left_b, right_a - right_b
            if left_delta == 0 and right_delta == 0:
                continue
            if left_delta == 0:
                left_ties += 1
            elif right_delta == 0:
                right_ties += 1
            elif np.sign(left_delta) == np.sign(right_delta):
                concordant += 1
            else:
                discordant += 1
    denominator = np.sqrt(
        (concordant + discordant + left_ties)
        * (concordant + discordant + right_ties)
    )
    return (concordant - discordant) / denominator if denominator else None


def _validate_formation(frame: pd.DataFrame, label: str) -> None:
    forbidden = FORMATION_FORBIDDEN.intersection(frame.columns)
    if forbidden:
        raise ValueError(f"{label} contains outcome columns: {sorted(forbidden)}")


def _identity_lookup(identity: pd.DataFrame) -> pd.DataFrame:
    required = {"nse_symbol", "isin"}
    missing = required.difference(identity.columns)
    if missing:
        raise ValueError(f"identity map missing columns: {sorted(missing)}")
    checked = identity.copy(deep=True)
    checked["nse_symbol"] = checked["nse_symbol"].astype(str).str.strip()
    checked["isin"] = checked["isin"].astype(str).str.strip().str.upper()
    if "bse_code" not in checked:
        checked["bse_code"] = ""
    if checked[["nse_symbol", "isin"]].eq("").any().any():
        raise ValueError("identity map contains blank keys")
    if checked.duplicated("nse_symbol").any():
        raise ValueError("identity map contains duplicate NSE symbols")
    return checked


def _canonicalize(
    frame: pd.DataFrame, identity: pd.DataFrame, *, label: str,
    formation: bool = True,
) -> pd.DataFrame:
    if "ticker" not in frame:
        raise ValueError(f"{label} missing ticker")
    if formation:
        _validate_formation(frame, label)
    checked = frame.copy(deep=True)
    checked["ticker"] = checked["ticker"].astype(str).str.strip()
    joined = checked.merge(
        identity, left_on="ticker", right_on="nse_symbol", how="left",
        validate="many_to_one",
    )
    if joined["isin"].isna().any():
        missing = sorted(joined.loc[joined["isin"].isna(), "ticker"].unique())
        raise ValueError(f"{label} has unresolved exact identities: {missing}")
    if joined.duplicated("isin").any():
        duplicates = sorted(joined.loc[joined.duplicated("isin", keep=False), "isin"].unique())
        raise ValueError(f"{label} contains duplicate security identities: {duplicates}")
    return joined


def build_same_cohort_rows(
    ranking_date: str,
    baseline_rankings: pd.DataFrame,
    research_v2_rankings: pd.DataFrame,
    outcomes: pd.DataFrame,
    identity: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Freeze the V2-eligible identities and restrict both models to them."""

    identity = _identity_lookup(identity)
    v2 = _canonicalize(research_v2_rankings, identity, label="Research V2 rankings")
    baseline = _canonicalize(baseline_rankings, identity, label="Baseline rankings")
    cohort_isins = set(v2["isin"])
    baseline = baseline.loc[baseline["isin"].isin(cohort_isins)].copy()
    if set(baseline["isin"]) != cohort_isins:
        raise ValueError("Baseline input cohort does not equal the PIT-safe V2 cohort")
    if set(v2["isin"]) != cohort_isins or len(v2) != len(cohort_isins):
        raise ValueError("Research V2 input cohort identity mismatch")

    required_baseline = {"baseline_score", "sector_rank", "sector"}
    required_v2 = {"research_v2_score", "sector_rank", "sector", "company"}
    if required_baseline.difference(baseline.columns):
        raise ValueError("Baseline comparison rankings lack scores, ranks, or sectors")
    if required_v2.difference(v2.columns):
        raise ValueError("Research V2 comparison rankings lack scores, ranks, sectors, or companies")
    shared = v2[[
        "isin", "ticker", "company", "sector", "nse_symbol", "bse_code",
        "research_v2_score", "sector_rank",
    ]].rename(columns={"sector_rank": "research_v2_sector_rank"}).merge(
        baseline[["isin", "baseline_score", "sector_rank", "sector"]].rename(columns={
            "sector_rank": "baseline_sector_rank", "sector": "baseline_sector",
        }), on="isin", how="inner", validate="one_to_one",
    )
    if not shared["sector"].eq(shared["baseline_sector"]).all():
        raise ValueError("shared sector/reference-data mismatch")
    shared = shared.drop(columns="baseline_sector")
    shared.insert(0, "ranking_date", ranking_date)

    needed_outcomes = {"ranking_date", "ticker", "horizon_months", "future_adjusted_return"}
    missing = needed_outcomes.difference(outcomes.columns)
    if missing:
        raise ValueError(f"outcomes missing columns: {sorted(missing)}")
    chosen = outcomes.loc[
        outcomes["ranking_date"].astype(str).eq(ranking_date)
        & pd.to_numeric(outcomes["horizon_months"], errors="coerce").eq(PRIMARY_HORIZON_MONTHS)
    ].copy()
    if chosen.duplicated(["ranking_date", "ticker", "horizon_months"]).any():
        raise ValueError("outcomes contain duplicate security-date-horizon keys")
    outcome_identity = _canonicalize(
        chosen, identity, label="shared outcomes", formation=False
    )
    outcome_columns = [
        "isin", "future_adjusted_return", "start_date", "actual_endpoint_date",
        "start_adjusted_close", "endpoint_adjusted_close", "target_date",
    ]
    for column in outcome_columns:
        if column not in outcome_identity:
            outcome_identity[column] = None
    outcome_identity["future_adjusted_return"] = pd.to_numeric(
        outcome_identity["future_adjusted_return"], errors="coerce"
    )
    valid = outcome_identity.loc[np.isfinite(outcome_identity["future_adjusted_return"])]
    evaluated = shared.merge(
        valid[outcome_columns], on="isin", how="inner", validate="one_to_one"
    )
    excluded = shared.loc[~shared["isin"].isin(evaluated["isin"]), [
        "ranking_date", "isin", "ticker", "company", "sector",
    ]].copy()
    excluded["outcome_status"] = "SHARED_OUTCOME_UNAVAILABLE"
    shared["cohort_fingerprint"] = sha256(canonical_json_bytes(_records(
        shared.drop(columns="cohort_fingerprint", errors="ignore").sort_values("isin")
    ))).hexdigest()
    return (
        shared.sort_values(["sector", "isin"], kind="stable").reset_index(drop=True),
        evaluated.sort_values(["sector", "isin"], kind="stable").reset_index(drop=True),
        excluded.sort_values(["sector", "isin"], kind="stable").reset_index(drop=True),
    )


def _model_metrics(group: pd.DataFrame, rank_column: str, k: int) -> dict[str, Any]:
    selected = group.sort_values([rank_column, "isin"], kind="stable").iloc[:k]
    returns = selected["future_adjusted_return"]
    return {
        "tickers": "|".join(selected["ticker"]),
        "mean_forward_return": float(returns.mean()),
        "median_forward_return": float(returns.median()),
        "minimum_forward_return": float(returns.min()),
        "maximum_forward_return": float(returns.max()),
    }


def evaluate_same_cohort(
    cohorts: pd.DataFrame,
    evaluated: pd.DataFrame,
    exclusions: pd.DataFrame,
) -> SameCohortComparison:
    date_rows: list[dict[str, Any]] = []
    sector_rows: list[dict[str, Any]] = []
    top_rows: list[dict[str, Any]] = []
    date_selection_rows: list[dict[str, Any]] = []
    for ranking_date, date_group in evaluated.groupby("ranking_date", sort=True):
        date_rows.append({
            "ranking_date": ranking_date,
            "cohort_size": int(len(cohorts.loc[cohorts["ranking_date"].eq(ranking_date)])),
            "evaluated_size": int(len(date_group)),
            "model_rank_spearman": _rank_correlation(
                date_group["baseline_sector_rank"], date_group["research_v2_sector_rank"]
            ),
            "model_rank_kendall_tau_b": _kendall_tau_b(
                date_group["baseline_sector_rank"], date_group["research_v2_sector_rank"]
            ),
            "mean_absolute_rank_difference": float((
                date_group["baseline_sector_rank"] - date_group["research_v2_sector_rank"]
            ).abs().mean()),
            "baseline_rank_vs_forward_return_spearman": _rank_correlation(
                -date_group["baseline_sector_rank"], date_group["future_adjusted_return"]
            ),
            "research_v2_rank_vs_forward_return_spearman": _rank_correlation(
                -date_group["research_v2_sector_rank"], date_group["future_adjusted_return"]
            ),
        })
        for sector, group in date_group.groupby("sector", sort=True):
            sector_rows.append({
                "ranking_date": ranking_date, "sector": sector,
                "cohort_size": int(len(group)),
                "model_rank_spearman": _rank_correlation(
                    group["baseline_sector_rank"], group["research_v2_sector_rank"]
                ),
                "model_rank_kendall_tau_b": _kendall_tau_b(
                    group["baseline_sector_rank"], group["research_v2_sector_rank"]
                ),
                "baseline_rank_vs_forward_return_spearman": _rank_correlation(
                    -group["baseline_sector_rank"], group["future_adjusted_return"]
                ),
                "research_v2_rank_vs_forward_return_spearman": _rank_correlation(
                    -group["research_v2_sector_rank"], group["future_adjusted_return"]
                ),
            })
            for k in sorted({1, min(3, len(group)), min(5, len(group))}):
                baseline_selected = group.sort_values(
                    ["baseline_sector_rank", "isin"], kind="stable"
                ).iloc[:k]
                v2_selected = group.sort_values(
                    ["research_v2_sector_rank", "isin"], kind="stable"
                ).iloc[:k]
                baseline_isins, v2_isins = set(baseline_selected["isin"]), set(v2_selected["isin"])
                top_rows.append({
                    "ranking_date": ranking_date, "sector": sector,
                    "cohort_size": int(len(group)), "k": int(k),
                    "overlap_count": len(baseline_isins & v2_isins),
                    "jaccard_overlap": len(baseline_isins & v2_isins) / len(baseline_isins | v2_isins),
                    "same_selection": baseline_isins == v2_isins,
                    "baseline": _model_metrics(group, "baseline_sector_rank", k),
                    "research_v2": _model_metrics(group, "research_v2_sector_rank", k),
                })
        for selection_rule, maximum in (("TOP_1_PER_SECTOR", 1), ("TOP_MIN_3_PER_SECTOR", 3)):
            selections: dict[str, pd.DataFrame] = {}
            for model, rank_column in (
                ("baseline", "baseline_sector_rank"),
                ("research_v2", "research_v2_sector_rank"),
            ):
                pieces = []
                for _, sector_group in date_group.groupby("sector", sort=True):
                    pieces.append(sector_group.sort_values(
                        [rank_column, "isin"], kind="stable"
                    ).iloc[:min(maximum, len(sector_group))])
                selections[model] = pd.concat(pieces, ignore_index=True)
            baseline_selected, v2_selected = selections["baseline"], selections["research_v2"]
            baseline_isins, v2_isins = set(baseline_selected["isin"]), set(v2_selected["isin"])
            date_selection_rows.append({
                "ranking_date": ranking_date, "selection_rule": selection_rule,
                "baseline_count": len(baseline_selected), "research_v2_count": len(v2_selected),
                "overlap_count": len(baseline_isins & v2_isins),
                "jaccard_overlap": len(baseline_isins & v2_isins) / len(baseline_isins | v2_isins),
                "baseline_mean_forward_return": float(baseline_selected["future_adjusted_return"].mean()),
                "baseline_median_forward_return": float(baseline_selected["future_adjusted_return"].median()),
                "research_v2_mean_forward_return": float(v2_selected["future_adjusted_return"].mean()),
                "research_v2_median_forward_return": float(v2_selected["future_adjusted_return"].median()),
            })
    date_metrics = pd.DataFrame(date_rows)
    sector_metrics = pd.DataFrame(sector_rows)
    top_k = pd.DataFrame(top_rows)
    date_selections = pd.DataFrame(date_selection_rows)
    primary_top = date_selections.loc[
        date_selections["selection_rule"].eq("TOP_1_PER_SECTOR")
    ]
    direction = []
    for row in primary_top.to_dict("records"):
        difference = row["research_v2_mean_forward_return"] - row["baseline_mean_forward_return"]
        direction.append(
            "TIE" if abs(difference) <= 1e-15
            else "V2_HIGHER" if difference > 0 else "BASELINE_HIGHER"
        )
    report = {
        "protocol_version": COMPARISON_PROTOCOL,
        "predeclared_metrics": [
            "cohort size", "Spearman model-vs-model sector-rank correlation",
            "Kendall tau-b model-vs-model sector-rank correlation", "exact rank differences",
            "top-1 agreement", "top-min(3,N) overlap and Jaccard",
            "model sector-rank vs 12-month forward-return rank correlation",
            "top-min(3,N) mean/median/minimum/maximum 12-month forward return",
        ],
        "ranking_dates": sorted(cohorts["ranking_date"].unique()),
        "primary_horizon_months": PRIMARY_HORIZON_MONTHS,
        "outcome_rule": {
            "label": "ADJUSTED-PRICE FUTURE RETURN",
            "shared_table": True,
            "entry": "exact ranking-date adjusted close",
            "exit": "last adjusted close on or before the 12-calendar-month target",
            "missing_policy": "exclude from both models",
        },
        "identity_key": "ISIN",
        "model_versions": MODEL_VERSIONS,
        "frozen_inputs": {
            "blind_prediction_fingerprint": BLIND_FINGERPRINT,
            "walk_forward_protocol_sha256": PROTOCOL_SHA256,
            "sector_amendment_sha256": AMENDMENT_SHA256,
        },
        "cohort_sizes": {
            row["ranking_date"]: int(row["cohort_size"])
            for row in date_metrics.to_dict("records")
        },
        "date_security_observations": int(len(cohorts)),
        "evaluated_date_security_observations": int(len(evaluated)),
        "outcome_exclusion_count": int(len(exclusions)),
        "date_metrics": _records(date_metrics),
        "date_selection_metrics": _records(date_selections),
        "sector_metrics": _records(sector_metrics),
        "top_k_metrics": _records(top_k),
        "aggregate": {
            "mean_model_rank_spearman": _finite_or_none(date_metrics["model_rank_spearman"].mean()),
            "top_one_per_sector_dates_v2_higher": direction.count("V2_HIGHER"),
            "top_one_per_sector_dates_baseline_higher": direction.count("BASELINE_HIGHER"),
            "top_one_per_sector_date_ties": direction.count("TIE"),
            "directional_result": "MIXED" if "V2_HIGHER" in direction and "BASELINE_HIGHER" in direction else (
                "V2_HIGHER" if "V2_HIGHER" in direction else "BASELINE_HIGHER" if "BASELINE_HIGHER" in direction else "TIE"
            ),
        },
        "limitations": [
            "Only four annual ranking dates and 36 date-security observations are available.",
            "Cohort sizes of 8, 4, 8, and 16 are too small for strong statistical inference.",
            "Sector-relative ranks make pooled date-level rank correlations descriptive; sector rows are authoritative.",
            "No persistent alpha, market outperformance, or model superiority is established.",
        ],
    }
    return SameCohortComparison(cohorts, evaluated, exclusions, date_metrics, sector_metrics, top_k, report)


def export_same_cohort_comparison(result: SameCohortComparison, output: Path) -> str:
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    output.mkdir(parents=True)
    for name, frame in (
        ("cohorts.csv", result.cohorts),
        ("evaluated_rows.csv", result.evaluated_rows),
        ("outcome_exclusions.csv", result.outcome_exclusions),
        ("date_metrics.csv", result.date_metrics),
        ("sector_metrics.csv", result.sector_metrics),
    ):
        frame.to_csv(output / name, index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")
    (output / "top_k_metrics.json").write_bytes(canonical_json_bytes(_records(result.top_k_metrics)) + b"\n")
    report_bytes = canonical_json_bytes(result.report) + b"\n"
    (output / "comparison.json").write_bytes(report_bytes)
    fingerprint = sha256(report_bytes).hexdigest()
    (output / "fingerprint.json").write_bytes(canonical_json_bytes({
        "comparison_sha256": fingerprint,
        "protocol_version": COMPARISON_PROTOCOL,
    }) + b"\n")
    return fingerprint
