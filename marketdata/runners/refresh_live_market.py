"""Autonomously refresh the accepted current-product snapshot from free public data."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4
from zoneinfo import ZoneInfo
from zipfile import BadZipFile, ZipFile


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
RUNNERS = ROOT / "marketdata" / "runners"
for item in (SRC, RUNNERS):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import prepare_live_market  # noqa: E402
from stock_ranker.data_state import (  # noqa: E402
    DataStatePaths,
    acquire_refresh_lock,
    data_state_status,
    immutable_evidence_path,
    promote_candidate_bundle,
    record_refresh_attempt,
    release_refresh_lock,
    resolve_accepted_bundle_root,
    store_immutable_evidence,
    validate_download_payload,
)
from stock_ranker.live_market import load_live_market_bundle  # noqa: E402


DEFAULT_STATE_ROOT = ROOT / "data" / "live_market"
USER_AGENT = "stock-ranking-platform/1.0 college-research offline-first"
NSE_CURRENT_SOURCES = prepare_live_market.OFFICIAL_SOURCE_URLS
NSE_BHAVCOPY = (
    "https://nsearchives.nseindia.com/content/cm/"
    "BhavCopy_NSE_CM_0_0_0_{compact}_F_0000.csv.zip"
)
BSE_BHAVCOPY = (
    "https://www.bseindia.com/download/BhavCopy/Equity/"
    "BhavCopy_BSE_CM_0_0_0_{compact}_F_0000.csv"
)
NSE_FULL_BHAVCOPY = (
    "https://nsearchives.nseindia.com/products/content/"
    "sec_bhavdata_full_{daymonthyear}.csv"
)


def candidate_trade_dates(today: date, lookback_days: int) -> list[str]:
    if lookback_days < 1 or lookback_days > 31:
        raise ValueError("lookback_days must be from 1 through 31")
    return [
        (today - timedelta(days=offset)).isoformat()
        for offset in range(lookback_days)
        if (today - timedelta(days=offset)).weekday() < 5
    ]


def _download(url: str, *, attempts: int, maximum_bytes: int = 150_000_000) -> tuple[bytes, str | None]:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/csv,application/zip,application/octet-stream,*/*",
                "Cache-Control": "no-cache",
            })
            with urlopen(request, timeout=60) as response:
                length = response.headers.get("Content-Length")
                if length and int(length) > maximum_bytes:
                    raise ValueError("source payload exceeds the configured safety limit")
                payload = response.read(maximum_bytes + 1)
                content_type = response.headers.get("Content-Type")
            if len(payload) > maximum_bytes:
                raise ValueError("source payload exceeds the configured safety limit")
            validate_download_payload(payload, label=url, content_type=content_type)
            return payload, content_type
        except (HTTPError, URLError, OSError, TimeoutError, ValueError) as exc:
            last = exc
            if attempt < attempts:
                time.sleep(min(2 ** (attempt - 1), 4))
    assert last is not None
    raise ValueError(f"download failed after {attempts} attempts: {type(last).__name__}: {last}")


def _validate_nse_bhavcopy(payload: bytes, trade_date: str) -> None:
    from io import BytesIO

    try:
        with ZipFile(BytesIO(payload)) as archive:
            files = [item for item in archive.infolist() if not item.is_dir()]
            if len(files) != 1 or not files[0].filename.lower().endswith(".csv"):
                raise ValueError("NSE bhavcopy ZIP must contain exactly one CSV")
            sample = archive.read(files[0])[:4096]
    except BadZipFile as exc:
        raise ValueError("NSE bhavcopy payload is not a valid ZIP") from exc
    if b"TradDt" not in sample or trade_date.encode("ascii") not in sample:
        raise ValueError("NSE bhavcopy schema/date validation failed")


def _validate_csv(payload: bytes, required_headers: tuple[str, ...], label: str) -> None:
    first = payload.splitlines()[0].decode("utf-8-sig", errors="strict")
    columns = {item.strip().strip('"') for item in first.split(",")}
    missing = sorted(set(required_headers).difference(columns))
    if missing:
        raise ValueError(f"{label} CSV is missing required columns: {missing}")


def discover_latest_nse_bhavcopy(
    paths: DataStatePaths,
    *,
    today: date,
    lookback_days: int,
    attempts: int,
) -> tuple[str, Path, list[dict[str, str]]]:
    failures: list[dict[str, str]] = []
    for trade_date in candidate_trade_dates(today, lookback_days):
        compact = trade_date.replace("-", "")
        destination = immutable_evidence_path(
            paths, provider="nse", effective_date=trade_date,
            filename=f"bhavcopy_{compact}.zip",
        )
        if destination.is_file():
            _validate_nse_bhavcopy(destination.read_bytes(), trade_date)
            return trade_date, destination, failures
        try:
            payload, _ = _download(NSE_BHAVCOPY.format(compact=compact), attempts=attempts)
            _validate_nse_bhavcopy(payload, trade_date)
            store_immutable_evidence(destination, payload)
            return trade_date, destination, failures
        except ValueError as exc:
            failures.append({"trade_date": trade_date, "reason": str(exc)})
    raise ValueError("no valid official NSE bhavcopy found in the discovery window")


def _materialize_nse_sources(
    paths: DataStatePaths,
    trade_date: str,
    bhavcopy: Path,
    *,
    attempts: int,
) -> tuple[Path, list[dict[str, object]]]:
    source = paths.raw / "nse" / trade_date
    records: list[dict[str, object]] = []
    for filename, url in NSE_CURRENT_SOURCES.items():
        destination = immutable_evidence_path(
            paths, provider="nse", effective_date=trade_date, filename=filename,
        )
        if destination.is_file():
            payload = destination.read_bytes()
            status = "ALREADY_PRESENT"
        else:
            payload, content_type = _download(url, attempts=attempts)
            _validate_csv(payload, ("SYMBOL", "ISIN NUMBER") if filename == "equity.csv" else ("Symbol", "ISIN Code"), filename)
            status = store_immutable_evidence(destination, payload)["status"]
            del content_type
        records.append({"filename": filename, "url": url, "size": len(payload), "status": status})
    if bhavcopy.parent != source:
        raise ValueError("discovered NSE bhavcopy is outside its immutable evidence directory")
    return source, records


def _attempt_bse_evidence(
    paths: DataStatePaths,
    trade_date: str,
    *,
    attempts: int,
) -> dict[str, object]:
    compact = trade_date.replace("-", "")
    destination = immutable_evidence_path(
        paths, provider="bse", effective_date=trade_date,
        filename=f"bhavcopy_{compact}.csv",
    )
    try:
        if destination.is_file():
            payload = destination.read_bytes()
            status = "ALREADY_PRESENT"
        else:
            payload, _ = _download(BSE_BHAVCOPY.format(compact=compact), attempts=attempts)
            _validate_csv(payload, ("TradDt", "Src", "ISIN", "FinInstrmId", "ClsPric"), "BSE UDiFF")
            status = store_immutable_evidence(destination, payload)["status"]
        rows = max(0, len(payload.splitlines()) - 1)
        return {"status": status, "path": str(destination), "rows": rows}
    except ValueError as exc:
        return {"status": "UNAVAILABLE", "reason": str(exc), "rows": 0}


def _discover_prior_nse_full_bhavcopy(
    paths: DataStatePaths,
    trade_date: str,
    *,
    attempts: int,
    lookback_days: int,
) -> dict[str, object]:
    """Acquire the nearest earlier official NSE full bhavcopy, if available."""

    current = date.fromisoformat(trade_date)
    failures: list[dict[str, str]] = []
    for prior_date in candidate_trade_dates(current - timedelta(days=1), lookback_days):
        daymonthyear = datetime.strptime(prior_date, "%Y-%m-%d").strftime("%d%m%Y")
        destination = immutable_evidence_path(
            paths, provider="nse", effective_date=prior_date,
            filename=f"sec_bhavdata_full_{daymonthyear}.csv",
        )
        try:
            if destination.is_file():
                payload = destination.read_bytes()
                status = "ALREADY_PRESENT"
            else:
                payload, _ = _download(
                    NSE_FULL_BHAVCOPY.format(daymonthyear=daymonthyear), attempts=attempts,
                )
                _validate_csv(
                    payload,
                    ("SYMBOL", "SERIES", "DATE1", "CLOSE_PRICE", "NO_OF_TRADES"),
                    "NSE full bhavcopy",
                )
                status = store_immutable_evidence(destination, payload)["status"]
            _validate_csv(
                payload,
                ("SYMBOL", "SERIES", "DATE1", "CLOSE_PRICE", "NO_OF_TRADES"),
                "NSE full bhavcopy",
            )
            return {
                "status": status, "trade_date": prior_date,
                "path": str(destination), "rows": max(0, len(payload.splitlines()) - 1),
                "failures": failures,
            }
        except ValueError as exc:
            failures.append({"trade_date": prior_date, "reason": str(exc)})
    return {
        "status": "UNAVAILABLE", "rows": 0, "failures": failures,
        "reason": "no valid earlier official NSE full bhavcopy found in the discovery window",
    }


def _accepted_trade_date(paths: DataStatePaths) -> str | None:
    try:
        root = resolve_accepted_bundle_root(paths.root)
        return str(load_live_market_bundle(root).manifest["snapshot"]["trade_date"])
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def refresh(args: argparse.Namespace) -> dict[str, object]:
    paths = DataStatePaths.from_root(args.state_root)
    lock = acquire_refresh_lock(paths)
    started = datetime.now(timezone.utc).isoformat()
    try:
        today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        trade_date, bhavcopy, discovery_failures = discover_latest_nse_bhavcopy(
            paths, today=today, lookback_days=args.lookback_days, attempts=args.attempts,
        )
        previous_date = _accepted_trade_date(paths)
        if previous_date is not None and trade_date <= previous_date and not args.force:
            completed = datetime.now(timezone.utc).isoformat()
            attempt = record_refresh_attempt(
                paths, status="NO_NEW_DATA", started_at=started, completed_at=completed,
                discovered_trade_date=trade_date,
                message=f"Latest official trade date {trade_date} is not newer than accepted {previous_date}.",
            )
            return {"status": "NO_NEW_DATA", "attempt": attempt, "discovery_failures": discovery_failures}
        source, nse_sources = _materialize_nse_sources(
            paths, trade_date, bhavcopy, attempts=args.attempts,
        )
        bse = _attempt_bse_evidence(paths, trade_date, attempts=args.attempts)
        prior_nse = _discover_prior_nse_full_bhavcopy(
            paths, trade_date, attempts=args.attempts, lookback_days=args.lookback_days,
        )
        run_id = f"{trade_date}-{uuid4().hex}"
        candidate = paths.staging / run_id / "bundle"
        if args.dry_run:
            return {
                "status": "DRY_RUN", "trade_date": trade_date,
                "previous_trade_date": previous_date, "candidate": str(candidate),
                "nse_sources": nse_sources, "bse_evidence": bse,
                "prior_nse_evidence": prior_nse,
                "discovery_failures": discovery_failures,
            }
        prepare_args = SimpleNamespace(
            source=str(source), output=str(candidate),
            cache=str(paths.root / "history_cache"), trade_date=trade_date,
            acquire_sources=False, attempts=args.attempts, workers=args.workers,
            download_limit=args.download_limit, no_download=args.no_history_download,
            bse_bhavcopy=(bse.get("path") if bse.get("status") != "UNAVAILABLE" else None),
            nse_prior_trades=(
                prior_nse.get("path") if prior_nse.get("status") != "UNAVAILABLE" else None
            ),
        )
        build_report = prepare_live_market.prepare(prepare_args)
        pointer = promote_candidate_bundle(paths, candidate)
        completed = datetime.now(timezone.utc).isoformat()
        attempt = record_refresh_attempt(
            paths, status="ACCEPTED", started_at=started, completed_at=completed,
            discovered_trade_date=trade_date, bundle_fingerprint=pointer["bundle_fingerprint"],
            message="Candidate passed structural, coverage, model and fingerprint gates; accepted atomically.",
        )
        report = {
            "status": "ACCEPTED", "trade_date": trade_date,
            "accepted_state": pointer, "attempt": attempt,
            "nse_sources": nse_sources, "bse_evidence": bse,
            "prior_nse_evidence": prior_nse,
            "discovery_failures": discovery_failures, "build": build_report,
        }
        report_path = paths.root / "refresh_reports" / f"{run_id}.json"
        from stock_ranker.data_state import atomic_write_json
        atomic_write_json(report_path, report)
        report["report_path"] = str(report_path)
        return report
    except Exception as exc:
        completed = datetime.now(timezone.utc).isoformat()
        record_refresh_attempt(
            paths, status="FAILED", started_at=started, completed_at=completed,
            message=f"{type(exc).__name__}: {exc}",
        )
        raise
    finally:
        release_refresh_lock(lock)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh the latest accepted market state transactionally from free public sources."
    )
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    parser.add_argument("--lookback-days", type=int, default=10)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--download-limit", type=int)
    parser.add_argument("--no-history-download", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.status:
            print(json.dumps(data_state_status(args.state_root), indent=2, sort_keys=True))
            return 0
        result = refresh(args)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"autonomous refresh failed; last-known-good remains active: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
