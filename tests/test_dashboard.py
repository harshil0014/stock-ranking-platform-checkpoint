from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode
from urllib.request import urlopen

import pytest

from stock_ranker import live_website
from stock_ranker.live_website import live_dashboard, live_overview
from stock_ranker.web_assets import APP_JS, INDEX_HTML, STYLES_CSS
from stock_ranker.webapp import create_server


AUTO = "Automobiles"
CHEMICALS = "Chemicals & Petrochemicals"


def test_all_screener_groups_have_exact_complete_prepared_membership() -> None:
    facts = live_website._company_facts().facts
    expected = facts.loc[facts["screener_industry_group"].notna()].groupby(
        "screener_industry_group", sort=True
    ).size().to_dict()
    rows = live_overview("baseline_v1")["rows"]
    actual: dict[str, int] = {}
    for row in rows:
        if row["sector"] is not None:
            actual[row["sector"]] = actual.get(row["sector"], 0) + 1
    assert len(expected) == 58
    assert set(expected).issubset(actual)
    assert all(actual[sector] >= count for sector, count in expected.items())
    assert sum(actual.values()) == len(rows) == 4436


def test_dashboard_all_sector_landing_never_creates_overall_rank() -> None:
    data = live_dashboard("", "baseline_v1", "ALL")
    assert data["selected_sector"] is None
    assert data["top_four"] == []
    assert data["sector_leaders"]
    assert all(row["canonical_sector_rank"] == 1 for row in data["sector_leaders"])
    assert "Choose a sector" in data["selection_warning"]
    assert "Overall rank" not in json.dumps(data)


def test_dashboard_top_four_uses_canonical_rank_then_ticker() -> None:
    data = live_dashboard(AUTO, "baseline_v1", "ALL")
    eligible = [row for row in live_overview("baseline_v1")["rows"] if row["sector"] == AUTO and row["eligible"]]
    expected = sorted(eligible, key=lambda row: (row["sector_rank"], row["ticker"]))[:4]
    assert [(row["ticker"], row["canonical_sector_rank"]) for row in data["top_four"]] == [
        (row["ticker"], row["sector_rank"]) for row in expected
    ]
    assert data["top_four"][0]["displayed_leader"] is True
    assert all(row["eligible"] for row in data["top_four"])


def test_size_filter_preserves_full_sector_ranks_and_ties() -> None:
    data = live_dashboard(AUTO, "baseline_v1", "SMALL")
    eligible = [row for row in live_overview("baseline_v1")["rows"] if row["sector"] == AUTO and row["size_segment"] == "SMALL" and row["eligible"]]
    expected = sorted(eligible, key=lambda row: (row["sector_rank"], row["ticker"]))[:4]
    assert [(row["ticker"], row["canonical_sector_rank"]) for row in data["top_four"]] == [
        (row["ticker"], row["sector_rank"]) for row in expected
    ]
    canonical = {row["ticker"]: row["sector_rank"] for row in live_overview("baseline_v1")["rows"]}
    assert all(row["canonical_sector_rank"] == canonical[row["ticker"]] for row in data["top_four"])
    assert data["sector_summary"]["selected_model_eligible_peers"] == sum(
        row["sector"] == AUTO and row["eligible"]
        for row in live_overview("baseline_v1")["rows"]
    )
    assert "never recompute" in data["rank_scope"]


def test_displayed_leader_can_keep_non_one_canonical_rank() -> None:
    data = live_dashboard(AUTO, "baseline_v1", "MID")
    assert data["top_four"][0]["displayed_leader"] is True
    canonical = {row["ticker"]: row["sector_rank"] for row in live_overview("baseline_v1")["rows"]}
    ticker = data["top_four"][0]["ticker"]
    assert data["top_four"][0]["canonical_sector_rank"] == canonical[ticker]
    assert data["top_four"][0]["canonical_sector_rank"] > 1


