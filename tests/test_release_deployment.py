import json
from pathlib import Path

from marketdata.runners.verify_release import verify
from stock_ranker.live_website import deployment_health


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_release_manifest_matches_runtime_evidence() -> None:
    result = verify(ROOT / "release/validated_state_20260920.json", ROOT / "data")
    assert result["status"] == "VERIFIED"
    assert result["universe_count"] == 4436


def test_deployment_health_is_a_real_readiness_check() -> None:
    health = deployment_health()
    assert health["status"] == "ok"
    assert health["ready"] is True
    assert health["ranked_count"] == 4436
    assert health["remaining_missing_cells"] == 0


def test_permanent_host_configuration_is_read_only_and_pinned() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    lock = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    assert "read_only: true" in compose
    assert ":ro" in compose
    assert "cap_drop" in compose
    assert "verify_release.py" in dockerfile
    assert "--host 0.0.0.0" in dockerfile
    assert "STOCK_RANKER_PROJECT_ROOT=/app" in dockerfile
    assert "pandas==3.0.5" in lock
    state = json.loads((ROOT / "release/validated_state_20260920.json").read_text())
    assert state["post_hoc_judgments_added"] is False
