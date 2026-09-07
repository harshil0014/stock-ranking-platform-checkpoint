"""Run an exhaustive current-product recovery pass for website data gaps.

This runner deliberately operates on the current-product/provider layers only.
It does not modify Baseline V1 or Research V2 formulas, frozen walk-forward
artifacts, PIT cutoffs, or accepted Research V2 evidence contracts.

The sequence is intentionally high-leverage:
1. Refresh accepted market state.
2. Drain all BSE secondary adjusted-history gaps through the validated exact-code route.
3. Acquire current official NSE/BSE evidence with effectively-unbounded residual limits.
4. Drain the identity-validated Yahoo secondary-fact market backlog.
5. Rebuild company facts transactionally.
6. Produce a root-cause and display-state audit for whatever remains.
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
MARKET = ROOT / "marketdata/runners/refresh_live_market.py"
BSE_HISTORY = ROOT / "marketdata/runners/daily_bse_history.py"
OFFICIAL = ROOT / "marketdata/runners/acquire_exchange_backbone.py"
YAHOO = ROOT / "marketdata/runners/acquire_yahoo_secondary_facts.py"
FACTS = ROOT / "marketdata/runners/prepare_company_facts.py"
AUDIT = ROOT / "marketdata/runners/audit_website_gap_root_causes.py"


def _market_python() -> str:
    for candidate in (
        ROOT / ".venv-marketdata/Scripts/python.exe",
        ROOT / ".venv-marketdata/bin/python",
    ):
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def _run(command: list[str], *, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"command": command, "exit_code": None, "status": "PLANNED"}
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
        "status": "PASS" if completed.returncode == 0 else "FAIL",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exhaust current-product recovery routes for website missing data."
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--official-days", type=int, default=550)
    parser.add_argument("--retry-suppressed-bse", action="store_true")
    parser.add_argument("--skip-market", action="store_true")
    parser.add_argument("--skip-yahoo", action="store_true")
    parser.add_argument("--skip-official", action="store_true")
    parser.add_argument("--skip-bse-history", action="store_true")
    parser.add_argument("--batch-id")
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 6:
        parser.error("workers must be from 1 through 6")
    if args.official_days < 120:
        parser.error("official-days must be at least 120")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch_id = args.batch_id or f"website-gap-recovery-{stamp}"
    market_python = _market_python()

    commands: list[tuple[str, list[str]]] = []
    if not args.skip_market:
        commands.append(("market", [
            sys.executable, str(MARKET), "--download-limit", "100000", "--workers", str(args.workers)
        ]))
    if not args.skip_bse_history:
        bse = [
            market_python, str(BSE_HISTORY),
            "--limit", "100000",
            "--workers", str(min(2, args.workers)),
            "--attempts", "2",
        ]
        if args.retry_suppressed_bse:
            bse.append("--retry-suppressed")
        commands.append(("bse_history", bse))
    if not args.skip_official:
        # The existing official runner interprets xbrl-limit=0 as all. Its
        # BSE-shareholding selector historically defaulted to a bounded sample,
        # so use a ceiling larger than the entire supported universe.
        commands.append(("official_exchange", [
            sys.executable, str(OFFICIAL),
            "--batch-id", batch_id,
            "--days", str(args.official_days),
            "--xbrl-limit", "0",
            "--bse-shareholding-limit", "100000",
        ]))
    if not args.skip_yahoo:
        commands.append(("secondary", [
            market_python, str(YAHOO),
            "--batch-id", batch_id + "-yahoo",
            "--workers", str(args.workers),
            "--full-market",
            "--retry-errors",
        ]))

    commands.append(("company_facts", [sys.executable, str(FACTS)]))
    commands.append(("gap_audit", [sys.executable, str(AUDIT)]))

    report: dict[str, Any] = {
        "schema_version": "website_gap_recovery_v1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "batch_id": batch_id,
        "scientific_models": "UNCHANGED",
        "frozen_research": "UNCHANGED",
        "steps": {},
    }
    failed: list[str] = []
    for name, command in commands:
        result = _run(command, dry_run=args.dry_run)
        report["steps"][name] = result
        if result.get("exit_code") not in (None, 0):
            failed.append(name)
            # Provider acquisition is fail-closed/last-known-good. Continue to
            # the company-fact rebuild and audit so the residual queue is still
            # measured rather than hiding a provider outage.

    report["failed_steps"] = failed
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    report["status"] = (
        "PLANNED" if args.dry_run else
        "COMPLETED_WITH_RESIDUAL_PROVIDER_FAILURES" if failed else
        "COMPLETED"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    # A provider failure does not mean accepted state was corrupted, but the
    # caller should know the recovery pass was incomplete.
    return 0 if args.dry_run or not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
