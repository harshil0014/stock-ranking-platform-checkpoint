from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("audit_final_data_quality", ROOT / "marketdata/runners/audit_final_data_quality.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_final_audit_rejects_incomplete_eligible_rows(monkeypatch, tmp_path: Path):
    frame = pd.DataFrame([{
        "ticker": "A", "isin": "INE000000001", "company": "A", "primary_exchange": "NSE",
        "latest_price": 10, "trade_date": "2026-08-21", "history_end_date": "2026-08-21",
        "product_baseline_eligible": True, "product_sector": "Sector",
        "product_baseline_yoy_growth": None, "product_baseline_cagr_3y": .1,
        "product_baseline_cagr_5y": .1, "product_baseline_days_since_recorded_high": 2,
        "product_baseline_score": 1, "product_baseline_sector_rank": 1,
        "promoter_holding_pct": 50, "public_holding_pct": 50, "fii_holding_pct": None,
        "dii_holding_pct": None, "promoter_pledge_pct": 0, "listing_date": "2020-01-01",
        "official_sector": "Sector", "professor_cohort": False,
        "product_classification_evidence": "OFFICIAL", "history_status": "OK",
        "annual_report_status": "OK", "shareholding_status": "OK",
        "product_baseline_reason_code": "ELIGIBLE",
    }])
    fake = type("Result", (), {"facts": frame, "manifest": {"fingerprint": "f", "market_fingerprint": "m", "trade_date": "2026-08-21"}})()
    monkeypatch.setattr(MODULE, "resolve_company_fact_snapshot", lambda value: tmp_path)
    monkeypatch.setattr(MODULE, "load_company_fact_snapshot", lambda value: fake)
    report = MODULE.audit(tmp_path)
    assert report["status"] == "FAIL"
    assert "INCOMPLETE_PRODUCT_BASELINE_ROW" in report["failures"]
