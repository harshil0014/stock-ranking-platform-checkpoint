from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pandas as pd
import pytest

from stock_research.current_price_ensemble import validate_current_price_ensemble


ROOT = Path(__file__).parents[1]


def _write_artifact(root: Path, *, outcome_access: bool = False) -> None:
    root.mkdir()
    pd.DataFrame(
        [{"isin": "INE000000001", "ticker": "AAA", "ensemble_score": 0.75}]
    ).to_csv(root / "rankings.csv", index=False, lineterminator="\n")
    summary = {
        "ranked": 1,
        "product_default": "baseline_v1",
        "product_default_changed": False,
        "outcomes_accessed_for_current_ranking": outcome_access,
    }
    (root / "summary.json").write_text(
        json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8"
    )
    artifacts = []
    for path in sorted(root.iterdir()):
        artifacts.append({
            "path": path.name,
            "sha256": sha256(path.read_bytes()).hexdigest(),
            "size": path.stat().st_size,
        })
    fingerprint = sha256(
        json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (root / "manifest.json").write_text(
        json.dumps({"artifacts": artifacts, "fingerprint": fingerprint}),
        encoding="utf-8",
    )


def test_current_candidate_artifact_is_identity_checked_and_outcome_blind(tmp_path: Path) -> None:
    root = tmp_path / "candidate"
    _write_artifact(root)
    summary = validate_current_price_ensemble(root)
    assert summary["ranked"] == 1
    assert summary["product_default"] == "baseline_v1"


def test_current_candidate_rejects_outcome_access(tmp_path: Path) -> None:
    root = tmp_path / "candidate"
    _write_artifact(root, outcome_access=True)
    with pytest.raises(ValueError, match="scientific boundary"):
        validate_current_price_ensemble(root)


def test_accepted_candidate_has_frozen_identity_and_no_default_promotion() -> None:
    summary = validate_current_price_ensemble(
        ROOT / "data/analysis/current_price_ensemble_v5_20260918_run_01"
    )
    assert summary["ranked"] == 3713
    assert summary["outcomes_accessed_for_current_ranking"] is False
    assert summary["product_default_changed"] is False
    assert summary["accepted_company_fingerprint"] == (
        "4064dc5b0a12fc385150a08e23a61f230b0f2acfcee76e394c8e80cee48d741e"
    )
