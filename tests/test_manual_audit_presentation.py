from __future__ import annotations

import pytest

from stock_ranker import research_website
from stock_ranker.live_website import live_overview, live_stock
from stock_ranker.web_assets import APP_JS, INDEX_HTML, STYLES_CSS


def test_ineligible_live_v2_copy_never_claims_ranking() -> None:
    data = live_stock("GABRIEL")
    assert data["research_v2"]["eligible"] is False
    assert "not currently eligible" in data["simple_explanation"]
    assert data["research_v2"]["reason"] in data["simple_explanation"]
    assert "ranks this company" not in data["simple_explanation"]


def test_eligible_live_v2_copy_and_canonical_values_are_unchanged() -> None:
    data = live_stock("RELIANCE")
    assert data["research_v2"]["eligible"] is True
    assert "ranks this company" in data["simple_explanation"]
    assert data["research_v2"]["score"] == 50
    assert data["research_v2"]["sector_rank"] == 1
    assert data["research_v2"]["peer_count"] == 1
    assert len(data["research_v2"]["factor_details"]) == 9


def test_singleton_warning_and_sector_position_semantics_are_explicit() -> None:
    assert "Rank 1 of 1 is therefore not a meaningful peer comparison" in APP_JS
    assert "Sector Rank ${fmt(rank)} of ${n}" in APP_JS
    assert "Lower ranked" in APP_JS and "Higher ranked" in APP_JS
    assert "Top ${Math.ceil(rank/n*100)}%" in APP_JS


def test_factor_display_uses_human_numbers_and_common_contribution_scale() -> None:
    assert "replace(/\\.?0+$/,'')" in APP_JS
    assert "Number(f.contribution)/15*100" in APP_JS
    assert "Weighted contribution · common 0–15 scale" in APP_JS
    assert "fill.dataset.contribution=String(f.contribution)" in APP_JS
    assert "Number(f.contribution)/Number(f.weight_percent)" not in APP_JS


def test_simple_and_technical_factor_views_are_distinct() -> None:
    assert "renderFactorSummary(factors" in APP_JS
    assert "renderFactorDetails($('liveFactorDetails')" in APP_JS
    assert "Canonical value" in APP_JS
    assert "Relative scores are within-sector positions" in APP_JS


def test_rank_ic_uses_zero_centered_negative_side_encoding() -> None:
    assert "renderDivergingBars(rankHost" in APP_JS
    assert "fill.dataset.side=value<0?'negative':'positive'" in APP_JS
    assert "right:50%" in STYLES_CSS
    assert "Negative ← 0 → Positive" in APP_JS
    validation = research_website.validation()
    assert validation["chart_data"][-1]["matched_baseline_rank_ic"] == pytest.approx(-0.04465819873852043)


def test_pairwise_values_remain_canonical() -> None:
    data = research_website.validation()
    by_horizon = {item["horizon_months"]: item for item in data["chart_data"]}
    assert by_horizon[3]["research_v2_pairwise_accuracy"] == pytest.approx(0.5384615384615384)
    assert by_horizon[3]["matched_baseline_pairwise_accuracy"] == pytest.approx(0.5769230769230769)
    assert by_horizon[6]["research_v2_pairwise_accuracy"] == pytest.approx(0.6153846153846154)
    assert by_horizon[6]["matched_baseline_pairwise_accuracy"] == pytest.approx(0.4230769230769231)
    assert by_horizon[12]["research_v2_pairwise_accuracy"] == pytest.approx(0.5384615384615384)
    assert by_horizon[12]["matched_baseline_pairwise_accuracy"] == pytest.approx(0.5)


def test_historical_display_humanizes_without_mutating_raw_api() -> None:
    data = research_website.historical("2025")
    assert data["ranking_date"] == "2025-08-07"
    assert data["cutoff_timestamp"] == "2025-08-07T15:30:00+05:30"
    excluded = next(row for row in data["rows"] if not row["eligible"])
    assert "_" in excluded["reason_code"] or ";" in excluded["reason_code"]
    assert "readableDate(data.cutoff_timestamp,true)" in APP_JS
    assert "historical reconstructed universe snapshot" in APP_JS
    assert "'Raw code: '+row.reason_code" in APP_JS
    assert "humanStatus(row.reason_code)" in APP_JS
    assert "compactNumber(row.research_v2_score)" in APP_JS


