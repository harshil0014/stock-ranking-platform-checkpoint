from __future__ import annotations

import pandas as pd

from stock_ranker.internal_codex_audit import (
    audit_complete_universe,
    freeze_independent_judgments,
)


def _facts() -> pd.DataFrame:
    rows = []
    for index in range(6):
        rows.append({
            "ticker": f"T{index}", "isin": f"INE0000000{index}",
            "company": f"Company {index}", "product_sector": "Sector",
            "product_baseline_eligible": True,
            "product_baseline_reason_code": "ELIGIBLE",
            "product_baseline_ranking_tier": "PRIMARY_5Y",
            "product_baseline_score": index + 1,
            "product_baseline_sector_rank": index + 1,
            "product_baseline_yoy_growth": 1 - index / 10,
            "product_baseline_cagr_3y": 1 - index / 10,
            "product_baseline_cagr_5y": 1 - index / 10,
            "product_baseline_days_since_recorded_high": index,
            "screener_roce_pct": 20 - index,
            "screener_roe_pct": 20 - index,
            "screener_profit_growth_pct": 20 - index,
            "screener_sales_growth_pct": 20 - index,
            "screener_debt_to_equity": index / 10,
            "screener_pledged_pct": index,
            "screener_cash_conversion_quality": 2 - index / 10,
            "screener_earnings_yield_pct": 10 - index,
        })
    rows.append({
        "ticker": "U", "isin": "INE000000099", "company": "Unranked",
        "product_sector": None, "product_baseline_eligible": False,
        "product_baseline_reason_code": "UNCLASSIFIED",
        "product_baseline_ranking_tier": None,
        "product_baseline_score": None, "product_baseline_sector_rank": None,
    })
    return pd.DataFrame(rows)


def test_complete_audit_covers_ranked_and_unranked_universe() -> None:
    result = audit_complete_universe(_facts())
    assert result.summary["universe_count"] == 7
    assert result.summary["ranked_count"] == 6
    assert result.summary["unranked_count"] == 1
    assert result.summary["counts_reconcile"] is True
    assert result.summary["agreement_target_met"] is True
    assert result.summary["pairwise_agreement"] == 1.0
    assert set(result.rows["ticker"]) == {"T0", "T1", "T2", "T3", "T4", "T5", "U"}


def test_audit_rejects_inconsistent_system_rank() -> None:
    facts = _facts()
    facts.loc[facts["ticker"].eq("T0"), "product_baseline_sector_rank"] = 6
    try:
        audit_complete_universe(facts)
    except ValueError as exc:
        assert "inconsistent" in str(exc)
    else:
        raise AssertionError("inconsistent rank must fail the audit")


def test_independent_judgments_freeze_without_system_score_or_rank() -> None:
    evidence_only = _facts().drop(columns=[
        "product_baseline_score", "product_baseline_sector_rank",
    ])
    frozen = freeze_independent_judgments(evidence_only)
    assert len(frozen) == 7
    assert frozen.loc[frozen["benchmark_ranked"], "audit_rank"].notna().all()
    assert "system_rank" not in frozen.columns
    assert "system_score" not in frozen.columns


def test_below_target_agreement_is_reported_without_rejecting_result() -> None:
    facts = _facts()
    frozen = freeze_independent_judgments(facts)
    ranked = frozen["benchmark_ranked"]
    frozen.loc[ranked, "audit_score"] = -frozen.loc[ranked, "audit_score"]
    frozen.loc[ranked, "audit_rank"] = (
        frozen.loc[ranked]
        .groupby(["benchmark_sector", "benchmark_ranking_tier"])["audit_score"]
        .rank(ascending=False, method="min")
    )
    result = audit_complete_universe(facts, frozen_judgments=frozen)
    assert result.summary["benchmark_frozen_before_comparison"] is True
    assert result.summary["agreement_target_met"] is False
    assert result.summary["pairwise_agreement"] == 0.0