def test_v2_two_peer_and_four_plus_cohorts_show_only_available_up_to_four() -> None:
    two = live_dashboard("Cement & Cement Products", "research_v2", "ALL")
    many = live_dashboard("IT - Software", "research_v2", "ALL")
    assert len(two["top_four"]) == 2
    assert two["sector_summary"]["selected_model_eligible_peers"] == 2
    assert len(many["top_four"]) == 4
    expected = sum(
        row["sector"] == "IT - Software" and row["eligible"]
        for row in live_overview("research_v2")["rows"]
    )
    assert many["sector_summary"]["selected_model_eligible_peers"] == expected == 6


def test_v2_expanded_sector_has_real_companies_and_strict_coverage_warning() -> None:
    data = live_dashboard(CHEMICALS, "research_v2", "ALL")
    assert len(data["top_four"]) == 2
    row = data["top_four"][0]
    assert (row["ticker"], row["canonical_sector_rank"], row["eligible_peer_count"]) == ("SOLARINDS", 1, 2)
    assert data["sector_summary"]["research_v2_eligible"] == 2
    # The accepted market is a moving snapshot.  Verify reconciliation to the
    # returned complete sector instead of pinning an obsolete provider count.
    assert data["sector_summary"]["prepared_companies"] == len(data["sector_rows"])
    assert data["sector_summary"]["prepared_companies"] > 2
    assert (
        data["sector_summary"]["displayed_companies"]
        == data["sector_summary"]["prepared_companies"]
    )
    assert len(data["sector_rows"]) == data["sector_summary"]["prepared_companies"]
    json.dumps(data, allow_nan=False)
    assert sum(not item["eligible"] for item in data["sector_rows"]) == (
        data["sector_summary"]["prepared_companies"]
        - data["sector_summary"]["research_v2_eligible"]
    )
    assert data["sector_summary"]["v2_coverage_ratio"] == pytest.approx(
        data["sector_summary"]["research_v2_eligible"]
        / data["sector_summary"]["prepared_companies"]
    )
    assert "intentionally strict" in data["selection_warning"]


def test_v2_grouped_donut_is_exact_sum_of_existing_contributions() -> None:
    row = live_dashboard(CHEMICALS, "research_v2", "ALL")["top_four"][0]
    details = row["factor_details"]
    expected = {
        category: sum(item["contribution"] for item in details if item["category"] == category)
        for category in ("PRICE / GROWTH", "RISK", "FUNDAMENTALS")
    }
    assert row["grouped_contributions"] == pytest.approx(expected)
    assert row["grouped_contribution_total"] == pytest.approx(row["canonical_score"], abs=1e-12)
    assert sum(row["grouped_contributions"].values()) == pytest.approx(row["canonical_score"])
    assert len(row["strongest_contributions"]) == 3


def test_baseline_rank_position_and_peer_scope_are_preserved() -> None:
    row = live_dashboard(AUTO, "baseline_v1", "ALL")["top_four"][0]
    assert row["canonical_sector_rank"] == 1
    expected_peers = sum(
        item["sector"] == AUTO
        and item["eligible"]
        and item["ranking_tier"] == row["ranking_tier"]
        for item in live_overview("baseline_v1")["rows"]
    )
    assert row["eligible_peer_count"] == expected_peers
    assert row["rank_percentile"] == pytest.approx(100 / expected_peers)
    assert "row.canonical_sector_rank" in APP_JS
    assert "row.ranking_tier" in APP_JS
    assert "score share" not in APP_JS.lower()


def test_dashboard_sparklines_are_cached_adjusted_history_only() -> None:
    data = live_dashboard(AUTO, "baseline_v1", "ALL")
    assert all(row["sparkline"]["available"] for row in data["top_four"])
    assert all(row["sparkline"]["range"] == "6m" for row in data["top_four"])
    assert all("prepared current-product history cache" in row["sparkline"]["price_basis"] for row in data["top_four"])
    source = Path(__file__).parents[1].joinpath("src/stock_ranker/live_website.py").read_text(encoding="utf-8")
    assert "yfinance" not in source


