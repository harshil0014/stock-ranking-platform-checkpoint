from __future__ import annotations

from dataclasses import replace
import json

import pandas as pd
import pytest

from stock_research.comparison import compare_evaluations
from stock_research.contracts import validate_labels
from stock_research.errors import ResearchValidationError
from stock_research.evaluation import EvaluationProtocol, evaluate_signals
from stock_research.fingerprints import fingerprint_dataframe


def label_frame() -> pd.DataFrame:
    rows = []
    values = {
        "2026-01-02": [0.4, 0.2, -0.1, -0.3],
        "2026-01-09": [0.1, 0.4, -0.2, 0.0],
        "2026-01-16": [-0.1, 0.2, 0.3, -0.2],
    }
    for date, returns in values.items():
        end = (
            pd.Timestamp(date) + pd.Timedelta(days=7)
        ).strftime("%Y-%m-%d")
        for ticker, value in zip(["A", "B", "C", "D"], returns):
            rows.append({
                "as_of_date": date, "ticker": ticker,
                "label_end_date": end, "forward_return": value,
                "label_name": "forward_5d_return",
            })
    return pd.DataFrame(rows)


def signal_frame(inverse: bool = False) -> pd.DataFrame:
    labels = label_frame()
    score = labels["forward_return"] * (-1 if inverse else 1)
    return pd.DataFrame({
        "as_of_date": labels["as_of_date"],
        "ticker": labels["ticker"],
        "score": score,
        "model_id": "inverse" if inverse else "strong",
        "run_id": "run-inverse" if inverse else "run-strong",
    })


def protocol(frequency="synthetic", factor=None) -> EvaluationProtocol:
    label_fp = fingerprint_dataframe(validate_labels(label_frame()))
    return EvaluationProtocol(
        label_name="forward_5d_return",
        label_definition="fixture forward return",
        label_dataset_fingerprint=label_fp,
        train_start="2020-01-01",
        train_end="2022-12-31",
        validation_start="2023-01-15",
        validation_end="2024-12-31",
        test_start="2026-01-02",
        test_end="2026-01-16",
        purge_days=7,
        embargo_days=5,
        evaluation_frequency=frequency,
        metric_definitions={"ic": "Pearson", "rank_ic": "average-rank Pearson"},
        annualization_factor=factor,
        minimum_cross_sectional_observations=2,
        test_universe_policy="label universe",
    )


def test_pearson_spearman_and_outputs(tmp_path):
    result = evaluate_signals(
        signal_frame(), label_frame(), protocol(),
        model_configuration_fingerprint="model-a",
        dataset_fingerprints={"features": "feature-a"},
        output_dir=tmp_path,
    )
    assert result.daily_ic["ic"].tolist() == pytest.approx([1, 1, 1])
    assert result.daily_rank_ic["rank_ic"].tolist() == pytest.approx([1, 1, 1])
    assert result.summary["icir"] is None
    assert result.summary["annualized_icir"] is None
    assert result.summary["annualization_factor"] is None
    assert "synthetic" in result.summary["annualization_status"]
    assert result.summary["mean_coverage"] == 1
    assert {
        "evaluation_summary.json", "daily_ic.csv",
        "daily_rank_ic.csv", "coverage_report.csv",
    } == {item.name for item in tmp_path.iterdir()}
    assert json.loads(
        (tmp_path / "evaluation_summary.json").read_text()
    )["annualized_icir"] is None


def test_inverse_signal_and_average_rank_ties():
    signals = signal_frame(inverse=True)
    signals.loc[signals["as_of_date"].eq("2026-01-02"), "score"] = [-1, -1, 0, 1]
    result = evaluate_signals(
        signals, label_frame(), protocol(),
        model_configuration_fingerprint="different-model",
    )
    assert result.daily_ic.loc[1:, "ic"].tolist() == pytest.approx([-1, -1])
    assert result.daily_rank_ic.loc[0, "rank_ic"] < 0


