from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pandas as pd
import pytest

from marketdata.runners.acquire_walk_forward_blind import SNAPSHOTS, _select_report
from marketdata.runners.adjudicate_walk_forward_fundamentals import (
    DEBT_EQUITY,
    ROCE,
    identify_statement_ranges,
    split_pages,
)
from marketdata.runners.finalize_walk_forward_adjudication import NONCOMPARABLE_PERIODS
from marketdata.runners.rescue_walk_forward_nse_availability import classify_announcement
from marketdata.runners.audit_walk_forward_integrity import cohort_summary
from stock_ranker.walk_forward_blind import (
    PROTOCOL_SHA256,
    apply_historical_sector_mapping,
    assert_outcome_blind,
    cutoff_rebased_prices,
    parse_mcwb_archive,
    protocol_fingerprint,
    provider_identity,
    provider_request_window,
    repair_sensitivity,
    validate_blind_snapshot_directory,
    _fundamentals_from_mapping,
    _baseline_from_prices,
)


ROOT = Path(__file__).resolve().parents[1]


def _mcwb_zip(rows: list[str]) -> tuple[bytes, str]:
    csv_bytes = (
        "Annexure II- Nifty 50 Index,,,,\n,,,,\n"
        "Sr. No,Security Symbol,Security Name,Industry\n"
        + "\n".join(rows)
        + "\n"
    ).encode()
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("nifty50_mcwb.csv", csv_bytes)
    return stream.getvalue(), sha256(csv_bytes).hexdigest()


def test_frozen_protocol_hash_is_unchanged() -> None:
    assert protocol_fingerprint(
        ROOT / "experiments/walk_forward/protocol_v1.json"
    ) == PROTOCOL_SHA256


def test_all_official_mcwb_hashes_are_frozen() -> None:
    assert [row["zip_sha256"] for row in SNAPSHOTS] == [
        "af2bb20cc901eaaa4694f102dc4cd62517397092660bf000b4f03029764e291a",
        "ce8a335221f222def0ee68b5d2aa6e2cdf500ec171e9c3d100df01a8a4545ac4",
        "5a89a9e0fd709a1b310f03be4b8a4bc8f36c6982a4e83a8746c88af084b700ba",
        "0244f8ac658343e07c045eb390f6ac6e42cefc45540a5badcefefdcd284201f4",
    ]
    assert [row["csv_sha256"] for row in SNAPSHOTS] == [
        "85032a234edeb1adb8fbc1bf233b04151a03467961b64c852cb3bd1b53befd65",
        "aa6ecd85791511aef647a546dfaf7db9b956f10c60ae331885e5855e657debbf",
        "b8bb21128768ee8beb74d5fc9072818900e81a8aa7a11787c9990c72baf694b6",
        "2f4b9ae31c1f840bf15a8f452c77a0d2fc21fc409d2cee03e0851694d903eafd",
    ]


def test_mcwb_parser_preserves_historical_sector_and_excludes_dummyrel(
    tmp_path: Path,
) -> None:
    content, csv_hash = _mcwb_zip([
        "1,AAA,Alpha Ltd.,HISTORICAL INDUSTRY",
        "2,DUMMYREL,DUMMY - JIO FINANCIAL SERVICES LTD.,NBFC",
    ])
    path = tmp_path / "mcwb.zip"
    path.write_bytes(content)
    parsed = parse_mcwb_archive(
        path, expected_zip_sha256=sha256(content).hexdigest(),
        expected_csv_sha256=csv_hash,
    )
    assert parsed.loc[0, "historical_industry"] == "HISTORICAL INDUSTRY"
    dummy = parsed.loc[parsed["historical_symbol"].eq("DUMMYREL")].iloc[0]
    assert dummy["source_status"] == "SYNTHETIC_CORPORATE_ACTION_PLACEHOLDER"
    assert not bool(dummy["investable"])


def test_mcwb_parser_rejects_hash_drift(tmp_path: Path) -> None:
    content, csv_hash = _mcwb_zip(["1,AAA,Alpha Ltd.,Industry"])
    path = tmp_path / "mcwb.zip"
    path.write_bytes(content)
    with pytest.raises(ValueError, match="ZIP hash mismatch"):
        parse_mcwb_archive(path, expected_zip_sha256="0" * 64, expected_csv_sha256=csv_hash)


