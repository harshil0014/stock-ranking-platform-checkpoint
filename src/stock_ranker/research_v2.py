"""Offline point-in-time Research V2 scoring engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import sqrt
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

from stock_ranker.v2_config import ResearchV2Config
from stock_ranker.v2_contracts import (
    HIGHER_IS_BETTER_METRICS,
    LOWER_IS_BETTER_METRICS,
    V2_CONTRIBUTION_COLUMNS,
    V2_ELIGIBILITY_COLUMNS,
    V2_METRIC_COLUMNS,
    V2_OUTPUT_COLUMNS,
)
from stock_ranker.v2_validation import validate_v2_structures


@dataclass(frozen=True, slots=True)
class ResearchV2Inputs:
    universe: pd.DataFrame
    prices: pd.DataFrame
    fundamentals: pd.DataFrame


@dataclass(frozen=True, slots=True)
class ResearchV2Result:
    rankings: pd.DataFrame
    eligibility: pd.DataFrame


class ResearchScoringModel(Protocol):
    """Compatibility boundary for explainable scoring implementations."""

    @property
    def method_version(self) -> str: ...

    def score(self, data: pd.DataFrame) -> pd.DataFrame: ...


def _read_csv(path: str | Path, label: str) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.is_file():
        raise ValueError(f"{label} CSV does not exist or is not a file: {csv_path}")
    try:
        return pd.read_csv(csv_path)
    except (OSError, pd.errors.ParserError, UnicodeError) as exc:
        raise ValueError(f"Could not read {label} CSV '{csv_path}': {exc}") from exc


def load_research_v2_inputs(
    universe_path: str | Path,
    prices_path: str | Path,
    fundamentals_path: str | Path,
) -> ResearchV2Inputs:
    """Load V2 CSV inputs without performing ranking-date-dependent validation."""

    return ResearchV2Inputs(
        universe=_read_csv(universe_path, "universe"),
        prices=_read_csv(prices_path, "prices"),
        fundamentals=_read_csv(fundamentals_path, "fundamentals"),
    )


def _anchor(
    prices: pd.DataFrame,
    target: pd.Timestamp,
    tolerance_days: int,
) -> tuple[pd.Series | None, str | None]:
    candidates = prices.loc[prices["date"] <= target]
    if candidates.empty:
        return None, "missing"
    selected = candidates.iloc[-1]
    if (target - selected["date"]).days > tolerance_days:
        return None, "stale"
    return selected, None


def _numeric_series(data: pd.Series) -> tuple[pd.Series, bool]:
    numeric = pd.to_numeric(data, errors="coerce")
    valid = numeric.notna() & np.isfinite(numeric.to_numpy(dtype=float))
    return numeric.astype(float), bool(valid.all())


def _price_metrics(
    ticker_prices: pd.DataFrame,
    ranking_date: pd.Timestamp,
    config: ResearchV2Config,
) -> tuple[dict[str, float | int], list[tuple[str, str]]]:
    issues: list[tuple[str, str]] = []
    if ticker_prices.empty:
        return {}, [("NO_PRICE_HISTORY", "No price history is available on or before the ranking date.")]

    prices = ticker_prices.sort_values("date", kind="mergesort").copy()
    numeric, valid = _numeric_series(prices["adjusted_close"])
    if not valid or (numeric <= 0).any():
        return {}, [(
            "INVALID_PRICE_VALUE",
            "Point-in-time price history contains a nonnumeric, nonfinite, zero, or negative adjusted close.",
        )]
    prices["adjusted_close"] = numeric

    targets = {
        "current": ranking_date,
        "1Y": ranking_date - pd.DateOffset(years=1),
        "3Y": ranking_date - pd.DateOffset(years=3),
        "5Y": ranking_date - pd.DateOffset(years=5),
    }
    anchors: dict[str, pd.Series] = {}
    for name, target in targets.items():
        selected, problem = _anchor(
            prices, target, config.anchor_tolerance_days
        )
        if problem:
            code_name = "CURRENT" if name == "current" else name
            code = (
                f"STALE_{code_name}_PRICE_ANCHOR"
                if problem == "stale"
                else f"MISSING_{code_name}_PRICE_ANCHOR"
            )
            issues.append(
                (
                    code,
                    f"No adjusted close exists within {config.anchor_tolerance_days} "
                    f"days on or before the {name} target date.",
                )
            )
        else:
            anchors[name] = selected
    if issues:
        return {}, issues

    current = float(anchors["current"]["adjusted_close"])
    one_year = float(anchors["1Y"]["adjusted_close"])
    three_year = float(anchors["3Y"]["adjusted_close"])
    five_year = float(anchors["5Y"]["adjusted_close"])

    volatility_window = prices.loc[
        (prices["date"] >= anchors["1Y"]["date"])
        & (prices["date"] <= anchors["current"]["date"])
    ]
    daily_returns = volatility_window["adjusted_close"].pct_change().dropna()
    if len(daily_returns) < 2:
        issues.append(
            (
                "INSUFFICIENT_VOLATILITY_OBSERVATIONS",
                "At least two trailing daily returns are required for volatility.",
            )
        )
        return {}, issues

    drawdown_window = prices.loc[
        (prices["date"] >= anchors["3Y"]["date"])
        & (prices["date"] <= anchors["current"]["date"])
    ]
    drawdowns = (
        drawdown_window["adjusted_close"]
        / drawdown_window["adjusted_close"].cummax()
        - 1
    )

    history_through_current = prices.loc[
        prices["date"] <= anchors["current"]["date"]
    ]
    recorded_high = history_through_current["adjusted_close"].max()
    recorded_high_date = history_through_current.loc[
        history_through_current["adjusted_close"].eq(recorded_high), "date"
    ].max()

    return {
        "return_1y": current / one_year - 1,
        "cagr_3y": (current / three_year) ** (1 / 3) - 1,
        "cagr_5y": (current / five_year) ** (1 / 5) - 1,
        "days_since_recorded_high": int(
            (ranking_date - recorded_high_date).days
        ),
        "annualized_volatility_1y": float(
            daily_returns.std(ddof=1) * sqrt(config.annualization_periods)
        ),
        "max_drawdown_3y": float(drawdowns.min()),
    }, []


def _fundamental_metrics(
    ticker_fundamentals: pd.DataFrame,
) -> tuple[dict[str, float], list[tuple[str, str]]]:
    if ticker_fundamentals.empty:
        return {}, [(
            "NO_AVAILABLE_FUNDAMENTALS",
            "No fundamental record was publicly available by the ranking date.",
        )]

    latest_period = ticker_fundamentals["period_end"].max()
    period_rows = ticker_fundamentals.loc[
        ticker_fundamentals["period_end"].eq(latest_period)
    ]
    selected = period_rows.sort_values(
        "available_date", kind="mergesort"
    ).iloc[-1]

    metrics: dict[str, float] = {}
    issues: list[tuple[str, str]] = []
    labels = {
        "roce": "ROCE",
        "debt_to_equity": "debt-to-equity",
        "profit_growth_yoy": "profit growth",
    }
    for column, label in labels.items():
        numeric = pd.to_numeric(pd.Series([selected[column]]), errors="coerce")
        value = float(numeric.iloc[0]) if numeric.notna().iloc[0] else float("nan")
        if not np.isfinite(value):
            issues.append(
                (
                    f"INVALID_{column.upper()}",
                    f"The selected {label} value is missing, nonnumeric, or nonfinite.",
                )
            )
        elif column == "debt_to_equity" and value < 0:
            issues.append(
                (
                    "INVALID_DEBT_TO_EQUITY",
                    "Debt-to-equity cannot be negative for lower-is-better scoring.",
                )
            )
        else:
            metrics[column] = value
    return metrics, issues


def _rank_range_scores(
    values: pd.Series,
    *,
    higher_is_better: bool,
) -> pd.Series:
    """Convert directional average ranks to observed-rank-range scores."""

    if len(values) == 1 or values.nunique(dropna=False) == 1:
        return pd.Series(50.0, index=values.index)
    average_ranks = values.rank(
        method="average", ascending=not higher_is_better
    )
    best_rank = average_ranks.min()
    worst_rank = average_ranks.max()
    return 100 * (worst_rank - average_ranks) / (worst_rank - best_rank)


def _score_eligible(
    metrics: pd.DataFrame,
    config: ResearchV2Config,
) -> pd.DataFrame:
    if metrics.empty:
        return pd.DataFrame(columns=list(V2_OUTPUT_COLUMNS))

    scored = metrics.copy()
    direction = {
        **{metric: True for metric in HIGHER_IS_BETTER_METRICS},
        **{metric: False for metric in LOWER_IS_BETTER_METRICS},
    }
    for metric in V2_METRIC_COLUMNS:
        scored[f"{metric}_score"] = scored.groupby(
            "sector", sort=False
        )[metric].transform(
            lambda values, metric_name=metric: _rank_range_scores(
                values, higher_is_better=direction[metric_name]
            )
        )

    for metric, weight in config.weights.as_dict().items():
        scored[f"{metric}_contribution"] = (
            scored[f"{metric}_score"] * float(weight) / 100
        )
    scored["research_v2_score"] = scored[
        list(V2_CONTRIBUTION_COLUMNS)
    ].sum(axis=1)
    scored["sector_rank"] = scored.groupby("sector")[
        "research_v2_score"
    ].rank(method="min", ascending=False).astype("int64")
    scored["eligible"] = True
    scored["method_version"] = config.method_version
    return (
        scored.loc[:, list(V2_OUTPUT_COLUMNS)]
        .sort_values(
            ["sector", "research_v2_score", "ticker"],
            ascending=[True, False, True],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )


def calculate_research_v2(
    inputs: ResearchV2Inputs,
    config: ResearchV2Config,
) -> ResearchV2Result:
    """Calculate point-in-time eligibility, metrics, scores, and sector ranks."""

    universe, prices, fundamentals = validate_v2_structures(
        inputs.universe, inputs.prices, inputs.fundamentals
    )
    ranking_timestamp = pd.Timestamp(config.ranking_date)
    universe_tickers = set(universe["ticker"])

    point_in_time_prices = prices.loc[
        (prices["date"] <= ranking_timestamp)
        & prices["ticker"].isin(universe_tickers)
    ].copy()
    point_in_time_fundamentals = fundamentals.loc[
        (fundamentals["period_end"] <= ranking_timestamp)
        & (fundamentals["available_date"] <= ranking_timestamp)
        & fundamentals["ticker"].isin(universe_tickers)
    ].copy()

    metric_rows: list[dict[str, object]] = []
    eligibility_rows: list[dict[str, object]] = []
    ranking_date_text = config.ranking_date.isoformat()

    for identity in universe.sort_values("ticker").to_dict("records"):
        ticker = str(identity["ticker"])
        price_metrics, price_issues = _price_metrics(
            point_in_time_prices.loc[
                point_in_time_prices["ticker"].eq(ticker)
            ],
            ranking_timestamp,
            config,
        )
        fundamental_metrics, fundamental_issues = _fundamental_metrics(
            point_in_time_fundamentals.loc[
                point_in_time_fundamentals["ticker"].eq(ticker)
            ]
        )
        issues = [*price_issues, *fundamental_issues]
        eligible = not issues
        eligibility_rows.append(
            {
                **identity,
                "ranking_date": ranking_date_text,
                "eligible": eligible,
                "reason_code": (
                    "ELIGIBLE"
                    if eligible
                    else ";".join(code for code, _ in issues)
                ),
                "reason": (
                    "All Research V2 eligibility requirements are satisfied."
                    if eligible
                    else " ".join(reason for _, reason in issues)
                ),
            }
        )
        if eligible:
            metric_rows.append(
                {
                    **identity,
                    "ranking_date": ranking_date_text,
                    **price_metrics,
                    **fundamental_metrics,
                }
            )

    eligibility = (
        pd.DataFrame(eligibility_rows)
        .loc[:, list(V2_ELIGIBILITY_COLUMNS)]
        .sort_values(["sector", "ticker"], kind="mergesort")
        .reset_index(drop=True)
    )
    metrics = pd.DataFrame(metric_rows)
    rankings = _score_eligible(metrics, config)
    return ResearchV2Result(rankings=rankings, eligibility=eligibility)


def get_top_research_v2_by_sector(
    rankings: pd.DataFrame,
    top_n: int = 5,
) -> pd.DataFrame:
    """Select exactly top N per sector using ticker at cutoff ties."""

    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0:
        raise ValueError("top_n must be a positive integer")
    missing = set(V2_OUTPUT_COLUMNS).difference(rankings.columns)
    if missing:
        raise ValueError(
            "Research V2 rankings missing required columns: "
            + ", ".join(sorted(missing))
        )
    ordered = rankings.sort_values(
        ["sector", "research_v2_score", "ticker"],
        ascending=[True, False, True],
        kind="mergesort",
    )
    return (
        ordered.groupby("sector", sort=False, group_keys=False)
        .head(top_n)
        .reset_index(drop=True)
    )
