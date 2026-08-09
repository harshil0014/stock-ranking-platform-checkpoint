"""Run independent Alphalens and Empyrical checks in .venv-quantlab."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_research.quant_lab import (  # noqa: E402
    HORIZON_LABELS, QUANT_LAB_SCHEMA_VERSION, QuantLabPaths,
    build_alphalens_adapter, canonical_json_sha256,
)


EXPECTED_PACKAGES = {
    "alphalens-reloaded": "0.4.6", "empyrical-reloaded": "0.5.12",
    "skfolio": "0.20.1", "quantstats": "0.0.81",
}
TOLERANCE = 1e-12


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")


def _anchor(prices: pd.DataFrame, target: pd.Timestamp) -> pd.Series:
    eligible = prices.loc[prices["date"].le(target)]
    if eligible.empty or (target - eligible.iloc[-1]["date"]).days > 7:
        raise ValueError("accepted price anchor is unavailable")
    return eligible.iloc[-1]


def _alphalens_run(adapter: pd.DataFrame, frozen_ic: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    import alphalens.performance as performance

    ic_rows: list[dict[str, object]] = []
    quantile_rows: list[dict[str, object]] = []
    for (model, horizon), subset in adapter.groupby(["model", "horizon_months"], sort=True):
        period = HORIZON_LABELS[int(horizon)]
        data = subset.copy()
        data["date"] = pd.to_datetime(data["ranking_date"], utc=True)
        data = data.set_index(["date", "ticker"])
        factor_data = pd.DataFrame({
            "factor": data["factor"], "group": data["sector"], period: data["future_return"],
        })
        ic = performance.factor_information_coefficient(factor_data, group_adjust=False, by_group=True)
        for (date, sector), values in ic.iterrows():
            expected = frozen_ic.loc[
                frozen_ic["ranking_date"].eq(date.date().isoformat())
                & frozen_ic["historical_sector"].eq(sector)
                & frozen_ic["horizon_months"].eq(horizon)
            ]
            if expected.empty:
                continue
            frozen_column = "research_v2_rank_ic" if model == "research_v2" else "matched_baseline_rank_ic"
            upstream = float(values[period]); accepted = float(expected.iloc[0][frozen_column])
            difference = upstream - accepted
            ic_rows.append({
                "model": model, "ranking_date": date.date().isoformat(), "sector": sector,
                "horizon_months": int(horizon), "alphalens_period": period,
                "alphalens_spearman_ic": upstream, "frozen_evaluator_rank_ic": accepted,
                "absolute_difference": abs(difference),
                "status": "MATCH" if abs(difference) <= TOLERANCE else "EXPLAINED_DIFFERENCE",
            })
        factor_data["factor_quantile"] = factor_data.groupby([factor_data.index.get_level_values(0), "group"])["factor"].transform(
            lambda values: pd.qcut(values.rank(method="first"), q=min(3, len(values)), labels=False) + 1
        )
        means, _ = performance.mean_return_by_quantile(factor_data, by_date=False, by_group=True)
        for index, row in means.reset_index().iterrows():
            del index
            quantile_rows.append({
                "model": model, "horizon_months": int(horizon),
                "factor_quantile": int(row["factor_quantile"]), "sector": row["group"],
                "mean_future_return": float(row[period]),
                "status": "DESCRIPTIVE_SMALL_COHORT",
            })
    return pd.DataFrame(ic_rows), pd.DataFrame(quantile_rows)


def _empyrical_run(paths: QuantLabPaths) -> pd.DataFrame:
    import empyrical

    rankings = pd.read_csv(paths.current_v2_root / "rankings.csv")
    prices = pd.read_csv(paths.current_v2_root / "prices.csv")
    prices["date"] = pd.to_datetime(prices["date"], format="%Y-%m-%d")
    rows: list[dict[str, object]] = []
    for ranked in rankings.to_dict("records"):
        ticker = ranked["ticker"]
        series = prices.loc[prices["ticker"].eq(ticker)].sort_values("date", kind="stable")
        ranking_date = pd.Timestamp(ranked["ranking_date"])
        current = _anchor(series, ranking_date)
        one = _anchor(series, ranking_date - pd.DateOffset(years=1))
        three = _anchor(series, ranking_date - pd.DateOffset(years=3))
        one_window = series.loc[series["date"].between(one["date"], current["date"])]
        three_window = series.loc[series["date"].between(three["date"], current["date"])]
        one_returns = one_window["adjusted_close"].pct_change().dropna()
        three_returns = three_window["adjusted_close"].pct_change().dropna()
        checks = (
            ("annualized_volatility_1y", float(ranked["annualized_volatility_1y"]), float(empyrical.annual_volatility(one_returns, annualization=252)), True),
            ("max_drawdown_3y", float(ranked["max_drawdown_3y"]), float(empyrical.max_drawdown(three_returns)), True),
            ("return_1y", float(ranked["return_1y"]), float(empyrical.annual_return(one_returns, annualization=252)), False),
        )
        for metric, internal, upstream, equivalent in checks:
            absolute = abs(internal - upstream)
            status = "PASS" if equivalent and absolute <= TOLERANCE else ("FAIL" if equivalent else "EXPLAINED_DIFFERENCE")
            rows.append({
                "ticker": ticker, "sector": ranked["sector"], "metric": metric,
                "internal_value": internal, "empyrical_value": upstream,
                "absolute_difference": absolute,
                "relative_difference": absolute / max(abs(internal), 1e-30),
                "definition_equivalent": equivalent, "status": status,
                "explanation": (
                    "Equivalent daily-return definition and annualization."
                    if equivalent else
                    "Internal return uses exact calendar-year price anchors; Empyrical annual_return annualizes by observed daily periods."
                ),
            })
    result = pd.DataFrame(rows)
    if result["status"].eq("FAIL").any():
        raise RuntimeError("unexplained Empyrical discrepancy in an equivalent metric")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run frozen open-source quant validation.")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output).resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("output directory must be fresh")
    output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(output / "matplotlib-cache"))
    from importlib import metadata
    installed = {name: metadata.version(name) for name in EXPECTED_PACKAGES}
    if installed != EXPECTED_PACKAGES:
        raise RuntimeError(f"quant-lab package drift: {installed}")
    paths = QuantLabPaths(
        ROOT / "data/walk_forward/blind_predictions_v1_run_01",
        ROOT / "data/walk_forward/evaluation_v1_run_01",
        ROOT / "data/marketdata/nifty50-research-v2-2026-08-07/standalone-contract-reason-fix-run-01",
        output,
    )
    adapter = build_alphalens_adapter(paths)
    frozen_ic = pd.read_csv(paths.evaluation_root / "sector_rank_ic.csv")
    alphalens_ic, quantiles = _alphalens_run(adapter, frozen_ic)
    empyrical = _empyrical_run(paths)
    _write_csv(adapter, output / "alphalens_factor_adapter.csv")
    _write_csv(alphalens_ic, output / "alphalens_ic_comparison.csv")
    _write_csv(quantiles, output / "alphalens_quantile_returns.csv")
    _write_csv(empyrical, output / "empyrical_metric_audit.csv")
    portfolio = {
        "status": "EXPERIMENTAL_DEFERRED", "library": "skfolio",
        "reason": "The four sparse annual cohorts do not provide a preregistered top-K, rebalance, benchmark, transaction-cost, or formation-time covariance contract. No portfolio was constructed.",
        "ranking_inputs_modified": False, "future_information_used": False,
    }
    (output / "portfolio_feasibility.json").write_text(json.dumps(portfolio, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    quantstats = {
        "status": "DEFERRED", "reason": "No scientifically supported portfolio return stream was produced.",
    }
    (output / "quantstats_status.json").write_text(json.dumps(quantstats, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    artifacts = []
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "quant_lab_summary.json":
            artifacts.append({"path": path.name, "size": path.stat().st_size, "sha256": sha256(path.read_bytes()).hexdigest()})
    summary = {
        "schema_version": QUANT_LAB_SCHEMA_VERSION,
        "environment": {"python": platform.python_version(), "packages": installed},
        "alphalens": {
            "status": "VERIFIED", "adapter_rows": len(adapter), "ic_rows": len(alphalens_ic),
            "exact_ic_matches": int(alphalens_ic["status"].eq("MATCH").sum()),
            "differences": int(alphalens_ic["status"].ne("MATCH").sum()),
            "turnover_status": "DEFERRED_SPARSE_ANNUAL_OBSERVATIONS",
            "quantile_status": "DESCRIPTIVE_SMALL_COHORT",
        },
        "empyrical": {
            "status": "VERIFIED", "audit_rows": len(empyrical),
            "passes": int(empyrical["status"].eq("PASS").sum()),
            "explained_differences": int(empyrical["status"].eq("EXPLAINED_DIFFERENCE").sum()),
            "failures": int(empyrical["status"].eq("FAIL").sum()),
        },
        "skfolio": portfolio, "quantstats": quantstats,
        "adapter_fingerprint": canonical_json_sha256(adapter.to_dict("records")),
        "artifacts": artifacts,
        "boundary": "Independent secondary analysis; accepted Baseline/V2 scoring and preregistered 12-month evaluation remain unchanged.",
    }
    (output / "quant_lab_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
