from datetime import date

import pandas as pd
import pytest

from stock_ranker.pit_structured_fundamentals import bridge_structured_fundamentals


def _structured(**changes):
    row = {
        "isin": "INE000A01001", "period_end": "2024-03-31", "reporting_basis": "STANDALONE",
        "roce": .15, "debt_to_equity": .4, "current_pat": 120, "prior_pat": 100,
        "source_observed_at": "2024-06-01T10:00:00+05:30", "source_name": "structured-reference",
        "source_record_id": "record-1", "evidence_mode": "CONTEMPORANEOUS_ARCHIVED_EXPORT",
        "filing_value_match_sha256": "",
    }
    row.update(changes)
    return pd.DataFrame([row])


def _filing(**changes):
    row = {
        "isin": "INE000A01001", "period_end": "2024-03-31", "reporting_basis": "STANDALONE",
        "official_available_at": "2024-05-30T18:00:00+05:30", "filing_id": "NSE-1",
        "filing_url": "https://example.invalid/official.pdf", "filing_sha256": "a" * 64,
    }
    row.update(changes)
    return pd.DataFrame([row])


def test_exact_identity_period_basis_and_pre_cutoff_observation_are_admitted():
    result = bridge_structured_fundamentals(_structured(), _filing(), ranking_date=date(2024, 8, 7))
    assert result.accepted["isin"].tolist() == ["INE000A01001"]
    assert result.rejected.empty


def test_current_screener_export_is_not_backdated_to_old_official_filing():
    result = bridge_structured_fundamentals(
        _structured(source_observed_at="2026-08-29T10:00:00+05:30"),
        _filing(), ranking_date=date(2024, 8, 7),
    )
    assert result.accepted.empty
    assert result.rejected["bridge_status"].tolist() == ["STRUCTURED_EXPORT_OBSERVED_AFTER_RANKING_DATE"]


def test_later_export_can_be_used_only_after_exact_original_filing_match():
    result = bridge_structured_fundamentals(
        _structured(
            source_observed_at="2026-08-29T10:00:00+05:30",
            evidence_mode="EXACT_ORIGINAL_FILING_MATCH",
            filing_value_match_sha256="b" * 64,
        ),
        _filing(), ranking_date=date(2024, 8, 7),
    )
    assert len(result.accepted) == 1


def test_exact_match_mode_requires_evidence_hash_and_no_identity_substitution():
    missing_evidence = bridge_structured_fundamentals(
        _structured(evidence_mode="EXACT_ORIGINAL_FILING_MATCH"), _filing(), ranking_date=date(2024, 8, 7)
    )
    assert missing_evidence.rejected["bridge_status"].tolist() == ["MISSING_ORIGINAL_FILING_VALUE_MATCH"]
    mismatch = bridge_structured_fundamentals(
        _structured(isin="INE999A01001"), _filing(), ranking_date=date(2024, 8, 7)
    )
    assert mismatch.rejected["bridge_status"].tolist() == ["NO_EXACT_OFFICIAL_FILING_MATCH"]


def test_duplicate_natural_keys_and_bad_values_are_rejected():
    with pytest.raises(ValueError, match="duplicate structured natural keys"):
        bridge_structured_fundamentals(pd.concat([_structured(), _structured()]), _filing(), ranking_date=date(2024, 8, 7))
    with pytest.raises(ValueError, match="roce: invalid numeric"):
        bridge_structured_fundamentals(_structured(roce=float("nan")), _filing(), ranking_date=date(2024, 8, 7))

