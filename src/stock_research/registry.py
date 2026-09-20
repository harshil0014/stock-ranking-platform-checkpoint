"""Open-source model and feature registry validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from stock_research.errors import Diagnostic, ResearchValidationError


ALLOWED_STATUSES = {
    "provenance_verified",
    "adoption_specified",
    "environment_verified",
    "synthetic_reproduced",
}
REQUIRED_FIELDS = {
    "id", "name", "kind", "official_source", "paper", "release",
    "code_license", "dataset_license_status", "inputs", "outputs", "metrics",
    "dependencies", "role", "adoption_status", "risks", "citations",
    "verification_date",
}


@dataclass(frozen=True, slots=True)
class Registry:
    schema_version: str
    entries: tuple[dict[str, Any], ...]

    @property
    def model_ids(self) -> set[str]:
        return {
            entry["id"] for entry in self.entries
            if entry.get("kind") in {"model", "baseline", "framework"}
        }


@dataclass(frozen=True, slots=True)
class ExecutionRegistry:
    """Capability registry used by the common model execution layer."""

    schema_version: str
    entries: tuple[dict[str, Any], ...]

    @property
    def model_ids(self) -> set[str]:
        return {entry["id"] for entry in self.entries}

    def get(self, model_id: str) -> dict[str, Any]:
        matches = [entry for entry in self.entries if entry["id"] == model_id]
        if not matches:
            raise KeyError(model_id)
        return dict(matches[0])


def validate_execution_registry(value: str | Path | dict[str, Any]) -> ExecutionRegistry:
    """Validate model capabilities without importing any model dependency."""

    if isinstance(value, (str, Path)):
        try:
            raw = json.loads(Path(value).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ResearchValidationError(Diagnostic("invalid_execution_registry", str(exc))) from exc
    else:
        raw = value
    if not isinstance(raw, dict) or raw.get("schema_version") != "model_execution_registry_v1":
        raise ResearchValidationError(Diagnostic("execution_registry_schema", "unexpected schema version"))
    entries = raw.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ResearchValidationError(Diagnostic("execution_registry_entries", "entries must be nonempty"))
    required = {
        "id", "display_name", "implementation_kind", "required_features",
        "optional_features", "training_required", "supported_frequencies",
        "status", "upstream_reference", "pit_policy", "output_contract",
    }
    seen = set()
    allowed_statuses = {"specified", "adapter_ready", "synthetic_reproduced", "blocked", "verified"}
    for row, entry in enumerate(entries):
        if not isinstance(entry, dict) or required - set(entry):
            missing = sorted(required - set(entry)) if isinstance(entry, dict) else sorted(required)
            raise ResearchValidationError(Diagnostic("execution_registry_fields", f"missing fields: {missing}", row))
        model_id = entry["id"]
        if not isinstance(model_id, str) or not model_id.strip() or model_id in seen:
            raise ResearchValidationError(Diagnostic("execution_registry_id", f"invalid or duplicate id: {model_id}", row))
        seen.add(model_id)
        if entry["status"] not in allowed_statuses:
            raise ResearchValidationError(Diagnostic("execution_registry_status", "invalid status", row))
        features = entry["required_features"]
        if not isinstance(features, list) or not features:
            raise ResearchValidationError(Diagnostic("execution_registry_features", "required_features must be nonempty", row))
        names = []
        for feature in features:
            if not isinstance(feature, dict) or not isinstance(feature.get("name"), str) or not feature["name"].strip():
                raise ResearchValidationError(Diagnostic("execution_registry_feature", "malformed feature requirement", row))
            names.append(feature["name"])
        if len(names) != len(set(names)):
            raise ResearchValidationError(Diagnostic("execution_registry_feature", "duplicate feature requirement", row))
        if not isinstance(entry["training_required"], bool):
            raise ResearchValidationError(Diagnostic("execution_registry_training", "training_required must be boolean", row))
        if not isinstance(entry["pit_policy"], str) or "current_only" not in entry["pit_policy"]:
            raise ResearchValidationError(Diagnostic("execution_registry_pit_policy", "PIT policy must address current_only evidence", row))
        if entry["output_contract"] != "canonical_signals_v1":
            raise ResearchValidationError(Diagnostic("execution_registry_output", "unsupported output contract", row))
    return ExecutionRegistry(raw["schema_version"], tuple(entries))


def validate_registry(value: str | Path | dict[str, Any]) -> Registry:
    if isinstance(value, (str, Path)):
        try:
            raw = json.loads(Path(value).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ResearchValidationError(
                Diagnostic("invalid_registry_json", str(exc))
            ) from exc
    else:
        raw = value
    if not isinstance(raw, dict) or not isinstance(raw.get("schema_version"), str):
        raise ResearchValidationError(
            Diagnostic("registry_schema", "schema_version must be a string")
        )
    entries = raw.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ResearchValidationError(
            Diagnostic("registry_entries", "entries must be a nonempty list")
        )
    seen: set[str] = set()
    for row, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ResearchValidationError(
                Diagnostic("registry_entry", "entry must be an object", row)
            )
        missing = sorted(REQUIRED_FIELDS.difference(entry))
        if missing:
            raise ResearchValidationError(
                Diagnostic("registry_fields", f"missing fields: {missing}", row)
            )
        identifier = entry["id"]
        if not isinstance(identifier, str) or not identifier.strip():
            raise ResearchValidationError(
                Diagnostic("registry_id", "id must be nonblank", row)
            )
        if identifier in seen:
            raise ResearchValidationError(
                Diagnostic("registry_duplicate_id", f"duplicate id: {identifier}", row)
            )
        seen.add(identifier)
        if entry["adoption_status"] not in ALLOWED_STATUSES:
            raise ResearchValidationError(
                Diagnostic("registry_status", "invalid adoption_status", row)
            )
        if entry["adoption_status"] in {
            "environment_verified", "synthetic_reproduced"
        }:
            evidence = entry.get("local_evidence")
            if not isinstance(evidence, dict) or not str(
                evidence.get("scope", "")
            ).strip():
                raise ResearchValidationError(
                    Diagnostic(
                        "registry_local_evidence",
                        "verified/reproduced status requires scoped local_evidence",
                        row,
                    )
                )
        source = entry["official_source"]
        if not isinstance(source, dict) or not source.get("url"):
            raise ResearchValidationError(
                Diagnostic("registry_source", "official_source requires url", row)
            )
        release = entry["release"]
        if not isinstance(release, dict) or not {
            "version", "commit"
        }.issubset(release):
            raise ResearchValidationError(
                Diagnostic("registry_release", "release requires version and commit", row)
            )
        try:
            datetime.strptime(entry["verification_date"], "%Y-%m-%d")
        except (TypeError, ValueError) as exc:
            raise ResearchValidationError(
                Diagnostic("registry_date", "verification_date must be ISO date", row)
            ) from exc
        for field in ("inputs", "outputs", "metrics", "dependencies", "risks", "citations"):
            if not isinstance(entry[field], list):
                raise ResearchValidationError(
                    Diagnostic("registry_field_type", f"{field} must be a list", row)
                )
        if not isinstance(entry["code_license"], dict) or not {
            "name", "status"
        }.issubset(entry["code_license"]):
            raise ResearchValidationError(
                Diagnostic("registry_license", "structured code_license required", row)
            )
    return Registry(raw["schema_version"], tuple(entries))
