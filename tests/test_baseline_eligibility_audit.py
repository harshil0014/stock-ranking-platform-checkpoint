import pandas as pd

from stock_ranker.baseline_eligibility_audit import audit_baseline_eligibility


def test_reconciles_strict_temporal_change_and_expanded_product_cohort():
    old = pd.DataFrame([
        {"ticker": "A", "baseline_eligible": True, "baseline_reason_code": "ELIGIBLE"},
        {"ticker": "B", "baseline_eligible": True, "baseline_reason_code": "ELIGIBLE"},
    ])
    new = pd.DataFrame([
        {"ticker": "A", "baseline_eligible": True, "baseline_reason_code": "ELIGIBLE"},
        {"ticker": "B", "baseline_eligible": False, "baseline_reason_code": "CURRENT_PRICE_MISMATCH"},
    ])
    facts = pd.DataFrame([
        {"ticker": "A", "product_baseline_eligible": True, "product_baseline_reason_code": "ELIGIBLE", "product_classification_evidence": "OFFICIAL"},
        {"ticker": "B", "product_baseline_eligible": True, "product_baseline_reason_code": "ELIGIBLE", "product_classification_evidence": "OFFICIAL"},
        {"ticker": "C", "product_baseline_eligible": True, "product_baseline_reason_code": "ELIGIBLE", "product_classification_evidence": "EXACT_IDENTITY_SECONDARY_REFERENCE"},
    ])
    detail, summary = audit_baseline_eligibility(old, new, facts)
    assert summary["earlier_strict_eligible"] == 2
    assert summary["current_strict_eligible"] == 1
    assert summary["current_product_eligible"] == 3
    assert summary["lost_reason_counts"] == {"CURRENT_PRICE_MISMATCH": 1}
    assert set(detail.loc[detail.current_product_eligible, "ticker"]) == {"A", "B", "C"}


def test_rejects_duplicate_security_identity():
    live = pd.DataFrame([
        {"ticker": "A", "baseline_eligible": True, "baseline_reason_code": "ELIGIBLE"},
        {"ticker": "A", "baseline_eligible": True, "baseline_reason_code": "ELIGIBLE"},
    ])
    facts = pd.DataFrame([{
        "ticker": "A", "product_baseline_eligible": True,
        "product_baseline_reason_code": "ELIGIBLE", "product_classification_evidence": "OFFICIAL",
    }])
    try:
        audit_baseline_eligibility(live, live.iloc[:1], facts)
    except ValueError as exc:
        assert "duplicate tickers" in str(exc)
    else:
        raise AssertionError("duplicate ticker accepted")
