from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from stock_ranker import research_website
from stock_ranker.research_website import ResearchWebsiteError
from stock_ranker.web_assets import APP_JS, INDEX_HTML, STYLES_CSS
from stock_ranker.webapp import create_server


def test_overview_distinguishes_original_operationalization_and_v2() -> None:
    data = research_website.overview()
    assert data["models"][0]["label"] == "Original-paper signals — project operationalization"
    assert "Nine-factor" in data["models"][1]["label"]
    assert data["research_status"]["predictions_frozen_before_outcomes"] == "YES"
    assert data["research_status"]["primary_sample"] == "3 sector-date observations"


@pytest.mark.parametrize("model", ["baseline_v1", "research_v2"])
def test_current_rankings_load_canonical_rows_and_explicit_exclusions(model: str) -> None:
    data = research_website.rankings(model)
    assert data["available"] is True
    assert len(data["rows"]) == 50
    assert data["sectors"] == sorted(data["sectors"])
    if model == "research_v2":
        assert sum(row["eligible"] for row in data["rows"]) == 34
        assert sum(not row["eligible"] for row in data["rows"]) == 16
        assert all(row["reason"] for row in data["rows"] if not row["eligible"])


def test_stock_explanation_has_nine_canonical_factors_weights_and_contributions() -> None:
    data = research_website.stock_explanation("research_v2", "HINDUNILVR")
    stock = data["stock"]
    assert stock["eligible"] is True
    assert len(stock["factors"]) == 9
    assert sum(item["weight_percent"] for item in stock["factors"]) == 100
    assert all({"value", "direction", "component_score", "contribution"}.issubset(item) for item in stock["factors"])
    assert "not investment advice" in data["advice_warning"].lower()


@pytest.mark.parametrize("ticker", ["../../secret", "A/B", "", "A" * 33])
def test_stock_and_provenance_selectors_reject_path_traversal(ticker: str) -> None:
    with pytest.raises(ResearchWebsiteError, match="safe identifier"):
        research_website.stock_explanation("research_v2", ticker)


@pytest.mark.parametrize("year,eligible", [("2022", 8), ("2023", 4), ("2024", 8), ("2025", 16)])
def test_historical_views_require_blind_integrity_and_preserve_cohorts(year: str, eligible: int) -> None:
    data = research_website.historical(year)
    assert data["available"] is True
    assert data["eligible_count"] == eligible
    assert len(data["rows"]) == 50
    assert data["blind_fingerprint"] == research_website.BLIND_FINGERPRINT
    assert "WHAT THE MODEL KNEW THEN" in data["separation_warning"]
    assert not any("future_adjusted_return" in row for row in data["rows"])


def test_historical_integrity_mismatch_is_not_displayed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps({
        "protocol_sha256": research_website.PROTOCOL_SHA256,
        "blind_prediction_fingerprint": "0" * 64,
        "future_outcome_data_present": False,
    }), encoding="utf-8")
    monkeypatch.setattr(research_website, "BLIND_ROOT", tmp_path)
    with pytest.raises(ResearchWebsiteError, match="blind fingerprint mismatch"):
        research_website.historical("2025")


def test_validation_primary_is_canonical_and_secondary_is_separate() -> None:
    data = research_website.validation()
    assert data["protocol"]["sha256"] == research_website.PROTOCOL_SHA256
    assert data["amendment"]["sha256"] == research_website.AMENDMENT_SHA256
    assert data["blind_fingerprint"] == research_website.BLIND_FINGERPRINT
    assert data["evaluation_fingerprint"] == research_website.EVALUATION_FINGERPRINT
    assert data["primary"]["rank_ic_observation_count"] == 3
    assert data["primary"]["research_v2_rank_ic"]["mean"] == pytest.approx(0.0)
    assert data["primary"]["matched_baseline_rank_ic"]["mean"] == pytest.approx(-0.04465819873852043)
    assert data["primary"]["mean_delta_rank_ic"] == pytest.approx(0.04465819873852043)
    assert (data["primary"]["wins"], data["primary"]["ties"], data["primary"]["losses"]) == (1, 2, 0)
    assert data["secondary"]["6"]["research_v2_rank_ic"]["mean"] == pytest.approx(0.6666666666666666)
    assert data["secondary"]["3"]["research_v2_rank_ic"]["mean"] == pytest.approx(0.16666666666666666)
    assert "not statistically conclusive" in data["interpretation"]


