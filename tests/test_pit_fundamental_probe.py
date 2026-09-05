from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from marketdata.runners.acquire_nse_annual_reports import select_annual_report
from stock_ranker.pit_fundamental_probe import (
    PITFundamentalProbeConfig,
    assess_annual_report_probe,
    select_probe_cohort,
    summarize_structured_fact_coverage,
)


def _facts(count: int = 55) -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": [f"T{i:03d}" for i in range(count)],
        "company": [f"Company {i}" for i in range(count)],
        "isin": [f"INE{i:09d}" for i in range(count)],
        "primary_exchange": ["NSE"] * count,
        "product_sector": ["Sector A" if i % 2 else "Sector B" for i in range(count)],
        "product_baseline_eligible": [True] * count,
        "v2_eligible": [False] * count,
    })


def test_probe_cohort_is_exact_identity_deterministic_and_does_not_mutate() -> None:
    data = _facts()
    original = data.copy(deep=True)
    first = select_probe_cohort(data, 50)
    second = select_probe_cohort(data.sample(frac=1, random_state=7), 50)
    pd.testing.assert_frame_equal(first, second)
    pd.testing.assert_frame_equal(data, original)
    assert first["isin"].str.fullmatch(r"INE[A-Z0-9]{9}").all()
    assert first["ticker"].is_unique and first["isin"].is_unique


def test_probe_configuration_rejects_out_of_scope_sizes() -> None:
    with pytest.raises(ValueError, match="between 50 and 100"):
        PITFundamentalProbeConfig(sample_size=49)


def test_annual_report_selection_supports_probe_year_without_changing_default() -> None:
    cutoff = pd.Timestamp("2026-08-21T23:59:59+05:30").to_pydatetime()
    row = {
        "fromYr": "2024", "toYr": "2025",
        "disseminationDateTime": "01-AUG-2026 10:00:00",
        "fileName": "https://nsearchives.nseindia.com/annual_reports/example.pdf",
    }
    assert select_annual_report([row], cutoff)[1] == "NO_ELIGIBLE_ANNUAL_REPORT"
    assert select_annual_report(
        [row], cutoff, from_year="2024", to_year="2025"
    )[1] == "SELECTED"


def test_structured_facts_are_point_in_time_and_exact_concept_only() -> None:
    cohort = select_probe_cohort(_facts(50), 50)
    ticker = cohort.iloc[0]["ticker"]
    rows = []
    for concept, canonical in (
        ("ReturnOnCapitalEmployed", "unknown:ReturnOnCapitalEmployed"),
        ("DebtEquityRatio", "unknown:DebtEquityRatio"),
        ("ProfitLossForPeriod", "pat"),
    ):
        rows.append({
            "ticker": ticker, "statement_basis": "STANDALONE", "period_type": "ANNUAL",
            "period_end": "2026-03-31", "available_at": "2026-06-01T10:00:00+00:00",
            "canonical_concept": canonical, "source_concept": concept, "value": "1",
        })
    rows.append({
        "ticker": cohort.iloc[1]["ticker"], "statement_basis": "STANDALONE",
        "period_type": "ANNUAL", "period_end": "2026-03-31",
        "available_at": "2026-08-22T10:00:00+00:00", "canonical_concept": "pat",
        "source_concept": "ReturnOnCapitalEmployed", "value": "1",
    })
    summary = summarize_structured_fact_coverage(pd.DataFrame(rows), cohort, "2026-08-21")
    assert summary["complete_required_concept_count"] == 1
    assert summary["complete_required_tickers"] == [ticker]


