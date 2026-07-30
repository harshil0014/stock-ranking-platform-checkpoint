"""Open-source model and feature registry validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from stock_research.errors import Diagnostic, ResearchValidationError


ALLOWED_STATUSES = {"provenance_verified", "adoption_specified"}
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
