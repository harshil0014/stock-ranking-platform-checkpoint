from pathlib import Path

import pandas as pd
import pytest
import json
from hashlib import sha256

from stock_research.prospective_validation import validate_prospective_freeze
from stock_research.prospective_validation import freeze_prospective_challengers, SCHEMA_VERSION


def test_validator_requires_untouched_outcome_blind_artifacts(tmp_path: Path) -> None:
    with pytest.raises((FileNotFoundError, ValueError)):
        validate_prospective_freeze(tmp_path)


def test_strict_momentum_uses_only_predecision_prices() -> None:
    from stock_research.exploratory_benchmark import strict_mom12m

    dates = pd.date_range("2025-09-30", "2026-08-31", freq="ME")
    history = pd.DataFrame({"date": dates, "adjusted_close": range(100, 112)})
    history.loc[len(history)] = [pd.Timestamp("2026-10-31"), 999999]
    assert strict_mom12m(history, "2026-09-07") == pytest.approx(111 / 100 - 1)


def test_freeze_cannot_be_backdated_by_caller(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="automatically"):
        freeze_prospective_challengers(state_root=tmp_path, history_root=tmp_path,
                                      output=tmp_path / "new", frozen_at="2020-01-01T00:00:00Z")
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize("paths", [[], ["../outside.json"], ["summary.json"] * 5])
def test_manifest_rejects_missing_duplicate_or_traversal_inventory(tmp_path: Path, paths: list[str]) -> None:
    manifest = {"schema_version": SCHEMA_VERSION, "artifacts": [
        {"path": path, "sha256": "a" * 64, "size": 0} for path in paths
    ]}
    manifest["fingerprint"] = sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="inventory"):
        validate_prospective_freeze(tmp_path)


def test_manifest_fingerprint_is_verified(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps({"schema_version": SCHEMA_VERSION, "artifacts": [], "fingerprint": "bad"}))
    with pytest.raises(ValueError, match="fingerprint"):
        validate_prospective_freeze(tmp_path)
