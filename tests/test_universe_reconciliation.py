from pathlib import Path

import pandas as pd

from stock_ranker.universe_reconciliation import reconcile_universes, write_reconciliation


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ROOT / "data/live_market/snapshots/2026-09-15-ceaec46dc1455c358441429bd525af9bba62f42a41af23ce96dd1c2ea9beb0ee/live_market.csv"
FINAL = ROOT / "data/live_market/snapshots/2026-09-18-98adc0296bff77fd44fc4c6815692a86033b14763d689791df14752550983eb1/live_market.csv"


def test_historical_and_final_universes_reconcile_without_silent_exclusions(tmp_path: Path) -> None:
    result = reconcile_universes(
        pd.read_csv(HISTORICAL, low_memory=False),
        pd.read_csv(FINAL, low_memory=False),
    )
    assert result.summary["historical_count"] == 4549
    assert result.summary["final_count"] == 4436
    assert result.summary["exact_retained_count"] == 4308
    assert result.summary["superseded_identity_count"] == 1
    assert result.summary["excluded_historical_count"] == 240
    assert result.summary["final_addition_count"] == 128
    assert result.summary["new_final_identity_count"] == 127
    assert result.summary["missing_disposition_count"] == 0
    assert result.summary["historical_counts_reconcile"] is True
    assert result.summary["final_counts_reconcile"] is True
    written = write_reconciliation(result, tmp_path / "reconciliation")
    assert written["fingerprint"]
