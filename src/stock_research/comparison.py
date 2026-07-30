"""Fair comparison of model evaluations under one shared protocol."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from stock_research.errors import Diagnostic, ResearchValidationError


COMPARISON_COLUMNS = (
    "model_id", "run_id", "validation_status", "failure_reason",
    "evaluation_protocol_fingerprint", "model_configuration_fingerprint",
    "dataset_fingerprints", "provenance", "signal_ticker_count", "label_ticker_count",
    "evaluation_date_count", "mean_coverage", "mean_ic", "mean_rank_ic",
    "icir", "rank_icir", "unannualized_icir", "unannualized_rank_icir",
    "annualized_icir", "annualized_rank_icir",
    "signal_tickers", "label_tickers", "evaluated_dates", "coverage_by_date",
)


def _summary(value: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        return json.loads(Path(value).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchValidationError(
            Diagnostic("comparison_summary", str(exc))
        ) from exc


def compare_evaluations(
    evaluations: Iterable[str | Path | Mapping[str, Any]],
    *,
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    summaries = [_summary(value) for value in evaluations]
    if len(summaries) < 2:
        raise ResearchValidationError(
            Diagnostic("comparison_count", "at least two evaluations are required")
        )
    contaminated = [
        item.get("model_id", "<unknown>")
        for item in summaries
        if item.get("test_contamination") is True
        or item.get("contamination_status") in {"detected", "failed"}
    ]
    if contaminated:
        raise ResearchValidationError(Diagnostic(
            "test_contamination",
            f"comparison rejected contaminated models: {sorted(contaminated)}",
        ))
    protocols = {
        item.get("evaluation_protocol_fingerprint") for item in summaries
    }
    if None in protocols or len(protocols) != 1:
        raise ResearchValidationError(Diagnostic(
            "evaluation_protocol_mismatch",
            "all models must share one evaluation_protocol_fingerprint",
        ))
    rows: list[dict[str, Any]] = []
    for item in summaries:
        rows.append({
            column: (
                json.dumps(item.get(column), sort_keys=True, separators=(",", ":"))
                if column in {
                    "dataset_fingerprints", "provenance", "signal_tickers",
                    "label_tickers", "evaluated_dates", "coverage_by_date",
                }
                else item.get(column)
            )
            for column in COMPARISON_COLUMNS
        })
    comparison = pd.DataFrame(rows, columns=COMPARISON_COLUMNS).sort_values(
        ["model_id", "run_id"], kind="mergesort"
    ).reset_index(drop=True)
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        comparison.to_csv(
            target, index=False, na_rep="", encoding="utf-8",
            lineterminator="\n", float_format="%.17g",
        )
    return comparison
