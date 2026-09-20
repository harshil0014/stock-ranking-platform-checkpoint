from pathlib import Path

from marketdata.runners.audit_completed_universe import run


ROOT = Path(__file__).resolve().parents[1]


def test_final_completion_audit_uses_only_pre_frozen_ordering(tmp_path: Path) -> None:
    summary = run(
        ROOT / "data/analysis/complete_universe_20260918_run_05",
        ROOT / "data/analysis/codex_complete_universe_audit_20260918_run_06",
        tmp_path / "audit",
    )
    assert summary["universe_count"] == 4436
    assert summary["ranked_count"] == 4436
    assert summary["stock_by_stock_audit_count"] == 4436
    assert summary["frozen_order_auditable_count"] == 3987
    assert summary["reviewed_without_pre_frozen_order_count"] == 449
    assert summary["benchmark_frozen_before_final_completion"] is True
    assert summary["post_hoc_judgments_added"] is False
    assert summary["pairwise_agreement"] == 0.9501581944737397
    assert summary["agreement_target_met"] is True
    assert summary["all_stocks_reviewed"] is True
