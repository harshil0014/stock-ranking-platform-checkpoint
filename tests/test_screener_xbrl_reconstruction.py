from __future__ import annotations

import pandas as pd
import pytest

from stock_ranker.screener_xbrl_reconstruction import (
    audit_xbrl_component_alignment,
    reconstruct_screener_methodology_from_xbrl,
)


def _facts(*, include_prior: bool = True) -> pd.DataFrame:
    rows = []
    periods = [("2025-03-31", "2025-06-01T00:00:00Z", 80.0)]
    if include_prior:
        periods.insert(0, ("2024-03-31", "2024-06-01T00:00:00Z", 60.0))
    for period, available, pat in periods:
        filing = period[:4]
        for concept, value, period_type in (
            ("pbt", pat + 20, "ANNUAL"),
            ("finance_costs", 10, "ANNUAL"),
            ("pat", pat, "ANNUAL"),
            ("equity_share_capital", 100, "INSTANT"),
            ("unknown:OtherEquity", 900, "INSTANT"),
            ("unknown:BorrowingsCurrent", 120, "INSTANT"),
            ("unknown:BorrowingsNoncurrent", 80, "INSTANT"),
        ):
            rows.append({
                "ticker": "EXACT", "isin": "INE123A01010",
                "statement_basis": "STANDALONE", "period_type": period_type,
                "period_end": period, "available_at": available,
                "filing_id": filing, "canonical_concept": concept,
                "value": value * 10_000_000, "unit": "INR",
                "source_url": f"https://nse.example/{filing}.xml",
                "source_sha256": filing.zfill(64),
            })
    return pd.DataFrame(rows)


def test_complete_official_period_pair_applies_exact_screener_formula() -> None:
    result = reconstruct_screener_methodology_from_xbrl(_facts())
    assert len(result.candidates) == 1
    row = result.candidates.iloc[0]
    assert row["period_end"] == pd.Timestamp("2025-03-31", tz="UTC")
    assert row["current_pat"] == 80
    assert row["prior_pat"] == 60
    assert row["debt_to_equity"] == pytest.approx(200 / 1000)
    assert row["roce"] == pytest.approx((100 + 10) * 2 / 2400)
    assert row["promotion_status"] == "CANDIDATE_REQUIRES_CALIBRATION"


def test_missing_comparative_period_fails_closed() -> None:
    result = reconstruct_screener_methodology_from_xbrl(_facts(include_prior=False))
    assert result.candidates.empty
    assert result.rejected.iloc[0]["status"] == "MISSING_PRIOR_ANNUAL_XBRL_COMPONENTS"


def test_does_not_mix_reporting_basis_or_ambiguous_values() -> None:
    facts = _facts()
    duplicate = facts.iloc[[2]].copy()  # prior PAT, which is required by the later period
    duplicate["value"] = duplicate["value"] + 1
    facts = pd.concat([facts, duplicate], ignore_index=True)
    consolidated = _facts()
    consolidated["statement_basis"] = "CONSOLIDATED"
    result = reconstruct_screener_methodology_from_xbrl(
        pd.concat([facts, consolidated], ignore_index=True)
    )
    # The prior period is ambiguous, so the later period has no defensible pair.
    assert result.candidates.empty
    assert "INCOMPLETE_CURRENT_XBRL_COMPONENTS" in set(result.rejected["status"])


def test_component_audit_exposes_vendor_line_mismatch_and_missing_prior() -> None:
    facts = _facts(include_prior=False)
    workbook = pd.DataFrame([{
        "ticker": "EXACT", "isin": "INE123A01010",
        "period_end": "2025-03-31", "prior_period_end": "2024-03-31",
        "current_pbt": 100, "current_interest": 10, "current_pat": 80,
        "current_equity_capital": 100, "current_reserves": 900,
        "current_borrowings": 250,
    }])
    audit = audit_xbrl_component_alignment(workbook, facts)
    assert audit.iloc[0]["pbt_matches_workbook_precision"]
    assert not audit.iloc[0]["borrowings_matches_workbook_precision"]
    assert audit.iloc[0]["borrowings_delta"] == -50
    assert not audit.iloc[0]["xbrl_prior_complete"]
