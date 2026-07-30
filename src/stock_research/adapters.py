"""Canonical signal adapters for Research V2 and Qlib predictions."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from stock_research.contracts import validate_signals
from stock_research.errors import Diagnostic, ResearchValidationError


RESEARCH_V2_MODEL_ID = "research_v2_baseline"


def research_v2_to_signals(
    rankings: pd.DataFrame,
    *,
    run_id: str | None = None,
) -> pd.DataFrame:
    required = {
        "ticker", "ranking_date", "research_v2_score", "sector",
        "sector_rank", "eligible", "method_version",
    }
    missing = sorted(required.difference(rankings.columns))
    if missing:
        raise ResearchValidationError(
            Diagnostic("research_v2_columns", f"missing columns: {missing}")
        )
    if rankings.empty:
        raise ResearchValidationError(
            Diagnostic("empty_dataset", "Research V2 rankings must not be empty")
        )
    if not rankings["eligible"].map(lambda value: value is True or value == True).all():
        raise ResearchValidationError(
            Diagnostic("ineligible_research_v2", "all converted rows must be eligible")
        )
    if rankings.duplicated(["ranking_date", "ticker"]).any():
        raise ResearchValidationError(
            Diagnostic("duplicate_research_v2", "duplicate ranking_date/ticker")
        )
    identifier = run_id or str(uuid4())
    signals = pd.DataFrame({
        "as_of_date": rankings["ranking_date"],
        "ticker": rankings["ticker"],
        "score": rankings["research_v2_score"],
        "model_id": RESEARCH_V2_MODEL_ID,
        "run_id": identifier,
        "sector": rankings["sector"],
        "rank": rankings["sector_rank"],
        "method_version": rankings["method_version"],
    })
    return validate_signals(signals, {RESEARCH_V2_MODEL_ID})


def _read_qlib_prediction(
    source: str | Path | pd.Series | pd.DataFrame,
    *,
    allow_unsafe_pickle: bool,
) -> pd.Series | pd.DataFrame:
    if isinstance(source, (pd.Series, pd.DataFrame)):
        return source.copy(deep=True)
    path = Path(source)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".pkl", ".pickle"}:
        if not allow_unsafe_pickle:
            raise ResearchValidationError(Diagnostic(
                "unsafe_pickle_blocked",
                "pickle input requires explicit --allow-unsafe-pickle",
            ))
        return pd.read_pickle(path)
    raise ResearchValidationError(Diagnostic(
        "unsupported_prediction_format", "Qlib predictions must be CSV or trusted pickle"
    ))


def _qlib_long(data: pd.Series | pd.DataFrame) -> pd.DataFrame:
    if isinstance(data, pd.Series):
        frame = data.rename("score").reset_index()
    elif isinstance(data.index, pd.MultiIndex):
        frame = data.reset_index()
    else:
        frame = data.copy()
    aliases = {
        "datetime": "as_of_date",
        "date": "as_of_date",
        "instrument": "qlib_instrument",
        "pred": "score",
        "prediction": "score",
    }
    frame = frame.rename(columns={
        key: value for key, value in aliases.items()
        if key in frame.columns and value not in frame.columns
    })
    if "score" not in frame and len(frame.columns) == 3:
        remaining = [
            name for name in frame.columns
            if name not in {"as_of_date", "qlib_instrument"}
        ]
        if len(remaining) == 1:
            frame = frame.rename(columns={remaining[0]: "score"})
    required = {"as_of_date", "qlib_instrument", "score"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ResearchValidationError(
            Diagnostic("qlib_prediction_columns", f"missing columns: {missing}")
        )
    return frame[["as_of_date", "qlib_instrument", "score"]]


def convert_qlib_predictions(
    predictions: str | Path | pd.Series | pd.DataFrame,
    mapping: str | Path | pd.DataFrame,
    *,
    model_id: str,
    run_id: str,
    upstream_model_id: str | None = None,
    upstream_run_id: str | None = None,
    allow_unsafe_pickle: bool = False,
    drop_unmapped: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convert Qlib-style output without importing Qlib."""

    raw = _read_qlib_prediction(
        predictions, allow_unsafe_pickle=allow_unsafe_pickle
    )
    frame = _qlib_long(raw)
    map_frame = (
        pd.read_csv(mapping) if isinstance(mapping, (str, Path))
        else mapping.copy(deep=True)
    )
    required = {"qlib_instrument", "ticker"}
    missing = sorted(required.difference(map_frame.columns))
    if missing:
        raise ResearchValidationError(
            Diagnostic("mapping_columns", f"missing columns: {missing}")
        )
    if map_frame[list(required)].isna().any().any() or (
        map_frame[list(required)].astype(str).apply(lambda col: col.str.strip().eq("")).any().any()
    ):
        raise ResearchValidationError(
            Diagnostic("mapping_identifier", "mapping identifiers must be nonblank")
        )
    if map_frame["qlib_instrument"].duplicated().any():
        raise ResearchValidationError(
            Diagnostic("duplicate_mapping", "qlib_instrument mapping must be unique")
        )
    merged = frame.merge(
        map_frame[["qlib_instrument", "ticker"]],
        on="qlib_instrument", how="left", validate="many_to_one",
    )
    unmapped = merged["ticker"].isna()
    dropped = merged.loc[unmapped, [
        "as_of_date", "qlib_instrument", "score"
    ]].sort_values(
        ["as_of_date", "qlib_instrument"], kind="mergesort"
    ).reset_index(drop=True)
    if unmapped.any() and not drop_unmapped:
        values = sorted(merged.loc[unmapped, "qlib_instrument"].astype(str).unique())
        raise ResearchValidationError(
            Diagnostic("unmapped_instruments", f"unmapped instruments: {values}")
        )
    merged = merged.loc[~unmapped].copy()
    score = pd.to_numeric(merged["score"], errors="coerce")
    if score.isna().any() or not np.isfinite(score.to_numpy(dtype=float)).all():
        raise ResearchValidationError(
            Diagnostic("nonfinite_numeric", "Qlib scores must be finite numeric")
        )
    method = (
        f"qlib:{upstream_model_id or model_id}:"
        f"{upstream_run_id or run_id}"
    )
    signals = pd.DataFrame({
        "as_of_date": pd.to_datetime(
            merged["as_of_date"], errors="coerce"
        ).dt.strftime("%Y-%m-%d"),
        "ticker": merged["ticker"],
        "score": score,
        "model_id": model_id,
        "run_id": run_id,
        "method_version": method,
    })
    return validate_signals(signals, {model_id}), dropped
