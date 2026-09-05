from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from stock_ranker.historical_evaluation_readiness import (
    RANKING_DATES,
    _outcome_key_availability,
    audit_historical_evaluation_readiness,
)


def test_outcome_readiness_uses_only_keys_and_dates() -> None:
    rows = pd.DataFrame([
        {"ranking_date":"2024-08-07", "ticker":"A", "date":"2024-08-07"},
        {"ranking_date":"2024-08-07", "ticker":"A", "date":"2025-08-07"},
        {"ranking_date":"2024-08-07", "ticker":"B", "date":"2024-08-07"},
        {"ranking_date":"2024-08-07", "ticker":"B", "date":"2025-08-08"},
    ])
    assert _outcome_key_availability(rows, "2024-08-07", {"A", "B"}) == {"A"}


def _price_rows(ranking_date: str) -> pd.DataFrame:
    current = pd.Timestamp(ranking_date)
    dates = [
        current - pd.DateOffset(years=5),
        current - pd.DateOffset(years=3),
        current - pd.DateOffset(years=1),
        current - pd.DateOffset(years=1) + pd.Timedelta(days=1),
        current - pd.DateOffset(years=1) + pd.Timedelta(days=2),
        current,
    ]
    return pd.DataFrame({
        "ticker": "T00", "date": [value.date().isoformat() for value in dates],
        "pit_adjusted_price": [50, 60, 80, 81, 82, 100],
    })


def _snapshot(root: Path, ranking_date: str) -> None:
    path = root / ranking_date
    path.mkdir(parents=True)
    universe = pd.DataFrame([
        {
            "historical_symbol": f"T{index:02d}", "company": f"Company {index}",
            "historical_sector": "Sector A" if index < 25 else "Sector B",
            "investable": True,
        }
        for index in range(50)
    ])
    universe.to_csv(path / "historical_universe.csv", index=False)
    pd.DataFrame([{
        "ticker":"T00", "company":"Company 0", "sector":"Sector A",
        "as_of_date":ranking_date, "current_price":100, "close_1y_ago":80,
        "close_3y_ago":60, "close_5y_ago":50, "ath_date":ranking_date,
    }]).to_csv(path / "baseline_full.csv", index=False)
    _price_rows(ranking_date).to_csv(path / "predictor_prices.csv", index=False)


def test_readiness_intersects_with_historical_membership_and_freezes_same_cohort(
    tmp_path: Path,
) -> None:
    blind = tmp_path / "blind"
    selected_rows = []
    outcome_rows = []
    for ranking_date in RANKING_DATES:
        _snapshot(blind, ranking_date)
        period_end = f"{ranking_date[:4]}-03-31"
        selected_rows.append({
            "ticker":"T00", "company":"Company 0", "isin":"INE000A01001",
            "ranking_date":ranking_date, "period_end":period_end,
            "official_available_at":f"{ranking_date}T09:00:00Z",
            "period_status":"ELIGIBLE_PERIOD", "selected_for_ranking_date":True,
            "roce":.2, "debt_to_equity":.1, "current_pat":12, "prior_pat":10,
        })
        outcome_rows.extend([
            {"ranking_date":ranking_date, "ticker":"T00", "date":ranking_date},
            {
                "ranking_date":ranking_date, "ticker":"T00",
                "date":str((pd.Timestamp(ranking_date) + pd.DateOffset(months=12)).date()),
            },
        ])
    result = audit_historical_evaluation_readiness(
        screener_selected=pd.DataFrame(selected_rows),
        identity_master=pd.DataFrame([{
            "ticker":"T00", "company":"Company 0", "isin":"INE000A01001",
        }]),
        prospective_counts=pd.DataFrame([
            {"ranking_date":value, "prospective_union_count":99}
            for value in RANKING_DATES
        ]),
        blind_root=blind,
        outcome_dates=pd.DataFrame(outcome_rows),
        protocol={"protocol_identifier":"test_protocol"},
    )
    assert result.cohort_summary["starting_prospective_v2_count"].tolist() == [99] * 4
    assert result.cohort_summary["final_same_cohort_count"].tolist() == [1] * 4
    assert result.cohort_membership["primary_outcome_key_available"].all()
    assert result.report["outcomes_calculated_or_inspected"] is False
    assert result.report["verdict"] == "TARGETED_DATA_FIX_REQUIRED"
    assert set(result.exclusions["reason_code"]) == {"NO_EXACT_CURRENT_ISIN_IDENTITY"}
