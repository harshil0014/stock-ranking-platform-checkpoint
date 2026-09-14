from datetime import datetime, timezone

import pandas as pd
import pytest

from stock_ranker.upstox_fundamentals import (
    PIT_CANDIDATE_STATUS,
    build_profit_pairs,
    normalize_balance_sheet,
    normalize_income_statement,
    period_label_to_end,
)


OBSERVED = datetime(2026, 9, 14, 4, 30, tzinfo=timezone.utc)
ISIN = "INE002A01018"


def _income(*, basis="standalone"):
    return {
        "status": "success",
        "data": {
            "type": basis,
            "time_period": "yearly",
            "units_in": "crore",
            "income_statement": [
                {
                    "category": "revenue",
                    "history": [
                        {"value": 1000, "period": "Mar 2026", "change": "+10%"},
                        {"value": 900, "period": "Mar 2025"},
                    ],
                },
                {
                    "category": "operating_profit",
                    "history": [
                        {"value": 180, "period": "Mar 2026", "change": "+20%"},
                        {"value": 150, "period": "Mar 2025"},
                    ],
                },
                {
                    "category": "net_profit",
                    "history": [
                        {"value": 120, "period": "Mar 2026", "change": "+20%"},
                        {"value": 100, "period": "Mar 2025"},
                    ],
                },
            ],
            "full_statement": [
                {
                    "particular": "Profit After Tax",
                    "history": [
                        {"period": "Mar 2026", "value": 120},
                        {"period": "Mar 2025", "value": 100},
                    ],
                }
            ],
        },
    }


def _balance(*, basis="standalone"):
    return {
        "status": "success",
        "data": {
            "type": basis,
            "time_period": "yearly",
            "units_in": "crore",
            "history": [
                {"total_asset": 2000, "total_liability": 800, "period": "Mar 2026"},
                {"total_asset": 1800, "total_liability": 750, "period": "Mar 2025"},
            ],
            "full_statement": [
                {
                    "particular": "Equity Capital",
                    "history": [
                        {"period": "Mar 2026", "value": 1200},
                        {"period": "Mar 2025", "value": 1050},
                    ],
                }
            ],
        },
    }


def test_period_labels_are_calendar_month_ends():
    assert period_label_to_end("Mar 2026") == "2026-03-31"
    assert period_label_to_end("Feb 2024") == "2024-02-29"
    with pytest.raises(ValueError, match="unsupported Upstox period label"):
        period_label_to_end("FY26")


def test_income_is_exact_isin_basis_and_candidate_only():
    facts = normalize_income_statement(
        _income(), isin=ISIN, reporting_basis="STANDALONE",
        source_observed_at=OBSERVED,
    )
    net = facts.loc[facts["metric"].eq("net_profit")].sort_values("period_end")
    assert net["period_end"].tolist() == ["2025-03-31", "2026-03-31"]
    assert net["value"].tolist() == [100.0, 120.0]
    assert set(facts["reporting_basis"]) == {"STANDALONE"}
    assert set(facts["pit_candidate_status"]) == {PIT_CANDIDATE_STATUS}
    assert facts["source_observed_at"].str.startswith("2026-09-14").all()
    assert not facts["metric"].isin(["roce", "debt_to_equity"]).any()


def test_profit_pairs_do_not_backdate_present_day_observation():
    facts = normalize_income_statement(
        _income(), isin=ISIN, reporting_basis="STANDALONE",
        source_observed_at=OBSERVED,
    )
    pairs = build_profit_pairs(facts)
    row = pairs.loc[pairs["period_end"].eq("2026-03-31")].iloc[0]
    assert row["current_pat"] == 120.0
    assert row["prior_pat"] == 100.0
    assert row["pit_candidate_status"] == PIT_CANDIDATE_STATUS
    assert str(row["source_observed_at"]).startswith("2026-09-14")


def test_balance_sheet_is_normalized_without_ratio_derivation():
    facts = normalize_balance_sheet(
        _balance(), isin=ISIN, reporting_basis="STANDALONE",
        source_observed_at=OBSERVED,
    )
    assert {"total_assets", "total_liabilities", "balance_line:equity_capital"}.issubset(
        set(facts["metric"])
    )
    assert not facts["metric"].isin(["roce", "debt_to_equity"]).any()
    assert set(facts["pit_candidate_status"]) == {PIT_CANDIDATE_STATUS}


def test_basis_mismatch_and_bad_identity_are_rejected():
    with pytest.raises(ValueError, match="reporting basis mismatch"):
        normalize_income_statement(
            _income(basis="consolidated"), isin=ISIN,
            reporting_basis="STANDALONE", source_observed_at=OBSERVED,
        )
    with pytest.raises(ValueError, match="invalid Indian ISIN"):
        normalize_income_statement(
            _income(), isin="RELIANCE", reporting_basis="STANDALONE",
            source_observed_at=OBSERVED,
        )


def test_naive_observation_and_duplicate_periods_are_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_income_statement(
            _income(), isin=ISIN, reporting_basis="STANDALONE",
            source_observed_at="2026-09-14T10:00:00",
        )
    payload = _income()
    payload["data"]["income_statement"][2]["history"].append(
        {"value": 121, "period": "Mar 2026"}
    )
    with pytest.raises(ValueError, match="duplicate Upstox income fact"):
        normalize_income_statement(
            payload, isin=ISIN, reporting_basis="STANDALONE",
            source_observed_at=OBSERVED,
        )


def test_schema_rejects_non_crore_and_failed_payloads():
    payload = _income()
    payload["data"]["units_in"] = "million"
    with pytest.raises(ValueError, match="unsupported Upstox monetary unit"):
        normalize_income_statement(
            payload, isin=ISIN, reporting_basis="STANDALONE",
            source_observed_at=OBSERVED,
        )
    with pytest.raises(ValueError, match="not a successful payload"):
        normalize_income_statement(
            {"status": "error", "data": {}}, isin=ISIN,
            reporting_basis="STANDALONE", source_observed_at=OBSERVED,
        )