def test_identity_uses_exact_symbol_and_forbids_successor_substitution() -> None:
    universe = pd.DataFrame([
        {"historical_symbol": "HDFC", "company": "Housing Development Finance Corporation Ltd.",
         "historical_industry": "HOUSING FINANCE", "historical_sector": "Financial Services",
         "official_sector_code": "IN0501", "classification_document_id": "official", "investable": True},
        {"historical_symbol": "DUMMYREL", "company": "DUMMY", "historical_industry": "NBFC",
         "historical_sector": "Financial Services", "official_sector_code": "IN0501",
         "classification_document_id": "official", "investable": False},
    ])
    identity = provider_identity(universe)
    assert identity.loc[identity["historical_symbol"].eq("HDFC"), "provider_symbol"].iat[0] == "HDFC.NS"
    assert pd.isna(identity.loc[identity["historical_symbol"].eq("DUMMYREL"), "provider_symbol"].iat[0])
    with pytest.raises(ValueError, match="must not be substituted"):
        provider_identity(universe, {"HDFC": "HDFCBANK.NS"})


def test_provider_request_is_cutoff_bounded_with_exclusive_end() -> None:
    assert provider_request_window("2023-08-07") == {
        "start_inclusive": "1900-01-01",
        "end_exclusive": "2023-08-08",
        "maximum_allowed_observation": "2023-08-07",
    }


def test_pit_rebase_equals_raw_close_at_cutoff_and_preserves_actions() -> None:
    frame = pd.DataFrame([
        {"ticker": "AAA", "provider_symbol": "AAA.NS", "date": "2023-08-04",
         "close": 90.0, "adj_close": 81.0, "dividends": 1.0,
         "stock_splits": 0.0, "repaired": True},
        {"ticker": "AAA", "provider_symbol": "AAA.NS", "date": "2023-08-07",
         "close": 100.0, "adj_close": 90.0, "dividends": 0.0,
         "stock_splits": 2.0, "repaired": True},
    ])
    result = cutoff_rebased_prices(frame, "2023-08-07")
    assert result.iloc[-1]["pit_adjusted_price"] == pytest.approx(100.0, abs=1e-10)
    assert result.iloc[0]["pit_adjusted_price"] == pytest.approx(90.0)
    assert result.iloc[0]["dividends"] == 1.0
    assert result.iloc[-1]["stock_splits"] == 2.0


def test_post_cutoff_price_is_rejected_before_feature_use() -> None:
    frame = pd.DataFrame([
        {"ticker": "AAA", "provider_symbol": "AAA.NS", "date": "2023-08-08",
         "close": 100.0, "adj_close": 100.0, "dividends": 0.0,
         "stock_splits": 0.0, "repaired": True},
    ])
    with pytest.raises(ValueError, match="BLINDNESS_VIOLATION"):
        cutoff_rebased_prices(frame, "2023-08-07")


@pytest.mark.parametrize("column", [
    "future_return", "forward_return", "label", "label_end_date", "rank_ic",
    "pairwise_accuracy", "realized_return", "spread_return", "winner",
])
def test_outcome_fields_are_forbidden(column: str) -> None:
    with pytest.raises(ValueError, match="OUTCOME_FIELD_FORBIDDEN"):
        assert_outcome_blind(pd.DataFrame({column: [0.0]}))


def test_required_fiscal_year_does_not_fall_back_and_availability_is_strict() -> None:
    cutoff = pd.Timestamp("2023-08-07T15:30:00+05:30").to_pydatetime()
    rows = [
        {"fromYr": "2021", "toYr": "2022", "disseminationDateTime": "01-Jul-2022 10:00:00", "fileName": "https://example/old.pdf"},
        {"fromYr": "2022", "toYr": "2023", "disseminationDateTime": "07-Aug-2023 15:31:00", "fileName": "https://example/post.pdf"},
    ]
    selected, status, counts = _select_report(rows, "2022-23", cutoff)
    assert selected is None
    assert status == "POST_CUTOFF_ANNUAL_REPORT"
    assert counts["post_cutoff_count"] == 1


