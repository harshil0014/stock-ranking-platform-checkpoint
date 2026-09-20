"""Validation for fixed chronological ML experiments on a frozen panel.

The model runtime lives in an isolated runner.  This module deliberately has
no Qlib, LightGBM, Torch, or provider imports so product processes can inspect
the resulting evidence without importing research dependencies.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCHEMA_VERSION = "chronological_ml_benchmark_v1"
FEATURES = (
    "baseline_rank_signal", "mom12m", "mom6m", "reversal1m",
    "low_volatility_12m", "shallow_drawdown_12m",
    "derived_net_margin", "derived_roe_closing_equity",
    "derived_debt_to_equity", "derived_cfo_to_assets",
)
FORBIDDEN_FEATURES = {
    "future_adjusted_return", "actual_endpoint_date", "target", "maturity",
    "research_v2_score", "vendor_v2_signal",
}
ARTIFACTS = {"predictions.csv", "sector_metrics.csv", "summary.json", "execution.json"}


def file_hash(path: str | Path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def validate_panel(panel: pd.DataFrame) -> None:
    required = {
        "ranking_date", "ticker", "isin", "sector", "future_adjusted_return",
        "actual_endpoint_date", "baseline_sector_rank", *FEATURES,
    }
    missing = required.difference(panel.columns)
    if missing:
        raise ValueError(f"frozen panel lacks columns: {sorted(missing)}")
    if panel.duplicated(["ranking_date", "isin"]).any():
        raise ValueError("frozen panel has duplicate company-date identities")
    if panel["isin"].isna().any():
        raise ValueError("frozen panel contains missing ISIN identity")
    outcomes = pd.to_numeric(panel["future_adjusted_return"], errors="coerce")
    if not np.isfinite(outcomes).all():
        raise ValueError("frozen outcomes must be finite")
    if FORBIDDEN_FEATURES.intersection(FEATURES):
        raise ValueError("outcome or post-outcome field entered the feature set")


def eligible_training_rows(panel: pd.DataFrame, decision_date: str) -> pd.Series:
    """Return rows whose complete sector outcome matured before decision time."""
    dates = pd.to_datetime(panel["ranking_date"], errors="raise")
    endpoints = pd.to_datetime(panel["actual_endpoint_date"], errors="raise")
    sector_maturity = endpoints.groupby([dates, panel["sector"]]).transform("max")
    return dates.lt(pd.Timestamp(decision_date)) & sector_maturity.lt(pd.Timestamp(decision_date))


def score_sector_metrics(panel: pd.DataFrame, predictions: pd.DataFrame) -> pd.DataFrame:
    keys = ["ranking_date", "ticker", "isin"]
    if predictions.duplicated(keys + ["model"]).any():
        raise ValueError("duplicate model predictions")
    joined = predictions.merge(
        panel[[*keys, "sector", "future_adjusted_return", "baseline_rank_signal"]],
        on=keys, validate="many_to_one",
    )
    rows: list[dict[str, Any]] = []
    for (model, date, sector), group in joined.groupby(["model", "ranking_date", "sector"], sort=True):
        if len(group) < 3:
            continue
        outcome_rank = group["future_adjusted_return"].rank(method="average")
        for name, column in ((model, "prediction"), (f"baseline_on_{model}", "baseline_rank_signal")):
            signal_rank = group[column].rank(method="average")
            if signal_rank.nunique() > 1 and outcome_rank.nunique() > 1:
                rows.append({
                    "ranking_date": date, "sector": sector, "model": name,
                    "peers": len(group), "rank_ic": float(signal_rank.corr(outcome_rank)),
                })
    return pd.DataFrame(rows)


def validate_result(directory: str | Path) -> dict[str, Any]:
    root = Path(directory)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unexpected chronological ML manifest schema")
    payload = {key: value for key, value in manifest.items() if key != "fingerprint"}
    expected = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if manifest.get("fingerprint") != expected:
        raise ValueError("chronological ML manifest fingerprint mismatch")
    entries = manifest.get("artifacts", [])
    if {item.get("path") for item in entries} != ARTIFACTS:
        raise ValueError("chronological ML artifact inventory is incomplete")
    for item in entries:
        path = root / item["path"]
        if not path.is_file() or path.stat().st_size != item["size"] or file_hash(path) != item["sha256"]:
            raise ValueError(f"chronological ML artifact changed: {item['path']}")
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    if summary.get("product_default_changed") is not False:
        raise ValueError("supplementary experiment changed the product default")
    if summary.get("outcome_status") != "PREVIOUSLY_REVEALED_NOT_UNSEEN":
        raise ValueError("supplementary outcome status is missing")
    return summary
