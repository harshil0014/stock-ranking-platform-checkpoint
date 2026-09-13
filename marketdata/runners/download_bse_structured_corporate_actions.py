from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
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


API = "https://api.bseindia.com/BseIndiaAPI/api/DefaultData/w"
REFERER = "https://www.bseindia.com/corporates/corporates_act.html"

DEFAULT_FROM = date(2021, 9, 5)
DEFAULT_TO = date.today()

CODE_PATTERN = re.compile(r"^(?:BSE_)?(?P<code>\d{6})(?:[_-].*)?\.csv$", re.I)
PROBE_CODES = ("500500", "505690", "505720")

EVENT_PATTERNS = (
    ("SPLIT", re.compile(r"\b(stock\s+split|split|sub-?division|subdivision)\b", re.I)),
    ("BONUS", re.compile(r"\bbonus\b", re.I)),
    ("RIGHTS", re.compile(r"\bright(s)?\b", re.I)),
    ("DIVIDEND", re.compile(r"\bdividend\b", re.I)),
    ("BUYBACK", re.compile(r"\b(buy\s*back|buyback)\b", re.I)),
    ("MERGER_DEMERGER_SCHEME", re.compile(
        r"\b(merger|de-?merger|demerger|amalgamat(?:e|ed|ion)|"
        r"scheme\s+of\s+arrangement|reduction\s+of\s+(share\s+)?capital|"
        r"capital\s+reduction|consolidation\s+of\s+shares?)\b",
        re.I,
    )),
)

