from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_broad_study_was_predeclared_and_locked_before_test() -> None:
    protocol = json.loads((
        ROOT / "research/specifications/broad_chronological_price_ml_v1.json"
    ).read_text(encoding="utf-8"))
    assert "validation" in protocol["selection_policy"]
    assert protocol["validation"]["end"] < protocol["locked_test"]["start"]
    assert protocol["primary_horizon_months"] == 12


def test_locked_test_and_stress_artifacts_preserve_nonpromotion_boundary() -> None:
    broad = json.loads((
        ROOT / "data/analysis/broad_chronological_price_ml_v2_run_01/summary.json"
    ).read_text(encoding="utf-8"))
    stress = json.loads((
        ROOT / "data/analysis/broad_price_ml_stress_v1_run_01/summary.json"
    ).read_text(encoding="utf-8"))
    assert broad["selected_before_locked_test"] == ["ridge", "price_multifactor_signal"]
    assert broad["locked_test_models"]["selected_ensemble"]["mean_rank_ic"] > broad["locked_test_models"]["baseline_signal"]["mean_rank_ic"]
    assert stress["promotion_permitted"] is False
    assert stress["company_rows"] == 36639