def test_missing_dissemination_is_unverified_not_inferred() -> None:
    cutoff = pd.Timestamp("2023-08-07T15:30:00+05:30").to_pydatetime()
    selected, status, _ = _select_report([
        {"fromYr": "2022", "toYr": "2023", "disseminationDateTime": "-", "fileName": "https://example/report.pdf"}
    ], "2022-23", cutoff)
    assert selected is None
    assert status == "UNVERIFIED_FILING_AVAILABILITY"


def _announcement(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "symbol": "AAA", "sm_name": "Alpha Limited", "desc": "General updates",
        "attchmntText": "Alpha Limited has submitted its Annual Report for FY 2022-23.",
        "attchmntFile": "https://nsearchives.nseindia.com/corporate/AAA_AnnualReport_2022_23.pdf",
        "an_dt": "07-Aug-2023 15:00:00", "exchdisstime": "07-Aug-2023 15:00:05",
        "seq_id": "1",
    }
    row.update(overrides)
    return row


def test_official_nse_exact_report_can_rescue_blank_archive_timestamp() -> None:
    status, _ = classify_announcement(
        _announcement(), ticker="AAA", required_fy="2022-23",
        cutoff=pd.Timestamp("2023-08-07T15:30:00+05:30").to_pydatetime(),
    )
    assert status == "RESCUED_EXACT_NSE_DISSEMINATION"


@pytest.mark.parametrize("overrides, expected", [
    ({"attchmntFile": "https://example.com/AAA_AnnualReport_2022_23.pdf"}, "NOT_RESCUED_AMBIGUOUS_ATTACHMENT"),
    ({"exchdisstime": "07-Aug-2023 15:30:01"}, "NOT_RESCUED_POST_CUTOFF"),
    ({"exchdisstime": None}, "NOT_RESCUED_NO_EXACT_EVIDENCE"),
    ({"desc": "Copy of Newspaper Publication"}, "NOT_RESCUED_AMBIGUOUS_ATTACHMENT"),
    ({"attchmntText": "Annual Report for FY 2021-22", "attchmntFile": "https://nsearchives.nseindia.com/corporate/AAA_AnnualReport_2021_22.pdf"}, "NOT_RESCUED_AMBIGUOUS_ATTACHMENT"),
])
def test_rescue_rejects_unofficial_post_cutoff_broadcast_only_broad_or_wrong_fy(
    overrides: dict[str, object], expected: str,
) -> None:
    status, _ = classify_announcement(
        _announcement(**overrides), ticker="AAA", required_fy="2022-23",
        cutoff=pd.Timestamp("2023-08-07T15:30:00+05:30").to_pydatetime(),
    )
    assert status == expected


def test_company_website_date_and_ambiguous_attachment_cannot_rescue() -> None:
    status, _ = classify_announcement(
        _announcement(
            attchmntText="Annual Report 2022-23 is available on the company website.",
            attchmntFile="https://nsearchives.nseindia.com/corporate/AGM_notice.pdf",
        ),
        ticker="AAA", required_fy="2022-23",
        cutoff=pd.Timestamp("2023-08-07T15:30:00+05:30").to_pydatetime(),
    )
    assert status == "NOT_RESCUED_AMBIGUOUS_ATTACHMENT"


def test_fiscal_year_wording_and_compact_annual_report_filename_are_exact() -> None:
    status, _ = classify_announcement(
        _announcement(
            attchmntText="Please find enclosed the Annual Report of the Bank for fiscal 2023.",
            attchmntFile="https://nsearchives.nseindia.com/corporate/AAA_AnnualReport2023.pdf",
        ),
        ticker="AAA", required_fy="2022-23",
        cutoff=pd.Timestamp("2023-08-07T15:30:00+05:30").to_pydatetime(),
    )
    assert status == "RESCUED_EXACT_NSE_DISSEMINATION"


