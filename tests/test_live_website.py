from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

import pandas as pd
import pytest

from stock_ranker import live_website
from stock_ranker.web_assets import APP_JS, INDEX_HTML
from stock_ranker.webapp import create_server


def test_live_overview_exposes_actual_all_nse_counts_and_separate_models() -> None:
    data = live_website.live_overview("baseline_v1")
    assert data["mode"] == "LIVE MARKET"
    assert data["summary"]["all_nse_equities"] == 2397
    assert data["summary"]["price_ready"] == 2393
    assert data["summary"]["baseline_eligible"] == 567
    assert data["summary"]["research_v2_eligible"] == 34
    assert len(data["rows"]) == 2397
    assert data["snapshot"]["trade_date"] == "2026-08-07"
    assert "real-time" in data["warnings"][0].lower()


def test_live_models_preserve_eligibility_gates_and_searchable_other_nse() -> None:
    baseline = live_website.live_overview("baseline_v1")
    v2 = live_website.live_overview("research_v2")
    assert sum(row["eligible"] for row in baseline["rows"]) == baseline["summary"]["baseline_eligible"]
    assert sum(row["eligible"] for row in v2["rows"]) == 34
    assert any(row["size_segment"] == "OTHER NSE" for row in baseline["rows"])
    assert any(row["classification_status"] == "UNCLASSIFIED" for row in baseline["rows"])


def test_live_stock_reliance_has_price_both_models_and_nine_v2_factors() -> None:
    data = live_website.live_stock("RELIANCE")
    assert data["stock"]["ticker"] == "RELIANCE"
    assert data["display"]["price"].startswith("₹")
    assert data["baseline_v1"]["eligible"] is True
    assert data["research_v2"]["eligible"] is True
    assert len(data["research_v2"]["factors"]) == 9
    assert all(value is not None for value in data["research_v2"]["factors"].values())
    json.dumps(data, allow_nan=False)


def test_every_eligible_live_detail_matches_the_canonical_v2_model_inputs() -> None:
    canonical_path = Path(__file__).parents[1] / (
        "data/marketdata/nifty50-research-v2-2026-08-07/"
        "standalone-contract-reason-fix-run-01/rankings.csv"
    )
    canonical = pd.read_csv(canonical_path).set_index("ticker")
    bundle = live_website._bundle()
    assert live_website.validate_v2_detail_invariants(bundle.market) == 34
    eligible = bundle.market.loc[bundle.market["v2_eligible"].astype(bool)]
    assert set(eligible["ticker"]) == set(canonical.index)
    for ticker in sorted(canonical.index):
        detail = live_website.live_stock(ticker)["research_v2"]
        expected = canonical.loc[ticker]
        assert detail["eligible"] is True
        assert detail["score"] == pytest.approx(expected["research_v2_score"], abs=1e-14)
        assert detail["sector_rank"] == pytest.approx(expected["sector_rank"], abs=1e-14)
        for factor in live_website.V2_FACTORS:
            assert detail["factors"][factor] == pytest.approx(expected[factor], abs=1e-14)


@pytest.mark.parametrize("ticker", ["RELIANCE", "HINDUNILVR"])
def test_named_eligible_stocks_expose_all_nine_canonical_factors(ticker: str) -> None:
    factors = live_website.live_stock(ticker)["research_v2"]["factors"]
    assert tuple(factors) == live_website.V2_FACTORS
    assert all(value is not None for value in factors.values())


def test_live_timestamp_is_readable_ist_while_raw_provenance_is_preserved() -> None:
    data = live_website.live_overview()
    raw = data["provenance"]["acquisition_completed_at"]
    assert raw == live_website._bundle().manifest["acquisition_completed_at"]
    assert data["provenance"]["acquisition_completed_display"] == live_website.format_ist_timestamp(raw)
    assert live_website.format_ist_timestamp("2026-08-09T13:57:29.700342+00:00") == "09 Aug 2026, 7:27 PM IST"


def test_live_ui_explains_rank_scope_and_uses_human_factor_labels() -> None:
    assert "Sector Rank is calculated across the full eligible sector" in INDEX_HTML
    assert "filters do not recompute model ranks" in INDEX_HTML
    for label in (
        "1-Year Return", "3-Year CAGR", "5-Year CAGR", "Days Since Recorded High",
        "1-Year Annualized Volatility", "3-Year Maximum Drawdown", "ROCE",
        "Debt-to-Equity", "YoY Profit Growth",
    ):
        assert label in APP_JS
    assert "acquisition_completed_display" in APP_JS


@pytest.mark.parametrize("ticker", ["", "../../secret", "A/B", "A" * 33])
def test_live_stock_rejects_unsafe_identity(ticker: str) -> None:
    with pytest.raises(live_website.LiveWebsiteError, match="safe identifier"):
        live_website.live_stock(ticker)


def test_number_formatting_does_not_change_stored_values() -> None:
    assert live_website.format_price(1234.5) == "₹1,234.50"
    assert live_website.format_percent_points(-15.234) == "-15.23%"
    assert live_website.format_decimal_percent(.0842) == "+8.42%"
    assert live_website.format_price(None) == "Unavailable"


def test_spa_defaults_to_live_and_keeps_frozen_research_lab_views() -> None:
    assert 'id="view-live" class="view"' in INDEX_HTML
    assert "LIVE MARKET" in INDEX_HTML
    assert "RESEARCH LAB" in INDEX_HTML
    assert "Latest Market Snapshot" in INDEX_HTML
    for view in ("overview", "rankings", "historical", "validation", "provenance", "methodology", "status"):
        assert f'id="view-{view}"' in INDEX_HTML
    assert "location.pathname.split('/')[1]||'live'" in APP_JS
    assert "guaranteed-return claim" in INDEX_HTML


def test_live_http_routes_and_default_page() -> None:
    server = create_server(port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(base + "/", timeout=10) as response:
            assert response.status == 200
            assert b"Latest Market Snapshot" in response.read()
        with urlopen(base + "/api/live/overview?model=baseline_v1", timeout=30) as response:
            data = json.load(response)
            assert data["summary"]["all_nse_equities"] == 2397
        with urlopen(base + "/api/live/stock?ticker=RELIANCE", timeout=15) as response:
            assert json.load(response)["stock"]["ticker"] == "RELIANCE"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
