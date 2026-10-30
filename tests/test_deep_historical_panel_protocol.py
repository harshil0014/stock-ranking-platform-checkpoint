from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_deep_panel_declares_matured_nonduplicated_additions_and_provenance_gate():
    source = (ROOT / "research/runners/build_deep_personalized_panel_20261002.py").read_text(encoding="utf-8")
    for date in (
        "2020-03-31", "2020-09-30", "2021-03-31", "2021-09-30",
        "2022-03-31", "2022-09-30", "2023-03-31", "2023-09-30",
        "2024-03-31", "2024-09-30", "2025-03-31", "2025-06-30",
    ):
        assert source.count(date) >= 1
    assert "endpoint.gt(CUTOFF).any()" in source
    assert "decision_strictly_before_endpoint" in source
    assert "added_rows_use_current_facts\": False" in source
    assert "verify_provider_ledger" in source
    assert "raw_response_integrity_verified" in source
    assert "provider_split_ledger_is_observed\": True" in source


def test_deep_panel_keeps_overlap_as_an_audited_statistic():
    source = (ROOT / "research/runners/build_deep_personalized_panel_20261002.py").read_text(encoding="utf-8")
    assert "outcome_window_overlap.csv" in source
    assert "horizon_overlap_fraction" in source