@pytest.mark.parametrize(
    ("frequency", "factor", "expected_factor", "status"),
    [
        ("daily", None, 252.0, "applied_daily_default_252"),
        ("weekly", 52.0, 52.0, "applied_explicit_factor"),
        ("monthly", None, None, "not_applied"),
        ("unknown", None, None, "not_applied"),
    ],
)
def test_frequency_controls_annualization(
    frequency, factor, expected_factor, status
):
    signals = signal_frame()
    # Make valid IC vary across dates so ICIR exists.
    signals.loc[
        (signals["as_of_date"].eq("2026-01-09"))
        & (signals["ticker"].eq("D")), "score"
    ] = 0.5
    result = evaluate_signals(
        signals, label_frame(), protocol(frequency, factor),
        model_configuration_fingerprint="model",
    )
    assert result.summary["annualization_factor"] == expected_factor
    assert status in result.summary["annualization_status"]
    if expected_factor is None:
        assert result.summary["annualized_icir"] is None
    else:
        assert result.summary["annualized_icir"] == pytest.approx(
            result.summary["icir"] * expected_factor ** 0.5
        )


def test_constant_and_insufficient_cross_sections_have_blank_correlations():
    signals = signal_frame()
    signals.loc[signals["as_of_date"].eq("2026-01-02"), "score"] = 1
    signals = signals.loc[~(
        signals["as_of_date"].eq("2026-01-09")
        & signals["ticker"].isin(["B", "C", "D"])
    )]
    result = evaluate_signals(
        signals, label_frame(), protocol(),
        model_configuration_fingerprint="model",
    )
    assert result.daily_ic.loc[0, "status"] == "constant_signal"
    assert pd.isna(result.daily_ic.loc[0, "ic"])
    assert result.daily_ic.loc[1, "status"] == "insufficient_cross_section"
    assert result.coverage.loc[1, "coverage"] == 0.25


def test_label_fingerprint_is_enforced():
    wrong = replace(protocol(), label_dataset_fingerprint="bad")
    with pytest.raises(ResearchValidationError, match="label_fingerprint_mismatch"):
        evaluate_signals(
            signal_frame(), label_frame(), wrong,
            model_configuration_fingerprint="model",
        )


def test_comparison_allows_different_models_but_requires_same_protocol(tmp_path):
    first = evaluate_signals(
        signal_frame(), label_frame(), protocol(),
        model_configuration_fingerprint="linear-config",
        dataset_fingerprints={"features": "linear-features"},
    ).summary
    second = evaluate_signals(
        signal_frame(inverse=True), label_frame(), protocol(),
        model_configuration_fingerprint="lightgbm-config",
        dataset_fingerprints={"features": "lightgbm-features"},
    ).summary
    output = tmp_path / "comparison.csv"
    comparison = compare_evaluations([second, first], output_path=output)
    assert list(comparison["model_id"]) == ["inverse", "strong"]
    assert comparison["model_configuration_fingerprint"].nunique() == 2
    assert output.is_file()
    mismatched = dict(second)
    mismatched["evaluation_protocol_fingerprint"] = "other"
    with pytest.raises(ResearchValidationError, match="evaluation_protocol_mismatch"):
        compare_evaluations([first, mismatched])


def test_failed_models_remain_visible_in_comparison():
    first = evaluate_signals(
        signal_frame(), label_frame(), protocol(),
        model_configuration_fingerprint="linear",
    ).summary
    failed = dict(first)
    failed.update({
        "model_id": "failed-model",
        "run_id": "failed-run",
        "validation_status": "failed",
        "failure_reason": "contract violation",
        "mean_ic": None,
    })
    result = compare_evaluations([first, failed])
    row = result.loc[result["model_id"].eq("failed-model")].iloc[0]
    assert row["validation_status"] == "failed"
    assert row["failure_reason"] == "contract violation"


def test_comparison_rejects_explicit_test_contamination():
    first = evaluate_signals(
        signal_frame(), label_frame(), protocol(),
        model_configuration_fingerprint="linear",
    ).summary
    second = dict(first)
    second.update({
        "model_id": "contaminated",
        "run_id": "bad-run",
        "test_contamination": True,
    })
    with pytest.raises(ResearchValidationError, match="test_contamination"):
        compare_evaluations([first, second])
