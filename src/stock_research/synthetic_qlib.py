"""Deterministic point-in-time synthetic data for Qlib reproduction."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.contracts import (
    ChronologicalSplit,
    DateRange,
    validate_feature_panel,
    validate_labels,
)


DEFAULT_SEED = 20260730
LABEL_NAME = "forward_1d_return"
INSTRUMENT_COUNT = 30
FEATURE_COLUMNS = (
    "irrelevant_noise",
    "momentum_20d",
    "momentum_5d",
    "price_to_trend_20d",
    "quality_proxy",
    "redundant_momentum_20d",
    "sector_momentum_20d",
    "size_proxy",
    "value_proxy",
    "volatility_20d",
)
PRICE_DERIVED_FEATURES = (
    "momentum_20d",
    "momentum_5d",
    "price_to_trend_20d",
    "sector_momentum_20d",
    "volatility_20d",
)
LATENT_COEFFICIENTS = {
    "irrelevant_noise": 0.0,
    "momentum_20d": 0.0016,
    "momentum_5d": 0.0012,
    "price_to_trend_20d": 0.0008,
    "quality_proxy": 0.0010,
    "redundant_momentum_20d": 0.0007,
    "sector_momentum_20d": 0.0010,
    "size_proxy": -0.0003,
    "value_proxy": 0.0008,
    "volatility_20d": -0.0007,
}
THREAD_CONTROLS = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}


@dataclass(frozen=True, slots=True)
class SyntheticDatasetBundle:
    features: pd.DataFrame
    labels: pd.DataFrame
    qlib_panel: pd.DataFrame
    universe: pd.DataFrame
    prices: pd.DataFrame
    fundamentals: pd.DataFrame
    mapping: pd.DataFrame
    split: ChronologicalSplit
    metadata: dict[str, Any]
    latent_coefficients: dict[str, float]


def _zscore(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    scale = values.std(ddof=0)
    if not np.isfinite(scale) or scale == 0:
        raise ValueError("Synthetic cross-section unexpectedly has zero variance")
    return (values - values.mean()) / scale


def _identity_frames() -> tuple[pd.DataFrame, np.ndarray]:
    tickers = np.array(
        [f"SYN{number:03d}" for number in range(1, INSTRUMENT_COUNT + 1)]
    )
    sectors = np.repeat(
        ["Synthetic Financials", "Synthetic Industrials", "Synthetic Technology"],
        INSTRUMENT_COUNT // 3,
    )
    universe = pd.DataFrame({
        "ticker": tickers,
        "company": [
            f"Fictional Company {number:03d}"
            for number in range(1, INSTRUMENT_COUNT + 1)
        ],
        "sector": sectors,
    })
    return universe, sectors


def _price_feature_arrays(
    price_history: np.ndarray,
    sectors: np.ndarray,
) -> dict[str, np.ndarray]:
    if price_history.shape[0] < 21:
        raise ValueError("At least 21 price observations are required")
    current = price_history[-1]
    momentum_5 = current / price_history[-6] - 1
    momentum_20 = current / price_history[-21] - 1
    simple_returns = price_history[-21:][1:] / price_history[-21:][:-1] - 1
    volatility_20 = simple_returns.std(axis=0, ddof=1)
    price_to_trend = current / price_history[-20:].mean(axis=0) - 1
    sector_momentum = np.empty(INSTRUMENT_COUNT, dtype=float)
    for sector in sorted(set(sectors)):
        selected = sectors == sector
        sector_momentum[selected] = momentum_20[selected].mean()
    return {
        "momentum_20d": _zscore(momentum_20),
        "momentum_5d": _zscore(momentum_5),
        "price_to_trend_20d": _zscore(price_to_trend),
        "sector_momentum_20d": _zscore(sector_momentum),
        "volatility_20d": _zscore(volatility_20),
    }


def reconstruct_price_features(
    prices: pd.DataFrame,
    universe: pd.DataFrame,
    as_of_date: str,
) -> pd.DataFrame:
    """Reconstruct price-derived features using only history through ``as_of_date``."""

    target = pd.Timestamp(as_of_date)
    history = prices.copy(deep=True)
    history["date"] = pd.to_datetime(history["date"], format="%Y-%m-%d")
    history = history.loc[history["date"] <= target]
    matrix = history.pivot(
        index="date", columns="ticker", values="adjusted_close"
    ).sort_index().reindex(columns=universe["ticker"])
    arrays = _price_feature_arrays(
        matrix.to_numpy(dtype=float), universe["sector"].to_numpy()
    )
    return pd.DataFrame({
        "ticker": universe["ticker"].to_numpy(),
        **arrays,
    }).sort_values("ticker", kind="mergesort").reset_index(drop=True)


def _split() -> ChronologicalSplit:
    return ChronologicalSplit(
        train=DateRange("2025-09-23", "2026-03-09"),
        validation=DateRange("2026-03-17", "2026-04-27"),
        test=DateRange("2026-05-05", "2026-06-29"),
        purge_days=7,
        embargo_days=7,
    )


def generate_synthetic_qlib_data(seed: int = DEFAULT_SEED) -> SyntheticDatasetBundle:
    """Generate the complete deterministic offline reproduction dataset."""

    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    rng = np.random.default_rng(seed)
    universe, sectors = _identity_frames()
    tickers = universe["ticker"].to_numpy()
    sector_codes = pd.Categorical(sectors).codes

    quality_trait = rng.normal(0, 1, INSTRUMENT_COUNT)
    value_trait = rng.normal(0, 1, INSTRUMENT_COUNT)
    size_trait = rng.normal(0, 1, INSTRUMENT_COUNT)
    sector_drift = np.array([0.00005, 0.00010, 0.00015])[sector_codes]

    price_dates = pd.bdate_range("2020-01-02", "2026-06-30")
    observation_with_end = pd.bdate_range(end="2026-06-30", periods=201)
    observation_dates = observation_with_end[:-1]
    observation_set = set(observation_dates)
    first_observation_index = price_dates.get_loc(observation_dates[0])
    prices_matrix = np.empty((len(price_dates), INSTRUMENT_COUNT), dtype=float)
    prices_matrix[0] = 35 + 45 * rng.random(INSTRUMENT_COUNT)

    for index in range(1, first_observation_index + 1):
        market = rng.normal(0.00015, 0.003)
        returns = market + sector_drift + rng.normal(
            0, 0.009, INSTRUMENT_COUNT
        )
        returns = np.clip(returns, -0.06, 0.06)
        prices_matrix[index] = prices_matrix[index - 1] * (1 + returns)

    feature_rows: list[dict[str, Any]] = []
    label_rows: list[dict[str, Any]] = []
    observation_number = 0
    beta = np.array([LATENT_COEFFICIENTS[name] for name in FEATURE_COLUMNS])
    for price_index in range(first_observation_index, len(price_dates) - 1):
        date = price_dates[price_index]
        if date not in observation_set:
            continue
        price_features = _price_feature_arrays(
            prices_matrix[:price_index + 1], sectors
        )
        time_phase = observation_number / 17
        quality = _zscore(
            quality_trait
            + 0.08 * np.sin(time_phase + sector_codes)
            + rng.normal(0, 0.03, INSTRUMENT_COUNT)
        )
        value = _zscore(
            value_trait
            + 0.06 * np.cos(time_phase / 2 + sector_codes)
            + rng.normal(0, 0.03, INSTRUMENT_COUNT)
        )
        size = _zscore(size_trait + rng.normal(0, 0.015, INSTRUMENT_COUNT))
        irrelevant = _zscore(rng.normal(0, 1, INSTRUMENT_COUNT))
        redundant_noise = _zscore(rng.normal(0, 1, INSTRUMENT_COUNT))
        redundant = _zscore(
            0.85 * price_features["momentum_20d"]
            + 0.15 * redundant_noise
        )
        arrays = {
            "irrelevant_noise": irrelevant,
            **price_features,
            "quality_proxy": quality,
            "redundant_momentum_20d": redundant,
            "size_proxy": size,
            "value_proxy": value,
        }
        matrix = np.column_stack([arrays[name] for name in FEATURE_COLUMNS])
        next_returns = matrix @ beta + rng.normal(
            0, 0.006, INSTRUMENT_COUNT
        )
        next_returns = np.clip(next_returns, -0.06, 0.06)
        prices_matrix[price_index + 1] = (
            prices_matrix[price_index] * (1 + next_returns)
        )
        date_text = date.strftime("%Y-%m-%d")
        end_text = price_dates[price_index + 1].strftime("%Y-%m-%d")
        for stock_index, ticker in enumerate(tickers):
            feature_rows.append({
                "as_of_date": date_text,
                "ticker": ticker,
                "sector": sectors[stock_index],
                "max_feature_available_date": date_text,
                **{
                    name: float(arrays[name][stock_index])
                    for name in FEATURE_COLUMNS
                },
            })
            label_rows.append({
                "as_of_date": date_text,
                "ticker": ticker,
                "label_end_date": end_text,
                "forward_return": float(next_returns[stock_index]),
                "label_name": LABEL_NAME,
            })
        observation_number += 1

    if observation_number != 200:
        raise RuntimeError(f"Expected 200 observation dates; got {observation_number}")
    features = validate_feature_panel(pd.DataFrame(feature_rows))
    labels = validate_labels(pd.DataFrame(label_rows))

    price_frame = (
        pd.DataFrame(
            prices_matrix,
            index=price_dates,
            columns=tickers,
        )
        .rename_axis("date")
        .reset_index()
        .melt(id_vars="date", var_name="ticker", value_name="adjusted_close")
    )
    price_frame["date"] = price_frame["date"].dt.strftime("%Y-%m-%d")
    price_frame = price_frame.sort_values(
        ["ticker", "date"], kind="mergesort"
    ).reset_index(drop=True)

    fundamentals_rows: list[dict[str, Any]] = []
    period_ends = pd.date_range("2024-12-31", "2026-03-31", freq="QE")
    for period_number, period_end in enumerate(period_ends):
        available_date = period_end + pd.Timedelta(days=45)
        for stock_index, ticker in enumerate(tickers):
            debt = 0.65 - 0.08 * value_trait[stock_index] + 0.015 * period_number
            if ticker == "SYN030":
                debt = -0.10
            fundamentals_rows.append({
                "ticker": ticker,
                "period_end": period_end.strftime("%Y-%m-%d"),
                "available_date": available_date.strftime("%Y-%m-%d"),
                "roce": float(0.12 + 0.025 * quality_trait[stock_index]
                              + 0.002 * period_number),
                "debt_to_equity": float(debt),
                "profit_growth_yoy": float(
                    0.08 + 0.02 * quality_trait[stock_index]
                    + 0.01 * np.sin(period_number + sector_codes[stock_index])
                ),
            })
    fundamentals = pd.DataFrame(fundamentals_rows).sort_values(
        ["ticker", "period_end", "available_date"], kind="mergesort"
    ).reset_index(drop=True)

    feature_indexed = features.set_index(["as_of_date", "ticker"])
    label_indexed = labels.set_index(["as_of_date", "ticker"])
    panel = pd.concat(
        {
            "feature": feature_indexed[list(FEATURE_COLUMNS)],
            "label": label_indexed[["forward_return"]],
        },
        axis=1,
    )
    panel.index = panel.index.set_names(["datetime", "instrument"])
    panel.columns = pd.MultiIndex.from_tuples([
        (group, LABEL_NAME if group == "label" else name)
        for group, name in panel.columns
    ])
    panel = panel.sort_index()

    split = _split()
    mapping = pd.DataFrame({
        "qlib_instrument": tickers,
        "ticker": tickers,
    })
    metadata = {
        "schema_version": "1.0",
        "seed": seed,
        "generator": "stock_research.synthetic_qlib",
        "fictional_data": True,
        "missing_value_policy": "reject",
        "price_start": price_dates[0].strftime("%Y-%m-%d"),
        "price_end": price_dates[-1].strftime("%Y-%m-%d"),
        "observation_start": observation_dates[0].strftime("%Y-%m-%d"),
        "observation_end": observation_dates[-1].strftime("%Y-%m-%d"),
        "observation_date_count": len(observation_dates),
        "instrument_count": INSTRUMENT_COUNT,
        "feature_list": list(FEATURE_COLUMNS),
        "label_name": LABEL_NAME,
        "label_definition": (
            "Simple adjusted-close return from as_of_date to the next business "
            "day; generated from time-t features plus independent noise."
        ),
        "label_horizon_business_days": 1,
        "noise_standard_deviation": 0.006,
        "return_clip": [-0.06, 0.06],
        "thread_controls": THREAD_CONTROLS,
    }
    return SyntheticDatasetBundle(
        features=features,
        labels=labels,
        qlib_panel=panel,
        universe=universe,
        prices=price_frame,
        fundamentals=fundamentals,
        mapping=mapping,
        split=split,
        metadata=metadata,
        latent_coefficients=dict(LATENT_COEFFICIENTS),
    )


def write_canonical_csv(
    data: pd.DataFrame,
    path: str | Path,
    *,
    index: bool = False,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(
        target,
        index=index,
        encoding="utf-8",
        lineterminator="\n",
        float_format="%.17g",
    )
    return target


def write_canonical_json(value: Any, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False,
        separators=(",", ": "),
    )
    target.write_text(payload + "\n", encoding="utf-8", newline="\n")
    return target
