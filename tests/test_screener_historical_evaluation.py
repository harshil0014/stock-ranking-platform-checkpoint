from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest

from stock_ranker.screener_historical_evaluation import (
    calculate_frozen_future_returns,
    evaluate_frozen_same_cohort,
    export_frozen_evaluation,
)


def _membership() -> pd.DataFrame:
    rows = []
    for ticker, baseline, v2 in (("AAA", 1, 3), ("BBB", 2, 2), ("CCC", 3, 1)):
        rows.append({
            "ranking_date": "2022-08-05", "ticker": ticker,
            "company": ticker, "isin": f"ISIN-{ticker}", "sector": "Sector",
            "baseline_score": 1.0, "baseline_sector_rank": baseline,
            "research_v2_score": 1.0, "research_v2_sector_rank": v2,
            "comparison_cohort_member": True,
        })
    return pd.DataFrame(rows)


def _returns() -> pd.DataFrame:
    rows = []
    values = {"AAA": 0.3, "BBB": 0.2, "CCC": 0.1}
    for ticker, value in values.items():
        for months in (3, 6, 12):
            rows.append({
                "ranking_date": "2022-08-05", "ticker": ticker,
                "isin": f"ISIN-{ticker}", "horizon_months": months,
                "future_adjusted_return": value,
            })
    return pd.DataFrame(rows)


def test_evaluation_uses_frozen_ranks_and_primary_equal_sector_cells() -> None:
    result = evaluate_frozen_same_cohort(
        _membership(), _returns(), protocol_fingerprint="protocol",
        cohort_fingerprint="cohort", blind_manifest_fingerprint="blind",
    )
    primary = result.sector_metrics.query("horizon_months == 12").iloc[0]
    assert primary["matched_baseline_rank_ic"] == pytest.approx(1.0)
    assert primary["research_v2_rank_ic"] == pytest.approx(-1.0)
    assert primary["delta_rank_ic"] == pytest.approx(-2.0)
    assert result.summary["primary_descriptive_direction"] == "DESCRIPTIVE_BASELINE_HIGHER"
    assert result.summary["rankings_frozen_before_outcomes_read"] is True


def test_future_returns_use_exact_start_and_last_observation_on_or_before_target(tmp_path: Path) -> None:
    member = _membership().iloc[[0]]
    pd.DataFrame({
        "date": ["2022-08-05", "2022-11-04", "2023-02-03", "2023-08-04", "2023-08-08"],
        "adjusted_close": [100.0, 110.0, 120.0, 130.0, 999.0],
    }).to_csv(tmp_path / "AAA.csv", index=False)
    result = calculate_frozen_future_returns(member, tmp_path)
    assert result["actual_endpoint_date"].tolist() == ["2022-11-04", "2023-02-03", "2023-08-04"]
    assert result["future_adjusted_return"].tolist() == pytest.approx([0.1, 0.2, 0.3])
    assert 999.0 not in result["endpoint_adjusted_close"].tolist()


def test_export_is_canonical_and_rejects_stale_output(tmp_path: Path) -> None:
    result = evaluate_frozen_same_cohort(
        _membership(), _returns(), protocol_fingerprint="protocol",
        cohort_fingerprint="cohort", blind_manifest_fingerprint="blind",
    )
    one, two = tmp_path / "one", tmp_path / "two"
    first = export_frozen_evaluation(result, one, {"test": True})
    second = export_frozen_evaluation(result, two, {"test": True})
    assert first == second
    names = sorted(path.name for path in one.iterdir())
    for name in names:
        assert (one / name).read_bytes() == (two / name).read_bytes()
    manifest = json.loads((one / "manifest.json").read_text())
    assert manifest["evaluation_fingerprint"] == first
    for item in manifest["artifacts"]:
        assert sha256((one / item["path"]).read_bytes()).hexdigest() == item["sha256"]
    with pytest.raises(ValueError, match="already exists"):
        export_frozen_evaluation(result, one, {"test": True})


def test_primary_result_is_separate_from_supplementary_diagnostics() -> None:
    result = evaluate_frozen_same_cohort(
        _membership(), _returns(), protocol_fingerprint="protocol",
        cohort_fingerprint="cohort", blind_manifest_fingerprint="blind",
    )
    assert result.summary["primary_metric"] == "EQUAL_WEIGHT_SECTOR_DATE_SPEARMAN_RANK_IC"
    assert result.summary["robustness_diagnostics_are_supplementary"] is True
    assert result.summary["transaction_cost_model"] is None
    assert "portfolio profitability" in result.summary["forbidden_claims"]