def test_historical_mapping_contains_only_reviewed_standalone_acceptance() -> None:
    mapping = json.loads((
        ROOT / "marketdata/specifications/walk_forward_annual_report_mapping.json"
    ).read_text(encoding="utf-8"))
    assert mapping["contract_identifier"] == "nse_audited_standalone_fundamentals_v1"
    by_date = {snapshot["ranking_date"]: snapshot for snapshot in mapping["snapshots"]}
    expected = {
        "2022-08-05": ["CIPLA", "DRREDDY", "EICHERMOT", "HCLTECH", "HINDUNILVR", "TITAN", "UPL", "WIPRO"],
        "2023-08-07": ["GRASIM", "HCLTECH", "HEROMOTOCO", "M&M"],
        "2024-08-07": ["ADANIENT", "BHARTIARTL", "DRREDDY", "GRASIM", "M&M", "TECHM", "TITAN", "WIPRO"],
        "2025-08-07": ["ADANIENT", "ADANIPORTS", "ASIANPAINT", "BAJAJ-AUTO", "BHARTIARTL", "HCLTECH", "HEROMOTOCO", "HINDUNILVR", "JSWSTEEL", "M&M", "RELIANCE", "TATACONSUM", "TATASTEEL", "TCS", "TECHM", "TRENT"],
    }
    for ranking_date, fiscal_year in (("2022-08-05", "2021-22"), ("2023-08-07", "2022-23"), ("2024-08-07", "2023-24"), ("2025-08-07", "2024-25")):
        accepted = by_date[ranking_date]["accepted"]
        assert [row["ticker"] for row in accepted] == expected[ranking_date]
        for row in accepted:
            assert row["financial_year"] == fiscal_year
            assert row["reporting_basis"] == "STANDALONE"
            assert row["review_status"] == "ACCEPTED"
            assert len(row["pdf_sha256"]) == 64
            assert row["roce"]["classification"] == "DIRECT_DISCLOSURE"
            assert row["debt_to_equity"]["classification"] == "DIRECT_DISCLOSURE"
            assert row["profit"]["classification"] == "DIRECT_DISCLOSURE"
            assert row["profit"]["current_value"] != row["profit"]["prior_value"]
            assert row["profit"]["current_period_months"] == 12
            assert row["profit"]["prior_period_months"] == 12
            assert row["profit"]["comparison_status"] == "COMPARABLE_EXACT_ISSUER_PRIOR_YEAR"


def test_rescue_spec_preserves_null_archive_state_and_official_provenance() -> None:
    specification = json.loads((
        ROOT / "marketdata/specifications/walk_forward_nse_availability_rescue.json"
    ).read_text(encoding="utf-8"))
    assert specification["source_policy"] == "OFFICIAL_NSE_ONLY"
    assert specification["outcome_data_acquired"] is False
    assert [len(row["attempts"]) for row in specification["snapshots"]] == [41, 38]
    for snapshot in specification["snapshots"]:
        for attempt in snapshot["attempts"]:
            assert attempt["annual_report_archive_dissemination"] is None
            rescue = attempt["availability_rescue"]
            if rescue["evidence_status"] == "RESCUED_EXACT_NSE_DISSEMINATION":
                assert rescue["source"] == "NSE_CORPORATE_ANNOUNCEMENT"
                assert rescue["attachment_url"].startswith("https://nsearchives.nseindia.com/")
                assert len(rescue["attachment_sha256"]) == 64
                assert rescue["exchange_dissemination_timestamp"]


def test_rescued_profit_periods_are_exact_annual_pairs_without_fallback() -> None:
    mapping = json.loads((
        ROOT / "marketdata/specifications/walk_forward_annual_report_mapping.json"
    ).read_text(encoding="utf-8"))
    by_date = {row["ranking_date"]: row for row in mapping["snapshots"]}
    expected = {
        "2022-08-05": ("2021-04-01", "2022-03-31", "2020-04-01", "2021-03-31"),
        "2023-08-07": ("2022-04-01", "2023-03-31", "2021-04-01", "2022-03-31"),
    }
    for ranking_date, periods in expected.items():
        for row in by_date[ranking_date]["accepted"]:
            profit = row["profit"]
            assert (
                profit["current_period_start"], profit["current_period_end"],
                profit["prior_period_start"], profit["prior_period_end"],
            ) == periods
            assert profit["current_period_months"] == profit["prior_period_months"] == 12
            assert row["availability_rescue"]["annual_report_archive_dissemination"] is None


