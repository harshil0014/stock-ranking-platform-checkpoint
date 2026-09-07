from __future__ import annotations

import argparse
import calendar
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from typing import Iterable
from zipfile import ZipFile


BSE_HOME = "https://www.bseindia.com/"
ACTIONS_API = "https://api.bseindia.com/BseIndiaAPI/api/DefaultData/w"

START_DATE = date(2021, 9, 5)
END_DATE_DEFAULT = date.today()

CODE_PATTERN = re.compile(r"^(?:BSE_)?(?P<code>\d{6})(?:[_-].*)?\.csv$", re.IGNORECASE)

CLASSIFIERS = (
    ("SPLIT", re.compile(r"\b(stock\s+split|sub-?division|subdivision|split)\b", re.I)),
    ("BONUS", re.compile(r"\bbonus\b", re.I)),
    ("RIGHTS", re.compile(r"\bright(s)?\s+(issue|entitlement)|rights?\b", re.I)),
    ("DIVIDEND", re.compile(r"\bdividend\b", re.I)),
    ("BUYBACK", re.compile(r"\bbuy\s*back|buyback\b", re.I)),
    ("MERGER_DEMERGER_SCHEME", re.compile(
        r"\b(merger|demerger|amalgamat(?:e|ion)|scheme\s+of\s+arrangement|"
        r"reduction\s+of\s+capital|capital\s+reduction|consolidation\s+of\s+shares)\b",
        re.I,
    )),
)

