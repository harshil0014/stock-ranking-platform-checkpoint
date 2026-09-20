from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from stock_ranker.universe_completion import complete_universe, validate_completion


ROOT = Path(__file__).resolve().parents[1]
COMPLETION = ROOT / "data/analysis/complete_universe_20260918_run_05"


def _facts() -> pd.DataFrame:
    rows = []
    for index in range(4):
        rows.append({
            "ticker": f"T{index}", "isin": f"INE0000000{index}",
            "company": "Alpha Chemicals Limited" if index == 3 else f"Company {index}",
            "product_sector": None if index == 3 else "Chemicals & Petrochemicals",
            "product_industry": None if index == 3 else "Commodity Chemicals",
            "product_baseline_eligible": index < 3,
            "product_baseline_reason_code": "UNCLASSIFIED" if index == 3 else "RANKED_PRIMARY_5Y",
            "product_baseline_yoy_growth": np.nan if index == 3 else 0.30 - index / 20,
            "product_baseline_cagr_3y": np.nan if index == 3 else 0.20 - index / 30,
            "product_baseline_cagr_5y": np.nan if index == 3 else 0.15 - index / 40,
            "product_baseline_days_since_recorded_high": np.nan if index == 3 else index * 5,
            "screener_roce_pct": np.nan if index == 3 else 20 - index,
            "screener_roe_pct": np.nan if index == 3 else 18 - index,
            "screener_profit_growth_pct": np.nan if index == 3 else 15 - index,
            "screener_sales_growth_pct": np.nan if index == 3 else 12 - index,
            "screener_debt_to_equity": np.nan if index == 3 else index / 10,
            "screener_pledged_pct": np.nan if index == 3 else index,
            "screener_cash_conversion_quality": np.nan if index == 3 else 1.2 - index / 10,
            "screener_earnings_yield_pct": np.nan if index == 3 else 8 - index,
            "screener_return_1y_pct": np.nan,
            "trade_date": "2026-09-18",
            "company_profile": None if index == 3 else "Observed profile",
        })
    return pd.DataFrame(rows)


def test_completion_fills_and_ranks_every_identity_without_mutating_source() -> None:
    facts = _facts()
    original = facts.copy(deep=True)
    result = complete_universe(facts)
    pd.testing.assert_frame_equal(facts, original)
    assert result.summary["all_ranked"] is True
    assert result.summary["remaining_missing_cell_count"] == 0
    assert len(result.rankings) == len(facts)
    assert result.completed["complete_sector_rank"].notna().all()
    assert result.completed["product_baseline_eligible"].all()
    inferred = result.completed.loc[result.completed["ticker"].eq("T3")].iloc[0]
    assert inferred["complete_sector"] == "Chemicals & Petrochemicals"
    assert inferred["complete_sector_confidence"] == "LOW"
    assert result.estimate_codes.loc[
        result.estimate_codes["ticker"].eq("T3"), "estimate_code__product_sector"
    ].iloc[0] != 0


def test_checked_in_completion_is_fingerprint_valid_and_total() -> None:
    summary = validate_completion(COMPLETION)
    assert summary["universe_count"] == 4436
    assert summary["ranked_count"] == 4436
    assert summary["resolved_unranked_count"] == 449
    assert summary["resolved_unclassified_count"] == 131
    assert summary["remaining_missing_cell_count"] == 0
