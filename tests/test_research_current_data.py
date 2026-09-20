from pathlib import Path

import json
import pytest

from stock_research.current_data import load_accepted_current_evidence
from stock_research.errors import ResearchValidationError
from stock_research.platform import validate_feature_evidence


ROOT = Path(__file__).parents[1]


def test_accepted_current_bridge_preserves_fingerprint_and_cannot_become_history():
    state_root = ROOT / "data/company_facts"
    state = json.loads((state_root / "accepted_state.json").read_text(encoding="utf-8"))
    evidence = load_accepted_current_evidence(state_root)
    assert not evidence.empty
    assert set(evidence.availability_status) == {"current_only"}
    assert set(evidence.evidence_fingerprint) == {state["fingerprint"]}
    assert {"return_1y", "cagr_3y", "cagr_5y", "roce", "debt_to_equity", "profit_growth_yoy"} <= set(evidence.feature)
    assert {
        "market_pe", "operating_margin_pct", "free_cash_flow_crore",
        "promoter_holding_pct", "quarterly_profit_growth_pct",
        "current_roce_pct", "current_debt_to_equity", "current_pat_crore",
    } <= set(evidence.feature)
    broad = evidence.loc[evidence.feature.eq("current_roce_pct")]
    assert len(broad) > len(evidence.loc[evidence.feature.eq("roce")])
    assert set(broad.source_id) == {"accepted_screener_exact_isin_current"}
    with pytest.raises(ResearchValidationError, match="current_only_historical_leakage"):
        validate_feature_evidence(evidence, mode="historical_evaluation")
