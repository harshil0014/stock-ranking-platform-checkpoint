"""Deterministic cross-sectional signal evaluation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from math import sqrt
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from stock_research.contracts import validate_labels, validate_signals
from stock_research.errors import Diagnostic, ResearchValidationError
from stock_research.fingerprints import (
    evaluation_protocol_fingerprint, fingerprint_dataframe, fingerprint_file
)


@dataclass(frozen=True, slots=True)
class EvaluationProtocol:
    label_name: str
    label_definition: str
    label_dataset_fingerprint: str
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str
    test_start: str
    test_end: str
    purge_days: int
    embargo_days: int
    evaluation_frequency: str
    metric_definitions: Mapping[str, Any]
    annualization_factor: float | None
    minimum_cross_sectional_observations: int
    test_universe_policy: str

    def __post_init__(self) -> None:
        if not self.label_name.strip() or not self.label_definition.strip():
            raise ValueError("label name and definition must not be blank")
        if self.minimum_cross_sectional_observations < 2:
            raise ValueError("minimum_cross_sectional_observations must be at least 2")
        if self.annualization_factor is not None and (
            isinstance(self.annualization_factor, bool)
            or not np.isfinite(float(self.annualization_factor))
            or self.annualization_factor <= 0
        ):
            raise ValueError("annualization_factor must be positive when supplied")
        for name in ("purge_days", "embargo_days"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        for name in (
            "train_start", "train_end", "validation_start", "validation_end",
            "test_start", "test_end",
        ):
            try:
                pd.Timestamp(getattr(self, name))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be a valid date") from exc

    def resolved_annualization(self) -> tuple[float | None, str]:
        if self.annualization_factor is not None:
            return float(self.annualization_factor), "applied_explicit_factor"
        if self.evaluation_frequency.lower() == "daily":
            return 252.0, "applied_daily_default_252"
        return None, (
            "not_applied_frequency_requires_explicit_factor:"
            f"{self.evaluation_frequency}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "label_name": self.label_name,
            "label_definition": self.label_definition,
            "label_dataset_fingerprint": self.label_dataset_fingerprint,
            "train": {"start": self.train_start, "end": self.train_end},
            "validation": {
                "start": self.validation_start, "end": self.validation_end
            },
            "test": {"start": self.test_start, "end": self.test_end},
            "purge_days": self.purge_days,
            "embargo_days": self.embargo_days,
            "evaluation_frequency": self.evaluation_frequency,
            "metric_definitions": dict(self.metric_definitions),
            "annualization_factor": self.annualization_factor,
            "minimum_cross_sectional_observations":
                self.minimum_cross_sectional_observations,
            "test_universe_policy": self.test_universe_policy,
        }

    @property
    def fingerprint(self) -> str:
        return evaluation_protocol_fingerprint(self.as_dict())


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    summary: dict[str, Any]
    daily_ic: pd.DataFrame
    daily_rank_ic: pd.DataFrame
    coverage: pd.DataFrame


def _correlation(x: pd.Series, y: pd.Series) -> float:
    return float(x.corr(y, method="pearson"))


def _metric_summary(values: pd.Series) -> dict[str, float | int | None]:
    valid = values.dropna().astype(float)
    count = len(valid)
    mean = float(valid.mean()) if count else None
    std = float(valid.std(ddof=1)) if count >= 2 else None
    icir = (
        mean / std if mean is not None and std is not None and std != 0
        else None
    )
    positive = float((valid > 0).mean() * 100) if count else None
    return {
        "valid_date_count": count,
        "mean": mean,
        "sample_std": std,
        "icir": icir,
        "positive_percentage": positive,
    }


def evaluate_signals(
    signals: pd.DataFrame,
    labels: pd.DataFrame,
    protocol: EvaluationProtocol,
    *,
    model_configuration_fingerprint: str,
    dataset_fingerprints: Mapping[str, str] | None = None,
    provenance: Mapping[str, Any] | None = None,
    output_dir: str | Path | None = None,
) -> EvaluationResult:
    canonical_signals = validate_signals(signals)
    canonical_labels = validate_labels(labels)
    selected_labels = canonical_labels.loc[
        canonical_labels["label_name"].eq(protocol.label_name)
    ].copy()
    if selected_labels.empty:
        raise ResearchValidationError(Diagnostic(
            "missing_required_label", f"no labels named {protocol.label_name}"
        ))
    actual_label_fp = fingerprint_dataframe(selected_labels)
    if actual_label_fp != protocol.label_dataset_fingerprint:
        raise ResearchValidationError(Diagnostic(
            "label_fingerprint_mismatch",
            "validated label dataset does not match evaluation protocol",
        ))
    start, end = protocol.test_start, protocol.test_end
    test_signals = canonical_signals.loc[
        canonical_signals["as_of_date"].between(start, end)
    ].copy()
    test_labels = selected_labels.loc[
        selected_labels["as_of_date"].between(start, end)
    ].copy()
    identities = test_signals[["model_id", "run_id"]].drop_duplicates()
    if len(identities) != 1:
        raise ResearchValidationError(Diagnostic(
            "signal_identity", "evaluation requires exactly one model_id/run_id"
        ))
    identity = identities.iloc[0]
    joined = test_labels.merge(
        test_signals[["as_of_date", "ticker", "score"]],
        on=["as_of_date", "ticker"], how="outer", indicator=True,
    )
    dates = sorted(set(test_labels["as_of_date"]).union(test_signals["as_of_date"]))
    ic_rows, rank_rows, coverage_rows = [], [], []
    minimum = protocol.minimum_cross_sectional_observations
    for observation_date in dates:
        daily = joined.loc[joined["as_of_date"].eq(observation_date)]
        matched = daily.loc[daily["_merge"].eq("both")].dropna(
            subset=["score", "forward_return"]
        )
        label_count = int(
            daily.loc[daily["_merge"].isin(["both", "left_only"]), "ticker"].nunique()
        )
        usable = len(matched)
        status = "valid"
        pearson: float | None = None
        spearman: float | None = None
        if usable < minimum:
            status = "insufficient_cross_section"
        elif matched["score"].nunique() < 2:
            status = "constant_signal"
        elif matched["forward_return"].nunique() < 2:
            status = "constant_label"
        else:
            pearson = _correlation(matched["score"], matched["forward_return"])
            spearman = _correlation(
                matched["score"].rank(method="average"),
                matched["forward_return"].rank(method="average"),
            )
        ic_rows.append({
            "as_of_date": observation_date, "ic": pearson,
            "status": status, "usable_observations": usable,
        })
        rank_rows.append({
            "as_of_date": observation_date, "rank_ic": spearman,
            "status": status, "usable_observations": usable,
        })
        coverage_rows.append({
            "as_of_date": observation_date,
            "label_observations": label_count,
            "signal_observations": int(
                daily.loc[daily["_merge"].isin(["both", "right_only"]), "ticker"].nunique()
            ),
            "usable_matched_observations": usable,
            "coverage": usable / label_count if label_count else None,
        })
    daily_ic = pd.DataFrame(ic_rows)
    daily_rank = pd.DataFrame(rank_rows)
    coverage = pd.DataFrame(coverage_rows)
    ic = _metric_summary(daily_ic["ic"])
    rank_ic = _metric_summary(daily_rank["rank_ic"])
    factor, annualization_status = protocol.resolved_annualization()
    annualized_icir = (
        ic["icir"] * sqrt(factor)
        if factor is not None and ic["icir"] is not None else None
    )
    annualized_rank_icir = (
        rank_ic["icir"] * sqrt(factor)
        if factor is not None and rank_ic["icir"] is not None else None
    )
    summary = {
        "schema_version": "1.0",
        "model_id": str(identity["model_id"]),
        "run_id": str(identity["run_id"]),
        "validation_status": "completed",
        "failure_reason": None,
        "model_configuration_fingerprint": model_configuration_fingerprint,
        "dataset_fingerprints": dict(dataset_fingerprints or {}),
        "provenance": dict(provenance or {}),
        "evaluation_protocol_fingerprint": protocol.fingerprint,
        "evaluation_frequency": protocol.evaluation_frequency,
        "annualization_factor": factor,
        "annualization_status": annualization_status,
        "mean_ic": ic["mean"],
        "ic_sample_std": ic["sample_std"],
        "icir": ic["icir"],
        "unannualized_icir": ic["icir"],
        "annualized_icir": annualized_icir,
        "ic_positive_percentage": ic["positive_percentage"],
        "valid_ic_dates": ic["valid_date_count"],
        "mean_rank_ic": rank_ic["mean"],
        "rank_ic_sample_std": rank_ic["sample_std"],
        "rank_icir": rank_ic["icir"],
        "unannualized_rank_icir": rank_ic["icir"],
        "annualized_rank_icir": annualized_rank_icir,
        "rank_ic_positive_percentage": rank_ic["positive_percentage"],
        "valid_rank_ic_dates": rank_ic["valid_date_count"],
        "mean_coverage": (
            float(coverage["coverage"].dropna().mean())
            if coverage["coverage"].notna().any() else None
        ),
        "signal_ticker_count": int(test_signals["ticker"].nunique()),
        "label_ticker_count": int(test_labels["ticker"].nunique()),
        "evaluation_date_count": len(dates),
        "signal_tickers": sorted(test_signals["ticker"].unique().tolist()),
        "label_tickers": sorted(test_labels["ticker"].unique().tolist()),
        "evaluated_dates": dates,
        "coverage_by_date": coverage.to_dict("records"),
    }
    result = EvaluationResult(summary, daily_ic, daily_rank, coverage)
    if output_dir is not None:
        export_evaluation(result, output_dir)
    return result


def export_evaluation(result: EvaluationResult, output_dir: str | Path) -> dict[str, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": directory / "evaluation_summary.json",
        "daily_ic": directory / "daily_ic.csv",
        "daily_rank_ic": directory / "daily_rank_ic.csv",
        "coverage": directory / "coverage_report.csv",
    }
    paths["summary"].write_text(
        json.dumps(result.summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    csv_options = {
        "index": False,
        "na_rep": "",
        "encoding": "utf-8",
        "lineterminator": "\n",
        "float_format": "%.17g",
    }
    result.daily_ic.to_csv(paths["daily_ic"], **csv_options)
    result.daily_rank_ic.to_csv(paths["daily_rank_ic"], **csv_options)
    result.coverage.to_csv(paths["coverage"], **csv_options)
    return paths