def test_historical_missing_score_rank_stays_missing_while_numeric_zero_is_valid() -> None:
    data = research_website.historical("2025")
    excluded = next(row for row in data["rows"] if row["ticker"] == "GRASIM")
    assert excluded["eligible"] is False
    assert excluded["research_v2_score"] is None
    assert excluded["research_v2_sector_rank"] is None
    raw_reason = excluded["reason_code"]
    assert raw_reason != "ELIGIBLE"
    assert "if(value===null||value===undefined||value==='')return '—'" in APP_JS
    assert "const number=Number(value);return Number.isFinite(number)?fmt(number,digits):'—'" in APP_JS
    assert "compactNumber(row.research_v2_score)+' / '+compactNumber(row.research_v2_sector_rank)" in APP_JS
    assert research_website.historical("2025")["rows"][[row["ticker"] for row in data["rows"]].index("GRASIM")]["reason_code"] == raw_reason


def test_validation_return_diagnostics_use_percent_but_rank_ic_remains_decimal() -> None:
    assert "function signedReturnPct(value)" in APP_JS
    assert "signedReturnPct(item.mean_top_stock_excess_return[model])" in APP_JS
    assert "signedReturnPct(item.mean_top_bottom_spread[model])" in APP_JS
    assert "pct(item.pairwise[model].pairwise_accuracy)" in APP_JS
    assert "fmt(row.research_v2_rank_ic)" in APP_JS
    assert "fmt(row.matched_baseline_rank_ic)" in APP_JS
    assert "signedReturnPct(row.research_v2_rank_ic)" not in APP_JS
    values = research_website.validation()
    assert values["primary"]["matched_baseline_rank_ic"]["mean"] == pytest.approx(-0.04465819873852043)


def test_historical_status_mapping_and_integer_formatting_are_display_only() -> None:
    assert "Fundamentals unavailable by cutoff" in APP_JS
    assert "5-year price history unavailable" in APP_JS
    assert "Multiple eligibility requirements unavailable" in APP_JS
    assert "compactNumber(item.value)" in APP_JS
    assert research_website.historical("2025")["coverage_by_year"] == {"2022": 8, "2023": 4, "2024": 8, "2025": 16}


def test_quant_lab_human_summary_is_artifact_backed() -> None:
    data = research_website.quant_lab()
    assert data["alphalens"]["exact_ic_matches"] == 18
    assert data["alphalens"]["ic_rows"] == 18
    by_metric = {item["metric"]: item for item in data["empyrical_metric_summary"]}
    assert by_metric["annualized_volatility_1y"]["passes"] == 34
    assert by_metric["max_drawdown_3y"]["passes"] == 34
    assert by_metric["return_1y"]["explained_differences"] == 34
    assert data["empyrical"]["failures"] == 0


def test_quant_lab_statuses_metrics_and_difference_note_are_humanized() -> None:
    assert "Deferred — sparse annual observations" in APP_JS
    assert "Descriptive only — small cohorts" in APP_JS
    assert "Explained difference" in APP_JS
    assert "grouped IC checks matched exactly" in APP_JS
    assert "factorValue(row.metric,row.internal_value)" in APP_JS
    assert "Empyrical annualizes the observed daily period" in APP_JS


def test_qlib_is_explicitly_synthetic_and_separate_from_live_rankings() -> None:
    data = research_website.quant_lab()
    assert [(item["name"], item["status"]) for item in data["qlib_models"]] == [
        ("Linear", "REPRODUCED"),
        ("LightGBM", "REPRODUCED"),
        ("TRA", "REPRODUCED"),
        ("DoubleEnsemble", "COMPATIBILITY / SCIENTIFIC BLOCKER"),
    ]
    assert "synthetic benchmark data" in APP_JS
    assert "not used to generate current Live Market" in APP_JS


def test_reproducibility_wording_preserves_historical_milestone() -> None:
    assert research_website.status()["accepted_test_milestone"] == "324 passed"
    assert "324 tests passed" not in INDEX_HTML  # derived from canonical API value
    assert "historical accepted milestone" in APP_JS
    for sentence in research_website.status()["plain_checks"]:
        assert sentence in APP_JS


def test_price_history_heading_and_compact_badge_are_display_only() -> None:
    assert ">Price History<" in INDEX_HTML
    assert "accepted adjusted-price series" in INDEX_HTML
    assert "Adjusted Price History" not in INDEX_HTML
    assert "latest-badge" in INDEX_HTML and ".latest-badge" in STYLES_CSS


def test_live_counts_and_bundle_fingerprint_are_unchanged() -> None:
    data = live_overview("research_v2")
    assert data["summary"] == {
        "all_nse_equities": 2397,
        "price_ready": 2393,
        "baseline_eligible": 567,
        "research_v2_eligible": 34,
    }
    assert data["bundle_fingerprint"] == "73803826866c63f3844d644cebf5cb6f729812213095f49271b0db60262dbbc4"
