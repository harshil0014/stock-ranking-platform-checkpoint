import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_deeper_protocol_has_disjoint_50_date_partition_and_new_final_block():
    p = json.loads((ROOT / "research/protocols/personalized_deeper_walkforward_v2.json").read_text())
    groups = [
        p["initial_history_dates"],
        p["development_selection_dates"],
        p["postlock_2024_diagnostics"],
        p["untouched_final_dates"],
        p["postfinal_2025_diagnostics"],
    ]
    flat = [d for group in groups for d in group]
    assert len(flat) == 50
    assert len(set(flat)) == 50
    assert min(flat) == "2015-01-31"
    assert p["panel"].endswith("real-panel-v12/deep_panel.csv.gz")
    assert p["untouched_final_dates"] == ["2025-01-31", "2025-08-31"]
    assert max(p["development_selection_dates"]) == "2023-12-31"


def test_deeper_runner_seals_all_postselection_labels_before_lock():
    source = (ROOT / "research/runners/personalized_deeper_championship_v2.py").read_text()
    assert 'p["postlock_2024_diagnostics"]' in source
    assert 'p["untouched_final_dates"]' in source
    assert 'p["postfinal_2025_diagnostics"]' in source
    assert 'panel.loc[sealed, ["future_xirr", "future_shortfall", "future_drawdown"]] = np.nan' in source
    assert '"selection_uses_untouched_final": False' in source
    assert '"development_tournament_sha256"' in source


def test_deeper_selection_penalizes_worst_date_failures_and_excludes_mean_xirr():
    source = (ROOT / "research/runners/personalized_deeper_championship_v2.py").read_text()
    assert "worst_date_shortfall_delta" in source
    assert "worst_date_achievement_delta" in source
    assert "worst_date_median_xirr_delta" in source
    assert "worst_date_drawdown_delta" in source
    section = source[source.index("def metric_deltas"):source.index("def development")]
    assert "mean_xirr_top20" not in section


def test_deeper_tournament_is_two_stage_and_broad():
    source = (ROOT / "research/runners/personalized_deeper_championship_v2.py").read_text()
    assert 'labels = ("utility4", "xirr4", "xirr8")' in source
    assert 'pnames = ("top20", "regularized", "frozen")' in source
    assert '"risk_no_3y"' in source
    assert "qualification_config_leaders.csv" in source
    assert "finalist_keys = leaders.head(10)" in source