def test_nestle_noncomparable_period_is_not_annualized_or_accepted() -> None:
    mapping = json.loads((ROOT / "marketdata/specifications/walk_forward_annual_report_mapping.json").read_text(encoding="utf-8"))
    snapshot = next(row for row in mapping["snapshots"] if row["ranking_date"] == "2025-08-07")
    assert "NESTLEIND" not in {row["ticker"] for row in snapshot["accepted"]}
    period = NONCOMPARABLE_PERIODS[("2025-08-07", "NESTLEIND")]
    assert period["current_period_months"] == 12
    assert period["prior_period_months"] == 15
    assert period["comparison_status"] == "NONCOMPARABLE_PERIOD_LENGTH"
    assert period["annualization_applied"] is False


def test_techm_debt_equity_percentages_are_decimal_model_inputs() -> None:
    mapping = json.loads((ROOT / "marketdata/specifications/walk_forward_annual_report_mapping.json").read_text(encoding="utf-8"))
    by_date = {row["ranking_date"]: row for row in mapping["snapshots"]}
    values = {}
    for date in ("2024-08-07", "2025-08-07"):
        item = next(row for row in by_date[date]["accepted"] if row["ticker"] == "TECHM")
        values[date] = item["debt_to_equity"]["canonical_decimal"]
    assert values == {"2024-08-07": 0.0202, "2025-08-07": 0.0438}


def test_primary_feasibility_is_derived_from_actual_three_stock_cohort() -> None:
    signals = [
        {"ticker": ticker, "historical_sector": sector, "sector_rank": str(rank)}
        for ticker, sector, rank in (("A", "S1", 1), ("B", "S1", 2), ("C", "S1", 3), ("D", "S2", 1))
    ]
    matched = {
        row["ticker"]: {"matched_baseline_sector_rank": row["sector_rank"], "original_baseline_sector_rank": row["sector_rank"]}
        for row in signals
    }
    sectors, possible = cohort_summary(signals, matched)
    assert [row["ticker"] for row in sectors["S1"]] == ["A", "B", "C"]
    assert len(sectors["S2"]) == 1
    assert possible == 1


def test_standalone_section_range_excludes_consolidated_pages() -> None:
    dump = (
        "\n=== PDF PAGE 10 ===\nReport on the Audit of the Standalone Financial Statements"
        "\n=== PDF PAGE 11 ===\nReturn on Capital Employed 20%"
        "\n=== PDF PAGE 12 ===\nReport on the Audit of the Consolidated Financial Statements"
    )
    pages = split_pages(dump)
    assert identify_statement_ranges(pages) == {
        "standalone_start_page": 10,
        "standalone_end_page": 11,
        "consolidated_start_page": 12,
        "consolidated_end_page": 12,
    }


def test_wrapped_ratio_labels_are_discovered_without_formula_requirement() -> None:
    assert ROCE.search("Return on\nCapital Employed (%) 20.0%")
    assert DEBT_EQUITY.search("Debt -\nEquity Ratio 0.25")


def test_official_sector_mapping_is_exact_and_preserves_raw_industry() -> None:
    mapping = json.loads((
        ROOT / "marketdata/specifications/walk_forward_nse_sector_mapping.json"
    ).read_text(encoding="utf-8"))
    universe = pd.DataFrame([{
        "historical_symbol": "AAA", "company": "Alpha",
        "historical_industry": "PRIVATE SECTOR BANK", "investable": True,
    }])
    result = apply_historical_sector_mapping(universe, mapping, "2023-08-07")
    assert result.loc[0, "historical_industry"] == "PRIVATE SECTOR BANK"
    assert result.loc[0, "historical_sector"] == "Financial Services"
    assert result.loc[0, "official_sector_code"] == "IN0501"
    assert result.loc[0, "classification_document_id"].endswith("2023_07")


