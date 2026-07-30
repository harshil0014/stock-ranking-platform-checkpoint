"""Schema-versioned experiment manifests and lifecycle validation."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any
from uuid import UUID, uuid4

from stock_research.errors import Diagnostic, ResearchValidationError
from stock_research.fingerprints import fingerprint_file


STATUSES = {"planned", "running", "completed", "failed", "abandoned"}
TRANSITIONS = {
    "planned": {"running"},
    "running": {"completed", "failed", "abandoned"},
    "completed": set(),
    "failed": set(),
    "abandoned": set(),
}
MANIFEST_REQUIRED = {
    "schema_version", "run_id", "model_id", "status", "created_at",
    "source_commit", "worktree_status", "model_configuration",
    "model_configuration_fingerprint", "datasets", "splits", "seeds",
    "parameters", "paths", "evaluation_protocol",
    "evaluation_protocol_fingerprint", "notes",
}


def repository_state(cwd: str | Path | None = None) -> dict[str, str]:
    def run(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
        ).stdout.strip()
    return {
        "branch": run("branch", "--show-current"),
        "source_commit": run("rev-parse", "HEAD"),
        "worktree_status": run("status", "--short"),
    }


def _valid_uuid(value: str) -> bool:
    try:
        return str(UUID(value, version=4)) == value.lower()
    except (ValueError, AttributeError):
        return False


def validate_manifest(
    manifest: dict[str, Any],
    *,
    manifest_directory: str | Path | None = None,
) -> dict[str, Any]:
    missing = sorted(MANIFEST_REQUIRED.difference(manifest))
    if missing:
        raise ResearchValidationError(
            Diagnostic("manifest_fields", f"missing fields: {missing}")
        )
    if not _valid_uuid(manifest["run_id"]):
        raise ResearchValidationError(
            Diagnostic("manifest_run_id", "run_id must be UUID4")
        )
    status = manifest["status"]
    if status not in STATUSES:
        raise ResearchValidationError(
            Diagnostic("manifest_status", f"invalid status: {status}")
        )
    if status in {"failed", "abandoned"} and not str(
        manifest.get("failure_reason", "")
    ).strip():
        raise ResearchValidationError(
            Diagnostic("manifest_failure_reason", "failure reason is required")
        )
    if manifest_directory is not None:
        directory = Path(manifest_directory)
        duplicates = []
        for path in directory.glob("*.json"):
            try:
                other = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if other.get("run_id") == manifest["run_id"]:
                duplicates.append(path)
        if len(duplicates) > 1:
            raise ResearchValidationError(
                Diagnostic("duplicate_run_id", f"run_id appears in {len(duplicates)} files")
            )
    if status == "completed":
        artifacts = manifest.get("evaluation_artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ResearchValidationError(
                Diagnostic("completed_artifacts", "completed run requires artifacts")
            )
        for artifact in artifacts:
            path = Path(artifact.get("path", ""))
            expected = artifact.get("sha256")
            if not path.is_file() or not expected or fingerprint_file(path) != expected:
                raise ResearchValidationError(
                    Diagnostic("artifact_fingerprint", f"invalid artifact: {path}")
                )
    return deepcopy(manifest)


def load_manifest(path: str | Path) -> dict[str, Any]:
    try:
        manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchValidationError(
            Diagnostic("invalid_manifest_json", str(exc))
        ) from exc
    return validate_manifest(manifest)


def create_manifest(
    *,
    model_id: str,
    model_configuration: dict[str, Any],
    model_configuration_fingerprint: str,
    datasets: dict[str, Any],
    splits: dict[str, Any],
    seeds: dict[str, Any],
    parameters: dict[str, Any],
    paths: dict[str, Any],
    evaluation_protocol: dict[str, Any],
    evaluation_protocol_fingerprint: str,
    notes: str = "",
    run_id: str | None = None,
    status: str = "planned",
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    state = repository_state(repository_root)
    manifest = {
        "schema_version": "1.0",
        "run_id": run_id or str(uuid4()),
        "model_id": model_id,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": state["source_commit"],
        "worktree_status": state["worktree_status"],
        "model_configuration": model_configuration,
        "model_configuration_fingerprint": model_configuration_fingerprint,
        "datasets": datasets,
        "splits": splits,
        "seeds": seeds,
        "parameters": parameters,
        "paths": paths,
        "evaluation_protocol": evaluation_protocol,
        "evaluation_protocol_fingerprint": evaluation_protocol_fingerprint,
        "notes": notes,
    }
    return validate_manifest(manifest)


def transition_manifest(
    manifest: dict[str, Any],
    new_status: str,
    *,
    failure_reason: str | None = None,
    evaluation_artifacts: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    current = manifest.get("status")
    if new_status not in TRANSITIONS.get(current, set()):
        raise ResearchValidationError(
            Diagnostic("manifest_transition", f"invalid transition {current} -> {new_status}")
        )
    changed = deepcopy(manifest)
    changed["status"] = new_status
    if failure_reason is not None:
        changed["failure_reason"] = failure_reason
    if evaluation_artifacts is not None:
        changed["evaluation_artifacts"] = evaluation_artifacts
    return validate_manifest(changed)


def write_manifest(manifest: dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target
