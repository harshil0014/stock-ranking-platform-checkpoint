import json

import pandas as pd
import pytest

from stock_research.chronological_ml_benchmark import (
    FEATURES, eligible_training_rows, score_sector_metrics, validate_panel, validate_result,
)


def _panel():
    rows = []
    for date, endpoint in (("2022-08-05", "2023-08-04"), ("2023-08-07", "2024-08-07")):
        for index in range(3):
            row = {name: float(index) for name in FEATURES}
            row.update({"ranking_date": date, "ticker": f"T{index}", "isin": f"INE{index:09d}",
                        "sector": "S", "future_adjusted_return": float(index),
                        "actual_endpoint_date": endpoint, "baseline_sector_rank": float(3 - index)})
            rows.append(row)
    return pd.DataFrame(rows)


def test_training_rows_require_sector_outcome_to_mature_strictly_before_decision():
    panel = _panel()
    assert eligible_training_rows(panel, "2023-08-07").sum() == 3
    assert eligible_training_rows(panel, "2024-08-07").sum() == 3
    assert eligible_training_rows(panel, "2024-08-08").sum() == 6


def test_validation_rejects_duplicate_identity_and_outcome_features_are_forbidden():
    panel = _panel()
    validate_panel(panel)
    with pytest.raises(ValueError, match="duplicate"):
        validate_panel(pd.concat([panel, panel.iloc[[0]]], ignore_index=True))
    assert "future_adjusted_return" not in FEATURES


def test_metrics_compare_baseline_on_exact_model_rows():
    panel = _panel().iloc[:3]
    panel["baseline_rank_signal"] = [0.0, 0.5, 1.0]
    predictions = panel[["ranking_date", "ticker", "isin"]].copy()
    predictions["model"] = "fixed"
    predictions["prediction"] = [0.0, 1.0, 2.0]
    result = score_sector_metrics(panel, predictions)
    assert set(result.model) == {"fixed", "baseline_on_fixed"}
    assert (result.peers == 3).all()


def test_result_rejects_product_default_change(tmp_path):
    for name in ("predictions.csv", "sector_metrics.csv", "execution.json"):
        (tmp_path / name).write_text("x\n", encoding="utf-8")
    (tmp_path / "summary.json").write_text(json.dumps({
        "outcome_status": "PREVIOUSLY_REVEALED_NOT_UNSEEN", "product_default_changed": True,
    }), encoding="utf-8")
    from stock_research.chronological_ml_benchmark import ARTIFACTS, SCHEMA_VERSION, file_hash
    import hashlib
    artifacts = [{"path": n, "sha256": file_hash(tmp_path / n), "size": (tmp_path / n).stat().st_size} for n in sorted(ARTIFACTS)]
    payload = {"schema_version": SCHEMA_VERSION, "artifacts": artifacts}
    payload["fingerprint"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="product default"):
        validate_result(tmp_path)