def test_official_sector_mapping_rejects_unresolved_value() -> None:
    mapping = json.loads((
        ROOT / "marketdata/specifications/walk_forward_nse_sector_mapping.json"
    ).read_text(encoding="utf-8"))
    universe = pd.DataFrame([{
        "historical_symbol": "AAA", "company": "Alpha",
        "historical_industry": "UNKNOWN INDUSTRY", "investable": True,
    }])
    with pytest.raises(ValueError, match="unresolved historical Industry"):
        apply_historical_sector_mapping(universe, mapping, "2023-08-07")


def test_sector_mapping_provenance_is_hash_pinned_and_complete() -> None:
    mapping = json.loads((
        ROOT / "marketdata/specifications/walk_forward_nse_sector_mapping.json"
    ).read_text(encoding="utf-8"))
    assert [item["sha256"] for item in mapping["classification_documents"]] == [
        "428e90ab2681a62d611362bb1d8a3bbb0d301c2a2ff198c9d1280ec2854ec21c",
        "8ae58cbd10d7dd5184d76cfec6486f91c019026c8de329432b69c54ff7235f8b",
    ]
    labels = [item["historical_industry"] for item in mapping["mappings"]]
    assert len(labels) == len(set(labels)) == 34
    assert all(item["official_sector_code"].startswith("IN") for item in mapping["mappings"])


def test_baseline_adapter_groups_on_official_sector_not_raw_industry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, pd.DataFrame] = {}

    def fake_prepare(universe: pd.DataFrame, *_args: object, **_kwargs: object) -> SimpleNamespace:
        captured["universe"] = universe
        return SimpleNamespace(
            baseline_input=pd.DataFrame(),
            eligibility=pd.DataFrame(columns=["eligible"]),
        )

    monkeypatch.setattr(
        "stock_ranker.walk_forward_blind.prepare_historical_baseline", fake_prepare
    )
    universe = pd.DataFrame([{
        "historical_symbol": "AAA", "company": "Alpha",
        "historical_industry": "PRIVATE SECTOR BANK",
        "historical_sector": "Financial Services", "investable": True,
    }])
    _baseline_from_prices(universe, pd.DataFrame(columns=["ticker"]), "2023-08-07")
    assert captured["universe"].loc[0, "Industry"] == "Financial Services"


def test_taxonomy_amendment_preserves_parent_protocol_and_primary_metric() -> None:
    amendment = json.loads((
        ROOT / "experiments/walk_forward/protocol_amendment_001.json"
    ).read_text(encoding="utf-8"))
    assert amendment["parent_protocol"]["sha256"] == PROTOCOL_SHA256
    assert amendment["amendment_created_before_outcome_acquisition"] is True
    assert amendment["primary_metric_changed"] is False
    assert amendment["clarification"]["evaluation_grouping_tier"] == "Official NSE Indices Sector"


def test_repair_availability_difference_is_affected_and_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    universe = pd.DataFrame([{
        "historical_symbol": "AAA", "company": "Alpha",
        "historical_industry": "Sector", "investable": True,
    }])
    repaired = pd.DataFrame({"ticker": ["AAA"]})
    unrepaired = pd.DataFrame({"ticker": ["AAA"]})
    calls = iter([
        pd.DataFrame([{
            "ticker": "AAA", "company": "Alpha", "sector": "Sector",
            "return_1y": 0.1, "cagr_3y": 0.1, "cagr_5y": 0.1,
            "days_since_recorded_high": 1, "annualized_volatility_1y": 0.2,
            "max_drawdown_3y": -0.1, "price_eligible": True,
            "price_reason_codes": "",
        }]),
        pd.DataFrame([{
            "ticker": "AAA", "company": "Alpha", "sector": "Sector",
            "return_1y": None, "cagr_3y": None, "cagr_5y": None,
            "days_since_recorded_high": None, "annualized_volatility_1y": None,
            "max_drawdown_3y": None, "price_eligible": False,
            "price_reason_codes": "MISSING_CURRENT_PRICE",
        }]),
    ])
    monkeypatch.setattr(
        "stock_ranker.walk_forward_blind._price_metric_rows",
        lambda *_args, **_kwargs: next(calls),
    )
    ranking_calls = iter([
        (pd.DataFrame([{"ticker": "AAA", "sector_rank": 1}]), pd.DataFrame(), pd.DataFrame()),
        (pd.DataFrame(), pd.DataFrame(), pd.DataFrame()),
    ])
    monkeypatch.setattr(
        "stock_ranker.walk_forward_blind._baseline_from_prices",
        lambda *_args, **_kwargs: next(ranking_calls),
    )
    result = repair_sensitivity(repaired, unrepaired, universe, "2023-08-07")
    assert result.loc[0, "repair_status"] == "REPAIR_AFFECTED"
    assert bool(result.loc[0, "material_baseline_rank_impact"])


