import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/personalized-deep-championship-20261002/v1"


def test_lock_precedes_holdout_and_matches_development_artifact():
    lock = json.loads((OUT / "locked_selection.json").read_text())
    record = json.loads((OUT / "evaluation_record.json").read_text())
    assert lock["holdout_evaluated"] is False
    assert lock["selection_uses_holdout"] is False
    assert lock["selection_uses_exposed_2025"] is False
    assert lock["holdout_dates"] == ["2024-03-31", "2024-09-30"]
    assert hashlib.sha256((OUT / "development_tournament.csv").read_bytes()).hexdigest() == lock["development_tournament_sha256"]
    assert hashlib.sha256((OUT / "locked_selection.json").read_bytes()).hexdigest() == record["locked_selection_sha256"]


def test_prepared_artifact_seals_final_labels_and_keeps_training_maturity():
    frame = pd.read_pickle(OUT / "prepared.pkl.gz", compression="gzip")
    protocol = json.loads((ROOT / "research/protocols/personalized_deep_walkforward_v1.json").read_text())
    sealed = frame.decision_date.isin(protocol["clean_holdout_dates"] + protocol["exposed_diagnostic_dates"])
    assert frame.loc[sealed, ["future_xirr", "future_shortfall", "future_drawdown"]].isna().all().all()
    assert (pd.to_datetime(frame.endpoint) > pd.to_datetime(frame.decision_date)).all()
    assert (pd.to_datetime(frame.endpoint) <= pd.Timestamp("2026-09-18")).all()
    for date in protocol["development_selection_dates"] + protocol["clean_holdout_dates"]:
        train = frame.loc[pd.to_datetime(frame.endpoint).lt(pd.Timestamp(date))]
        assert not train.empty
        assert pd.to_datetime(train.endpoint).max() < pd.Timestamp(date)


def test_holdout_and_diagnostic_dates_are_disjoint_and_coverage_matches():
    hold = pd.read_csv(OUT / "holdout_profiles.csv")
    exposed = pd.read_csv(OUT / "exposed_profiles.csv")
    assert set(hold.decision_date) == {"2024-03-31", "2024-09-30"}
    assert set(exposed.decision_date) == {"2025-03-31", "2025-06-30"}
    assert hold.coverage_champion.equals(hold.coverage_challenger)
    assert exposed.coverage_champion.equals(exposed.coverage_challenger)


def test_provider_quarantine_is_preserved():
    summary = json.loads((ROOT / "experiments/personalized-deep-history-20261002/real-panel-v7/summary.json").read_text())
    audit = summary["provider_reacquisition_audit"]
    assert audit["canonical_observed_event_count"] == 1802
    assert audit["raw_response_integrity_verified"] is True
    assert audit["failed_identities_quarantined"] == 104
