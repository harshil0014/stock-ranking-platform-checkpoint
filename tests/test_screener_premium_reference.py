from __future__ import annotations

import pandas as pd
import pytest

from stock_ranker.screener_premium_reference import exact_isin_coverage, reconcile_screener_exports, validate_screener_export


def _export(roce=20.0, growth=5.0):
    return pd.DataFrame([{
        "Name": "Example Ltd", "BSE Code": 500001, "NSE Code": "EXAMPLE",
        "ISIN Code": "INE000A01001", "Industry Group": "Industrials", "Industry": "Equipment",
        "Return on capital employed": roce, "Debt to equity": 0.2,
        "Profit after tax": 100.0, "Profit growth": growth,
    }])


def test_export_requires_exact_unique_isin_and_numeric_values():
    assert validate_screener_export(_export(), source_label="one").iloc[0]["ISIN Code"] == "INE000A01001"
    bad = _export()
    bad.loc[0, "ISIN Code"] = "BAD"
    with pytest.raises(ValueError, match="invalid ISIN"):
        validate_screener_export(bad, source_label="bad")
    with pytest.raises(ValueError, match="duplicate ISIN"):
        validate_screener_export(pd.concat([_export(), _export()], ignore_index=True), source_label="dup")


def test_reconciliation_preserves_conflicts_and_never_claims_pit(tmp_path):
    first, second = tmp_path / "one.csv", tmp_path / "two.csv"
    _export().to_csv(first, index=False)
    _export(roce=21.0).to_csv(second, index=False)
    result = reconcile_screener_exports([first, second])
    assert result.rows.iloc[0]["historical_pit_eligible"] == False  # noqa: E712
    assert result.manifest["canonical_store_admission"] is False
    assert result.conflicts[["field", "conflict_type"]].values.tolist() == [["reference_roce_percent", "VALUE"]]


def test_exact_identity_coverage_does_not_fuzzy_match():
    reference = pd.DataFrame([{
        "isin": "INE000A01001", "reference_roce_percent__source_1": 20.0,
        "reference_debt_to_equity__source_1": 0.2, "reference_profit_after_tax__source_1": 100.0,
        "reference_profit_growth_percent__source_1": 5.0,
    }])
    facts = pd.DataFrame([
        {"isin": "INE000A01001", "ticker": "EXAMPLE", "company": "Different spelling", "v2_eligible": False, "baseline_eligible": True},
        {"isin": "INE999A01001", "ticker": "OTHER", "company": "Example Ltd", "v2_eligible": False, "baseline_eligible": True},
    ])
    rows, summary = exact_isin_coverage(reference, facts)
    assert rows["screener_exact_isin_match"].tolist() == [True, False]
    assert summary["exact_isin_match_count"] == summary["all_reference_metrics_count"] == 1
