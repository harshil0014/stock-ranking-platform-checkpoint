from __future__ import annotations

import json
import re
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import pytest

from stock_ranker.personalized_product import (
    DOMAINS, PersonalizationError, PersonalizedRankingService, parse_profile, resolve_security,
)
from stock_ranker.web_assets import APP_JS, INDEX_HTML, STYLES_CSS
from stock_ranker.webapp import create_server


BASE = {"amount": 7500, "lookback_months": 36, "interval_days": 30,
        "target_cagr_percent": 20, "horizon_months": 12}


def test_public_profile_contract_accepts_decimals_without_silent_clamping():
    profile = parse_profile({**BASE, "amount": 7500.25, "target_cagr_percent": 19.75})
    assert profile.amount == 7500.25
    assert profile.target_cagr == .1975
    assert profile.whole_shares is True
    assert DOMAINS["lookback_months"]["choices"] == [12, 36, 60]
    assert DOMAINS["horizon_months"]["choices"] == [12]


@pytest.mark.parametrize(("change", "message"), [
    ({"amount": ""}, "amount is required"), ({"amount": "lots"}, "amount must be numeric"),
    ({"amount": 0}, "amount must be between"), ({"amount": -1}, "amount must be between"),
    ({"amount": 999}, "amount must be between"), ({"amount": 50001}, "amount must be between"),
    ({"lookback_months": 18}, "must be 12, 36, or 60"),
    ({"interval_days": 6}, "from 7 through 90"), ({"interval_days": 91}, "from 7 through 90"),
    ({"interval_days": 30.5}, "must be a whole number"),
    ({"target_cagr_percent": 9.99}, "between 10 and 30"),
    ({"target_cagr_percent": 30.01}, "between 10 and 30"),
    ({"horizon_months": 24}, "only a 12-month horizon"),
    ({"target_cagr_percent": float("inf")}, "must be finite"),
])
def test_invalid_and_unsupported_inputs_fail_honestly(change, message):
    with pytest.raises(PersonalizationError, match=message):
        parse_profile({**BASE, **change})


def _product():
    return pd.DataFrame([
        {"isin": "I1", "ticker": "ONE", "company": "One Ltd", "primary_exchange": "NSE",
         "exchange_security_id": "ONE", "screener_nse_code": "ONE", "screener_bse_code": "500001",
         "product_baseline_sector_rank": 1, "product_research_v2_sector_rank": 2},
        {"isin": "I2", "ticker": "BSE-500002", "company": "Two Ltd", "primary_exchange": "BSE",
         "exchange_security_id": "500002", "screener_nse_code": None, "screener_bse_code": "500002",
         "product_baseline_sector_rank": 2, "product_research_v2_sector_rank": np.nan},
    ])


def test_exact_exchange_aliases_resolve_without_guessing():
    product = _product()
    assert resolve_security("NSE:ONE", product) == "ONE"
    assert resolve_security("BOM:500002", product) == "BSE-500002"
    assert resolve_security("BSE:500002", product) == "BSE-500002"
    with pytest.raises(PersonalizationError, match="not uniquely present"):
        resolve_security("NSE:UNKNOWN", product)


def test_ui_exposes_editable_inputs_and_real_champion_workflow():
    rendered = INDEX_HTML + APP_JS + STYLES_CSS
    for field in ("personalizedAmount", "personalizedLookback", "personalizedInterval",
                  "personalizedTarget", "personalizedHorizon"):
        assert f'id="{field}"' in rendered
    for phrase in ("Amount per contribution", "Historical lookback", "Contribution / SIP interval",
                   "Desired annual return / target CAGR", "Investment horizon",
                   "/api/personalized/rank"):
        assert phrase in rendered
    product_html = INDEX_HTML.split('<section id="view-personalized"', 1)[1].split(
        '<section id="view-live"', 1)[0]
    assert "67% Goal + 33% LightGBM LambdaRank" not in product_html
    for clutter in ("FROZEN d499580", "scientific_boundary", "personalizedFingerprint",
                    "personalizedBoundary", "CURRENT PROFILE EXPLANATION"):
        assert clutter not in product_html
    assert "personalizedPayload()" in APP_JS
    assert "state.personalized=null" in APP_JS
    assert 'id="personalizedBoundary"' not in INDEX_HTML
    assert 'id="personalizedFingerprint"' not in INDEX_HTML
    assert "PRODUCT FALLBACK" not in INDEX_HTML  # status comes from the actual response


def test_primary_product_exposes_only_baseline_and_personalized_modes():
    for select_id in ("dashboardModel", "liveModel"):
        match = re.search(rf'<select id="{select_id}">(.*?)</select>', INDEX_HTML)
        assert match is not None
        options = re.findall(r'<option value="([^"]+)">([^<]+)</option>', match.group(1))
        assert options == [("baseline_v1", "Baseline"), ("personalized", "Personalized")]
        assert "Research V2" not in match.group(1)
    assert 'data-view="dashboard" class="mode-button">Baseline</button>' in INDEX_HTML
    assert 'data-view="personalized">Personalized</button>' in INDEX_HTML
    assert "Historical Research V2 rankings" in INDEX_HTML
    assert "not an active product ranking mode" in INDEX_HTML
    assert "value==='personalized'" in APP_JS


def test_personalized_http_validation_is_controlled(monkeypatch):
    import stock_ranker.webapp as webapp
    monkeypatch.setattr(webapp, "personalized_rank", lambda payload: (_ for _ in ()).throw(
        PersonalizationError("amount must be between ₹1,000 and ₹50,000")))
    server = create_server(port=0, refresh_enabled=False)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    request = Request(f"http://127.0.0.1:{server.server_address[1]}/api/personalized/rank",
                      data=json.dumps({"profile": BASE}).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        with pytest.raises(HTTPError) as caught:
            urlopen(request, timeout=10)
        assert caught.value.code == 400
        payload = json.loads(caught.value.read())
        assert payload["status"] == "INVALID PERSONALIZATION INPUT"
        assert "amount must be between" in payload["error"]
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