TERMINAL_CHUNK_STATUSES = {"OK"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def downloads_root() -> Path:
    return Path.home() / "Downloads"


def discover_source(root: Path) -> Path:
    candidates = (
        root / "BSE_2025_2026",
        root / "BSE_2025_2026.zip",
        root / "BSE_2025_2026(1).zip",
    )
    for p in candidates:
        if p.is_dir() or p.is_file():
            return p
    more = sorted(
        [p for p in root.glob("BSE_2025_2026*.zip") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if more:
        return more[0]
    raise FileNotFoundError("Could not find completed BSE_2025_2026 source in Downloads")


def _code_from_name(name: str) -> str | None:
    m = CODE_PATTERN.fullmatch(Path(name).name)
    return m.group("code") if m else None


def extract_codes(source: Path) -> list[str]:
    if source.is_dir():
        names = [p.name for p in source.rglob("*.csv") if p.is_file()]
    elif source.is_file() and source.suffix.lower() == ".zip":
        with ZipFile(source) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    else:
        raise ValueError("source must be a directory or ZIP")
    codes = sorted({c for n in names if (c := _code_from_name(n))})
    if not codes:
        raise ValueError("No exact six-digit BSE codes found")
    return codes


def fingerprint(codes: Iterable[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(codes)) + "\n").encode()).hexdigest()


def month_chunks(start: date, end: date) -> list[tuple[date, date]]:
    chunks: list[tuple[date, date]] = []
    current = date(start.year, start.month, 1)
    while current <= end:
        last_day = calendar.monthrange(current.year, current.month)[1]
        chunk_start = max(start, current)
        chunk_end = min(end, date(current.year, current.month, last_day))
        chunks.append((chunk_start, chunk_end))
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return chunks


def classify_purpose(purpose: str) -> str:
    text = purpose or ""
    for label, pattern in CLASSIFIERS:
        if pattern.search(text):
            return label
    return "OTHER"


def normalize_event(row: dict) -> dict:
    code_raw = row.get("scrip_code", row.get("SCRIP_CODE", row.get("scripcode", "")))
    code = str(code_raw).strip()
    if code.endswith(".0"):
        code = code[:-2]
    code = code.zfill(6) if code.isdigit() else code

    purpose = str(row.get("Purpose", row.get("purpose", ""))).strip()
    event_type = classify_purpose(purpose)

    event = {
        "bse_code": code,
        "short_name": str(row.get("short_name", "")).strip(),
        "long_name": str(row.get("long_name", "")).strip(),
        "ex_date": str(row.get("Ex_date", row.get("exdate", ""))).strip(),
        "record_date": str(row.get("RD_Date", "")).strip(),
        "purpose": purpose,
        "event_type": event_type,
        "bc_start_date": str(row.get("BCRD_FROM", "")).strip(),
        "bc_end_date": str(row.get("BCRD_TO", "")).strip(),
        "no_delivery_start": str(row.get("ND_START_DATE", "")).strip(),
        "no_delivery_end": str(row.get("ND_END_DATE", "")).strip(),
        "payment_date": str(row.get("payment_date", "")).strip(),
        "needs_announcement_verification": (
            "YES" if event_type == "MERGER_DEMERGER_SCHEME" else "NO"
        ),
        "source": "BSE_DefaultData",
    }
    return event


def event_key(event: dict) -> tuple[str, ...]:
    return (
        event["bse_code"],
        event["ex_date"],
        event["record_date"],
        event["purpose"],
        event["payment_date"],
    )


def curl_executable() -> str:
    value = shutil.which("curl.exe") or shutil.which("curl")
    if not value:
        raise RuntimeError("curl.exe not found")
    return value


def fetch_actions_json(
    curl: str,
    *,
    start: date,
    end: date,
    target: Path,
    timeout: int,
) -> tuple[list[dict], int | None]:
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.with_suffix(target.suffix + ".pending")
    if pending.exists():
        pending.unlink()

    cmd = [
        curl,
        "--http1.1",
        "--location",
        "--silent",
        "--show-error",
        "--fail-with-body",
        "--connect-timeout", "10",
        "--max-time", str(timeout),
        "--retry", "3",
        "--retry-all-errors",
        "--retry-delay", "1",
        "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "-H", "Accept: application/json, text/plain, */*",
        "-H", f"Referer: {BSE_HOME}",
        "--get", ACTIONS_API,
        "--data-urlencode", "ddlcategorys=E",
        "--data-urlencode", "ddlindustrys=",
        "--data-urlencode", "segment=0",
        "--data-urlencode", "strSearch=D",
        "--data-urlencode", f"Fdate={start:%Y%m%d}",
        "--data-urlencode", f"TDate={end:%Y%m%d}",
        "-o", str(pending),
        "--write-out", "%{http_code}",
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout + 20,
    )
    status_text = result.stdout.decode("ascii", errors="ignore").strip()
    http_status = int(status_text[-3:]) if len(status_text) >= 3 and status_text[-3:].isdigit() else None
    stderr = result.stderr.decode("utf-8", errors="replace").strip()

    if result.returncode != 0 and not pending.exists():
        raise RuntimeError(
            f"curl exit={result.returncode}, http={http_status}, stderr={stderr[:300]}"
        )
    if not pending.exists():
        raise RuntimeError("BSE action endpoint returned no output file")

    raw = pending.read_bytes()
    if not raw:
        data: list[dict] = []
    else:
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except Exception as exc:
            head = raw[:300].decode("utf-8", errors="replace")
            raise ValueError(f"BSE action response is not JSON: {head!r}") from exc

        if isinstance(payload, list):
            data = payload
        elif isinstance(payload, dict):
            # Be defensive in case BSE wraps the table.
            if isinstance(payload.get("Table"), list):
                data = payload["Table"]
            else:
                # Empty/metadata-only dict should not be treated as action rows.
                data = []
        else:
            raise ValueError(f"Unexpected BSE action JSON type: {type(payload).__name__}")

        if any(not isinstance(item, dict) for item in data):
            raise ValueError("BSE action JSON contains non-object rows")

    pending.replace(target)
    return data, http_status


class State:
    def __init__(self, path: Path, codes: list[str], source: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks(
                chunk_key TEXT PRIMARY KEY,
                from_date TEXT NOT NULL,
                to_date TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                row_count INTEGER,
                target_event_count INTEGER,
                http_status INTEGER,
                raw_file TEXT,
                error TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

        fp = fingerprint(codes)
        existing = dict(self.conn.execute("SELECT key,value FROM meta"))
        if existing.get("source_codes_sha256") and existing["source_codes_sha256"] != fp:
            raise ValueError("state DB belongs to a different exact 228-code manifest")
        meta = {
            "version": "bse_corporate_actions_v1",
            "source": str(source.resolve()),
            "source_code_count": str(len(codes)),
            "source_codes_sha256": fp,
        }
        for k, v in meta.items():
            self.conn.execute(
                "INSERT INTO meta(key,value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, v),
            )
        self.conn.commit()

    def ensure_chunks(self, chunks):
        for a, b in chunks:
            key = f"{a.isoformat()}|{b.isoformat()}"
            self.conn.execute(
                """
                INSERT OR IGNORE INTO chunks
                (chunk_key,from_date,to_date,status,attempts,updated_at)
                VALUES (?,?,?,'PENDING',0,?)
                """,
                (key, a.isoformat(), b.isoformat(), utc_now()),
            )
        self.conn.commit()

    def rows(self):
        return self.conn.execute(
            """
            SELECT chunk_key,from_date,to_date,status,attempts,row_count,
                   target_event_count,http_status,raw_file,error
            FROM chunks ORDER BY from_date
            """
        ).fetchall()

    def update(self, key: str, **fields):
        allowed = {
            "status", "attempts", "row_count", "target_event_count",
            "http_status", "raw_file", "error",
        }
        invalid = set(fields) - allowed
        if invalid:
            raise ValueError(f"invalid state fields: {sorted(invalid)}")
        fields["updated_at"] = utc_now()
        parts = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [key]
        self.conn.execute(f"UPDATE chunks SET {parts} WHERE chunk_key=?", values)
        self.conn.commit()

    def close(self):
        self.conn.close()


FIELDS = (
    "bse_code", "short_name", "long_name", "ex_date", "record_date",
    "purpose", "event_type", "bc_start_date", "bc_end_date",
    "no_delivery_start", "no_delivery_end", "payment_date",
    "needs_announcement_verification", "source",
)


def rebuild_normalized(raw_dir: Path, codes: set[str], output_csv: Path) -> list[dict]:
    events: dict[tuple[str, ...], dict] = {}
    for path in sorted(raw_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        rows = payload if isinstance(payload, list) else payload.get("Table", []) if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            event = normalize_event(row)
            if event["bse_code"] not in codes:
                continue
            events[event_key(event)] = event

    result = sorted(
        events.values(),
        key=lambda x: (x["bse_code"], x["ex_date"], x["purpose"]),
    )
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    pending = output_csv.with_suffix(output_csv.suffix + ".pending")
    with pending.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(result)
        handle.flush()
        os.fsync(handle.fileno())
    pending.replace(output_csv)
    return result


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Download historical BSE structured corporate actions in monthly all-market chunks and filter exact target scrip codes."
    )
    p.add_argument("--mode", choices=("probe", "full"), required=True)
    p.add_argument("--downloads-root", type=Path, default=downloads_root())
    p.add_argument("--source", type=Path)
    p.add_argument(
        "--output-root",
        type=Path,
        default=downloads_root() / "BSE_Corporate_Actions",
    )
    p.add_argument("--from-date", type=date.fromisoformat, default=START_DATE)
    p.add_argument("--to-date", type=date.fromisoformat, default=END_DATE_DEFAULT)
    p.add_argument("--delay-seconds", type=float, default=2.0)
    p.add_argument("--timeout-seconds", type=int, default=45)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.from_date > args.to_date:
        parser().error("--from-date must be <= --to-date")
    if args.delay_seconds < 0.5:
        parser().error("--delay-seconds must be >= 0.5")

    try:
        source = args.source.resolve() if args.source else discover_source(args.downloads_root.resolve())
        codes = extract_codes(source)
        if len(codes) != 228:
            print(f"WARNING: found {len(codes)} exact codes; expected 228", file=sys.stderr)

        all_chunks = month_chunks(args.from_date, args.to_date)
        chunks = all_chunks[:1] if args.mode == "probe" else all_chunks

        root = args.output_root.resolve()
        raw_dir = root / "raw" / "bse_actions"
        normalized_csv = root / "normalized" / "events.csv"
        state = State(root / "state" / "progress.sqlite", codes, source)
        state.ensure_chunks(all_chunks)

        selected_keys = {f"{a.isoformat()}|{b.isoformat()}" for a, b in chunks}
        rows = [r for r in state.rows() if r[0] in selected_keys]
        pending = [r for r in rows if r[3] not in TERMINAL_CHUNK_STATUSES]
        print(
            f"Exact target codes: {len(codes)}; selected monthly chunks: {len(rows)}; "
            f"resume-skipped: {len(rows)-len(pending)}"
        )
        print("Source: official BSE structured corporate-actions backing endpoint")

        curl = curl_executable()
        target_codes = set(codes)

        for idx, row in enumerate(pending, 1):
            key, from_s, to_s, status, attempts, *_ = row
            start = date.fromisoformat(from_s)
            end = date.fromisoformat(to_s)
            attempts += 1
            state.update(key, status="RUNNING", attempts=attempts, error=None)

            raw_path = raw_dir / f"actions_{start.isoformat()}_{end.isoformat()}.json"
            try:
                data, http_status = fetch_actions_json(
                    curl,
                    start=start,
                    end=end,
                    target=raw_path,
                    timeout=args.timeout_seconds,
                )
                target_count = 0
                for item in data:
                    event = normalize_event(item)
                    if event["bse_code"] in target_codes:
                        target_count += 1
                state.update(
                    key,
                    status="OK",
                    attempts=attempts,
                    row_count=len(data),
                    target_event_count=target_count,
                    http_status=http_status,
                    raw_file=str(raw_path),
                    error=None,
                )
                print(
                    f"[{idx}/{len(pending)}] {start}..{end}: OK "
                    f"all_market={len(data)} target228={target_count}"
                )
            except Exception as exc:
                state.update(
                    key,
                    status="FAILED",
                    attempts=attempts,
                    error=f"{type(exc).__name__}: {exc}",
                )
                print(f"[{idx}/{len(pending)}] {start}..{end}: FAILED {type(exc).__name__}: {exc}")

            if idx < len(pending):
                time.sleep(args.delay_seconds + random.uniform(0.0, 0.7))

        events = rebuild_normalized(raw_dir, target_codes, normalized_csv)
        counts: dict[str, int] = {}
        for event in events:
            counts[event["event_type"]] = counts.get(event["event_type"], 0) + 1

        print(json.dumps({
            "events_for_228": len(events),
            "by_type": counts,
            "monthly_chunks_total": len(all_chunks),
        }, sort_keys=True))
        print(f"Normalized: {normalized_csv}")
        print(f"State: {root / 'state' / 'progress.sqlite'}")
        state.close()
        return 0

    except (FileNotFoundError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"BSE corporate-action acquisition failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
