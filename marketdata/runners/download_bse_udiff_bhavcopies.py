"""Resumably download and validate official BSE cash-market UDiFF bhavcopies."""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any


URL = "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{day}_F_0000.CSV"
REQUIRED = {"TradDt", "Src", "ISIN", "FinInstrmId", "ClsPric"}


def is_bse_no_record_html(raw: bytes) -> bool:
    """Recognize BSE's own HTML fallback for dates with no bhavcopy."""
    sample = raw[:200_000].lower()
    return (
        sample.lstrip().startswith((b"<html", b"<!doctype"))
        and (b"bseindia" in sample or b"bse india" in sample)
        and (b"bombay stock exchange" in sample or b"bse ltd" in sample or b"bse limited" in sample)
    )


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(pending, path)


def validate(path: Path, expected: date) -> int:
    raw = path.read_bytes()
    if raw[:20].lstrip().lower().startswith((b"<html", b"<!doctype")):
        raise ValueError("response is HTML")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED.issubset(reader.fieldnames):
            raise ValueError("unexpected UDiFF schema")
        count = 0
        for row in reader:
            if row.get("TradDt") != expected.isoformat() or row.get("Src") != "BSE":
                raise ValueError("UDiFF date/source mismatch")
            count += 1
    if count == 0:
        raise ValueError("empty UDiFF file")
    return count


def fetch(curl: str, target: Path, day: date, timeout: int) -> tuple[int, str]:
    pending = target.with_suffix(target.suffix + ".pending")
    pending.unlink(missing_ok=True)
    command = [
        curl, "--http1.1", "--location", "--silent", "--show-error",
        "--connect-timeout", "10", "--max-time", str(timeout),
        "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "-H", "Referer: https://www.bseindia.com/markets/MarketInfo/BhavCopy.aspx",
        "--output", str(pending), "--write-out", "%{http_code}",
        URL.format(day=day.strftime("%Y%m%d")),
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout + 15)
    status = result.stdout.decode("ascii", errors="replace").strip()[-3:]
    if result.returncode != 0:
        pending.unlink(missing_ok=True)
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip()[:300])
    if status in {"404", "410"}:
        pending.unlink(missing_ok=True)
        return 0, "NO_RECORD"
    if status != "200":
        pending.unlink(missing_ok=True)
        raise RuntimeError(f"HTTP {status}")
    raw = pending.read_bytes()
    if is_bse_no_record_html(raw):
        pending.unlink(missing_ok=True)
        return 0, "NO_RECORD"
    rows = validate(pending, day)
    os.replace(pending, target)
    return rows, "OK"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-date", type=date.fromisoformat, required=True)
    parser.add_argument("--to-date", type=date.fromisoformat, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--delay-seconds", type=float, default=0.5)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    args = parser.parse_args(argv)
    if args.from_date > args.to_date or args.delay_seconds < 0.3:
        parser.error("invalid date range or delay below 0.3 seconds")
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        parser.error("curl not found")
    root = args.output_root.resolve()
    raw_root = root / "raw" / "udiff"
    state_path = root / "progress.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    days: list[date] = []
    current = args.from_date
    while current <= args.to_date:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    failures = 0
    for number, day in enumerate(days, 1):
        key = day.isoformat()
        if state.get(key, {}).get("status") in {"OK", "NO_RECORD"}:
            continue
        target = raw_root / str(day.year) / f"BhavCopy_BSE_CM_0_0_0_{day:%Y%m%d}_F_0000.CSV"
        target.parent.mkdir(parents=True, exist_ok=True)
        error = ""
        for attempt in range(1, 4):
            try:
                rows, status = fetch(curl, target, day, args.timeout_seconds)
                state[key] = {"status": status, "rows": rows, "attempts": attempt, "error": ""}
                break
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                if attempt < 3:
                    time.sleep(attempt * 1.5)
        else:
            failures += 1
            state[key] = {"status": "FAILED", "rows": 0, "attempts": 3, "error": error}
        atomic_json(state_path, state)
        print(f"[{number}/{len(days)}] {key} {state[key]['status']}", flush=True)
        if number < len(days):
            time.sleep(args.delay_seconds)
    summary = {status: sum(row["status"] == status for row in state.values()) for status in {r["status"] for r in state.values()}}
    print(json.dumps({"tasks": len(days), "statuses": summary, "output_root": str(root)}, sort_keys=True))
    unresolved = sum(row["status"] == "FAILED" for row in state.values())
    return 2 if failures or unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
