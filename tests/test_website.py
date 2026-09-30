from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

import pandas as pd
import pytest

from stock_ranker.webapp import create_server
from stock_ranker.website import (
    METHOD_BASELINE,
    METHOD_RESEARCH_V2,
    analyze_website_request,
)


ROOT = Path(__file__).resolve().parents[1]


def _sample(method: str) -> dict[str, object]:
    return analyze_website_request({
        "method": method,
        "use_synthetic_sample": True,
        "ranking_date": "2026-06-30",
    })


def test_web_server_starts_and_serves_main_screen() -> None:
    server = create_server(port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        with urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
        assert "Indian Equity Research Platform" in body
        assert 'id="view-personalized" class="view"' in body
        assert 'id="view-dashboard" class="view hidden"' in body
        with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as response:
            assert json.load(response)["status"] == "ok"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_baseline_dispatch_explanation_and_export() -> None:
    result = _sample(METHOD_BASELINE)
    assert result["method"] == METHOD_BASELINE
    assert len(result["results"]) == 18
    assert all(row["eligible"] for row in result["results"])
    assert set(result["results"][0]["explanation"]["metrics"]) == {
        "yoy_growth", "cagr_3y", "cagr_5y", "days_since_recorded_high"
    }
    assert set(result["results"][0]["explanation"]["metric_ranks"]) == {
        "yoy_rank", "cagr_3y_rank", "cagr_5y_rank",
        "recorded_high_recency_rank",
    }
    exported = pd.read_csv(StringIO(result["export_csv"]))
    assert len(exported) == 18
    assert {"baseline_score", "sector_rank", "eligible", "status"}.issubset(
        exported.columns
    )


def test_research_v2_dispatch_eligibility_contributions_and_export() -> None:
    result = _sample(METHOD_RESEARCH_V2)
    assert result["method"] == METHOD_RESEARCH_V2
    assert len(result["results"]) == 18
    assert sum(row["eligible"] for row in result["results"]) == 17
    assert sum(not row["eligible"] for row in result["results"]) == 1
    eligible = next(row for row in result["results"] if row["eligible"])
    assert len(eligible["explanation"]["metrics"]) == 9
    assert len(eligible["explanation"]["component_scores"]) == 9
    assert len(eligible["explanation"]["contributions"]) == 9
    ineligible = next(row for row in result["results"] if not row["eligible"])
    assert ineligible["score"] is None
    assert "reason_code" in ineligible["explanation"]
    exported = pd.read_csv(StringIO(result["export_csv"]))
    assert len(exported) == 18
    assert (exported["status"] == "Ineligible").sum() == 1
    json.dumps(result, allow_nan=False)


def test_uploaded_baseline_uses_real_snapshot_label_without_claiming_point_in_time() -> None:
    csv_text = (ROOT / "data/input/synthetic_stocks.csv").read_text(encoding="utf-8")
    result = analyze_website_request({
        "method": METHOD_BASELINE,
        "use_synthetic_sample": False,
        "source_label": "Locally supplied snapshot",
        "data_mode": "real_current_snapshot",
        "universe": "Demonstration universe",
        "ranking_date": "2026-06-30",
        "files": {"baseline": csv_text},
    })
    assert result["provenance"]["data_mode"] == "REAL CURRENT SNAPSHOT"
    assert any(
        "not a point-in-time" in warning
        for warning in result["provenance"]["warnings"]
    )


def test_baseline_rejects_unsupported_point_in_time_claim() -> None:
    with pytest.raises(ValueError, match="cannot be labelled point-in-time"):
        analyze_website_request({
            "method": METHOD_BASELINE,
            "use_synthetic_sample": False,
            "source_label": "Source",
            "data_mode": "real_historical_point_in_time",
            "files": {"baseline": "ticker\nTEST\n"},
        })


def test_missing_required_columns_are_clear() -> None:
    with pytest.raises(ValueError, match="Missing required columns"):
        analyze_website_request({
            "method": METHOD_BASELINE,
            "use_synthetic_sample": False,
            "source_label": "Local file",
            "data_mode": "real_current_snapshot",
            "files": {"baseline": "ticker,company\nTEST,Test Company\n"},
        })


@pytest.mark.parametrize(
    "payload, message",
    [
        ({}, "method must be"),
        ({"method": METHOD_BASELINE, "use_synthetic_sample": False}, "files must"),
        ({
            "method": METHOD_RESEARCH_V2,
            "use_synthetic_sample": False,
            "files": {},
            "data_mode": "synthetic_research_test",
            "source_label": "test",
            "ranking_date": "bad",
        }, "ranking_date"),
    ],
)
def test_request_validation(payload: dict[str, object], message: str) -> None:
    with pytest.raises((ValueError, TypeError), match=message):
        analyze_website_request(payload)


def test_synthetic_sample_is_never_described_as_real() -> None:
    for method in (METHOD_BASELINE, METHOD_RESEARCH_V2):
        result = _sample(method)
        provenance = result["provenance"]
        assert provenance["data_mode"] == "SYNTHETIC RESEARCH TEST"
        assert "fictional" in provenance["source_label"].lower()
        assert any(
            "fictional" in warning.lower() for warning in provenance["warnings"]
        )
