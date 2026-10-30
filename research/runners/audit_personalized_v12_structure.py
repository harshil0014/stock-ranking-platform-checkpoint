"""V12 structural audit. Deliberately never loads future outcome columns."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import pandas as pd

BASE = ROOT / "experiments/personalized-deep-history-20261002"
V12 = BASE / "real-panel-v12"
V11 = BASE / "real-panel-v11"
LEDGER = BASE / "yahoo-split-ledger-v2"
SHARDS = [BASE / "real-panel-v11-boundary-shard", *[BASE / f"real-panel-v12-v2-shard{x}" for x in "ABCD"]]
STRUCT = ["isin", "decision_date", "endpoint", "profile_name", "status", "partition"]
KEY = ["decision_date", "profile_name", "isin"]
FINAL = {"2025-01-31", "2025-08-31"}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run() -> None:
    summary = json.loads((V12 / "summary.json").read_text())
    provider = summary["provider_v2_propagation"]
    assert provider["reconstructed_dates"] == 40
    assert provider["successful_identities"] == 3790
    assert provider["remaining_failed_identities"] == 18
    assert provider["split_event_count"] == 1816
    assert provider["sealed_final_outcomes_inspected_for_collection"] is False
    assert sha(LEDGER / "split_ledger.csv") == provider["ledger_sha256"]
    assert sha(LEDGER / "acquisition_audit.csv") == provider["audit_sha256"]
    for name, expected in summary["output_sha256"].items():
        assert sha(V12 / name) == expected, name

    checkpoints = {}
    for shard in SHARDS:
        for path in (shard / "checkpoints").glob("deep_added-*.csv.gz"):
            date = path.name.removeprefix("deep_added-").removesuffix(".csv.gz")
            if date in provider["checkpoint_sha256"]:
                assert date not in checkpoints, f"duplicate checkpoint {date}"
                checkpoints[date] = {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha(path)}
    assert set(checkpoints) == set(provider["checkpoint_sha256"])
    assert all(checkpoints[d]["sha256"] == h for d, h in provider["checkpoint_sha256"].items())

    panel = pd.read_csv(V12 / "deep_panel.csv.gz", usecols=STRUCT, low_memory=False)
    assert len(panel) == summary["total_matured_observations"] == 1516870
    assert not panel[KEY].duplicated().any()
    assert set(panel.decision_date) == set(summary["all_dates"])
    assert FINAL.issubset(set(panel.decision_date))
    endpoint = pd.to_datetime(panel.endpoint, errors="raise")
    decision = pd.to_datetime(panel.decision_date, errors="raise")
    assert decision.lt(endpoint).all()
    assert endpoint.le(pd.Timestamp(summary["cutoff"])).all()
    assert all(x >= "2015-01-31" for x in summary["additional_dates"])
    assert len(summary["source_dates"]) == 10 and len(summary["additional_dates"]) == 40
    assert set(summary["source_dates"]).isdisjoint(summary["additional_dates"])
    assert panel.loc[panel.decision_date.isin(summary["additional_dates"]), "partition"].eq("DEEP_ADDED").all()

    coverage = panel.groupby("decision_date").agg(rows=("isin", "size"), identities=("isin", "nunique"),
        profiles=("profile_name", "nunique"), endpoint=("endpoint", "max"),
        available=("status", lambda x: int(x.eq("AVAILABLE").sum()))).reset_index()
    claimed = pd.read_csv(V12 / "date_coverage.csv")
    pd.testing.assert_frame_equal(coverage, claimed, check_dtype=False)
    assert coverage.profiles.eq(9).all()
    assert set(coverage.decision_date) == set(summary["all_dates"])
    assert coverage.loc[coverage.decision_date.isin(summary["additional_dates"]), "identities"].eq(3790).all()

    original = pd.read_csv(V11 / "deep_panel.csv.gz", usecols=STRUCT, low_memory=False)
    source = set(summary["source_dates"])
    a = panel.loc[panel.decision_date.isin(source)].sort_values(KEY).reset_index(drop=True)
    b = original.loc[original.decision_date.isin(source)].sort_values(KEY).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b, check_dtype=False)
    assert len(a) == 304670
    delta = pd.read_csv(V12 / "coverage_delta_vs_v11.csv")
    assert delta.loc[delta.decision_date.isin(source), ["rows_delta", "identities_delta", "available_delta"]].eq(0).all().all()
    overlap = pd.read_csv(V12 / "outcome_window_overlap.csv")
    assert len(overlap) == 1225 and (overlap.horizon_overlap_fraction > 0).sum() == 212

    official = ROOT / "experiments/personalized-official-action-freeze/build-06/normalized_official_action_ledger.csv.gz"
    assert sha(official) == summary["input_sha256"][r"experiments\personalized-official-action-freeze\build-06\normalized_official_action_ledger.csv.gz"]
    report = {
        "schema": "personalized_v12_structural_audit_v1",
        "sealed_outcome_columns_loaded": False,
        "panel_sha256": sha(V12 / "deep_panel.csv.gz"),
        "rows": len(panel), "decision_dates": len(coverage), "profiles": 9,
        "source_dates": len(source), "source_rows_structurally_identical_to_v11": len(a),
        "reconstructed_dates": len(checkpoints),
        "reconstructed_rows": len(panel) - len(a),
        "duplicate_keys": 0, "invalid_maturity_rows": 0,
        "earliest_decision": min(summary["all_dates"]), "latest_decision": max(summary["all_dates"]),
        "status_counts": panel.status.value_counts().astype(int).to_dict(),
        "sealed_final_structural_rows": panel.loc[panel.decision_date.isin(FINAL)].groupby("decision_date").size().astype(int).to_dict(),
        "overlap_pairs": 212, "total_date_pairs": 1225,
        "provider_ledger_sha256": provider["ledger_sha256"],
        "provider_audit_sha256": provider["audit_sha256"],
        "checkpoint_hashes_verified": len(checkpoints),
        "action_ledger_sha256": sha(official),
    }
    (V12 / "integrity_audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    run()
