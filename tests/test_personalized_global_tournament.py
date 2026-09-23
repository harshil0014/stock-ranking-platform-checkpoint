from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.personalized_global_tournament import (
    add_transparent_candidates,
    load_protocol,
)


ROOT = Path(__file__).parents[1]


def test_preregistered_locked_dates_follow_prelock_maturity() -> None:
    protocol, profiles = load_protocol(ROOT / "research/protocols/personalized_global_tournament_v1.json")
    assert min(pd.to_datetime(protocol["locked_test_decision_dates"])) > pd.Timestamp(
        protocol["latest_prelock_outcome_maturity"]
    )
    assert {profile.lookback_months for profile in profiles.values()} == {12, 36, 60}


def test_protocol_rejects_lockbox_overlap(tmp_path: Path) -> None:
    source = json.loads((ROOT / "research/protocols/personalized_global_tournament_v1.json").read_text())
    source["locked_test_decision_dates"] = [source["latest_prelock_outcome_maturity"]]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(ValueError, match="locked decisions"):
        load_protocol(path)


def test_global_blend_requires_both_components() -> None:
    frame = pd.DataFrame({
        "goal_score": [0.1, 0.2, None],
        "global_existing_score": [0.3, 0.1, 0.2],
        "historical_target_frequency": [0.5, 1.0, 0.0],
    })
    result = add_transparent_candidates(frame)
    assert result.loc[:1, "goal_plus_global_existing_score"].notna().all()
    assert pd.isna(result.loc[2, "goal_plus_global_existing_score"])
    assert result.historical_target_frequency_score.tolist() == [0.5, 1.0, 0.0]
