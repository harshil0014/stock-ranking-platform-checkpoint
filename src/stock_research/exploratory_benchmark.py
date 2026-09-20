"""Theory-fixed supplementary benchmarks on an already revealed frozen study.

This module never changes the preregistered Baseline/V2 result. It evaluates a
strict OpenSourceAP Mom12m signal and fixed equal-weight rank ensembles only as
supplementary evidence. No parameter is selected from the outcomes.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

MODEL_COLUMNS = {
    "baseline_v1": "baseline_signal",
    "research_v2": "research_v2_signal",
    "opensourceap_mom12m": "mom12m_signal",
    "baseline_mom12m_equal_weight": "baseline_mom12m_signal",
    "v2_mom12m_equal_weight": "v2_mom12m_signal",
    "baseline_v2_mom12m_equal_weight": "three_way_signal",
    "mom6m": "mom6m_signal",
    "short_term_reversal": "reversal1m_signal",
    "low_volatility_12m": "low_volatility_signal",
    "shallow_drawdown_12m": "shallow_drawdown_signal",
    "baseline_price_multifactor_equal_weight": "baseline_price_multifactor_signal",
}


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _artifact_hash(root: Path, relative: str) -> str:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    matches = [item["sha256"] for item in manifest["artifacts"] if item["path"] == relative]
    if len(matches) != 1:
        raise ValueError(f"evaluation manifest does not uniquely identify {relative}")
    path = root / relative
    if _hash(path) != matches[0]:
        raise ValueError(f"frozen evaluation artifact changed: {relative}")
    return matches[0]


def strict_mom12m(history: pd.DataFrame, ranking_date: str) -> float:
    """Compound complete calendar-month returns t-11 through t-1."""
    required = {"date", "adjusted_close"}
    if missing := required.difference(history.columns):
        raise ValueError(f"adjusted-price history is missing {sorted(missing)}")
    frame = history[list(required)].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    frame["adjusted_close"] = pd.to_numeric(frame["adjusted_close"], errors="coerce")
    if frame["date"].duplicated().any():
        raise ValueError("adjusted-price history contains duplicate dates")
    decision = pd.Timestamp(ranking_date)
    frame = frame.loc[frame["date"].le(decision)].copy()
    frame["month"] = frame["date"].dt.to_period("M")
    prices = frame.sort_values("date", kind="stable").groupby("month", sort=True).tail(1).set_index("month")["adjusted_close"]
    current = decision.to_period("M")
    needed = [current - lag for lag in range(12, 0, -1)]
    absent = [str(month) for month in needed if month not in prices.index]
    if absent:
        raise ValueError(f"incomplete Mom12m calendar history: {absent}")
    selected = prices.loc[needed].astype(float)
    if (~np.isfinite(selected) | selected.le(0)).any():
        raise ValueError("Mom12m month-end window contains an invalid price")
    returns = selected.pct_change().iloc[1:]
    if len(returns) != 11 or not np.isfinite(returns).all():
        raise ValueError("Mom12m return window is incomplete")
    return float(np.prod(1.0 + returns.to_numpy()) - 1.0)


def strict_price_factors(history: pd.DataFrame, ranking_date: str) -> dict[str, float]:
    """Fixed, outcome-independent price factors available before ranking."""
    frame = history[["date", "adjusted_close"]].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    frame["adjusted_close"] = pd.to_numeric(frame["adjusted_close"], errors="coerce")
    decision = pd.Timestamp(ranking_date)
    frame = frame.loc[frame["date"].lt(decision)].sort_values("date", kind="stable")
    if frame["date"].duplicated().any():
        raise ValueError("price-factor history contains duplicate dates")
    frame["month"] = frame["date"].dt.to_period("M")
    month_end = frame.groupby("month", sort=True).tail(1).set_index("month")["adjusted_close"]
    current = decision.to_period("M")
    months12 = [current - lag for lag in range(12, 0, -1)]
    if any(month not in month_end.index for month in months12):
        raise ValueError("incomplete twelve-month calendar history")
    monthly = month_end.loc[months12].astype(float)
    if (~np.isfinite(monthly) | monthly.le(0)).any():
        raise ValueError("price-factor month-end window contains an invalid price")
    mom12m = float(monthly.iloc[-1] / monthly.iloc[0] - 1.0)
    mom6m = float(monthly.iloc[-1] / monthly.iloc[-6] - 1.0)
    reversal1m = float(-(monthly.iloc[-1] / monthly.iloc[-2] - 1.0))
    start = decision - pd.DateOffset(months=12)
    daily = frame.loc[frame["date"].ge(start), "adjusted_close"].astype(float)
    if (~np.isfinite(daily) | daily.le(0)).any():
        raise ValueError("price-factor daily window contains an invalid price")
    if len(daily) < 200:
        raise ValueError("fewer than 200 valid daily prices in twelve-month window")
    log_returns = np.log(daily).diff().dropna()
    low_volatility = float(-log_returns.std(ddof=1) * np.sqrt(252.0))
    drawdown = daily / daily.cummax() - 1.0
    shallow_drawdown = float(drawdown.min())
    return {
        "mom12m": mom12m, "mom6m": mom6m, "reversal1m": reversal1m,
        "low_volatility_12m": low_volatility,
        "shallow_drawdown_12m": shallow_drawdown,
    }


def _load_predictor_history(root: Path, ranking_date: str, ticker: str) -> pd.DataFrame:
    blind_prices = root / ranking_date / "predictor_prices.csv"
    if blind_prices.is_file():
        frame = pd.read_csv(blind_prices, usecols=["ticker", "date", "pit_adjusted_price"])
        frame = frame.loc[frame["ticker"].astype(str).eq(ticker), ["date", "pit_adjusted_price"]]
        return frame.rename(columns={"pit_adjusted_price": "adjusted_close"})
    path = root / f"{ticker}.csv"
    if not path.is_file():
        raise ValueError(f"missing predictor history: {ticker}")
    return pd.read_csv(path)


def build_exploratory_signals(membership: pd.DataFrame, predictor_root: str | Path) -> pd.DataFrame:
    histories = Path(predictor_root)
    date_prices: dict[str, pd.DataFrame] = {}
    for ranking_date in sorted(membership["ranking_date"].astype(str).unique()):
        path = histories / ranking_date / "predictor_prices.csv"
        if path.is_file():
            date_prices[ranking_date] = pd.read_csv(
                path, usecols=["ticker", "date", "pit_adjusted_price"]
            ).rename(columns={"pit_adjusted_price": "adjusted_close"})
    rows: list[dict[str, Any]] = []
    for row in membership.sort_values(["ranking_date", "sector", "ticker"], kind="stable").to_dict("records"):
        history = (
            date_prices[str(row["ranking_date"])].loc[
                date_prices[str(row["ranking_date"])]["ticker"].astype(str).eq(str(row["ticker"])),
                ["date", "adjusted_close"],
            ] if str(row["ranking_date"]) in date_prices else _load_predictor_history(
                histories, str(row["ranking_date"]), str(row["ticker"])
            )
        )
        factors = strict_price_factors(history, str(row["ranking_date"]))
        rows.append({
            "ranking_date": str(row["ranking_date"]), "ticker": str(row["ticker"]),
            "isin": str(row["isin"]), "sector": str(row["sector"]),
            "baseline_sector_rank": float(row["baseline_sector_rank"]),
            "research_v2_sector_rank": float(row["research_v2_sector_rank"]),
            **factors,
        })
    result = pd.DataFrame(rows)
    groups = result.groupby(["ranking_date", "sector"], sort=True)
    result["baseline_signal"] = groups["baseline_sector_rank"].rank(method="average", ascending=False, pct=True)
    result["research_v2_signal"] = groups["research_v2_sector_rank"].rank(method="average", ascending=False, pct=True)
    result["mom12m_signal"] = groups["mom12m"].rank(method="average", ascending=True, pct=True)
    result["mom6m_signal"] = groups["mom6m"].rank(method="average", ascending=True, pct=True)
    result["reversal1m_signal"] = groups["reversal1m"].rank(method="average", ascending=True, pct=True)
    result["low_volatility_signal"] = groups["low_volatility_12m"].rank(method="average", ascending=True, pct=True)
    result["shallow_drawdown_signal"] = groups["shallow_drawdown_12m"].rank(method="average", ascending=True, pct=True)
    result["baseline_mom12m_signal"] = (result["baseline_signal"] + result["mom12m_signal"]) / 2.0
    result["v2_mom12m_signal"] = (result["research_v2_signal"] + result["mom12m_signal"]) / 2.0
    result["three_way_signal"] = (result["baseline_signal"] + result["research_v2_signal"] + result["mom12m_signal"]) / 3.0
    result["baseline_price_multifactor_signal"] = (
        result["baseline_signal"] + result["mom12m_signal"]
        + result["low_volatility_signal"] + result["shallow_drawdown_signal"]
    ) / 4.0
    return result.sort_values(["ranking_date", "sector", "ticker"], kind="stable").reset_index(drop=True)


def expanding_ridge_predictions(signals: pd.DataFrame, future_returns: pd.DataFrame) -> pd.DataFrame:
    """Train only on entire sector/date targets matured before the decision day.

    Endpoint closes on the ranking day are not known at its 15:30 cutoff.
    A cross-sectional target also depends on every peer's outcome, so maturity
    is checked for the whole sector/date, not just the individual security.
    This remains retrospective exploratory analysis, not unseen validation.
    """
    outcomes = future_returns.loc[future_returns["horizon_months"].eq(12), [
        "ranking_date", "ticker", "isin", "future_adjusted_return", "actual_endpoint_date"
    ]]
    panel = signals.merge(outcomes, on=["ranking_date", "ticker", "isin"], validate="one_to_one")
    if len(panel) != len(signals):
        raise ValueError("ridge outcome merge changed the frozen cohort")
    endpoints = pd.to_datetime(panel["actual_endpoint_date"], errors="raise")
    if endpoints.isna().any() or not np.isfinite(panel["future_adjusted_return"].to_numpy(float)).all():
        raise ValueError("ridge requires finite outcomes and explicit endpoint dates")
    if endpoints.le(pd.to_datetime(panel["ranking_date"])).any():
        raise ValueError("outcome endpoint must follow ranking date")
    panel["label_available_after"] = endpoints
    panel["sector_label_available_after"] = panel.groupby(
        ["ranking_date", "sector"], sort=True
    )["label_available_after"].transform("max")
    features = [
        "baseline_signal", "research_v2_signal", "mom12m_signal", "mom6m_signal",
        "reversal1m_signal", "low_volatility_signal", "shallow_drawdown_signal",
    ]
    panel["target"] = panel.groupby(["ranking_date", "sector"], sort=True)["future_adjusted_return"].rank(method="average", pct=True)
    predictions = []
    dates = sorted(panel["ranking_date"].astype(str).unique())
    for date in dates[1:]:
        train = panel.loc[
            panel["ranking_date"].astype(str).lt(date)
            & panel["sector_label_available_after"].lt(pd.Timestamp(date))
        ].copy()
        if train.empty:
            continue
        test = panel.loc[panel["ranking_date"].astype(str).eq(date)].copy()
        x_train, x_test = train[features].to_numpy(float), test[features].to_numpy(float)
        mean, scale = x_train.mean(axis=0), x_train.std(axis=0)
        scale[scale == 0] = 1.0
        x_train, x_test = (x_train - mean) / scale, (x_test - mean) / scale
        design = np.column_stack([np.ones(len(x_train)), x_train])
        penalty = np.eye(design.shape[1]); penalty[0, 0] = 0.0
        coefficients = np.linalg.solve(design.T @ design + penalty, design.T @ train["target"].to_numpy(float))
        test = test[["ranking_date", "ticker", "isin", "sector", "future_adjusted_return"]].copy()
        test["expanding_ridge_signal"] = np.column_stack([np.ones(len(x_test)), x_test]) @ coefficients
        test["training_rows"] = len(train)
        test["latest_training_endpoint"] = train["sector_label_available_after"].max().date().isoformat()
        test["training_dates"] = "|".join(sorted(train["ranking_date"].astype(str).unique()))
        predictions.append(test)
    if not predictions:
        return pd.DataFrame(columns=[
            "ranking_date", "ticker", "isin", "sector",
            "future_adjusted_return", "expanding_ridge_signal",
        ])
    return pd.concat(predictions, ignore_index=True).sort_values(["ranking_date", "sector", "ticker"], kind="stable").reset_index(drop=True)


def evaluate_exploratory_signals(signals: pd.DataFrame, future_returns: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    outcomes = future_returns.loc[future_returns["horizon_months"].eq(12), [
        "ranking_date", "ticker", "isin", "future_adjusted_return"
    ]]
    panel = signals.merge(outcomes, on=["ranking_date", "ticker", "isin"], validate="one_to_one")
    if len(panel) != len(signals):
        raise ValueError("exploratory outcome merge changed the frozen cohort")
    rows: list[dict[str, Any]] = []
    for (date, sector), group in panel.groupby(["ranking_date", "sector"], sort=True):
        if len(group) < 3:
            continue
        row: dict[str, Any] = {"ranking_date": date, "sector": sector, "peer_count": len(group)}
        outcome_rank = group["future_adjusted_return"].rank(method="average")
        for model, column in MODEL_COLUMNS.items():
            signal_rank = group[column].rank(method="average")
            correlation = signal_rank.corr(outcome_rank) if signal_rank.nunique() > 1 and outcome_rank.nunique() > 1 else np.nan
            row[f"{model}_rank_ic"] = float(correlation) if np.isfinite(correlation) else None
        rows.append(row)
    metrics = pd.DataFrame(rows).sort_values(["ranking_date", "sector"], kind="stable").reset_index(drop=True)
    models = {}
    for model in MODEL_COLUMNS:
        values = pd.to_numeric(metrics[f"{model}_rank_ic"], errors="coerce").dropna()
        models[model] = {
            "valid_sector_dates": int(len(values)),
            "mean_rank_ic": float(values.mean()) if len(values) else None,
            "median_rank_ic": float(values.median()) if len(values) else None,
        }
    ridge = expanding_ridge_predictions(signals, future_returns)
    ridge_rows = []
    for (date, sector), group in ridge.groupby(["ranking_date", "sector"], sort=True):
        if len(group) >= 3:
            value = group["expanding_ridge_signal"].rank(method="average").corr(
                group["future_adjusted_return"].rank(method="average")
            )
            ridge_rows.append({"ranking_date": date, "sector": sector, "peer_count": len(group), "expanding_ridge_rank_ic": float(value)})
    ridge_metrics = pd.DataFrame(ridge_rows)
    ridge_values = ridge_metrics["expanding_ridge_rank_ic"] if not ridge_metrics.empty else pd.Series(dtype=float)
    models["expanding_ridge_meta_model"] = {
        "valid_sector_dates": int(len(ridge_values)),
        "mean_rank_ic": float(ridge_values.mean()) if len(ridge_values) else None,
        "median_rank_ic": float(ridge_values.median()) if len(ridge_values) else None,
        "evaluation_dates": sorted(ridge["ranking_date"].astype(str).unique()),
        "training_rule": "fixed alpha=1 ridge; train-only standardization; every sector target endpoint strictly before decision day",
    }
    # Compare ridge with the incumbents only on its exact evaluated cells.
    paired = metrics.merge(ridge_metrics, on=["ranking_date", "sector", "peer_count"], validate="one_to_one") if not ridge_metrics.empty else pd.DataFrame()
    paired_results = {}
    for model in ("baseline_v1", "research_v2", "opensourceap_mom12m"):
        if paired.empty:
            paired_results[model] = {"valid_sector_dates": 0, "mean_ridge_minus_comparator": None}
            continue
        values = paired[["expanding_ridge_rank_ic", f"{model}_rank_ic"]].dropna()
        delta = values["expanding_ridge_rank_ic"] - values[f"{model}_rank_ic"]
        paired_results[model] = {
            "valid_sector_dates": len(delta),
            "mean_ridge_minus_comparator": float(delta.mean()) if len(delta) else None,
        }
    return metrics, {
        "schema_version": "exploratory_fixed_model_benchmark_v2",
        "status": "SUPPLEMENTARY_NOT_MODEL_SELECTION",
        "company_date_count": int(len(signals)), "sector_date_count": int(len(metrics)),
        "primary_horizon_months": 12, "models": models,
        "ridge_same_cell_comparison": paired_results,
        "ridge_sector_results": ridge_rows,
        "selection_performed": False, "product_default_changed": False,
        "warning": "Four annual dates cannot support reliable winner selection; all results are descriptive and outcome-revealed.",
    }


def run_exploratory_benchmark(
    *, readiness_root: str | Path, protocol_path: str | Path,
    blind_root: str | Path,
    evaluation_root: str | Path, output: str | Path,
) -> str:
    readiness, evaluation, destination, blind = Path(readiness_root), Path(evaluation_root), Path(output), Path(blind_root)
    if destination.exists():
        raise ValueError(f"output directory already exists: {destination}")
    report = json.loads((readiness / "readiness_report.json").read_text(encoding="utf-8"))
    if report.get("verdict") != "READY_RUN_FINAL_EVALUATION" or report.get("outcomes_calculated_or_inspected") is not False:
        raise ValueError("frozen outcome-blind readiness gate is invalid")
    protocol = json.loads(Path(protocol_path).read_text(encoding="utf-8"))
    protocol_hash = sha256(json.dumps(protocol, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    if protocol_hash != report.get("protocol_fingerprint"):
        raise ValueError("frozen protocol fingerprint mismatch")
    inventory = json.loads((readiness / "artifact_inventory.json").read_text(encoding="utf-8"))
    membership_path = readiness / "cohort_membership.csv"
    recorded = {item["path"]: item["sha256"] for item in inventory}
    if _hash(membership_path) != recorded.get("cohort_membership.csv"):
        raise ValueError("frozen cohort membership changed")
    if _hash(blind / "manifest.json") != report["input_fingerprints"]["blind_manifest"]:
        raise ValueError("frozen blind manifest changed")
    blind_manifest = json.loads((blind / "manifest.json").read_text(encoding="utf-8"))
    for item in blind_manifest["date_manifests"]:
        date_root = blind / item["ranking_date"]
        date_manifest_path = date_root / "manifest.json"
        if _hash(date_manifest_path) != item["manifest_sha256"]:
            raise ValueError(f"blind date manifest changed: {item['ranking_date']}")
        date_manifest = json.loads(date_manifest_path.read_text(encoding="utf-8"))
        expected = {entry["path"]: entry["sha256"] for entry in date_manifest["files"]}
        if _hash(date_root / "predictor_prices.csv") != expected.get("predictor_prices.csv"):
            raise ValueError(f"blind predictor prices changed: {item['ranking_date']}")
    membership = pd.read_csv(membership_path).sort_values(["ranking_date", "sector", "ticker"], kind="stable").reset_index(drop=True)
    future_hash = _artifact_hash(evaluation, "future_returns.csv")
    signals = build_exploratory_signals(membership, blind)
    metrics, summary = evaluate_exploratory_signals(signals, pd.read_csv(evaluation / "future_returns.csv"))
    summary.update({
        "protocol_fingerprint": report["protocol_fingerprint"],
        "cohort_membership_sha256": _hash(readiness / "cohort_membership.csv"),
        "frozen_future_returns_sha256": future_hash,
        "methodology": {
            "mom12m": "OpenSourceAP t-1 through t-11 product; complete calendar months required; no missing-return zero-fill",
            "ensembles": "Fixed arithmetic mean of within-sector percentile signals; no fitted weights",
        },
    })
    destination.mkdir(parents=True)
    signals.to_csv(destination / "signals.csv", index=False, lineterminator="\n", float_format="%.17g")
    metrics.to_csv(destination / "sector_metrics.csv", index=False, lineterminator="\n", float_format="%.17g")
    expanding_ridge_predictions(signals, pd.read_csv(evaluation / "future_returns.csv")).to_csv(
        destination / "ridge_predictions.csv", index=False, lineterminator="\n", float_format="%.17g"
    )
    (destination / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    artifacts = []
    for name in ("signals.csv", "sector_metrics.csv", "ridge_predictions.csv", "summary.json"):
        path = destination / name
        artifacts.append({"path": name, "sha256": _hash(path), "size": path.stat().st_size})
    manifest = {"schema_version": "exploratory_fixed_model_benchmark_v2", "artifacts": artifacts}
    fingerprint = sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    manifest["fingerprint"] = fingerprint
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return fingerprint
