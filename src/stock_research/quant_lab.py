"""Contracts and adapters for independent open-source quant validation."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pandas as pd


HORIZON_LABELS = {3: "90D", 6: "180D", 12: "365D"}
QUANT_LAB_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class QuantLabPaths:
    blind_root: Path
    evaluation_root: Path
    current_v2_root: Path
    output_root: Path


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(payload.encode("utf-8")).hexdigest()


def build_alphalens_adapter(paths: QuantLabPaths) -> pd.DataFrame:
    """Map frozen matched rankings and outcomes without recomputing signals."""

    future = pd.read_csv(paths.evaluation_root / "future_returns.csv")
    required_future = {
        "ranking_date", "ticker", "horizon_months", "actual_endpoint_date",
        "future_adjusted_return",
    }
    if not required_future.issubset(future.columns):
        raise ValueError("frozen future-return artifact is missing required columns")
    future["ranking_date"] = pd.to_datetime(future["ranking_date"], format="%Y-%m-%d")
    future["actual_endpoint_date"] = pd.to_datetime(future["actual_endpoint_date"], format="%Y-%m-%d")
    if (future["actual_endpoint_date"] <= future["ranking_date"]).any():
        raise ValueError("future-return endpoint must follow its ranking date")
    rows: list[dict[str, Any]] = []
    for date_directory in sorted(path for path in paths.blind_root.iterdir() if path.is_dir()):
        ranking_date = pd.Timestamp(date_directory.name)
        v2 = pd.read_csv(date_directory / "research_v2.csv")
        matched = pd.read_csv(date_directory / "matched_baseline.csv")
        if v2["ticker"].duplicated().any() or matched["ticker"].duplicated().any():
            raise ValueError("frozen ranking ticker keys must be unique")
        joined = v2[["ticker", "historical_sector", "research_v2_score", "sector_rank"]].merge(
            matched[["ticker", "matched_baseline_sector_rank", "historical_sector"]],
            on=["ticker", "historical_sector"], how="inner", validate="one_to_one",
        )
        outcomes = future.loc[future["ranking_date"].eq(ranking_date)]
        for item in joined.to_dict("records"):
            ticker_outcomes = outcomes.loc[outcomes["ticker"].eq(item["ticker"])]
            for outcome in ticker_outcomes.to_dict("records"):
                horizon = int(outcome["horizon_months"])
                if horizon not in HORIZON_LABELS:
                    continue
                for model, factor in (
                    ("research_v2", float(item["research_v2_score"])),
                    ("matched_baseline", -float(item["matched_baseline_sector_rank"])),
                ):
                    rows.append({
                        "ranking_date": ranking_date.date().isoformat(),
                        "ticker": item["ticker"], "sector": item["historical_sector"],
                        "model": model, "horizon_months": horizon,
                        "alphalens_period": HORIZON_LABELS[horizon], "factor": factor,
                        "future_return": float(outcome["future_adjusted_return"]),
                        "actual_endpoint_date": outcome["actual_endpoint_date"].date().isoformat(),
                    })
    result = pd.DataFrame(rows).sort_values(
        ["model", "horizon_months", "ranking_date", "sector", "ticker"], kind="stable"
    ).reset_index(drop=True)
    if result.empty or result.duplicated(["ranking_date", "ticker", "model", "horizon_months"]).any():
        raise ValueError("Alphalens adapter produced empty or duplicate keys")
    if result[["factor", "future_return"]].isna().any(axis=None):
        raise ValueError("Alphalens adapter does not permit missing factor or outcome values")
    return result


def validate_quant_lab_artifacts(root: str | Path) -> dict[str, Any]:
    directory = Path(root)
    summary_path = directory / "quant_lab_summary.json"
    if not summary_path.is_file():
        raise ValueError("quant-lab summary is unavailable")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("schema_version") != QUANT_LAB_SCHEMA_VERSION:
        raise ValueError("quant-lab schema version mismatch")
    for artifact in summary.get("artifacts", []):
        path = directory / artifact["path"]
        if not path.is_file() or path.stat().st_size != artifact["size"]:
            raise ValueError(f"quant-lab artifact mismatch: {artifact['path']}")
        if sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
            raise ValueError(f"quant-lab artifact hash mismatch: {artifact['path']}")
    return summary

