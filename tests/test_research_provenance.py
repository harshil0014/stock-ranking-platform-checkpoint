from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.errors import ResearchValidationError
from stock_research.fingerprints import (
    fingerprint_config, fingerprint_dataframe, fingerprint_file
)
from stock_research.manifests import (
    load_manifest, transition_manifest, validate_manifest
)
from stock_research.registry import validate_registry


ROOT = Path(__file__).parents[1]


def test_registry_is_valid_and_contains_separate_alpha_handlers():
    registry = validate_registry(
        ROOT / "research/registry/open_source_registry.json"
    )
    identifiers = {entry["id"] for entry in registry.entries}
    assert {"qlib_alpha158", "qlib_alpha360", "qlib_linear"} <= identifiers
    assert all(
        entry["adoption_status"] != "reproduced" for entry in registry.entries
    )
    statuses = {
        entry["id"]: entry["adoption_status"] for entry in registry.entries
    }
    assert statuses["qlib_framework"] == "environment_verified"
    assert statuses["qlib_linear"] == "synthetic_reproduced"
    linear = next(
        entry for entry in registry.entries if entry["id"] == "qlib_linear"
    )
    assert "synthetic-only" in linear["local_evidence"]["scope"]
    assert "not real-market validation" in linear["local_evidence"]["scope"]


def test_registry_rejects_duplicate_ids():
    raw = json.loads(
        (ROOT / "research/registry/open_source_registry.json").read_text()
    )
    raw["entries"].append(raw["entries"][0])
    with pytest.raises(ResearchValidationError, match="registry_duplicate_id"):
        validate_registry(raw)


def test_verified_registry_status_requires_scoped_local_evidence():
    raw = json.loads(
        (ROOT / "research/registry/open_source_registry.json").read_text()
    )
    framework = next(
        entry for entry in raw["entries"] if entry["id"] == "qlib_framework"
    )
    framework.pop("local_evidence")
    with pytest.raises(ResearchValidationError, match="registry_local_evidence"):
        validate_registry(raw)


def test_fingerprints_are_deterministic_and_sensitive(tmp_path):
    assert fingerprint_config({"b": 2, "a": 1}) == fingerprint_config(
        {"a": 1, "b": 2}
    )
    first = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    second = first.iloc[::-1].reset_index(drop=True)
    assert fingerprint_dataframe(first) != fingerprint_dataframe(second)
    path = tmp_path / "x.txt"
    path.write_text("x")
    before = fingerprint_file(path)
    path.write_text("y")
    assert before != fingerprint_file(path)


def test_planned_manifest_is_valid_and_not_fabricated():
    manifest = load_manifest(
        ROOT / "research/manifests/planned_qlib_linear.json"
    )
    assert manifest["status"] == "planned"
    assert "No model was trained" in manifest["notes"]


def test_manifest_status_rules_and_artifact_fingerprint(tmp_path):
    manifest = json.loads(
        (ROOT / "research/manifests/planned_qlib_linear.json").read_text()
    )
    running = transition_manifest(manifest, "running")
    with pytest.raises(ResearchValidationError, match="failure reason"):
        transition_manifest(running, "failed")
    failed = transition_manifest(running, "failed", failure_reason="fixture failure")
    assert failed["status"] == "failed"
    artifact = tmp_path / "summary.json"
    artifact.write_text("{}")
    completed = transition_manifest(
        running, "completed",
        evaluation_artifacts=[{
            "path": str(artifact), "sha256": fingerprint_file(artifact)
        }],
    )
    assert validate_manifest(completed)["status"] == "completed"
