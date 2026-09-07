"""Refresh current public evidence and rebuild the accepted company-fact state.

Each provider has its own immutable/accepted boundary. A secondary-provider
failure cannot invalidate the accepted exchange snapshot or company-fact
snapshot. This runner is suitable for Task Scheduler and never runs on a page
request.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stock_ranker.data_state import atomic_write_json


MARKET_RUNNER = ROOT / "marketdata/runners/refresh_live_market.py"
BSE_HISTORY_RUNNER = ROOT / "marketdata/runners/daily_bse_history.py"
YAHOO_RUNNER = ROOT / "marketdata/runners/acquire_yahoo_secondary_facts.py"
OFFICIAL_RUNNER = ROOT / "marketdata/runners/acquire_exchange_backbone.py"
FACT_RUNNER = ROOT / "marketdata/runners/prepare_company_facts.py"
MARKET_STATE = ROOT / "data/live_market"
YAHOO_STATE = ROOT / "data/company_facts/providers/yahoo"
OFFICIAL_STATE = ROOT / "data/company_facts/providers/official_exchange"
FACT_STATE = ROOT / "data/company_facts"


def _marketdata_interpreter() -> str:
    """Prefer the isolated market-data environment for yfinance work."""

    candidates = (
        ROOT / ".venv-marketdata/Scripts/python.exe",
        ROOT / ".venv-marketdata/bin/python",
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _accepted_official_batch() -> str | None:
    state = _read_json(OFFICIAL_STATE / "accepted_state.json")
    return None if state is None else str(state.get("accepted_batch") or "").strip() or None


def refresh_status() -> dict[str, Any]:
    return {
        "market": _read_json(MARKET_STATE / "accepted_state.json"),
        "secondary": _read_json(YAHOO_STATE / "accepted_state.json"),
        "official_exchange": _read_json(OFFICIAL_STATE / "accepted_state.json"),
        "company_facts": _read_json(FACT_STATE / "accepted_state.json"),
        "screener": "POLICY_DISABLED",
        "scientific_models": "UNCHANGED",
    }


def _run(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, check=False, text=True,
                               capture_output=True, encoding="utf-8", errors="replace")
    return {"command": command, "exit_code": completed.returncode,
            "stdout": completed.stdout[-8000:], "stderr": completed.stderr[-8000:]}


def _publish_status(
    path: Path | None,
    *,
    status: str = "RUNNING",
    running: bool = True,
    stage: str,
    message: str,
    **extra: Any,
) -> None:
    if path is None:
        return
    current = _read_json(path) or {}
    current.update({
        "status": status,
        "running": running,
        "stage": stage,
        "message": message,
        **extra,
    })
    atomic_write_json(path, current)


def _accepted_market_identity() -> dict[str, Any]:
    state = _read_json(MARKET_STATE / "accepted_state.json") or {}
    return {
        "trade_date": state.get("trade_date"),
        "fingerprint": state.get("bundle_fingerprint"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh the coherent offline company-data state.")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--full-backfill", action="store_true")
    parser.add_argument("--provider", choices=("all", "official", "yahoo", "screener"), default="all")
    parser.add_argument("--secondary-limit", type=int, default=250)
    parser.add_argument("--bse-history-limit", type=int, default=100)
    parser.add_argument("--skip-bse-history", action="store_true")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--batch-id")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--seed-batch")
    parser.add_argument("--status-file", type=Path)
    args = parser.parse_args(argv)
    if args.secondary_limit < 0 or args.bse_history_limit < 0 or not 1 <= args.workers <= 6:
        parser.error(
            "secondary-limit and bse-history-limit must be nonnegative; "
            "workers must be 1 through 6"
        )
    if args.status:
        print(json.dumps(refresh_status(), indent=2, sort_keys=True))
        return 0
    if args.provider == "screener":
        print(json.dumps({"status": "POLICY_DISABLED", "provider": "screener",
                          "reason": "Published terms and robots policy do not authorize this automated acquisition."}, sort_keys=True))
        return 0
    batch_id = args.batch_id or datetime.now(timezone.utc).strftime("automatic-%Y%m%dT%H%M%SZ")
    secondary = [sys.executable, str(YAHOO_RUNNER), "--batch-id", batch_id] + (
        ["--workers", str(args.workers), "--full-market"] if args.full_backfill
        else ["--workers", "1", "--drain-backlog", "--provider-budget", str(max(1, args.secondary_limit)),
              "--limit", str(args.secondary_limit)]
    )
    if args.resume:
        secondary.append("--resume")
    if args.retry_errors:
        secondary.append("--retry-errors")
    if args.seed_batch:
        secondary.extend(["--seed-batch", args.seed_batch])
    official = [sys.executable, str(OFFICIAL_RUNNER), "--batch-id", batch_id]
    bse_history = None
    if (
        args.provider in ("all", "official")
        and not args.skip_bse_history
        and args.bse_history_limit > 0
    ):
        bse_history = [
            _marketdata_interpreter(), str(BSE_HISTORY_RUNNER),
            "--limit", str(args.bse_history_limit),
            "--workers", str(min(2, args.workers)),
            "--attempts", "1",
        ]
    accepted_official = _accepted_official_batch()
    if accepted_official:
        official.extend(["--seed-batch", accepted_official])
    plan = {
        "write_free": args.dry_run,
        "market": [sys.executable, str(MARKET_RUNNER), "--download-limit", "1000", "--workers", "4"] if args.provider in ("all", "official") else None,
        "bse_history": bse_history,
        "official_exchange": official if args.provider in ("all", "official") else None,
        "secondary": secondary if args.provider in ("all", "yahoo") else None,
        "company_facts": [sys.executable, str(FACT_RUNNER)],
        "provider_precedence": "official exchange/audited evidence before secondary reference",
        "last_known_good_on_failure": True,
    }
    if args.dry_run:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    started_at = datetime.now(timezone.utc).isoformat()
    before = _accepted_market_identity()
    _publish_status(
        args.status_file,
        stage="CHECKING_LATEST_MARKET_DATA",
        message="Checking latest market data…",
        started_at=started_at,
        current_accepted_trade_date=before["trade_date"],
        current_accepted_fingerprint=before["fingerprint"],
        last_known_good_retained=True,
    )
    report: dict[str, Any] = {"started_at": started_at, "plan": plan}
    if plan["market"]:
        _publish_status(
            args.status_file,
            stage="REFRESHING_NSE_BSE_MARKET_SNAPSHOT",
            message="Refreshing NSE/BSE market snapshot…",
        )
        report["market"] = _run(plan["market"])
    if plan["bse_history"]:
        _publish_status(
            args.status_file,
            stage="UPDATING_HISTORICAL_PRICES",
            message="Updating historical prices…",
        )
        report["bse_history"] = _run(plan["bse_history"])
    if plan["official_exchange"]:
        _publish_status(
            args.status_file,
            stage="REFRESHING_OFFICIAL_COMPANY_EVIDENCE",
            message="Refreshing official company evidence…",
        )
        report["official_exchange"] = _run(plan["official_exchange"])
    if plan["secondary"]:
        _publish_status(
            args.status_file,
            stage="REFRESHING_SECONDARY_EVIDENCE",
            message="Refreshing allowed secondary evidence…",
        )
        report["secondary"] = _run(plan["secondary"])
    provider_failures = [
        name for name in ("market", "bse_history", "official_exchange", "secondary")
        if report.get(name, {}).get("exit_code", 0) != 0
    ]
    _publish_status(
        args.status_file,
        stage="REBUILDING_COMPANY_FACTS",
        message="Rebuilding and validating company facts…",
    )
    report["company_facts"] = _run(plan["company_facts"])
    report["provider_failures"] = provider_failures
    report["status"] = (
        "ACCEPTED_WITH_PROVIDER_FAILURES_USING_LAST_KNOWN_GOOD" if provider_failures and report["company_facts"]["exit_code"] == 0
        else "ACCEPTED" if report["company_facts"]["exit_code"] == 0
        else "FACT_BUILD_FAILED_LAST_KNOWN_GOOD_RETAINED"
    )
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    after = _accepted_market_identity()
    succeeded = report["status"].startswith("ACCEPTED")
    _publish_status(
        args.status_file,
        status="SUCCEEDED" if succeeded else "FAILED",
        running=False,
        stage="COMPLETED" if succeeded else "FAILED",
        message=(
            f"Updated successfully · {after['trade_date']}"
            if succeeded
            else "Refresh failed · Previous accepted data retained"
        ),
        completed_at=report["completed_at"],
        new_accepted_trade_date=after["trade_date"] if succeeded else None,
        new_accepted_fingerprint=after["fingerprint"] if succeeded else None,
        provider_failures=provider_failures,
        last_known_good_retained=True,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"].startswith("ACCEPTED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