def test_written_bundle_guard_rejects_post_cutoff_price(tmp_path: Path) -> None:
    names = {
        "historical_universe.csv", "identity_resolution.csv",
        "repair_sensitivity.csv", "baseline_full.csv", "fundamentals.csv",
        "research_v2.csv", "matched_baseline.csv", "exclusions.csv",
    }
    for name in names:
        pd.DataFrame({"ticker": ["AAA"]}).to_csv(tmp_path / name, index=False)
    pd.DataFrame({"ticker": ["AAA"], "date": ["2023-08-08"]}).to_csv(
        tmp_path / "predictor_prices.csv", index=False
    )
    (tmp_path / "provenance.json").write_text(
        '{"future_outcome_data_present": false}', encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="BLINDNESS_VIOLATION"):
        validate_blind_snapshot_directory(tmp_path, "2023-08-07")


def test_historical_fundamentals_reject_old_fy_and_ratio_substitute() -> None:
    item = {
        "ticker": "AAA", "reporting_basis": "STANDALONE",
        "financial_year": "2021-22", "period_end": "2022-03-31",
        "available_date": "2023-01-01", "pdf_sha256": "a" * 64,
        "roce": {"classification": "DIRECT_DISCLOSURE", "label": "ROA",
                 "canonical_decimal": 0.1, "page": 1, "table": "Ratios"},
        "debt_to_equity": {"classification": "DIRECT_DISCLOSURE",
                           "label": "Debt Equity Ratio", "canonical_decimal": 0.2,
                           "page": 1, "table": "Ratios"},
        "profit": {"classification": "DIRECT_DISCLOSURE", "current_value": 2,
                   "prior_value": 1, "page": 2, "table": "Statement"},
    }
    mapping = {"snapshots": [{
        "ranking_date": "2023-08-07", "required_fiscal_year": "2022-23",
        "accepted": [item],
    }]}
    with pytest.raises(ValueError, match="cannot fall back"):
        _fundamentals_from_mapping(mapping, "2023-08-07")
    item["financial_year"] = "2022-23"
    item["period_end"] = "2023-03-31"
    with pytest.raises(ValueError, match="substitute ratio"):
        _fundamentals_from_mapping(mapping, "2023-08-07")


def test_historical_fundamentals_reject_post_cutoff_availability() -> None:
    item = {
        "ticker": "AAA", "reporting_basis": "STANDALONE",
        "financial_year": "2022-23", "period_end": "2023-03-31",
        "available_date": "2023-08-08", "pdf_sha256": "a" * 64,
        "roce": {"classification": "DIRECT_DISCLOSURE",
                 "label": "Return on Capital Employed", "canonical_decimal": 0.1,
                 "page": 1, "table": "Ratios"},
        "debt_to_equity": {"classification": "DIRECT_DISCLOSURE",
                           "label": "Debt Equity Ratio", "canonical_decimal": 0.2,
                           "page": 1, "table": "Ratios"},
        "profit": {"classification": "DIRECT_DISCLOSURE", "current_value": 2,
                   "prior_value": 1, "page": 2, "table": "Statement"},
    }
    mapping = {"snapshots": [{
        "ranking_date": "2023-08-07", "required_fiscal_year": "2022-23",
        "accepted": [item],
    }]}
    with pytest.raises(ValueError, match="post-cutoff"):
        _fundamentals_from_mapping(mapping, "2023-08-07")
