"""Structured errors for research contracts and workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any


@dataclass(frozen=True, slots=True)
class Diagnostic:
    rule_id: str
    message: str
    row: int | None = None
    key: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResearchValidationError(ValueError):
    """A validation failure with deterministic machine-readable diagnostics."""

    def __init__(self, diagnostics: Diagnostic | list[Diagnostic]):
        self.diagnostics = (
            diagnostics if isinstance(diagnostics, list) else [diagnostics]
        )
        super().__init__("; ".join(
            f"{item.rule_id}: {item.message}" for item in self.diagnostics
        ))

    def as_json(self) -> str:
        return json.dumps(
            [item.as_dict() for item in self.diagnostics],
            sort_keys=True,
            separators=(",", ":"),
        )
