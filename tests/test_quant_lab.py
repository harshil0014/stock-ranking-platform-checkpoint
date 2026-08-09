from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

import pandas as pd
import pytest

from stock_ranker import research_website
from stock_ranker.webapp import create_server
from stock_research.quant_lab import QuantLabPaths, build_alphalens_adapter, validate_quant_lab_artifacts


ROOT = Path(__file__).resolve().parents[1]
QUANT_ROOT = ROOT / "research/generated/quantlab/real-frozen-v1"


def test_real_alphalens_adapter_is_exact_deterministic_and_leakage_safe() -> None:
    paths = QuantLabPaths(
        ROOT / "data/walk_forward/blind_predictions_v1_run_01",
        ROOT / "data/walk_forward/evaluation_v1_run_01",
        ROOT / "data/marketdata/nifty50-research-v2-2026-08-07/standalone-contract-reason-fix-run-01",
        QUANT_ROOT,
    )
    first = build_alphalens_adapter(paths)
    second = build_alphalens_adapter(paths)
    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 216
    assert set(first["horizon_months"]) == {3, 6, 12}
    assert set(first["alphalens_period"]) == {"90D", "180D", "365D"}
    assert not first.duplicated(["ranking_date", "ticker", "model", "horizon_months"]).any()
    assert (pd.to_datetime(first["actual_endpoint_date"]) > pd.to_datetime(first["ranking_date"])).all()


def test_adapter_rejects_future_endpoint_at_or_before_signal_date(tmp_path: Path) -> None:
    blind = tmp_path / "blind" / "2025-01-01"
    evaluation = tmp_path / "evaluation"
    blind.mkdir(parents=True)
    evaluation.mkdir()
    pd.DataFrame([{"ticker": "AAA", "historical_sector": "S", "research_v2_score": 50, "sector_rank": 1}]).to_csv(blind / "research_v2.csv", index=False)
    pd.DataFrame([{"ticker": "AAA", "historical_sector": "S", "matched_baseline_sector_rank": 1}]).to_csv(blind / "matched_baseline.csv", index=False)
    pd.DataFrame([{"ranking_date": "2025-01-01", "ticker": "AAA", "horizon_months": 3, "actual_endpoint_date": "2025-01-01", "future_adjusted_return": 0.1}]).to_csv(evaluation / "future_returns.csv", index=False)
    with pytest.raises(ValueError, match="endpoint"):
        build_alphalens_adapter(QuantLabPaths(tmp_path / "blind", evaluation, tmp_path, tmp_path))


def test_real_quant_lab_artifacts_are_hash_valid_and_match_frozen_evaluator() -> None:
    summary = validate_quant_lab_artifacts(QUANT_ROOT)
    assert summary["alphalens"] == {
        "adapter_rows": 216,
        "differences": 0,
        "exact_ic_matches": 18,
        "ic_rows": 18,
        "quantile_status": "DESCRIPTIVE_SMALL_COHORT",
        "status": "VERIFIED",
        "turnover_status": "DEFERRED_SPARSE_ANNUAL_OBSERVATIONS",
    }
    assert summary["empyrical"]["passes"] == 68
    assert summary["empyrical"]["explained_differences"] == 34
    assert summary["empyrical"]["failures"] == 0


def test_empyrical_audit_has_semantic_boundary_and_representative_stocks() -> None:
    audit = pd.read_csv(QUANT_ROOT / "empyrical_metric_audit.csv")
    assert {"RELIANCE", "HINDUNILVR"}.issubset(set(audit["ticker"]))
    equivalent = audit.loc[audit["definition_equivalent"]]
    assert set(equivalent["status"]) == {"PASS"}
    assert equivalent["absolute_difference"].max() <= 1e-12
    assert set(audit.loc[~audit["definition_equivalent"], "status"]) == {"EXPLAINED_DIFFERENCE"}


def test_portfolio_and_quantstats_are_honestly_deferred() -> None:
    portfolio = json.loads((QUANT_ROOT / "portfolio_feasibility.json").read_text(encoding="utf-8"))
    quantstats = json.loads((QUANT_ROOT / "quantstats_status.json").read_text(encoding="utf-8"))
    assert portfolio["status"] == "EXPERIMENTAL_DEFERRED"
    assert portfolio["ranking_inputs_modified"] is False
    assert portfolio["future_information_used"] is False
    assert quantstats["status"] == "DEFERRED"


def test_quant_lab_website_payload_is_artifact_backed_and_attributed() -> None:
    data = research_website.quant_lab()
    assert data["available"] is True
    assert data["alphalens"]["exact_ic_matches"] == 18
    assert data["empyrical"]["passes"] == 68
    assert {item["license"] for item in data["integrations"]} >= {"Apache-2.0", "BSD-3-Clause", "MIT"}
    assert all(item["core_ranking"] is False for item in data["integrations"])
    rendered = json.dumps(data).lower()
    assert "secondary independent analysis" in rendered
    assert "universal winner" not in rendered


def test_quant_lab_http_route_serves_validated_payload() -> None:
    server = create_server(port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_address[1]}/api/research/quant-lab") as response:
            data = json.loads(response.read())
        assert response.status == 200
        assert data["alphalens"]["differences"] == 0
        assert data["quantstats"]["status"] == "DEFERRED"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_product_modules_do_not_import_optional_quant_libraries() -> None:
    for path in [ROOT / "src/stock_research/quant_lab.py", ROOT / "src/stock_ranker/research_website.py"]:
        source = path.read_text(encoding="utf-8")
        for name in ("import alphalens", "import empyrical", "import skfolio", "import quantstats"):
            assert name not in source
    assert importlib.util.find_spec("alphalens") is None
    assert importlib.util.find_spec("empyrical") is None
    assert importlib.util.find_spec("skfolio") is None
    assert importlib.util.find_spec("quantstats") is None


def test_frozen_research_identities_are_unchanged() -> None:
    assert research_website.PROTOCOL_SHA256 == "a81278b799e1a61c3684f3b319fb14e2f6f0db6a2bdad1cd79b2ce13fd6f8576"
    assert research_website.AMENDMENT_SHA256 == "7f8c5d40de88077f3b6afcd471d0db4377fab567d2839e719a71ee6b11ae7163"
    assert research_website.BLIND_FINGERPRINT == "c438c31967e1f2685bbe77d85db6ca44617e024c699dba3749ee3523af6e401d"
    assert research_website.EVALUATION_FINGERPRINT == "04e29e8a0f641f900e2ef5ca6d6fe5252b75eff9b23a69fba3b6480f373606c1"