def test_candidates_are_not_silently_accepted(tmp_path: Path) -> None:
    cohort = select_probe_cohort(_facts(50), 50)
    acquisition = tmp_path / "acquisition"
    audit = tmp_path / "audit"
    (audit / "text").mkdir(parents=True)
    acquisition.mkdir()
    provenance = []
    audits = []
    for row in cohort.to_dict("records"):
        ticker = row["ticker"]
        (audit / "text" / f"{ticker}.txt").write_text(
            f"ISIN {row['isin']} Return on Capital Employed Debt Equity Ratio Profit after tax",
            encoding="utf-8",
        )
        provenance.append({
            "ticker": ticker, "selection_status": "SELECTED",
            "selected_metadata": {"disseminationDateTime": "01-AUG-2026 10:00:00"},
            "source_url": "https://nsearchives.nseindia.com/annual_reports/example.pdf",
            "pdf_sha256": "a" * 64,
        })
        audits.append({
            "ticker": ticker, "audit_status": "EXTRACTED",
            "text_path": f"text/{ticker}.txt", "roce_candidate_page_count": 1,
            "debt_equity_candidate_page_count": 1, "profit_candidate_page_count": 1,
        })
    (acquisition / "annual_report_provenance.json").write_text(json.dumps(provenance), encoding="utf-8")
    (audit / "candidate_audit.json").write_text(json.dumps(audits), encoding="utf-8")
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({
        "fundamental_data_contract_version": "nse_audited_standalone_fundamentals_v1",
        "accepted": [],
    }), encoding="utf-8")
    rows, summary = assess_annual_report_probe(cohort, acquisition, audit, mapping)
    assert rows["direct_disclosure_candidate_complete"].all()
    assert not rows["reviewed_complete_pit_safe"].any()
    assert summary["complete_direct_disclosure_candidate_count"] == 50
    assert summary["reviewed_complete_pit_safe_count"] == 0
    assert not summary["scale_gate_passed"]


def test_reviewed_mapping_requires_standalone_complete_fields(tmp_path: Path) -> None:
    cohort = select_probe_cohort(_facts(50), 50)
    chosen = cohort.iloc[0]
    acquisition = tmp_path / "acquisition"
    audit = tmp_path / "audit"
    (audit / "text").mkdir(parents=True)
    acquisition.mkdir()
    (audit / "text" / f"{chosen.ticker}.txt").write_text(
        str(chosen["isin"]), encoding="utf-8"
    )
    provenance = [{"ticker": ticker, "selection_status": "NO_ELIGIBLE_ANNUAL_REPORT"}
                  for ticker in cohort["ticker"]]
    audits = [{"ticker": ticker, "audit_status": "NO_ELIGIBLE_ANNUAL_REPORT"}
              for ticker in cohort["ticker"]]
    provenance[0] = {
        "ticker": chosen.ticker, "selection_status": "SELECTED",
        "selected_metadata": {
            "disseminationDateTime": "01-AUG-2026 10:00:00",
            "fromYr": "2025", "toYr": "2026",
        },
    }
    audits[0] = {
        "ticker": chosen.ticker, "audit_status": "EXTRACTED",
        "text_path": f"text/{chosen.ticker}.txt", "roce_candidate_page_count": 1,
        "debt_equity_candidate_page_count": 1, "profit_candidate_page_count": 1,
    }
    (acquisition / "annual_report_provenance.json").write_text(json.dumps(provenance), encoding="utf-8")
    (audit / "candidate_audit.json").write_text(json.dumps(audits), encoding="utf-8")
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({
        "fundamental_data_contract_version": "nse_audited_standalone_fundamentals_v1",
        "accepted": [{
            "ticker": chosen.ticker, "reporting_basis": "STANDALONE",
            "financial_year": "2025-26",
            "roce": {"classification": "DIRECT_DISCLOSURE", "canonical_decimal": 0.1},
            "debt_to_equity": {
                "classification": "DIRECT_DISCLOSURE", "canonical_decimal": 0.2,
            },
            "profit": {
                "classification": "DIRECT_DISCLOSURE", "current_value": 2,
                "prior_value": 1,
            },
        }],
    }), encoding="utf-8")
    rows, summary = assess_annual_report_probe(cohort, acquisition, audit, mapping)
    assert rows.loc[rows.ticker.eq(chosen.ticker), "final_probe_status"].item() == "REVIEWED_COMPLETE_PIT_SAFE"
    assert summary["reviewed_complete_pit_safe_count"] == 1