def test_corrupted_evaluation_fingerprint_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps({
        "evaluation_fingerprint": "0" * 64,
        "blind_prediction_fingerprint": research_website.BLIND_FINGERPRINT,
        "artifacts": [],
    }), encoding="utf-8")
    monkeypatch.setattr(research_website, "EVALUATION_ROOT", tmp_path)
    with pytest.raises(ResearchWebsiteError, match="evaluation fingerprint mismatch"):
        research_website.validation()


def test_provenance_exposes_real_annual_report_evidence_without_inventing_pages() -> None:
    data = research_website.provenance("HINDUNILVR")
    assert data["eligible"] is True
    assert data["fundamental_contract"] == "NSE Audited Standalone Fundamentals v1"
    assert data["annual_report"]["annual_report_pdf_sha_256"]
    assert data["final_fundamentals"]["roce_source_page"] is not None
    assert data["final_fundamentals"]["debt_to_equity_source_page"] is not None


def test_methodology_keeps_original_paper_and_project_extension_distinct() -> None:
    data = research_website.methodology()
    assert data["progression"][0] == "ORIGINAL PAPER"
    assert data["progression"][-1] == "ROBUSTNESS AUDIT"
    assert "project approximation" in data["baseline_caveat"]
    assert "project's explainable nine-factor extension" in data["research_v2_caveat"]
    assert sum(data["weights_percent"].values()) == 100
    assert "released after that cutoff is not allowed" in data["point_in_time_rule"]


def test_status_and_limitations_report_accepted_milestone_not_live_test_claim() -> None:
    data = research_website.status()
    assert data["robustness_audit"] == "PASS"
    assert data["accepted_test_milestone"] == "324 passed"
    assert set(data["checks"].values()) == {"PASS"}
    assert data["blind_reproduction"] == "46 files, byte-identical"
    assert data["evaluation_reproduction"] == "9 files, byte-identical"
    assert data["cohort_sizes"] == {"2022": 8, "2023": 4, "2024": 8, "2025": 16}
    assert len(data["limitations"]) >= 7


def test_missing_current_artifact_returns_controlled_state(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing() -> dict[str, object]:
        raise FileNotFoundError("private path must not escape")

    monkeypatch.setattr(research_website, "_prepared_real_baseline", missing)
    data = research_website.rankings("baseline_v1")
    assert data["available"] is False
    assert data["status"] == "DATA NOT AVAILABLE"
    assert "private path" not in data["message"]


def test_spa_contains_all_views_primary_before_secondary_and_visible_limits() -> None:
    for view in ("overview", "rankings", "historical", "validation", "provenance", "methodology", "status"):
        assert f'id="view-{view}"' in INDEX_HTML
    assert INDEX_HTML.index("PRIMARY · 12 MONTH") < INDEX_HTML.index("SECONDARY")
    assert "VERY LOW PRIMARY SAMPLE SIZE" in INDEX_HTML
    assert "VISIBLE LIMITATIONS" in INDEX_HTML
    assert "Original-paper signals" not in APP_JS  # supplied by the canonical backend adapter
    assert "grid-template-columns" in STYLES_CSS
    prohibited = ("guaranteed returns", "AI predicts winning stocks", "profitable strategy", "V2 proved superior")
    rendered = (INDEX_HTML + APP_JS).lower()
    assert not any(term.lower() in rendered for term in prohibited)


def test_http_routes_and_research_apis_smoke() -> None:
    server = create_server(port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        for route in ("/overview", "/rankings", "/historical", "/validation", "/provenance", "/methodology", "/status"):
            with urlopen(base + route, timeout=10) as response:
                assert response.status == 200
                assert b"Indian Equity Research Platform" in response.read()
        for route in (
            "/api/research/overview", "/api/research/rankings?model=research_v2",
            "/api/research/stock?model=research_v2&ticker=HINDUNILVR",
            "/api/research/historical?year=2025", "/api/research/validation",
            "/api/research/provenance?ticker=HINDUNILVR",
            "/api/research/methodology", "/api/research/status",
        ):
            with urlopen(base + route, timeout=20) as response:
                assert response.status == 200
                assert json.load(response)["available"] is True
        with pytest.raises(HTTPError) as error:
            urlopen(base + "/api/research/stock?ticker=../../secret", timeout=10)
        assert error.value.code == 400
        with pytest.raises(HTTPError) as error:
            urlopen(base + "/unknown", timeout=10)
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