def test_dashboard_research_summary_comes_from_accepted_artifacts() -> None:
    summary = live_dashboard(AUTO, "baseline_v1", "ALL")["research_summary"]
    assert summary["historical_evaluation"] == "2022–2025"
    assert summary["primary_horizon"] == "12 months"
    assert summary["research_v2_mean_rank_ic"] == 0
    assert summary["matched_baseline_mean_rank_ic"] == pytest.approx(-0.04465819873852043)
    assert summary["primary_sample"] == "3 sector-date observations"
    assert summary["alphalens_exact_matches"] == summary["alphalens_total_checks"] == 18
    assert summary["empyrical_passes"] == 68
    assert summary["empyrical_explained_differences"] == 34
    assert summary["empyrical_failures"] == 0


def test_dashboard_fingerprint_poll_is_lightweight_and_deterministic() -> None:
    data = live_dashboard(fingerprint_only=True)
    assert set(data) == {"available", "bundle_fingerprint", "snapshot"}
    assert data["bundle_fingerprint"] == live_overview()["bundle_fingerprint"]
    assert "fingerprint_only=true" in APP_JS
    assert "setInterval(pollDashboard,60000)" in APP_JS
    assert "dashboardRequest:0" in APP_JS
    assert "request===state.dashboardRequest" in APP_JS


def test_dashboard_dom_navigation_responsive_and_neutral() -> None:
    rendered = INDEX_HTML + APP_JS + STYLES_CSS
    assert 'id="view-dashboard" class="view hidden"' in INDEX_HTML
    assert "Baseline</button>" in INDEX_HTML
    assert 'data-view="personalized">Personalized' in INDEX_HTML
    assert 'data-view="live">Explore' in INDEX_HTML
    assert "dashboard-company-grid" in INDEX_HTML
    assert "repeat(4,minmax(0,1fr))" in STYLES_CSS
    assert "repeat(2,minmax(0,1fr))" in STYLES_CSS
    assert "grid-template-columns:1fr" in STYLES_CSS
    assert "View all sector companies" in INDEX_HTML
    assert "showView('live')" in APP_JS
    lowered = rendered.lower()
    for prohibited in ("buy signal", "sell signal", "target price", "top 4 stocks in india"):
        assert prohibited not in lowered
    dashboard_html = INDEX_HTML.split('<section id="view-dashboard"', 1)[1].split(
        '<section id="view-personalized"', 1)[0]
    assert "overall rank" not in dashboard_html.lower()
    for clutter in ("RESEARCH SUMMARY", "View full validation", "View methodology",
                    "dashboardFingerprint", "dashboardRankScope", "dashboardResearch"):
        assert clutter not in dashboard_html
    assert "Overall Personalized rank" in INDEX_HTML


def test_dashboard_uses_wide_dense_terminal_tables() -> None:
    assert "function dashboardSectorTable" in APP_JS
    assert "function dashboardCompanyTable" in APP_JS
    assert 'id="dashboardResearch"' not in INDEX_HTML
    assert 'id="dashboardFingerprint"' not in INDEX_HTML
    assert APP_JS.count("function renderDashboard(data)") == 1
    assert "max-width:1580px" in STYLES_CSS
    assert ".dashboard-company-grid,.sector-leader-grid{display:block" in STYLES_CSS


def test_dashboard_http_endpoint_and_default_route() -> None:
    server = create_server(port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(base + "/", timeout=10) as response:
            assert response.status == 200
            assert b"Personalized stock ranking" in response.read()
        query = urlencode({"sector": AUTO, "model": "baseline_v1", "segment": "SMALL"})
        with urlopen(base + "/api/live/dashboard?" + query, timeout=30) as response:
            data = json.load(response)
        assert response.status == 200
        canonical = {
            row["ticker"]: row["sector_rank"] for row in live_overview("baseline_v1")["rows"]
        }
        assert all(row["canonical_sector_rank"] == canonical[row["ticker"]] for row in data["top_four"])
        with urlopen(base + "/dashboard", timeout=10) as response:
            assert response.status == 200
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
