from __future__ import annotations

from copy import deepcopy

import pandas as pd
import pytest

from stock_research.contracts import (
    ChronologicalSplit,
    DateRange,
    reject_test_contamination,
    validate_feature_panel,
    validate_labels,
    validate_signals,
    validate_split,
)
from stock_research.errors import ResearchValidationError


def features() -> pd.DataFrame:
    return pd.DataFrame({
        "as_of_date": ["2026-01-02", "2026-01-02"],
        "ticker": ["AAA", "BBB"],
        "sector": ["Tech", "Finance"],
        "max_feature_available_date": ["2026-01-02", "2026-01-01"],
        "zeta": [2, 3],
        "alpha": [1, 4],
    })


def labels() -> pd.DataFrame:
    return pd.DataFrame({
        "as_of_date": ["2026-01-02", "2026-01-02"],
        "ticker": ["AAA", "BBB"],
        "label_end_date": ["2026-01-09", "2026-01-09"],
        "forward_return": [0.1, -0.1],
        "label_name": ["forward_5d_return"] * 2,
    })


def signals() -> pd.DataFrame:
    return pd.DataFrame({
        "as_of_date": ["2026-01-02", "2026-01-02"],
        "ticker": ["AAA", "BBB"],
        "score": [1.0, -1.0],
        "model_id": ["model"] * 2,
        "run_id": ["run"] * 2,
    })


def test_feature_contract_orders_features_and_does_not_mutate():
    data = features()
    before = data.copy(deep=True)
    result = validate_feature_panel(data)
    assert list(result.columns) == [
        "as_of_date", "ticker", "sector", "max_feature_available_date",
        "alpha", "zeta",
    ]
    pd.testing.assert_frame_equal(data, before)


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        (lambda d: d.drop(columns="sector"), "missing_columns"),
        (lambda d: d.assign(forward_return=[1, 2]), "label_feature_leakage"),
        (lambda d: pd.concat([d, d.iloc[[0]]]), "duplicate_feature_key"),
        (
            lambda d: d.assign(
                max_feature_available_date=["2026-01-03", "2026-01-01"]
            ),
            "future_feature_availability",
        ),
        (lambda d: d.assign(alpha=[float("inf"), 2]), "nonfinite_numeric"),
    ],
)
def test_feature_contract_rejects_invalid_data(change, rule):
    with pytest.raises(ResearchValidationError) as error:
        validate_feature_panel(change(features()))
    assert error.value.diagnostics[0].rule_id == rule


def test_conflicting_sector_has_specific_rule():
    data = pd.concat([features().iloc[[0]], features().iloc[[0]]], ignore_index=True)
    data.loc[1, "sector"] = "Other"
    with pytest.raises(ResearchValidationError, match="conflicting_sector"):
        validate_feature_panel(data)


def test_labels_and_signals_contracts():
    assert len(validate_labels(labels())) == 2
    assert len(validate_signals(signals(), {"model"})) == 2
    with pytest.raises(ResearchValidationError, match="invalid_label_horizon"):
        validate_labels(labels().assign(label_end_date="2026-01-02"))
    with pytest.raises(ResearchValidationError, match="unknown_model_id"):
        validate_signals(signals(), {"different"})


def test_mixed_or_malformed_dates_are_rejected():
    data = labels()
    data.loc[0, "as_of_date"] = "02/01/2026"
    with pytest.raises(ResearchValidationError, match="malformed_date"):
        validate_labels(data)
    data = labels()
    data["as_of_date"] = data["as_of_date"].astype(object)
    data.loc[0, "as_of_date"] = pd.Timestamp("2026-01-02")
    with pytest.raises(ResearchValidationError, match="mixed_date_representation"):
        validate_labels(data)


def test_split_gaps_and_test_contamination():
    split = validate_split({
        "train": {"start": "2020-01-01", "end": "2020-12-31"},
        "validation": {"start": "2021-01-04", "end": "2021-12-31"},
        "test": {"start": "2022-01-04", "end": "2022-12-31"},
        "purge_days": 2,
        "embargo_days": 0,
    })
    assert split.test.start.isoformat() == "2022-01-04"
    with pytest.raises(ResearchValidationError, match="test_contamination"):
        reject_test_contamination(["2021-06-01", "2022-01-04"], split)
    with pytest.raises(ResearchValidationError, match="split_gap_violation"):
        ChronologicalSplit(
            DateRange("2020-01-01", "2020-12-31"),
            DateRange("2021-01-01", "2021-12-31"),
            DateRange("2022-01-01", "2022-12-31"),
            purge_days=1,
        )


def test_split_applies_purge_and_embargo_to_their_own_boundaries():
    split = ChronologicalSplit(
        DateRange("2026-01-01", "2026-01-10"),
        DateRange("2026-01-13", "2026-01-20"),
        DateRange("2026-01-25", "2026-01-31"),
        purge_days=2,
        embargo_days=4,
    )

    assert split.purge_days == 2
    assert split.embargo_days == 4


def test_split_boundary_rules_are_asymmetric_and_old_stricter_splits_still_work():
    purge_only = ChronologicalSplit(
        DateRange("2026-01-01", "2026-01-10"),
        DateRange("2026-01-13", "2026-01-20"),
        DateRange("2026-01-21", "2026-01-31"),
        purge_days=2,
        embargo_days=0,
    )
    embargo_only = ChronologicalSplit(
        DateRange("2026-01-01", "2026-01-10"),
        DateRange("2026-01-11", "2026-01-20"),
        DateRange("2026-01-25", "2026-01-31"),
        purge_days=0,
        embargo_days=4,
    )
    old_stricter = ChronologicalSplit(
        DateRange("2026-01-01", "2026-01-10"),
        DateRange("2026-01-17", "2026-01-20"),
        DateRange("2026-01-27", "2026-01-31"),
        purge_days=2,
        embargo_days=4,
    )
    assert purge_only.validation.start.isoformat() == "2026-01-13"
    assert embargo_only.test.start.isoformat() == "2026-01-25"
    assert old_stricter.purge_days == 2

    with pytest.raises(ResearchValidationError, match="train/validation"):
        ChronologicalSplit(
            DateRange("2026-01-01", "2026-01-10"),
            DateRange("2026-01-12", "2026-01-20"),
            DateRange("2026-01-30", "2026-01-31"),
            purge_days=2,
            embargo_days=0,
        )
    with pytest.raises(ResearchValidationError, match="validation/test"):
        ChronologicalSplit(
            DateRange("2026-01-01", "2026-01-10"),
            DateRange("2026-01-13", "2026-01-20"),
            DateRange("2026-01-24", "2026-01-31"),
            purge_days=0,
            embargo_days=4,
        )
