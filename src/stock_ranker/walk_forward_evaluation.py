"""Frozen-cohort walk-forward outcome evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from stock_research.evaluation import _correlation, _metric_summary
from stock_ranker.walk_forward_blind import canonical_json_bytes


BLIND_FINGERPRINT = "c438c31967e1f2685bbe77d85db6ca44617e024c699dba3749ee3523af6e401d"
PROTOCOL_SHA256 = "a81278b799e1a61c3684f3b319fb14e2f6f0db6a2bdad1cd79b2ce13fd6f8576"
AMENDMENT_SHA256 = "7f8c5d40de88077f3b6afcd471d0db4377fab567d2839e719a71ee6b11ae7163"
HORIZONS = (3, 6, 12)
RANKING_DATES = ("2022-08-05", "2023-08-07", "2024-08-07", "2025-08-07")


@dataclass(frozen=True, slots=True)
class WalkForwardEvaluation:
    future_returns: pd.DataFrame
    sector_rank_ic: pd.DataFrame
    pairwise_accuracy: pd.DataFrame
    top_stock_excess_return: pd.DataFrame
    top_bottom_spread: pd.DataFrame
    summary: dict[str, Any]


def calendar_target(ranking_date: str, horizon_months: int) -> str:
    if horizon_months not in HORIZONS:
        raise ValueError("horizon must be 3, 6, or 12 months")
    return (pd.Timestamp(ranking_date) + pd.DateOffset(months=horizon_months)).date().isoformat()


def select_price_on_or_before(prices: pd.DataFrame, target_date: str) -> pd.Series:
    frame = prices.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    target = pd.Timestamp(target_date)
    eligible = frame.loc[frame["date"].le(target)].sort_values("date", kind="stable")
    if eligible.empty:
        raise ValueError(f"OUTCOME_UNAVAILABLE: no price on or before {target_date}")
    return eligible.iloc[-1]


def calculate_future_returns(outcome_prices: pd.DataFrame) -> pd.DataFrame:
    required = {"ranking_date", "ticker", "provider_symbol", "date", "adj_close"}
    missing = required.difference(outcome_prices.columns)
    if missing:
        raise ValueError(f"outcome prices missing columns: {sorted(missing)}")
    checked = outcome_prices.copy(deep=True)
    checked["date"] = pd.to_datetime(checked["date"], errors="raise")
    if checked[["ranking_date", "ticker", "provider_symbol"]].isna().any().any():
        raise ValueError("outcome prices contain missing identity values")
    if checked[["ranking_date", "ticker", "provider_symbol"]].astype(str).apply(
        lambda column: column.str.strip().eq("")
    ).any().any():
        raise ValueError("outcome prices contain blank identity values")
    if checked.duplicated(["ranking_date", "ticker", "date"]).any():
        raise ValueError("outcome prices contain duplicate company-date observations")
    provider_counts = checked.groupby(
        ["ranking_date", "ticker"], sort=True
    )["provider_symbol"].nunique(dropna=False)
    if provider_counts.ne(1).any():
        raise ValueError("outcome prices contain mixed provider identities")
    checked["adj_close"] = pd.to_numeric(checked["adj_close"], errors="coerce")
    if (~np.isfinite(checked["adj_close"]) | checked["adj_close"].le(0)).any():
        raise ValueError("OUTCOME_UNAVAILABLE: invalid adjusted price")
    rows = []
    for (ranking_date, ticker), group in checked.groupby(
        ["ranking_date", "ticker"], sort=True
    ):
        start = select_price_on_or_before(group, str(ranking_date))
        if pd.Timestamp(start["date"]).date().isoformat() != str(ranking_date):
            raise ValueError(f"OUTCOME_UNAVAILABLE: ranking-date observation absent for {ticker} {ranking_date}")
        start_price = float(start["adj_close"])
        if not np.isfinite(start_price) or start_price <= 0:
            raise ValueError(f"OUTCOME_UNAVAILABLE: invalid start adjusted price for {ticker}")
        for months in HORIZONS:
            target = calendar_target(str(ranking_date), months)
            endpoint = select_price_on_or_before(group, target)
            endpoint_date = pd.Timestamp(endpoint["date"]).date().isoformat()
            endpoint_price = float(endpoint["adj_close"])
            if endpoint_date > target:
                raise ValueError("future endpoint selected after calendar target")
            if not np.isfinite(endpoint_price) or endpoint_price <= 0:
                raise ValueError(f"OUTCOME_UNAVAILABLE: invalid endpoint adjusted price for {ticker}")
            rows.append({
                "ranking_date": str(ranking_date), "ticker": str(ticker),
                "provider_symbol": str(start["provider_symbol"]),
                "horizon_months": months, "target_date": target,
                "start_date": pd.Timestamp(start["date"]).date().isoformat(),
                "actual_endpoint_date": endpoint_date,
                "endpoint_distance_days": (pd.Timestamp(target) - pd.Timestamp(endpoint_date)).days,
                "start_adjusted_close": start_price,
                "endpoint_adjusted_close": endpoint_price,
                "future_adjusted_return": endpoint_price / start_price - 1,
                "label_semantics": "ADJUSTED-PRICE FUTURE RETURN",
            })
    return pd.DataFrame(rows).sort_values(
        ["ranking_date", "ticker", "horizon_months"], kind="stable"
    ).reset_index(drop=True)


def _spearman(signal: pd.Series, outcome: pd.Series) -> float | None:
    if len(signal) < 2 or signal.nunique() < 2 or outcome.nunique() < 2:
        return None
    return _correlation(signal.rank(method="average"), outcome.rank(method="average"))


def _frozen_groups(blind_root: Path) -> pd.DataFrame:
    frames = []
    for ranking_date in RANKING_DATES:
        v2 = pd.read_csv(blind_root / ranking_date / "research_v2.csv")
        matched = pd.read_csv(blind_root / ranking_date / "matched_baseline.csv")
        selected = matched.loc[matched["comparison_status"].isin([
            "MATCHED_COHORT", "SINGLE_ELIGIBLE_PEER"
        ])].copy()
        joined = v2[["ticker", "research_v2_score", "sector_rank"]].merge(
            selected[["ticker", "historical_sector", "matched_baseline_sector_rank",
                      "original_baseline_sector_rank", "eligible_peer_count"]],
            on="ticker", how="inner", validate="one_to_one",
        )
        joined["ranking_date"] = ranking_date
        joined = joined.rename(columns={"sector_rank": "research_v2_sector_rank"})
        frames.append(joined)
    return pd.concat(frames, ignore_index=True).sort_values(
        ["ranking_date", "historical_sector", "ticker"], kind="stable"
    ).reset_index(drop=True)


def _pairwise(group: pd.DataFrame, rank_column: str) -> tuple[float, int, int, int]:
    numerator = 0.0
    denominator = 0
    model_ties = 0
    outcome_ties = 0
    values = group.sort_values("ticker", kind="stable").to_dict("records")
    for left_index, left in enumerate(values):
        for right in values[left_index + 1:]:
            outcome_delta = left["future_adjusted_return"] - right["future_adjusted_return"]
            if outcome_delta == 0:
                outcome_ties += 1
                continue
            rank_delta = right[rank_column] - left[rank_column]
            denominator += 1
            if rank_delta == 0:
                model_ties += 1
                numerator += 0.5
            elif np.sign(rank_delta) == np.sign(outcome_delta):
                numerator += 1.0
    return numerator, denominator, model_ties, outcome_ties


def _ordered(group: pd.DataFrame, rank_column: str) -> pd.DataFrame:
    return group.sort_values([rank_column, "ticker"], kind="stable")


def evaluate_walk_forward(
    blind_root: Path, future_returns: pd.DataFrame,
) -> WalkForwardEvaluation:
    manifest = json.loads((blind_root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("blind_prediction_fingerprint") != BLIND_FINGERPRINT:
        raise ValueError("frozen blind fingerprint mismatch")
    if manifest.get("protocol_sha256") != PROTOCOL_SHA256:
        raise ValueError("frozen protocol hash mismatch")
    if manifest.get("future_outcome_data_present") is not False:
        raise ValueError("frozen prediction bundle is not outcome-blind")
    frozen = _frozen_groups(blind_root)
    required_outcomes = {
        "ranking_date", "ticker", "horizon_months", "future_adjusted_return",
    }
    missing_outcomes = required_outcomes.difference(future_returns.columns)
    if missing_outcomes:
        raise ValueError(f"future returns missing columns: {sorted(missing_outcomes)}")
    if future_returns.duplicated(["ranking_date", "ticker", "horizon_months"]).any():
        raise ValueError("future returns contain duplicate company-date-horizon keys")
    observed_horizons = set(pd.to_numeric(
        future_returns["horizon_months"], errors="coerce"
    ).dropna().astype(int))
    if observed_horizons != set(HORIZONS):
        raise ValueError("future returns do not contain the frozen horizon set")
    numeric_returns = pd.to_numeric(future_returns["future_adjusted_return"], errors="coerce")
    if (~np.isfinite(numeric_returns)).any():
        raise ValueError("OUTCOME_UNAVAILABLE: non-finite future return")
    future_returns = future_returns.copy(deep=True)
    future_returns["future_adjusted_return"] = numeric_returns
    expected_keys = frozen[["ranking_date", "ticker"]].drop_duplicates().sort_values(
        ["ranking_date", "ticker"], kind="stable"
    ).reset_index(drop=True)
    actual_keys = future_returns[["ranking_date", "ticker"]].drop_duplicates().sort_values(
        ["ranking_date", "ticker"], kind="stable"
    ).reset_index(drop=True)
    if not expected_keys.equals(actual_keys):
        raise ValueError("outcome cohort does not match frozen predictions")
    expected_outcomes = len(expected_keys) * len(HORIZONS)
    if len(future_returns) != expected_outcomes or future_returns["future_adjusted_return"].isna().any():
        raise ValueError("OUTCOME_UNAVAILABLE: incomplete frozen cohort labels")
    panel = frozen.merge(
        future_returns, on=["ranking_date", "ticker"], how="inner", validate="one_to_many"
    )
    rank_rows, pair_rows, top_rows, spread_rows = [], [], [], []
    for (ranking_date, sector, horizon), group in panel.groupby(
        ["ranking_date", "historical_sector", "horizon_months"], sort=True
    ):
        peers = len(group)
        if peers >= 3:
            v2_ic = _spearman(group["research_v2_score"], group["future_adjusted_return"])
            baseline_ic = _spearman(
                -group["matched_baseline_sector_rank"], group["future_adjusted_return"]
            )
            rank_rows.append({
                "ranking_date": ranking_date, "historical_sector": sector,
                "horizon_months": int(horizon), "peer_count": peers,
                "tickers": "|".join(sorted(group["ticker"])),
                "realized_returns": "|".join(
                    f"{row.ticker}:{row.future_adjusted_return:.17g}"
                    for row in group.sort_values("ticker", kind="stable").itertuples()
                ),
                "research_v2_ranks": "|".join(
                    f"{row.ticker}:{row.research_v2_sector_rank:.17g}"
                    for row in group.sort_values("ticker", kind="stable").itertuples()
                ),
                "matched_baseline_ranks": "|".join(
                    f"{row.ticker}:{row.matched_baseline_sector_rank:.17g}"
                    for row in group.sort_values("ticker", kind="stable").itertuples()
                ),
                "research_v2_rank_ic": v2_ic, "matched_baseline_rank_ic": baseline_ic,
                "delta_rank_ic": (
                    v2_ic - baseline_ic if v2_ic is not None and baseline_ic is not None else None
                ),
                "comparison": (
                    "V2_HIGHER" if v2_ic is not None and baseline_ic is not None and v2_ic > baseline_ic
                    else "BASELINE_HIGHER" if v2_ic is not None and baseline_ic is not None and v2_ic < baseline_ic
                    else "EQUAL"
                ),
            })
        if peers < 2:
            continue
        cohort_mean = float(group["future_adjusted_return"].mean())
        for model, rank_column in (
            ("RESEARCH_V2", "research_v2_sector_rank"),
            ("MATCHED_BASELINE", "matched_baseline_sector_rank"),
        ):
            numerator, denominator, model_ties, outcome_ties = _pairwise(group, rank_column)
            pair_rows.append({
                "ranking_date": ranking_date, "historical_sector": sector,
                "horizon_months": int(horizon), "model": model, "peer_count": peers,
                "evaluated_pairs": denominator, "correct_pair_credit": numerator,
                "model_tie_pairs": model_ties, "outcome_tie_pairs_excluded": outcome_ties,
                "pairwise_accuracy": numerator / denominator if denominator else None,
            })
            ordered = _ordered(group, rank_column)
            top = ordered.iloc[0]
            top_rows.append({
                "ranking_date": ranking_date, "historical_sector": sector,
                "horizon_months": int(horizon), "model": model, "peer_count": peers,
                "top_ticker": top["ticker"], "top_future_adjusted_return": top["future_adjusted_return"],
                "cohort_mean_future_adjusted_return": cohort_mean,
                "top_stock_excess_return": top["future_adjusted_return"] - cohort_mean,
            })
            half = peers // 2
            top_group = ordered.iloc[:half]
            bottom_group = ordered.iloc[-half:]
            spread_rows.append({
                "ranking_date": ranking_date, "historical_sector": sector,
                "horizon_months": int(horizon), "model": model, "peer_count": peers,
                "top_tickers": "|".join(top_group["ticker"]),
                "bottom_tickers": "|".join(bottom_group["ticker"]),
                "middle_omitted": ordered.iloc[half]["ticker"] if peers % 2 else "",
                "top_mean_future_adjusted_return": float(top_group["future_adjusted_return"].mean()),
                "bottom_mean_future_adjusted_return": float(bottom_group["future_adjusted_return"].mean()),
                "top_bottom_spread": float(top_group["future_adjusted_return"].mean() - bottom_group["future_adjusted_return"].mean()),
            })
    rank_ic = pd.DataFrame(rank_rows)
    pairwise = pd.DataFrame(pair_rows)
    top_excess = pd.DataFrame(top_rows)
    spreads = pd.DataFrame(spread_rows)
    horizons: dict[str, Any] = {}
    for months in HORIZONS:
        rank = rank_ic.loc[rank_ic["horizon_months"].eq(months)]
        model_metrics = {}
        for model, column in (
            ("research_v2", "research_v2_rank_ic"),
            ("matched_baseline", "matched_baseline_rank_ic"),
        ):
            model_metrics[model] = _metric_summary(rank[column])
            model_metrics[model]["median"] = (
                float(rank[column].median()) if rank[column].notna().any() else None
            )
        pair = pairwise.loc[pairwise["horizon_months"].eq(months)]
        pair_summary = {}
        for model in ("RESEARCH_V2", "MATCHED_BASELINE"):
            rows = pair.loc[pair["model"].eq(model)]
            denominator = int(rows["evaluated_pairs"].sum())
            pair_summary[model.lower()] = {
                "evaluated_pairs": denominator,
                "correct_pair_credit": float(rows["correct_pair_credit"].sum()),
                "pairwise_accuracy": float(rows["correct_pair_credit"].sum() / denominator) if denominator else None,
                "model_tie_pairs": int(rows["model_tie_pairs"].sum()),
                "outcome_tie_pairs_excluded": int(rows["outcome_tie_pairs_excluded"].sum()),
            }
        horizons[str(months)] = {
            "rank_ic_observation_count": len(rank),
            "research_v2_rank_ic": model_metrics["research_v2"],
            "matched_baseline_rank_ic": model_metrics["matched_baseline"],
            "mean_delta_rank_ic": float(rank["delta_rank_ic"].mean()) if len(rank) else None,
            "wins": int(rank["comparison"].eq("V2_HIGHER").sum()),
            "ties": int(rank["comparison"].eq("EQUAL").sum()),
            "losses": int(rank["comparison"].eq("BASELINE_HIGHER").sum()),
            "pairwise": pair_summary,
            "pairwise_accuracy_difference": (
                pair_summary["research_v2"]["pairwise_accuracy"]
                - pair_summary["matched_baseline"]["pairwise_accuracy"]
                if pair_summary["research_v2"]["pairwise_accuracy"] is not None
                and pair_summary["matched_baseline"]["pairwise_accuracy"] is not None
                else None
            ),
            "mean_top_stock_excess_return": {
                model.lower(): float(top_excess.loc[
                    top_excess["horizon_months"].eq(months) & top_excess["model"].eq(model),
                    "top_stock_excess_return",
                ].mean()) for model in ("RESEARCH_V2", "MATCHED_BASELINE")
            },
            "mean_top_bottom_spread": {
                model.lower(): float(spreads.loc[
                    spreads["horizon_months"].eq(months) & spreads["model"].eq(model),
                    "top_bottom_spread",
                ].mean()) for model in ("RESEARCH_V2", "MATCHED_BASELINE")
            },
        }
    primary = horizons["12"]
    if primary["wins"] and primary["losses"]:
        overall_descriptor = "MIXED"
    elif primary["wins"]:
        overall_descriptor = "V2_HIGHER"
    elif primary["losses"]:
        overall_descriptor = "BASELINE_HIGHER"
    else:
        overall_descriptor = "EQUAL"
    summary = {
        "schema_version": 1, "blind_prediction_fingerprint": BLIND_FINGERPRINT,
        "protocol_sha256": PROTOCOL_SHA256, "amendment_sha256": AMENDMENT_SHA256,
        "label_semantics": "ADJUSTED-PRICE FUTURE RETURN",
        "rank_ic_convention": "Pearson correlation of within-sector average ranks",
        "icir_convention": "unannualized mean sector-date Rank IC / sample standard deviation (ddof=1)",
        "pairwise_tie_policy": "model ties receive 0.5 credit; exact outcome ties are excluded",
        "odd_cohort_policy": "equal top/bottom groups; middle ticker omitted",
        "primary_horizon_months": 12, "very_low_primary_sample_size": True,
        "neutral_overall_descriptor": overall_descriptor,
        "frozen_company_date_count": len(expected_keys),
        "complete_company_date_horizon_count": len(future_returns),
        "horizons": horizons,
        "interpretation_limits": [
            "Only four annual ranking dates are evaluated.",
            "Strict point-in-time filing availability reduced Research V2 coverage.",
            "Only three primary sector-date observations were structurally available.",
            "Primary statistical power is very low.",
            "This evaluates ranking quality, not investment profitability.",
            "Yahoo historical data was retrospectively acquired and inherits adjusted-price semantics.",
            "No transaction costs, liquidity assumptions, or portfolio execution model are included.",
        ],
    }
    return WalkForwardEvaluation(future_returns, rank_ic, pairwise, top_excess, spreads, summary)


def export_evaluation(
    evaluation: WalkForwardEvaluation, outcome_prices: pd.DataFrame,
    provenance: dict[str, Any], output: Path,
) -> str:
    if output.exists():
        raise ValueError(f"evaluation output already exists: {output}")
    output.mkdir(parents=True)
    csv_options = dict(index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g", na_rep="")
    artifacts: list[tuple[str, Any]] = [
        ("outcome_prices.csv", outcome_prices),
        ("future_returns.csv", evaluation.future_returns),
        ("sector_rank_ic.csv", evaluation.sector_rank_ic),
        ("pairwise_accuracy.csv", evaluation.pairwise_accuracy),
        ("top_stock_excess_return.csv", evaluation.top_stock_excess_return),
        ("top_bottom_spread.csv", evaluation.top_bottom_spread),
    ]
    for name, frame in artifacts:
        frame.to_csv(output / name, **csv_options)
    (output / "evaluation_summary.json").write_text(
        json.dumps(evaluation.summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    (output / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    inventory = []
    for path in sorted(output.iterdir(), key=lambda item: item.name):
        inventory.append({"path": path.name, "sha256": sha256(path.read_bytes()).hexdigest(), "size": path.stat().st_size})
    fingerprint = sha256(canonical_json_bytes(inventory)).hexdigest()
    manifest = {
        "schema_version": 1, "evaluation_fingerprint": fingerprint,
        "blind_prediction_fingerprint": BLIND_FINGERPRINT, "artifacts": inventory,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return fingerprint
