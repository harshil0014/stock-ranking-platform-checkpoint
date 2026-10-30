import pandas as pd
import pytest

from research.runners.personalized_championship import mature_before, outcome_labels


def test_maturity_purge_requires_endpoint_before_decision():
    panel = pd.DataFrame({"endpoint": ["2022-12-30", "2022-12-31", "2023-01-01"],
                          "future_xirr": [0.1, 0.2, 0.3]})
    result = mature_before(panel, "2022-12-31")
    assert result.future_xirr.tolist() == [0.1]
    with pytest.raises(ValueError, match="maturity-purged"):
        mature_before(panel, "2022-12-30")


def test_graded_labels_are_within_query_and_bound_outliers():
    panel = pd.DataFrame({"decision_date": ["2022-01-01"] * 4 + ["2023-01-01"] * 4,
        "profile_name": ["base"] * 8,
        "future_xirr": [.1, .2, .3, 500., 10., 20., 30., 400.],
        "future_shortfall": [.3, .2, .1, 0., .3, .2, .1, 0.]})
    four = outcome_labels(panel, "xirr4")
    eight = outcome_labels(panel, "xirr8")
    assert four.iloc[:4].tolist() == four.iloc[4:].tolist()
    assert eight.iloc[:4].tolist() == eight.iloc[4:].tolist()
    assert four.between(0, 3).all()
    assert eight.between(0, 7).all()
