from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest

from marketdata.runners.compare_same_cohort import run
from stock_ranker.same_cohort_comparison import (
    build_same_cohort_rows,
    evaluate_same_cohort,
    export_same_cohort_comparison,
)


ROOT = Path(__file__).resolve().parents[1]


def _identity() -> pd.DataFrame:
    return pd.DataFrame({
        "nse_symbol": ["A", "A-OLD", "B", "C", "D"],
        "isin": ["ISIN-A", "ISIN-A", "ISIN-B", "ISIN-C", "ISIN-D"],
        "bse_code": ["1", "1", "2", "3", "4"],
    })


def _v2() -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": ["A", "B", "C"], "company": ["A Co", "B Co", "C Co"],
        "sector": ["Sector"] * 3, "research_v2_score": [90.0, 70.0, 50.0],
        "sector_rank": [1, 2, 3],
    })


def _baseline() -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": ["A-OLD", "B", "C", "D"], "sector": ["Sector"] * 4,
        "baseline_score": [1.0, 2.0, 3.0, 0.0], "sector_rank": [1, 2, 3, 1],
    })


def _outcomes(include_c: bool = True) -> pd.DataFrame:
    tickers = ["A-OLD", "B"] + (["C"] if include_c else [])
    return pd.DataFrame({
        "ranking_date": ["2025-08-07"] * len(tickers), "ticker": tickers,
        "horizon_months": [12] * len(tickers),
        "future_adjusted_return": [0.3, 0.2] + ([0.1] if include_c else []),
        "start_date": ["2025-08-07"] * len(tickers),
        "actual_endpoint_date": ["2026-08-07"] * len(tickers),
        "start_adjusted_close": [100.0] * len(tickers),
        "endpoint_adjusted_close": [130.0, 120.0] + ([110.0] if include_c else []),
        "target_date": ["2026-08-07"] * len(tickers),
    })


def test_extra_baseline_security_is_prohibited_and_alias_resolves_once() -> None:
    cohort, evaluated, excluded = build_same_cohort_rows(
        "2025-08-07", _baseline(), _v2(), _outcomes(), _identity()
    )
    assert set(cohort["isin"]) == {"ISIN-A", "ISIN-B", "ISIN-C"}
    assert "ISIN-D" not in set(cohort["isin"])
    assert len(cohort.loc[cohort["isin"].eq("ISIN-A")]) == 1
    assert len(evaluated) == 3
    assert excluded.empty


def test_missing_v2_security_is_excluded_from_both_models() -> None:
    v2 = _v2().query("ticker != 'C'")
    cohort, evaluated, _ = build_same_cohort_rows(
        "2025-08-07", _baseline(), v2, _outcomes(), _identity()
    )
    assert set(cohort["isin"]) == set(evaluated["isin"]) == {"ISIN-A", "ISIN-B"}


def test_same_outcome_is_shared_and_missing_outcome_excludes_both() -> None:
    cohort, evaluated, excluded = build_same_cohort_rows(
        "2025-08-07", _baseline(), _v2(), _outcomes(include_c=False), _identity()
    )
    assert len(cohort) == 3
    assert set(evaluated["isin"]) == {"ISIN-A", "ISIN-B"}
    assert excluded[["isin", "outcome_status"]].to_dict("records") == [{
        "isin": "ISIN-C", "outcome_status": "SHARED_OUTCOME_UNAVAILABLE",
    }]
    assert evaluated.loc[evaluated["isin"].eq("ISIN-A"), "future_adjusted_return"].iat[0] == pytest.approx(0.3)


def test_model_values_are_filtered_not_recalculated() -> None:
    cohort, _, _ = build_same_cohort_rows(
        "2025-08-07", _baseline(), _v2(), _outcomes(), _identity()
    )
    row = cohort.set_index("isin").loc["ISIN-A"]
    assert row["baseline_score"] == 1.0
    assert row["baseline_sector_rank"] == 1
    assert row["research_v2_score"] == 90.0
    assert row["research_v2_sector_rank"] == 1


def test_future_fields_cannot_enter_formation_rankings() -> None:
    with pytest.raises(ValueError, match="outcome columns"):
        build_same_cohort_rows(
            "2025-08-07", _baseline().assign(forward_return=999), _v2(),
            _outcomes(), _identity(),
        )


def test_sector_mismatch_and_missing_baseline_identity_are_rejected() -> None:
    bad_sector = _baseline().copy()
    bad_sector.loc[bad_sector["ticker"].eq("B"), "sector"] = "Other"
    with pytest.raises(ValueError, match="sector/reference"):
        build_same_cohort_rows("2025-08-07", bad_sector, _v2(), _outcomes(), _identity())
    with pytest.raises(ValueError, match="does not equal"):
        build_same_cohort_rows(
            "2025-08-07", _baseline().query("ticker != 'C'"), _v2(),
            _outcomes(), _identity(),
        )


def test_metrics_and_export_are_byte_deterministic(tmp_path: Path) -> None:
    cohort, evaluated, excluded = build_same_cohort_rows(
        "2025-08-07", _baseline(), _v2(), _outcomes(), _identity()
    )
    first = evaluate_same_cohort(cohort, evaluated, excluded)
    second = evaluate_same_cohort(cohort.sample(frac=1, random_state=4), evaluated, excluded)
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    fingerprint_1 = export_same_cohort_comparison(first, first_dir)
    fingerprint_2 = export_same_cohort_comparison(second, second_dir)
    assert fingerprint_1 == fingerprint_2
    assert sha256((first_dir / "comparison.json").read_bytes()).hexdigest() == fingerprint_1
    assert json.loads((first_dir / "comparison.json").read_text())["aggregate"]["directional_result"] == "TIE"


def test_frozen_historical_comparison_integration(tmp_path: Path) -> None:
    output = tmp_path / "comparison"
    fingerprint = run(
        ROOT / "data/walk_forward/blind_predictions_v1_run_01",
        ROOT / "data/walk_forward/evaluation_v1_run_01",
        output,
    )
    report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
    assert report["cohort_sizes"] == {
        "2022-08-05": 8, "2023-08-07": 4, "2024-08-07": 8, "2025-08-07": 16,
    }
    assert report["date_security_observations"] == 36
    assert report["evaluated_date_security_observations"] == 36
    assert report["outcome_exclusion_count"] == 0
    assert report["identity_key"] == "ISIN"
    assert sha256((output / "comparison.json").read_bytes()).hexdigest() == fingerprint
