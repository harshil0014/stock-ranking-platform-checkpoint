"""Transactional accepted-state management for autonomous market-data refreshes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping
from uuid import uuid4

import pandas as pd

from stock_ranker.live_market import (
    ORDINARY_EQUITY_CONTRACT_VERSION,
    LiveMarketBundle,
    load_live_market_bundle,
)


DATA_STATE_VERSION = "indian_equity_data_state_v1"


@dataclass(frozen=True, slots=True)
class DataStatePaths:
    root: Path
    accepted_pointer: Path
    last_attempt: Path
    snapshots: Path
    staging: Path
    raw: Path
    lock: Path
    legacy_current: Path

    @classmethod
    def from_root(cls, root: str | Path) -> "DataStatePaths":
        resolved = Path(root).resolve()
        return cls(
            root=resolved,
            accepted_pointer=resolved / "accepted_state.json",
            last_attempt=resolved / "last_refresh_attempt.json",
            snapshots=resolved / "snapshots",
            staging=resolved / "staging",
            raw=resolved / "evidence" / "raw",
            lock=resolved / "refresh.lock",
            legacy_current=resolved / "current",
        )


@dataclass(frozen=True, slots=True)
class RefreshLock:
    path: Path
    token: str


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def atomic_write_json(path: str | Path, value: Any) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    temporary.write_bytes(canonical_json_bytes(value))
    temporary.replace(destination)


def validate_download_payload(
    payload: bytes,
    *,
    label: str,
    minimum_bytes: int = 32,
    content_type: str | None = None,
) -> str:
    """Reject empty/truncated/HTML error bodies before they enter raw evidence."""

    if len(payload) < minimum_bytes:
        raise ValueError(f"{label} payload is empty or truncated ({len(payload)} bytes)")
    prefix = payload[:1024].lstrip().lower()
    if prefix.startswith((b"<html", b"<!doctype html")) or b"<title>access denied" in prefix:
        raise ValueError(f"{label} returned HTML instead of data")
    media = (content_type or "").split(";", 1)[0].strip().lower()
    if media in {"text/html", "application/xhtml+xml"}:
        raise ValueError(f"{label} returned HTML content type")
    return sha256(payload).hexdigest()


def immutable_evidence_path(
    paths: DataStatePaths,
    *,
    provider: str,
    effective_date: str,
    filename: str,
) -> Path:
    parsed = date.fromisoformat(effective_date)
    if parsed.isoformat() != effective_date:
        raise ValueError("effective_date must be canonical ISO YYYY-MM-DD")
    safe_provider = provider.strip().lower().replace(" ", "_")
    if not safe_provider or not safe_provider.replace("_", "").isalnum():
        raise ValueError("provider must contain only letters, digits, spaces, or underscores")
    name = Path(filename)
    if name.name != filename or filename in {"", ".", ".."}:
        raise ValueError("evidence filename must be a safe basename")
    return paths.raw / safe_provider / effective_date / filename


def store_immutable_evidence(
    destination: str | Path,
    payload: bytes,
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Store raw evidence once; identical repeats are idempotent, conflicts fail."""

    target = Path(destination)
    digest = sha256(payload).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(f"download hash mismatch for {target.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        existing = sha256(target.read_bytes()).hexdigest()
        if existing != digest:
            raise ValueError(f"immutable evidence conflict: {target}")
        return {"path": str(target), "sha256": digest, "size": len(payload), "status": "ALREADY_PRESENT"}
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(target)
    return {"path": str(target), "sha256": digest, "size": len(payload), "status": "STORED"}


def acquire_refresh_lock(paths: DataStatePaths) -> RefreshLock:
    """Acquire an exclusive process lock without silently deleting another run's lock."""

    paths.root.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    payload = canonical_json_bytes({
        "token": token,
        "pid": os.getpid(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        descriptor = os.open(paths.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"another refresh owns the lock: {paths.lock}") from exc
    try:
        os.write(descriptor, payload)
    finally:
        os.close(descriptor)
    return RefreshLock(paths.lock, token)


def release_refresh_lock(lock: RefreshLock) -> None:
    try:
        content = json.loads(lock.path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return
    if content.get("token") != lock.token:
        raise RuntimeError("refresh lock ownership changed unexpectedly")
    lock.path.unlink()


def _safe_relative_snapshot(pointer: Mapping[str, Any]) -> Path:
    value = pointer.get("bundle_path")
    if not isinstance(value, str) or not value:
        raise ValueError("accepted-state bundle_path is missing")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("accepted-state bundle_path is unsafe")
    return relative


def read_accepted_state(paths: DataStatePaths) -> dict[str, Any] | None:
    if not paths.accepted_pointer.is_file():
        return None
    state = json.loads(paths.accepted_pointer.read_text(encoding="utf-8"))
    if state.get("state_version") != DATA_STATE_VERSION:
        raise ValueError("accepted data-state version is unsupported")
    _safe_relative_snapshot(state)
    return state


def resolve_accepted_bundle_root(root: str | Path) -> Path:
    """Resolve the transactional accepted snapshot, falling back to legacy current."""

    paths = DataStatePaths.from_root(root)
    state = read_accepted_state(paths)
    if state is not None:
        candidate = (paths.root / _safe_relative_snapshot(state)).resolve()
        if paths.snapshots.resolve() not in candidate.parents:
            raise ValueError("accepted snapshot escapes the snapshot store")
        bundle = load_live_market_bundle(candidate)
        if bundle.fingerprint != state.get("bundle_fingerprint"):
            raise ValueError("accepted-state fingerprint does not match its bundle")
        return candidate
    return paths.legacy_current


def record_refresh_attempt(
    paths: DataStatePaths,
    *,
    status: str,
    started_at: str,
    completed_at: str,
    message: str,
    discovered_trade_date: str | None = None,
    bundle_fingerprint: str | None = None,
) -> dict[str, Any]:
    if status not in {"ACCEPTED", "NO_NEW_DATA", "FAILED", "REJECTED"}:
        raise ValueError("invalid refresh-attempt status")
    attempt = {
        "state_version": DATA_STATE_VERSION,
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "discovered_trade_date": discovered_trade_date,
        "bundle_fingerprint": bundle_fingerprint,
        "message": message,
    }
    atomic_write_json(paths.last_attempt, attempt)
    return attempt


def _acceptance_checks(candidate: LiveMarketBundle, previous: LiveMarketBundle | None) -> dict[str, Any]:
    manifest = candidate.manifest
    snapshot = manifest.get("snapshot", {})
    trade_date = date.fromisoformat(str(snapshot.get("trade_date")))
    universe = int(manifest.get("universe_count", 0))
    matched = int(snapshot.get("matched_count", 0))
    if universe < 1 or len(candidate.market) != universe:
        raise ValueError("candidate universe count is inconsistent")
    if matched < 1 or matched > universe:
        raise ValueError("candidate price coverage is invalid")
    if matched / universe < 0.90:
        raise ValueError("candidate price coverage is below the 90% safety floor")
    required = {"ticker", "company", "isin", "listing_date", "snapshot_status", "trade_date"}
    missing = sorted(required.difference(candidate.market.columns))
    if missing:
        raise ValueError(f"candidate is missing canonical columns: {missing}")
    if candidate.market["ticker"].duplicated().any():
        raise ValueError("candidate contains duplicate canonical tickers")
    for column in ("ticker", "company", "isin"):
        values = candidate.market[column].astype("string").str.strip()
        if values.isna().any() or values.eq("").any():
            raise ValueError(f"candidate {column} must be complete")
    if candidate.market["isin"].duplicated().any():
        raise ValueError("candidate contains duplicate ISIN identities")
    if not candidate.market["isin"].astype(str).str.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]").all():
        raise ValueError("candidate contains malformed ISIN identities")
    listing = candidate.market["listing_date"].dropna().astype(str).map(date.fromisoformat)
    if any(item > trade_date for item in listing):
        raise ValueError("candidate contains a listing date after its trade date")
    if trade_date > datetime.now(timezone.utc).date() + timedelta(days=1):
        raise ValueError("candidate trade date is implausibly in the future")
    row_dates = pd.to_datetime(candidate.market["trade_date"], format="%Y-%m-%d", errors="coerce")
    if row_dates.isna().any() or any(item.date() > trade_date for item in row_dates):
        raise ValueError("candidate price dates must be valid and no later than the snapshot date")
    if manifest.get("research_v2_current_ranking_date", trade_date.isoformat()) != trade_date.isoformat():
        raise ValueError("candidate Research V2 current ranking date is inconsistent")
    universe_contract = manifest.get("ranking_universe_contract")
    if universe_contract == ORDINARY_EQUITY_CONTRACT_VERSION:
        required_contract_columns = {
            "ranking_instrument_type", "ranking_universe_eligible",
            "ranking_universe_reason_code", "ranking_universe_contract",
        }
        contract_missing = sorted(required_contract_columns.difference(candidate.market.columns))
        if contract_missing:
            raise ValueError(f"ordinary-equity candidate is missing contract columns: {contract_missing}")
        if not candidate.market["ranking_universe_eligible"].astype(bool).all():
            raise ValueError("ordinary-equity candidate contains an ineligible instrument")
        if not candidate.market["ranking_instrument_type"].eq("ORDINARY_COMPANY_EQUITY").all():
            raise ValueError("ordinary-equity candidate contains a non-company instrument")
        if not candidate.market["ranking_universe_reason_code"].eq("ELIGIBLE_ORDINARY_EQUITY").all():
            raise ValueError("ordinary-equity candidate contains an invalid eligibility decision")
        if not candidate.market["ranking_universe_contract"].eq(ORDINARY_EQUITY_CONTRACT_VERSION).all():
            raise ValueError("ordinary-equity candidate mixes universe-contract versions")
        inventory_paths = {str(item.get("path")) for item in manifest.get("files", [])}
        if "ranking_universe_exclusions.csv" not in inventory_paths:
            raise ValueError("ordinary-equity candidate lacks its exclusion audit artifact")
    if previous is not None:
        previous_date = date.fromisoformat(str(previous.manifest["snapshot"]["trade_date"]))
        if trade_date < previous_date:
            raise ValueError("candidate trade date is older than the accepted state")
        previous_universe = int(previous.manifest["universe_count"])
        contract_migration = (
            universe_contract == ORDINARY_EQUITY_CONTRACT_VERSION
            and previous.manifest.get("ranking_universe_contract") != universe_contract
        )
        if universe < int(previous_universe * 0.90) and not contract_migration:
            raise ValueError("candidate universe unexpectedly shrank by more than 10%")
        previous_classified = int(previous.manifest.get("classified_count", 0))
        classified = int(manifest.get("classified_count", 0))
        if previous_classified and classified < int(previous_classified * 0.90):
            raise ValueError("candidate classification coverage unexpectedly collapsed")
        previous_baseline = int(previous.manifest.get("baseline_eligible_count", 0))
        baseline = int(manifest.get("baseline_eligible_count", 0))
        if previous_baseline and baseline < int(previous_baseline * 0.80):
            raise ValueError("candidate Baseline eligibility unexpectedly collapsed")
        previous_v2 = int(previous.manifest.get("research_v2_eligible_count", 0))
        current_v2 = int(manifest.get("research_v2_eligible_count", 0))
        if previous_v2 and current_v2 < int(previous_v2 * 0.80):
            raise ValueError("candidate Research V2 eligibility unexpectedly collapsed")
        previous_v2_evidence = previous.manifest.get("research_v2_frozen_evidence_fingerprint")
        candidate_v2_evidence = manifest.get("research_v2_frozen_evidence_fingerprint")
        if previous_v2_evidence and candidate_v2_evidence != previous_v2_evidence:
            raise ValueError("candidate changed the frozen Research V2 evidence fingerprint")
    return {
        "trade_date": trade_date.isoformat(),
        "universe_count": universe,
        "price_ready": matched,
        "price_coverage": matched / universe,
        "classified_count": int(manifest.get("classified_count", 0)),
        "baseline_eligible_count": int(manifest.get("baseline_eligible_count", 0)),
        "research_v2_eligible_count": int(manifest.get("research_v2_eligible_count", 0)),
    }


def promote_candidate_bundle(
    paths: DataStatePaths,
    candidate_directory: str | Path,
    *,
    accepted_at: str | None = None,
) -> dict[str, Any]:
    """Validate and atomically point readers to a complete immutable snapshot."""

    candidate_path = Path(candidate_directory).resolve()
    candidate = load_live_market_bundle(candidate_path)
    previous: LiveMarketBundle | None = None
    try:
        previous_root = resolve_accepted_bundle_root(paths.root)
        if previous_root.is_dir():
            previous = load_live_market_bundle(previous_root)
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
        previous = None
    checks = _acceptance_checks(candidate, previous)
    destination = paths.snapshots / f"{checks['trade_date']}-{candidate.fingerprint}"
    paths.snapshots.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        existing = load_live_market_bundle(destination)
        if existing.fingerprint != candidate.fingerprint:
            raise ValueError("existing immutable snapshot conflicts with candidate")
        if candidate_path != destination:
            shutil.rmtree(candidate_path)
    else:
        if paths.staging.resolve() not in candidate_path.parents:
            raise ValueError("candidate must be beneath the configured staging directory")
        candidate_path.replace(destination)
    accepted_timestamp = accepted_at or datetime.now(timezone.utc).isoformat()
    pointer = {
        "state_version": DATA_STATE_VERSION,
        "accepted_at": accepted_timestamp,
        "trade_date": checks["trade_date"],
        "bundle_path": destination.relative_to(paths.root).as_posix(),
        "bundle_fingerprint": candidate.fingerprint,
        "checks": checks,
        "previous_bundle_fingerprint": previous.fingerprint if previous is not None else None,
        "frozen_research_unchanged": True,
    }
    atomic_write_json(paths.accepted_pointer, pointer)
    return pointer


def data_state_status(root: str | Path) -> dict[str, Any]:
    paths = DataStatePaths.from_root(root)
    state = read_accepted_state(paths)
    attempt = None
    if paths.last_attempt.is_file():
        attempt = json.loads(paths.last_attempt.read_text(encoding="utf-8"))
    bundle_root = resolve_accepted_bundle_root(paths.root)
    bundle = load_live_market_bundle(bundle_root)
    snapshot = bundle.manifest["snapshot"]
    today = datetime.now(timezone.utc).date()
    trade_date = date.fromisoformat(str(snapshot["trade_date"]))
    return {
        "state_version": DATA_STATE_VERSION,
        "accepted_state": state,
        "last_refresh_attempt": attempt,
        "serving_bundle_path": str(bundle_root),
        "bundle_fingerprint": bundle.fingerprint,
        "trade_date": trade_date.isoformat(),
        "age_calendar_days": max(0, (today - trade_date).days),
        "serving_last_known_good": bool(attempt and attempt.get("status") in {"FAILED", "REJECTED"}),
    }
