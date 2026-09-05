"""Outcome evaluation for the frozen Screener historical same-cohort study.

This module has no acquisition path and never calculates either ranking model.
It consumes the outcome-blind membership artifact produced by the readiness gate,
then reads hash-pinned adjusted-price histories to form the protocol labels.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


HORIZONS = (3, 6, 12)
PRIMARY_HORIZON = 12
SCHEMA_VERSION = "screener_historical_same_cohort_evaluation_v1"


@dataclass(frozen=True, slots=True)
class ScreenerHistoricalEvaluation:
    future_returns: pd.DataFrame
    sector_metrics: pd.DataFrame
    pairwise_accuracy: pd.DataFrame
    top_stock_excess: pd.DataFrame
    top_bottom_spread: pd.DataFrame
    sector_top_n_overlap: pd.DataFrame
    date_top_n_overlap: pd.DataFrame
    rank_changes: pd.DataFrame
    selection_identity_overlap: pd.DataFrame
    concentration_diagnostics: pd.DataFrame
    summary: dict[str, Any]


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_fingerprint(value: object) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _finite(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    result = float(value)
    return result if np.isfinite(result) else None


def _metric_summary(values: pd.Series) -> dict[str, Any]:
    valid = pd.to_numeric(values, errors="coerce")
    valid = valid.loc[np.isfinite(valid)]
    count = int(len(valid))
    mean = float(valid.mean()) if count else None
    std = float(valid.std(ddof=1)) if count >= 2 else None
    return {
        "count": count,
        "mean": mean,
        "median": float(valid.median()) if count else None,
        "sample_std": std,
        "unannualized_mean_over_sample_std": (
            mean / std if mean is not None and std not in (None, 0.0) else None
        ),
        "positive_count": int(valid.gt(0).sum()),
        "negative_count": int(valid.lt(0).sum()),
        "zero_count": int(valid.eq(0).sum()),
    }


def _spearman(signal: pd.Series, outcome: pd.Series) -> float | None:
    if len(signal) < 2 or signal.nunique() < 2 or outcome.nunique() < 2:
        return None
    return _finite(
        signal.rank(method="average").corr(outcome.rank(method="average"))
    )


def _kendall_tau_b(signal: pd.Series, outcome: pd.Series) -> float | None:
    concordant = discordant = signal_ties = outcome_ties = 0
    values = list(zip(signal.astype(float), outcome.astype(float), strict=True))
    for index, (signal_a, outcome_a) in enumerate(values):
        for signal_b, outcome_b in values[index + 1:]:
            signal_delta = signal_a - signal_b
            outcome_delta = outcome_a - outcome_b
            if signal_delta == 0 and outcome_delta == 0:
                continue
            if signal_delta == 0:
                signal_ties += 1
            elif outcome_delta == 0:
                outcome_ties += 1
            elif np.sign(signal_delta) == np.sign(outcome_delta):
                concordant += 1
            else:
                discordant += 1
    denominator = np.sqrt(
        (concordant + discordant + signal_ties)
        * (concordant + discordant + outcome_ties)
    )
    return _finite((concordant - discordant) / denominator) if denominator else None


def validate_frozen_inputs(
    readiness_root: str | Path,
    protocol_path: str | Path,
    history_root: str | Path,
    blind_root: str | Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    readiness = Path(readiness_root)
    protocol_file = Path(protocol_path)
    histories = Path(history_root)
    report = json.loads((readiness / "readiness_report.json").read_text(encoding="utf-8"))
    if report.get("verdict") != "READY_RUN_FINAL_EVALUATION":
        raise ValueError("readiness gate did not authorize outcome evaluation")
    if report.get("outcomes_calculated_or_inspected") is not False:
        raise ValueError("readiness evidence is not outcome-blind")
    protocol = json.loads(protocol_file.read_text(encoding="utf-8"))
    protocol_hash = canonical_json_fingerprint(protocol)
    if protocol_hash != report.get("protocol_fingerprint"):
        raise ValueError("frozen evaluation protocol fingerprint mismatch")
    membership_path = readiness / "cohort_membership.csv"
    inventory = json.loads((readiness / "artifact_inventory.json").read_text(encoding="utf-8"))
    recorded = {row["path"]: row["sha256"] for row in inventory}
    if _file_hash(membership_path) != recorded.get("cohort_membership.csv"):
        raise ValueError("frozen cohort membership hash mismatch")
    membership = pd.read_csv(membership_path)
    required = {
        "ranking_date", "ticker", "company", "isin", "sector",
        "baseline_score", "baseline_sector_rank", "research_v2_score",
        "research_v2_sector_rank", "comparison_cohort_member",
    }
    missing = required.difference(membership.columns)
    if missing:
        raise ValueError(f"frozen cohort is missing columns: {sorted(missing)}")
    if membership.duplicated(["ranking_date", "isin"]).any():
        raise ValueError("frozen cohort has duplicate ranking-date/ISIN keys")
    if not membership["comparison_cohort_member"].astype(str).str.lower().eq("true").all():
        raise ValueError("frozen cohort contains a non-member row")
    expected_dates = list(protocol["ranking_dates"])
    if sorted(membership["ranking_date"].astype(str).unique()) != sorted(expected_dates):
        raise ValueError("frozen cohort ranking dates differ from protocol")
    expected_counts = {"2022-08-05": 25, "2023-08-07": 26, "2024-08-07": 27, "2025-08-07": 26}
    counts = membership.groupby("ranking_date", sort=True).size().to_dict()
    if counts != expected_counts:
        raise ValueError(f"frozen cohort counts changed: {counts}")
    history_hashes = report["input_fingerprints"]["outcome_history_files"]
    for filename, expected_hash in sorted(history_hashes.items()):
        path = histories / filename
        if not path.is_file() or _file_hash(path) != expected_hash:
            raise ValueError(f"hash-pinned outcome history changed: {filename}")
    if blind_root is not None:
        blind_manifest = Path(blind_root) / "manifest.json"
        if (
            not blind_manifest.is_file()
            or _file_hash(blind_manifest)
            != report["input_fingerprints"]["blind_manifest"]
        ):
            raise ValueError("frozen blind manifest hash mismatch")
    return membership.sort_values(
        ["ranking_date", "sector", "ticker"], kind="stable"
    ).reset_index(drop=True), protocol, report


def calculate_frozen_future_returns(
    membership: pd.DataFrame,
    history_root: str | Path,
) -> pd.DataFrame:
    histories = Path(history_root)
    rows: list[dict[str, Any]] = []
    for member in membership.sort_values(["ranking_date", "ticker"], kind="stable").to_dict("records"):
        ranking_date = pd.Timestamp(member["ranking_date"])
        ticker = str(member["ticker"])
        history = pd.read_csv(histories / f"{ticker}.csv")
        required = {"date", "adjusted_close"}
        if required.difference(history.columns):
            raise ValueError(f"{ticker}: adjusted-price history schema changed")
        history["date"] = pd.to_datetime(history["date"], errors="raise")
        history["adjusted_close"] = pd.to_numeric(history["adjusted_close"], errors="coerce")
        if history.duplicated("date").any():
            raise ValueError(f"{ticker}: duplicate adjusted-price dates")
        if (~np.isfinite(history["adjusted_close"]) | history["adjusted_close"].le(0)).any():
            raise ValueError(f"{ticker}: invalid adjusted-price value")
        start_rows = history.loc[history["date"].eq(ranking_date)]
        if len(start_rows) != 1:
            raise ValueError(f"{ticker} {ranking_date.date()}: exact ranking-date price absent")
        start_price = float(start_rows.iloc[0]["adjusted_close"])
        for months in HORIZONS:
            target = ranking_date + pd.DateOffset(months=months)
            endpoints = history.loc[history["date"].le(target)].sort_values("date", kind="stable")
            if endpoints.empty:
                raise ValueError(f"{ticker}: no endpoint on or before {target.date()}")
            endpoint = endpoints.iloc[-1]
            endpoint_date = pd.Timestamp(endpoint["date"])
            if endpoint_date < ranking_date:
                raise ValueError(f"{ticker}: endpoint precedes ranking date")
            endpoint_price = float(endpoint["adjusted_close"])
            rows.append({
                "ranking_date": ranking_date.date().isoformat(),
                "ticker": ticker,
                "isin": str(member["isin"]),
                "horizon_months": months,
                "target_date": target.date().isoformat(),
                "start_date": ranking_date.date().isoformat(),
                "actual_endpoint_date": endpoint_date.date().isoformat(),
                "endpoint_distance_days": int((target - endpoint_date).days),
                "start_adjusted_close": start_price,
                "endpoint_adjusted_close": endpoint_price,
                "future_adjusted_return": endpoint_price / start_price - 1.0,
                "label_semantics": "YAHOO_ADJ_CLOSE_ENDPOINT_OVER_RANKING_DATE_MINUS_ONE",
            })
    result = pd.DataFrame(rows).sort_values(
        ["ranking_date", "ticker", "horizon_months"], kind="stable"
    ).reset_index(drop=True)
    expected = len(membership) * len(HORIZONS)
    if len(result) != expected or result.duplicated(
        ["ranking_date", "isin", "horizon_months"]
    ).any():
        raise ValueError("future-return key set is incomplete or duplicated")
    return result


def _pairwise(group: pd.DataFrame, rank_column: str) -> tuple[float, int, int, int]:
    credit = 0.0
    evaluated = model_ties = outcome_ties = 0
    records = group.sort_values("isin", kind="stable").to_dict("records")
    for index, left in enumerate(records):
        for right in records[index + 1:]:
            outcome_delta = left["future_adjusted_return"] - right["future_adjusted_return"]
            if outcome_delta == 0:
                outcome_ties += 1
                continue
            rank_delta = right[rank_column] - left[rank_column]
            evaluated += 1
            if rank_delta == 0:
                model_ties += 1
                credit += 0.5
            elif np.sign(rank_delta) == np.sign(outcome_delta):
                credit += 1.0
    return credit, evaluated, model_ties, outcome_ties


def _selection(group: pd.DataFrame, rank_column: str, count: int) -> pd.DataFrame:
    return group.sort_values([rank_column, "ticker"], kind="stable").iloc[:count]


def evaluate_frozen_same_cohort(
    membership: pd.DataFrame,
    future_returns: pd.DataFrame,
    *,
    protocol_fingerprint: str,
    cohort_fingerprint: str,
    blind_manifest_fingerprint: str,
) -> ScreenerHistoricalEvaluation:
    panel = membership.merge(
        future_returns,
        on=["ranking_date", "ticker", "isin"],
        how="inner",
        validate="one_to_many",
    )
    if len(panel) != len(membership) * len(HORIZONS):
        raise ValueError("outcome merge changed the frozen same-cohort key set")
    sector_rows: list[dict[str, Any]] = []
    pair_rows: list[dict[str, Any]] = []
    top_rows: list[dict[str, Any]] = []
    spread_rows: list[dict[str, Any]] = []
    overlap_rows: list[dict[str, Any]] = []
    date_overlap_rows: list[dict[str, Any]] = []
    rank_rows: list[dict[str, Any]] = []
    selections: dict[tuple[str, int, str], set[str]] = {}

    for record in membership.sort_values(["ranking_date", "sector", "ticker"], kind="stable").to_dict("records"):
        rank_rows.append({
            "ranking_date": record["ranking_date"], "ticker": record["ticker"],
            "isin": record["isin"], "sector": record["sector"],
            "baseline_sector_rank": record["baseline_sector_rank"],
            "research_v2_sector_rank": record["research_v2_sector_rank"],
            "research_v2_minus_baseline_rank": (
                float(record["baseline_sector_rank"]) - float(record["research_v2_sector_rank"])
            ),
            "absolute_rank_change": abs(
                float(record["baseline_sector_rank"]) - float(record["research_v2_sector_rank"])
            ),
        })

    grouped = panel.groupby(["ranking_date", "sector", "horizon_months"], sort=True)
    for (ranking_date, sector, horizon), group in grouped:
        peers = len(group)
        model_values = {
            "MATCHED_BASELINE": "baseline_sector_rank",
            "RESEARCH_V2": "research_v2_sector_rank",
        }
        metrics: dict[str, Any] = {
            "ranking_date": ranking_date, "sector": sector,
            "horizon_months": int(horizon), "peer_count": peers,
            "tickers": "|".join(sorted(group["ticker"])),
        }
        if peers >= 3:
            for model, rank_column in model_values.items():
                prefix = model.lower()
                signal = -pd.to_numeric(group[rank_column])
                metrics[f"{prefix}_rank_ic"] = _spearman(
                    signal, group["future_adjusted_return"]
                )
                metrics[f"{prefix}_kendall_tau_b"] = _kendall_tau_b(
                    signal, group["future_adjusted_return"]
                )
            baseline_ic = metrics["matched_baseline_rank_ic"]
            v2_ic = metrics["research_v2_rank_ic"]
            metrics["delta_rank_ic"] = (
                v2_ic - baseline_ic if v2_ic is not None and baseline_ic is not None else None
            )
            metrics["rank_ic_comparison"] = (
                "V2_HIGHER" if metrics["delta_rank_ic"] > 0
                else "BASELINE_HIGHER" if metrics["delta_rank_ic"] < 0 else "TIE"
            )
            sector_rows.append(metrics)
        chosen: dict[str, pd.DataFrame] = {}
        for model, rank_column in model_values.items():
            count = min(5, peers)
            chosen[model] = _selection(group, rank_column, count)
            selections[(str(ranking_date), int(horizon), model)] = (
                selections.get((str(ranking_date), int(horizon), model), set())
                | set(chosen[model]["isin"])
            )
        baseline_set = set(chosen["MATCHED_BASELINE"]["isin"])
        v2_set = set(chosen["RESEARCH_V2"]["isin"])
        overlap_rows.append({
            "ranking_date": ranking_date, "sector": sector,
            "horizon_months": int(horizon), "selection_count": min(5, peers),
            "overlap_count": len(baseline_set & v2_set),
            "jaccard_overlap": len(baseline_set & v2_set) / len(baseline_set | v2_set),
            "baseline_tickers": "|".join(chosen["MATCHED_BASELINE"]["ticker"]),
            "research_v2_tickers": "|".join(chosen["RESEARCH_V2"]["ticker"]),
        })
        if peers >= 2:
            sector_mean = float(group["future_adjusted_return"].mean())
            for model, rank_column in model_values.items():
                credit, pair_count, model_ties, outcome_ties = _pairwise(group, rank_column)
                pair_rows.append({
                    "ranking_date": ranking_date, "sector": sector,
                    "horizon_months": int(horizon), "model": model,
                    "peer_count": peers, "evaluated_pairs": pair_count,
                    "correct_pair_credit": credit,
                    "pairwise_accuracy": credit / pair_count if pair_count else None,
                    "model_tie_pairs": model_ties,
                    "outcome_tie_pairs_excluded": outcome_ties,
                })
                ordered = _selection(group, rank_column, peers)
                top = ordered.iloc[0]
                top_rows.append({
                    "ranking_date": ranking_date, "sector": sector,
                    "horizon_months": int(horizon), "model": model,
                    "peer_count": peers, "top_ticker": top["ticker"],
                    "top_future_adjusted_return": top["future_adjusted_return"],
                    "sector_mean_future_adjusted_return": sector_mean,
                    "top_stock_excess_return": top["future_adjusted_return"] - sector_mean,
                })
                half = peers // 2
                top_half, bottom_half = ordered.iloc[:half], ordered.iloc[-half:]
                spread_rows.append({
                    "ranking_date": ranking_date, "sector": sector,
                    "horizon_months": int(horizon), "model": model,
                    "peer_count": peers,
                    "top_tickers": "|".join(top_half["ticker"]),
                    "bottom_tickers": "|".join(bottom_half["ticker"]),
                    "middle_omitted": ordered.iloc[half]["ticker"] if peers % 2 else "",
                    "top_mean_future_adjusted_return": float(top_half["future_adjusted_return"].mean()),
                    "bottom_mean_future_adjusted_return": float(bottom_half["future_adjusted_return"].mean()),
                    "top_bottom_spread": float(
                        top_half["future_adjusted_return"].mean()
                        - bottom_half["future_adjusted_return"].mean()
                    ),
                })

    for ranking_date in sorted(membership["ranking_date"].astype(str).unique()):
        for horizon in HORIZONS:
            baseline_set = selections[(ranking_date, horizon, "MATCHED_BASELINE")]
            v2_set = selections[(ranking_date, horizon, "RESEARCH_V2")]
            date_overlap_rows.append({
                "ranking_date": ranking_date, "horizon_months": horizon,
                "baseline_selection_count": len(baseline_set),
                "research_v2_selection_count": len(v2_set),
                "overlap_count": len(baseline_set & v2_set),
                "jaccard_overlap": len(baseline_set & v2_set) / len(baseline_set | v2_set),
            })

    identity_overlap_rows: list[dict[str, Any]] = []
    dates = sorted(membership["ranking_date"].astype(str).unique())
    for model in ("MATCHED_BASELINE", "RESEARCH_V2"):
        for previous, current in zip(dates, dates[1:]):
            prior = selections[(previous, PRIMARY_HORIZON, model)]
            later = selections[(current, PRIMARY_HORIZON, model)]
            shared = len(prior & later)
            identity_overlap_rows.append({
                "model": model, "previous_ranking_date": previous,
                "current_ranking_date": current,
                "previous_selection_count": len(prior),
                "current_selection_count": len(later), "shared_identity_count": shared,
                "jaccard_overlap": shared / len(prior | later),
                "one_way_replacement_rate": 1.0 - shared / min(len(prior), len(later)),
                "interpretation": "DESCRIPTIVE_IDENTITY_OVERLAP_NOT_A_COST_MODEL",
            })

    sector_metrics = pd.DataFrame(sector_rows)
    primary = sector_metrics.loc[sector_metrics["horizon_months"].eq(PRIMARY_HORIZON)].copy()
    diagnostic_rows: list[dict[str, Any]] = []
    for ranking_date, group in primary.groupby("ranking_date", sort=True):
        diagnostic_rows.append({
            "diagnostic": "PER_DATE_EQUAL_SECTOR_MEAN_DELTA",
            "omitted_group": "", "group": ranking_date,
            "observation_count": len(group), "mean_delta_rank_ic": float(group["delta_rank_ic"].mean()),
        })
    for omitted in sorted(primary["ranking_date"].unique()):
        kept = primary.loc[~primary["ranking_date"].eq(omitted)]
        diagnostic_rows.append({
            "diagnostic": "LEAVE_ONE_DATE_OUT", "omitted_group": omitted, "group": "ALL_OTHER_DATES",
            "observation_count": len(kept), "mean_delta_rank_ic": float(kept["delta_rank_ic"].mean()),
        })
    for omitted in sorted(primary["sector"].unique()):
        kept = primary.loc[~primary["sector"].eq(omitted)]
        diagnostic_rows.append({
            "diagnostic": "LEAVE_ONE_SECTOR_OUT", "omitted_group": omitted, "group": "ALL_OTHER_SECTORS",
            "observation_count": len(kept), "mean_delta_rank_ic": float(kept["delta_rank_ic"].mean()),
        })

    rank_changes = pd.DataFrame(rank_rows)
    pairwise = pd.DataFrame(pair_rows)
    top_excess = pd.DataFrame(top_rows)
    spreads = pd.DataFrame(spread_rows)
    sector_overlaps = pd.DataFrame(overlap_rows)
    date_overlaps = pd.DataFrame(date_overlap_rows)
    identity_overlaps = pd.DataFrame(identity_overlap_rows)
    diagnostics = pd.DataFrame(diagnostic_rows)
    horizon_summaries: dict[str, Any] = {}
    for horizon in HORIZONS:
        metrics = sector_metrics.loc[sector_metrics["horizon_months"].eq(horizon)]
        pairs = pairwise.loc[pairwise["horizon_months"].eq(horizon)]
        model_pairwise: dict[str, Any] = {}
        for model in ("MATCHED_BASELINE", "RESEARCH_V2"):
            subset = pairs.loc[pairs["model"].eq(model)]
            denominator = int(subset["evaluated_pairs"].sum())
            credit = float(subset["correct_pair_credit"].sum())
            model_pairwise[model.lower()] = {
                "evaluated_pairs": denominator,
                "correct_pair_credit": credit,
                "pairwise_accuracy": credit / denominator if denominator else None,
            }
        model_top = {}
        model_spread = {}
        for model in ("MATCHED_BASELINE", "RESEARCH_V2"):
            model_top[model.lower()] = float(top_excess.loc[
                top_excess["horizon_months"].eq(horizon) & top_excess["model"].eq(model),
                "top_stock_excess_return",
            ].mean())
            model_spread[model.lower()] = float(spreads.loc[
                spreads["horizon_months"].eq(horizon) & spreads["model"].eq(model),
                "top_bottom_spread",
            ].mean())
        top_pivot = top_excess.loc[top_excess["horizon_months"].eq(horizon)].pivot(
            index=["ranking_date", "sector"], columns="model", values="top_ticker"
        )
        top_same = top_pivot["MATCHED_BASELINE"].eq(top_pivot["RESEARCH_V2"])
        top_return_pivot = top_excess.loc[
            top_excess["horizon_months"].eq(horizon)
        ].pivot(
            index=["ranking_date", "sector"], columns="model",
            values="top_stock_excess_return",
        )
        top_return_delta = (
            top_return_pivot["RESEARCH_V2"] - top_return_pivot["MATCHED_BASELINE"]
        )
        spread_pivot = spreads.loc[spreads["horizon_months"].eq(horizon)].pivot(
            index=["ranking_date", "sector"], columns="model", values="top_bottom_spread"
        )
        spread_delta = spread_pivot["RESEARCH_V2"] - spread_pivot["MATCHED_BASELINE"]
        horizon_summaries[str(horizon)] = {
            "valid_sector_date_observations": int(len(metrics)),
            "matched_baseline_rank_ic": _metric_summary(metrics["matched_baseline_rank_ic"]),
            "research_v2_rank_ic": _metric_summary(metrics["research_v2_rank_ic"]),
            "delta_rank_ic": _metric_summary(metrics["delta_rank_ic"]),
            "v2_wins": int(metrics["rank_ic_comparison"].eq("V2_HIGHER").sum()),
            "ties": int(metrics["rank_ic_comparison"].eq("TIE").sum()),
            "baseline_wins": int(metrics["rank_ic_comparison"].eq("BASELINE_HIGHER").sum()),
            "pairwise": model_pairwise,
            "pairwise_accuracy_delta": (
                model_pairwise["research_v2"]["pairwise_accuracy"]
                - model_pairwise["matched_baseline"]["pairwise_accuracy"]
            ),
            "mean_top_stock_excess_return": model_top,
            "mean_top_bottom_spread": model_spread,
            "top_ranked_ticker_agreement": {
                "same": int(top_same.sum()), "different": int((~top_same).sum()),
                "rate": float(top_same.mean()),
            },
            "top_stock_excess_delta_wins_ties_losses": {
                "v2_wins": int(top_return_delta.gt(0).sum()),
                "ties": int(top_return_delta.eq(0).sum()),
                "baseline_wins": int(top_return_delta.lt(0).sum()),
            },
            "top_bottom_spread_delta_wins_ties_losses": {
                "v2_wins": int(spread_delta.gt(0).sum()),
                "ties": int(spread_delta.eq(0).sum()),
                "baseline_wins": int(spread_delta.lt(0).sum()),
            },
            "matched_baseline_kendall_tau_b": _metric_summary(
                metrics["matched_baseline_kendall_tau_b"]
            ),
            "research_v2_kendall_tau_b": _metric_summary(
                metrics["research_v2_kendall_tau_b"]
            ),
            "mean_date_top_n_jaccard": float(date_overlaps.loc[
                date_overlaps["horizon_months"].eq(horizon), "jaccard_overlap"
            ].mean()),
        }
    primary_summary = horizon_summaries[str(PRIMARY_HORIZON)]
    mean_delta = primary_summary["delta_rank_ic"]["mean"]
    if mean_delta > 0 and primary_summary["v2_wins"] > primary_summary["baseline_wins"]:
        direction = "DESCRIPTIVE_V2_HIGHER"
    elif mean_delta < 0 and primary_summary["baseline_wins"] > primary_summary["v2_wins"]:
        direction = "DESCRIPTIVE_BASELINE_HIGHER"
    else:
        direction = "DESCRIPTIVE_MIXED_OR_EQUIVALENT"
    summary = {
        "schema_version": SCHEMA_VERSION,
        "protocol_fingerprint": protocol_fingerprint,
        "cohort_membership_sha256": cohort_fingerprint,
        "blind_manifest_sha256": blind_manifest_fingerprint,
        "rankings_frozen_before_outcomes_read": True,
        "ranking_models_recomputed_after_outcome_reveal": False,
        "company_date_count": int(len(membership)),
        "company_date_horizon_count": int(len(future_returns)),
        "cohort_sizes": membership.groupby("ranking_date", sort=True).size().astype(int).to_dict(),
        "primary_horizon_months": PRIMARY_HORIZON,
        "primary_metric": "EQUAL_WEIGHT_SECTOR_DATE_SPEARMAN_RANK_IC",
        "primary_descriptive_direction": direction,
        "horizons": horizon_summaries,
        "mean_absolute_rank_change": float(rank_changes["absolute_rank_change"].mean()),
        "exact_rank_agreement_rate": float(rank_changes["absolute_rank_change"].eq(0).mean()),
        "transaction_cost_model": None,
        "selection_identity_overlap_is_descriptive_only": True,
        "robustness_diagnostics_are_supplementary": True,
        "limitations": [
            "Only four annual ranking dates are available; no significance claim is supported.",
            "Sector-date cells are small and only sectors with at least three members enter Rank IC.",
            "Adjusted-price outcomes were retrospectively acquired and inherit Yahoo adjustment semantics.",
            "No transaction-cost, liquidity, execution, or investable-portfolio model is part of this study.",
            "Screener values are hash-pinned standalone financials paired with official exchange availability clocks; later vendor restatement risk remains documented.",
        ],
        "forbidden_claims": [
            "universal model superiority", "statistical significance", "portfolio profitability",
            "real-time tradability", "investment advice",
        ],
    }
    return ScreenerHistoricalEvaluation(
        future_returns, sector_metrics, pairwise, top_excess, spreads,
        sector_overlaps, date_overlaps, rank_changes, identity_overlaps,
        diagnostics, summary,
    )


def _primary_aggregate_tables(
    evaluation: ScreenerHistoricalEvaluation,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    primary = evaluation.sector_metrics.loc[
        evaluation.sector_metrics["horizon_months"].eq(PRIMARY_HORIZON)
    ]
    date_rows = []
    for ranking_date, group in primary.groupby("ranking_date", sort=True):
        date_rows.append({
            "ranking_date": ranking_date, "valid_sector_count": len(group),
            "matched_baseline_mean_rank_ic": float(group["matched_baseline_rank_ic"].mean()),
            "research_v2_mean_rank_ic": float(group["research_v2_rank_ic"].mean()),
            "mean_delta_rank_ic": float(group["delta_rank_ic"].mean()),
            "v2_wins": int(group["rank_ic_comparison"].eq("V2_HIGHER").sum()),
            "ties": int(group["rank_ic_comparison"].eq("TIE").sum()),
            "baseline_wins": int(group["rank_ic_comparison"].eq("BASELINE_HIGHER").sum()),
        })
    sector_rows = []
    for sector, group in primary.groupby("sector", sort=True):
        sector_rows.append({
            "sector": sector, "ranking_date_count": len(group),
            "matched_baseline_mean_rank_ic": float(group["matched_baseline_rank_ic"].mean()),
            "research_v2_mean_rank_ic": float(group["research_v2_rank_ic"].mean()),
            "mean_delta_rank_ic": float(group["delta_rank_ic"].mean()),
            "v2_wins": int(group["rank_ic_comparison"].eq("V2_HIGHER").sum()),
            "ties": int(group["rank_ic_comparison"].eq("TIE").sum()),
            "baseline_wins": int(group["rank_ic_comparison"].eq("BASELINE_HIGHER").sum()),
        })
    return pd.DataFrame(date_rows), pd.DataFrame(sector_rows)


def _report_markdown(evaluation: ScreenerHistoricalEvaluation) -> str:
    primary = evaluation.summary["horizons"][str(PRIMARY_HORIZON)]
    date_summary, sector_summary = _primary_aggregate_tables(evaluation)
    lines = [
        "# Final historical Baseline V1 vs Research V2 evaluation", "",
        "## Scientific status", "",
        f"Primary descriptive direction: `{evaluation.summary['primary_descriptive_direction']}`.",
        "This is a four-date descriptive historical study, not a statistical-significance, portfolio-profitability, or investment claim.",
        "", "## Frozen execution", "",
        f"- Protocol fingerprint: `{evaluation.summary['protocol_fingerprint']}`",
        f"- Frozen cohort fingerprint: `{evaluation.summary['cohort_membership_sha256']}`",
        f"- Blind manifest fingerprint: `{evaluation.summary['blind_manifest_sha256']}`",
        f"- Company-date observations: {evaluation.summary['company_date_count']}",
        f"- Cohort sizes: {evaluation.summary['cohort_sizes']}",
        "- Rankings and eligibility were frozen before adjusted-price outcomes were read.",
        "", "## Primary 12-month evidence", "",
        f"- Valid sector-date cells: {primary['valid_sector_date_observations']}",
        f"- Matched Baseline mean Rank IC: {primary['matched_baseline_rank_ic']['mean']:.6f}",
        f"- Research V2 mean Rank IC: {primary['research_v2_rank_ic']['mean']:.6f}",
        f"- Mean paired Rank IC delta (V2 - Baseline): {primary['delta_rank_ic']['mean']:.6f}",
        f"- Rank IC wins/ties/losses for V2: {primary['v2_wins']}/{primary['ties']}/{primary['baseline_wins']}",
        f"- Baseline pairwise accuracy: {primary['pairwise']['matched_baseline']['pairwise_accuracy']:.6f}",
        f"- Research V2 pairwise accuracy: {primary['pairwise']['research_v2']['pairwise_accuracy']:.6f}",
        f"- Mean top-half-minus-bottom-half spread, Baseline/V2: {primary['mean_top_bottom_spread']['matched_baseline']:.6f} / {primary['mean_top_bottom_spread']['research_v2']:.6f}",
        f"- Mean top-stock excess, Baseline/V2: {primary['mean_top_stock_excess_return']['matched_baseline']:.6f} / {primary['mean_top_stock_excess_return']['research_v2']:.6f}",
        f"- Top-ranked ticker agreement: {primary['top_ranked_ticker_agreement']['same']} / {primary['top_ranked_ticker_agreement']['same'] + primary['top_ranked_ticker_agreement']['different']}",
        "", "## Primary result by ranking date", "",
        "| Ranking date | Baseline mean Rank IC | V2 mean Rank IC | Delta | V2 W/T/L |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in date_summary.to_dict("records"):
        lines.append(
            f"| {row['ranking_date']} | {row['matched_baseline_mean_rank_ic']:.6f} | "
            f"{row['research_v2_mean_rank_ic']:.6f} | {row['mean_delta_rank_ic']:.6f} | "
            f"{row['v2_wins']}/{row['ties']}/{row['baseline_wins']} |"
        )
    lines.extend([
        "", "## Primary result by sector", "",
        "| Sector | Baseline mean Rank IC | V2 mean Rank IC | Delta | V2 W/T/L |",
        "|---|---:|---:|---:|---:|",
    ])
    for row in sector_summary.to_dict("records"):
        lines.append(
            f"| {row['sector']} | {row['matched_baseline_mean_rank_ic']:.6f} | "
            f"{row['research_v2_mean_rank_ic']:.6f} | {row['mean_delta_rank_ic']:.6f} | "
            f"{row['v2_wins']}/{row['ties']}/{row['baseline_wins']} |"
        )
    lines.extend([
        "", "## Robustness and contradictory evidence", "",
        "The per-date and leave-one-group-out diagnostics are supplementary. They expose concentration and never replace the primary result. Every signed sector-date result remains in `sector_metrics.csv`.",
        "",
        "The frozen top-N rule selects `min(5, sector size)`. Every eligible sector has at most five members, so top-N overlap is mechanically 100% and is not informative. Top-1 and exact rank-change results remain informative.",
        "", "## Interpretation boundary", "",
        "The primary result gives every valid sector-date cell equal weight. Secondary horizons, top-stock excess, top-half-minus-bottom-half spreads, selection overlap, and leave-one-group-out tables are diagnostics only and do not redefine the primary result. Negative and contradictory cells remain visible.",
        "",
        "No transaction-cost result is reported because the frozen protocol contains no executable cost model. Adjacent-date identity overlap is descriptive only.", "",
    ])
    return "\n".join(lines)


def export_frozen_evaluation(
    evaluation: ScreenerHistoricalEvaluation,
    output: str | Path,
    provenance: dict[str, Any],
) -> str:
    root = Path(output)
    if root.exists():
        raise ValueError(f"evaluation output already exists: {root}")
    root.mkdir(parents=True)
    frames = {
        "future_returns.csv": evaluation.future_returns,
        "sector_metrics.csv": evaluation.sector_metrics,
        "pairwise_accuracy.csv": evaluation.pairwise_accuracy,
        "top_stock_excess.csv": evaluation.top_stock_excess,
        "top_bottom_spread.csv": evaluation.top_bottom_spread,
        "sector_top_n_overlap.csv": evaluation.sector_top_n_overlap,
        "date_top_n_overlap.csv": evaluation.date_top_n_overlap,
        "rank_changes.csv": evaluation.rank_changes,
        "selection_identity_overlap.csv": evaluation.selection_identity_overlap,
        "concentration_diagnostics.csv": evaluation.concentration_diagnostics,
    }
    date_summary, sector_summary = _primary_aggregate_tables(evaluation)
    frames["primary_date_summary.csv"] = date_summary
    frames["primary_sector_summary.csv"] = sector_summary
    options = {
        "index": False, "encoding": "utf-8", "lineterminator": "\n",
        "float_format": "%.17g", "na_rep": "",
    }
    for name, frame in frames.items():
        frame.to_csv(root / name, **options)
    (root / "evaluation_summary.json").write_bytes(
        canonical_json_bytes(evaluation.summary) + b"\n"
    )
    (root / "provenance.json").write_bytes(canonical_json_bytes(provenance) + b"\n")
    (root / "final_research_report.md").write_text(
        _report_markdown(evaluation), encoding="utf-8", newline="\n"
    )
    inventory = [
        {"path": path.name, "sha256": _file_hash(path), "size": path.stat().st_size}
        for path in sorted(root.iterdir(), key=lambda item: item.name)
    ]
    fingerprint = canonical_json_fingerprint(inventory)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "evaluation_fingerprint": fingerprint,
        "artifacts": inventory,
    }
    (root / "manifest.json").write_bytes(canonical_json_bytes(manifest) + b"\n")
    return fingerprint
