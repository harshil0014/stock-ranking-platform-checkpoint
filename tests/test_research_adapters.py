from __future__ import annotations

import pandas as pd
import pytest

from stock_research.adapters import (
    RESEARCH_V2_MODEL_ID,
    convert_qlib_predictions,
    research_v2_to_signals,
)
from stock_research.errors import ResearchValidationError


def test_research_v2_adapter_preserves_identity_and_is_not_ml():
    rankings = pd.DataFrame({
        "ticker": ["AAA"], "ranking_date": ["2026-01-02"],
        "research_v2_score": [75.0], "sector": ["Tech"],
        "sector_rank": [1], "eligible": [True],
        "method_version": ["research_v2_point_in_time_weighted"],
    })
    result = research_v2_to_signals(rankings, run_id="run-1")
    assert result.loc[0, "model_id"] == RESEARCH_V2_MODEL_ID
    assert result.loc[0, "score"] == 75.0
    with pytest.raises(ResearchValidationError, match="ineligible"):
        research_v2_to_signals(rankings.assign(eligible=False))


def test_qlib_multiindex_conversion_and_mapping():
    index = pd.MultiIndex.from_tuples(
        [(pd.Timestamp("2026-01-02"), "QLIB_A"),
         (pd.Timestamp("2026-01-02"), "QLIB_B")],
        names=["datetime", "instrument"],
    )
    prediction = pd.Series([0.5, -0.2], index=index, name="score")
    mapping = pd.DataFrame({
        "qlib_instrument": ["QLIB_A", "QLIB_B"],
        "ticker": ["AAA", "BBB"],
    })
    result, dropped = convert_qlib_predictions(
        prediction, mapping, model_id="qlib_linear", run_id="run-1"
    )
    assert list(result["ticker"]) == ["AAA", "BBB"]
    assert dropped.empty


def test_qlib_unmapped_default_rejection_and_drop_report():
    predictions = pd.DataFrame({
        "date": ["2026-01-02", "2026-01-02"],
        "instrument": ["A", "UNKNOWN"],
        "score": [1, 2],
    })
    mapping = pd.DataFrame({"qlib_instrument": ["A"], "ticker": ["AAA"]})
    with pytest.raises(ResearchValidationError, match="unmapped_instruments"):
        convert_qlib_predictions(
            predictions, mapping, model_id="m", run_id="r"
        )
    result, dropped = convert_qlib_predictions(
        predictions, mapping, model_id="m", run_id="r", drop_unmapped=True
    )
    assert len(result) == 1
    assert dropped.loc[0, "qlib_instrument"] == "UNKNOWN"


def test_pickle_requires_explicit_trust(tmp_path):
    path = tmp_path / "predictions.pkl"
    pd.DataFrame().to_pickle(path)
    with pytest.raises(ResearchValidationError, match="unsafe_pickle_blocked"):
        convert_qlib_predictions(
            path, pd.DataFrame(), model_id="m", run_id="r"
        )