FIELDS = (
    "bse_code", "short_name", "long_name", "ex_date", "record_date",
    "purpose", "event_type", "bc_start_date", "bc_end_date",
    "no_delivery_start", "no_delivery_end", "payment_date",
    "source", "source_chunk",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def downloads_root() -> Path:
    return Path.home() / "Downloads"


def discover_source(root: Path) -> Path:
    for p in (
        root / "BSE_2025_2026",
        root / "BSE_2025_2026.zip",
        root / "BSE_2025_2026(1).zip",
    ):
        if p.is_dir() or p.is_file():
            return p
    zips = sorted(
        root.glob("BSE_2025_2026*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if zips:
        return zips[0]
    raise FileNotFoundError("Could not find completed BSE_2025_2026 source in Downloads")


def code_from_name(name: str) -> str | None:
    m = CODE_PATTERN.fullmatch(Path(name).name)
    return m.group("code") if m else None


def extract_codes(source: Path) -> list[str]:
    if source.is_dir():
        names = [p.name for p in source.rglob("*.csv") if p.is_file()]
    elif source.is_file() and source.suffix.lower() == ".zip":
        with ZipFile(source) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    else:
        raise ValueError("source must be directory or ZIP")
    codes = sorted({c for n in names if (c := code_from_name(n))})
    if not codes:
        raise ValueError("No exact six-digit BSE codes found")
    return codes


def extract_codes_csv(source: Path) -> list[str]:
    """Load an explicit exact-code audit cohort without filename conventions."""
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "bse_code" not in reader.fieldnames:
            raise ValueError("--codes-csv must contain a bse_code column")
        codes = sorted({normalize_code(row.get("bse_code")) for row in reader})
    invalid = [code for code in codes if not re.fullmatch(r"\d{6}", code)]
    if invalid:
        raise ValueError(f"invalid exact BSE codes in --codes-csv: {invalid[:5]}")
    if not codes:
        raise ValueError("--codes-csv contains no exact six-digit BSE codes")
    return codes


def fingerprint(codes: Iterable[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(codes)) + "\n").encode()).hexdigest()


def yearly_chunks(start: date, end: date) -> list[tuple[date, date]]:
    chunks = []
    cur = start
    while cur <= end:
        try:
            nxt = cur.replace(year=cur.year + 1) - timedelta(days=1)
        except ValueError:
            nxt = cur + timedelta(days=364)
        chunk_end = min(nxt, end)
        chunks.append((cur, chunk_end))
        cur = chunk_end + timedelta(days=1)
    return chunks


def normalize_code(value: object) -> str:
    s = str(value or "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.zfill(6) if s.isdigit() else s


def classify_purpose(purpose: str) -> str:
    text = purpose or ""
    for label, pat in EVENT_PATTERNS:
        if pat.search(text):
            return label
    return "OTHER"


def parse_bse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%d %b %Y", "%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def normalize_row(row: dict, code: str, chunk: tuple[date, date]) -> dict:
    got = normalize_code(
        row.get("scrip_code", row.get("SCRIP_CODE", row.get("scripcode", "")))
    )
    if got != code:
        raise ValueError(f"wrong scrip returned: requested {code}, got {got!r}")

    ex_raw = str(row.get("Ex_date", row.get("exdate", "")) or "").strip()
    ex_date = parse_bse_date(ex_raw)
    if ex_date is not None and not (chunk[0] <= ex_date <= chunk[1]):
        raise ValueError(
            f"BSE ignored requested date range for {code}: ex-date {ex_date} "
            f"outside {chunk[0]}..{chunk[1]}"
        )

    purpose = str(row.get("Purpose", row.get("purpose", "")) or "").strip()

    return {
        "bse_code": got,
        "short_name": str(row.get("short_name", "") or "").strip(),
        "long_name": str(row.get("long_name", "") or "").strip(),
        "ex_date": ex_raw,
        "record_date": str(row.get("RD_Date", "") or "").strip(),
        "purpose": purpose,
        "event_type": classify_purpose(purpose),
        "bc_start_date": str(row.get("BCRD_FROM", "") or "").strip(),
        "bc_end_date": str(row.get("BCRD_TO", "") or "").strip(),
        "no_delivery_start": str(row.get("ND_START_DATE", "") or "").strip(),
        "no_delivery_end": str(row.get("ND_END_DATE", "") or "").strip(),
        "payment_date": str(row.get("payment_date", "") or "").strip(),
        "source": "BSE_DefaultData_exact_scrip",
        "source_chunk": f"{chunk[0].isoformat()}..{chunk[1].isoformat()}",
    }


def event_key(row: dict) -> tuple[str, ...]:
    return (
        row["bse_code"],
        row["ex_date"],
        row["record_date"],
        row["purpose"],
        row["payment_date"],
    )


def curl_executable() -> str:
    value = shutil.which("curl.exe") or shutil.which("curl")
    if not value:
        raise RuntimeError("curl.exe not found")
    return value


def fetch_exact_actions(
    curl: str,
    *,
    code: str,
    start: date,
    end: date,
    timeout: int,
) -> list[dict]:
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
        "-H", f"Referer: {REFERER}",
        "--get", API,
        "--data-urlencode", "ddlcategorys=E",
        "--data-urlencode", "ddlindustrys=",
        "--data-urlencode", "segment=0",
        "--data-urlencode", "strSearch=D",
        "--data-urlencode", f"Fdate={start:%Y%m%d}",
        "--data-urlencode", f"TDate={end:%Y%m%d}",
        "--data-urlencode", f"scripcode={code}",
    ]
    res = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout + 20,
    )
    stderr = res.stderr.decode("utf-8", errors="replace").strip()
    if res.returncode != 0:
        raise RuntimeError(f"curl exit={res.returncode}: {stderr[:300]}")

    raw = res.stdout
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        head = raw[:300].decode("utf-8", errors="replace")
        raise ValueError(f"BSE structured-actions response is not JSON: {head!r}") from exc

    if not isinstance(data, list):
        raise ValueError(f"unexpected BSE response type: {type(data).__name__}")

    return data


class State:
    def __init__(self, path: Path, source: Path, codes: list[str]):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS meta(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks(
                task_key TEXT PRIMARY KEY,
                bse_code TEXT NOT NULL,
                from_date TEXT NOT NULL,
                to_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                row_count INTEGER,
                relevant_count INTEGER,
                raw_file TEXT,
                error TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        old = dict(self.conn.execute("SELECT key,value FROM meta"))
        fp = fingerprint(codes)
        if old.get("source_codes_sha256") and old["source_codes_sha256"] != fp:
            raise ValueError("state DB belongs to a different exact-code universe")
        for k, v in {
            "version": "bse_structured_corporate_actions_v1",
            "source": str(source.resolve()),
            "source_code_count": str(len(codes)),
            "source_codes_sha256": fp,
        }.items():
            self.conn.execute(
                "INSERT INTO meta(key,value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, v),
            )
        self.conn.commit()

    def ensure(self, code: str, start: date, end: date) -> str:
        key = f"{code}|{start.isoformat()}|{end.isoformat()}"
        self.conn.execute("""
            INSERT OR IGNORE INTO tasks(
                task_key,bse_code,from_date,to_date,status,updated_at
            ) VALUES (?,?,?,?, 'PENDING', ?)
        """, (key, code, start.isoformat(), end.isoformat(), utc_now()))
        self.conn.commit()
        return key

    def status(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT status FROM tasks WHERE task_key=?", (key,)
        ).fetchone()
        return row[0] if row else None

    def update(self, key: str, *, status: str, row_count=None, relevant_count=None,
               raw_file=None, error=None):
        self.conn.execute("""
            UPDATE tasks SET status=?,row_count=?,relevant_count=?,
                raw_file=?,error=?,updated_at=?
            WHERE task_key=?
        """, (
            status, row_count, relevant_count, raw_file,
            error, utc_now(), key,
        ))
        self.conn.commit()

    def summary(self) -> dict[str, int]:
        return dict(self.conn.execute(
            "SELECT status,COUNT(*) FROM tasks GROUP BY status"
        ).fetchall())

    def close(self):
        self.conn.close()


def save_raw(path: Path, data: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_text(
        json.dumps(data, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(pending, path)


def rebuild(raw_root: Path, codes: set[str], out_csv: Path) -> list[dict]:
    events: dict[tuple[str, ...], dict] = {}
    for code in sorted(codes):
        folder = raw_root / code
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.json")):
            m = re.fullmatch(
                r"(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.json",
                path.name,
            )
            if not m:
                continue
            chunk = (date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2)))
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, list):
                continue
            for raw in data:
                if not isinstance(raw, dict):
                    continue
                row = normalize_row(raw, code, chunk)
                events[event_key(row)] = row

    rows = sorted(
        events.values(),
        key=lambda r: (
            r["bse_code"],
            parse_bse_date(r["ex_date"]) or date.min,
            r["purpose"],
        ),
    )
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    pending = out_csv.with_suffix(out_csv.suffix + ".pending")
    with pending.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
        f.flush()
        os.fsync(f.fileno())
    os.replace(pending, out_csv)
    return rows


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Download exact-scrip historical structured BSE corporate actions "
                    "with ex-date/record-date/purpose for the 228-code universe."
    )
    p.add_argument("--mode", choices=("probe", "full"), required=True)
    p.add_argument("--downloads-root", type=Path, default=downloads_root())
    p.add_argument("--source", type=Path)
    p.add_argument(
        "--codes-csv",
        type=Path,
        help="Explicit CSV cohort with a bse_code column; mutually exclusive with --source.",
    )
    p.add_argument(
        "--output-root",
        type=Path,
        default=downloads_root() / "BSE_Structured_Corporate_Actions",
    )
    p.add_argument("--from-date", type=date.fromisoformat, default=DEFAULT_FROM)
    p.add_argument("--to-date", type=date.fromisoformat, default=DEFAULT_TO)
    p.add_argument("--delay-seconds", type=float, default=0.6)
    p.add_argument("--timeout-seconds", type=int, default=45)
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.from_date > args.to_date:
        parser().error("--from-date must be <= --to-date")
    if args.delay_seconds < 0.3:
        parser().error("--delay-seconds must be >= 0.3")

    try:
        if args.codes_csv and args.source:
            raise ValueError("--codes-csv and --source are mutually exclusive")
        if args.codes_csv:
            source = args.codes_csv.resolve()
            codes = extract_codes_csv(source)
        else:
            source = args.source.resolve() if args.source else discover_source(args.downloads_root.resolve())
            codes = extract_codes(source)
        if not args.codes_csv and len(codes) != 228:
            print(f"WARNING: exact code count={len(codes)}, expected 228", file=sys.stderr)

        selected = set(PROBE_CODES) if args.mode == "probe" else set(codes)
        missing = selected - set(codes)
        if missing:
            raise ValueError(f"probe codes missing from source: {sorted(missing)}")

        chunks = yearly_chunks(args.from_date, args.to_date)
        root = args.output_root.resolve()
        raw_root = root / "raw" / "structured_actions"
        out_csv = root / "normalized" / "events.csv"
        state = State(root / "state" / "progress.sqlite", source, codes)
        curl = curl_executable()

        total = len(selected) * len(chunks)
        done = 0
        print(f"Exact target codes: {len(codes)}; selected scrips: {len(selected)}")
        print(f"Historical range: {args.from_date}..{args.to_date}")
        print(f"Yearly chunks per scrip: {len(chunks)}; total tasks: {total}")
        print("Source: official BSE DefaultData exact-scrip historical corporate actions")

        for code in sorted(selected):
            for start, end in chunks:
                done += 1
                key = state.ensure(code, start, end)
                if state.status(key) == "OK":
                    print(f"[{done}/{total}] {code} {start}..{end}: RESUME_OK")
                    continue

                try:
                    data = fetch_exact_actions(
                        curl, code=code, start=start, end=end,
                        timeout=args.timeout_seconds,
                    )
                    normalized = [normalize_row(r, code, (start, end)) for r in data]
                    relevant = sum(1 for r in normalized if r["event_type"] != "OTHER")

                    raw_path = raw_root / code / f"{start.isoformat()}_{end.isoformat()}.json"
                    save_raw(raw_path, data)
                    state.update(
                        key,
                        status="OK",
                        row_count=len(data),
                        relevant_count=relevant,
                        raw_file=str(raw_path),
                        error=None,
                    )
                    print(
                        f"[{done}/{total}] {code} {start}..{end}: "
                        f"OK rows={len(data)} relevant={relevant}"
                    )
                except Exception as exc:
                    state.update(
                        key,
                        status="FAILED",
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    print(
                        f"[{done}/{total}] {code} {start}..{end}: "
                        f"FAILED {type(exc).__name__}: {exc}"
                    )

                if done < total:
                    time.sleep(args.delay_seconds + random.uniform(0.0, 0.35))

        events = rebuild(raw_root, selected, out_csv)
        by_type: dict[str, int] = {}
        for r in events:
            by_type[r["event_type"]] = by_type.get(r["event_type"], 0) + 1

        print(json.dumps({
            "structured_events": len(events),
            "by_type": by_type,
            "selected_scrips": len(selected),
            "state_statuses": state.summary(),
        }, sort_keys=True))
        print(f"Normalized: {out_csv}")
        print(f"State: {root / 'state' / 'progress.sqlite'}")
        state.close()
        return 0

    except (FileNotFoundError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"BSE structured-action acquisition failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
