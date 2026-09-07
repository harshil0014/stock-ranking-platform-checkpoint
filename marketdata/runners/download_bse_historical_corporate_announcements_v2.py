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


API = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
REFERER = "https://www.bseindia.com/corporates/ann.html"

DEFAULT_FROM = date(2021, 9, 5)
DEFAULT_TO = date.today()

CODE_PATTERN = re.compile(r"^(?:BSE_)?(?P<code>\d{6})(?:[_-].*)?\.csv$", re.I)
PROBE_CODES = ("500500",)

PATTERNS = (
    ("SPLIT", re.compile(r"\b(stock\s+split|split\s+of\s+shares?|sub-?division|subdivision)\b", re.I)),
    ("BONUS", re.compile(r"\bbonus(\s+issue|\s+shares?)?\b", re.I)),
    ("RIGHTS", re.compile(r"\bright(s)?\s+(issue|entitlement|shares?)\b", re.I)),
    ("DIVIDEND", re.compile(r"\b(interim\s+dividend|final\s+dividend|special\s+dividend|dividend)\b", re.I)),
    ("BUYBACK", re.compile(r"\b(buy\s*back|buyback)\b", re.I)),
    ("MERGER", re.compile(r"\b(merger|merge(?:d|r)?|amalgamat(?:e|ed|ion))\b", re.I)),
    ("DEMERGER", re.compile(r"\b(de-?merger|demerg(?:e|ed|er))\b", re.I)),
    ("SCHEME_OF_ARRANGEMENT", re.compile(r"\bscheme\s+of\s+arrangement\b", re.I)),
    ("CAPITAL_REDUCTION", re.compile(r"\b(reduction\s+of\s+(share\s+)?capital|capital\s+reduction)\b", re.I)),
    ("CONSOLIDATION", re.compile(r"\b(consolidation\s+of\s+shares?|share\s+consolidation)\b", re.I)),
    ("DELISTING", re.compile(r"\bdelist(?:ing|ed)?\b", re.I)),
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
    zips = sorted(root.glob("BSE_2025_2026*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
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


def fingerprint(codes: Iterable[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(codes)) + "\n").encode()).hexdigest()


def initial_year_chunks(start: date, end: date) -> list[tuple[date, date]]:
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


def parse_dt(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%d %b %Y", "%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def combined_text(row: dict) -> str:
    return " | ".join(
        str(row.get(k, "") or "")
        for k in (
            "NEWSSUB", "HEADLINE", "SUBCATNAME", "CATEGORYNAME",
            "MORE", "SLONGNAME", "XML_NAME",
        )
    )


def classify(row: dict) -> list[str]:
    text = combined_text(row)
    return [label for label, pat in PATTERNS if pat.search(text)]


def normalize(row: dict, requested_code: str) -> dict:
    code = str(row.get("SCRIP_CD", "")).strip()
    if code.endswith(".0"):
        code = code[:-2]
    if code.isdigit():
        code = code.zfill(6)
    return {
        "bse_code": code,
        "requested_code": requested_code,
        "news_id": str(row.get("NEWSID", "") or "").strip(),
        "announcement_datetime": str(row.get("DT_TM", row.get("NEWS_DT", "")) or "").strip(),
        "dissemination_datetime": str(row.get("DissemDT", "") or "").strip(),
        "company_name": str(row.get("SLONGNAME", "") or "").strip(),
        "subject": str(row.get("NEWSSUB", "") or "").strip(),
        "headline": str(row.get("HEADLINE", "") or "").strip(),
        "category": str(row.get("CATEGORYNAME", "") or "").strip(),
        "subcategory": str(row.get("SUBCATNAME", "") or "").strip(),
        "attachment_name": str(row.get("ATTACHMENTNAME", "") or "").strip(),
        "xml_name": str(row.get("XML_NAME", "") or "").strip(),
        "event_types": "|".join(classify(row)),
        "source": "BSE_AnnSubCategoryGetData",
    }


FIELDS = (
    "bse_code", "requested_code", "news_id", "announcement_datetime",
    "dissemination_datetime", "company_name", "subject", "headline",
    "category", "subcategory", "attachment_name", "xml_name",
    "event_types", "source",
)


def event_key(r: dict) -> tuple[str, ...]:
    return (
        r["bse_code"], r["news_id"], r["announcement_datetime"],
        r["subject"], r["attachment_name"],
    )


def curl_executable() -> str:
    value = shutil.which("curl.exe") or shutil.which("curl")
    if not value:
        raise RuntimeError("curl.exe not found")
    return value


def fetch_json(curl: str, *, code: str, start: date, end: date, page: int, timeout: int) -> dict:
    cmd = [
        curl, "--http1.1", "--location", "--silent", "--show-error",
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
        "--data-urlencode", f"pageno={page}",
        "--data-urlencode", "strCat=-1",
        "--data-urlencode", "subcategory=-1",
        "--data-urlencode", f"strPrevDate={start:%Y%m%d}",
        "--data-urlencode", f"strToDate={end:%Y%m%d}",
        "--data-urlencode", "strSearch=P",
        "--data-urlencode", f"strscrip={code}",
        "--data-urlencode", "strType=C",
    ]
    res = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=timeout + 20
    )
    stderr = res.stderr.decode("utf-8", errors="replace").strip()
    if res.returncode != 0:
        raise RuntimeError(f"curl exit={res.returncode}: {stderr[:300]}")
    raw = res.stdout
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        head = raw[:300].decode("utf-8", errors="replace")
        raise ValueError(f"not JSON: {head!r}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"unexpected top-level BSE response type: {type(data).__name__}")
    return data


def is_range_rejected(payload: dict) -> bool:
    # Proven by user's local test: long range returns {"Status": ..., "Message": ...}
    return "Table" not in payload and ("Status" in payload or "Message" in payload)


def validate_rows(rows: list[dict], code: str, start: date, end: date) -> None:
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("non-object announcement row")
        got = str(row.get("SCRIP_CD", "")).strip()
        if got.endswith(".0"):
            got = got[:-2]
        if got.isdigit():
            got = got.zfill(6)
        if got != code:
            raise ValueError(f"wrong scrip returned: requested {code}, got {got!r}")

        dt = parse_dt(str(row.get("DT_TM", row.get("NEWS_DT", "")) or ""))
        if dt is None:
            raise ValueError("announcement row has unparseable date")
        if not (start <= dt.date() <= end):
            raise ValueError(
                f"BSE ignored requested range: {dt.date()} outside {start}..{end}"
            )


def total_count(payload: dict) -> int:
    t1 = payload.get("Table1")
    if isinstance(t1, list) and t1 and isinstance(t1[0], dict):
        try:
            return int(t1[0].get("ROWCNT", 0) or 0)
        except (TypeError, ValueError):
            return 0
    return 0


class State:
    def __init__(self, path: Path, source: Path, codes: list[str], start: date, end: date):
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
            CREATE TABLE IF NOT EXISTS chunks(
                task_key TEXT PRIMARY KEY,
                bse_code TEXT NOT NULL,
                from_date TEXT NOT NULL,
                to_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                pages INTEGER NOT NULL DEFAULT 0,
                announcements INTEGER,
                relevant INTEGER,
                output_file TEXT,
                error TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        old = dict(self.conn.execute("SELECT key,value FROM meta"))
        fp = fingerprint(codes)
        if old.get("source_codes_sha256") and old["source_codes_sha256"] != fp:
            raise ValueError("state DB belongs to a different target-code manifest")
        for k, v in {
            "version": "bse_historical_announcements_v2_adaptive",
            "source": str(source.resolve()),
            "source_code_count": str(len(codes)),
            "source_codes_sha256": fp,
            "requested_from": start.isoformat(),
            "requested_to": end.isoformat(),
        }.items():
            self.conn.execute(
                "INSERT INTO meta(key,value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, v),
            )
        self.conn.commit()

    def ensure(self, code: str, start: date, end: date):
        key = f"{code}|{start.isoformat()}|{end.isoformat()}"
        self.conn.execute("""
            INSERT OR IGNORE INTO chunks
            (task_key,bse_code,from_date,to_date,status,updated_at)
            VALUES (?,?,?,?, 'PENDING', ?)
        """, (key, code, start.isoformat(), end.isoformat(), utc_now()))
        self.conn.commit()
        return key

    def get_status(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT status FROM chunks WHERE task_key=?", (key,)
        ).fetchone()
        return row[0] if row else None

    def update(self, key: str, *, status: str, pages=0, announcements=None,
               relevant=None, output_file=None, error=None):
        self.conn.execute("""
            UPDATE chunks
            SET status=?,pages=?,announcements=?,relevant=?,output_file=?,error=?,updated_at=?
            WHERE task_key=?
        """, (
            status, pages, announcements, relevant, output_file, error,
            utc_now(), key
        ))
        self.conn.commit()

    def summary(self):
        return dict(self.conn.execute(
            "SELECT status,COUNT(*) FROM chunks GROUP BY status"
        ).fetchall())

    def close(self):
        self.conn.close()


def save_chunk(path: Path, payload_pages: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_text(
        json.dumps(payload_pages, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(pending, path)


def fetch_chunk_adaptive(
    state: State,
    curl: str,
    *,
    code: str,
    start: date,
    end: date,
    raw_root: Path,
    timeout: int,
    delay: float,
    min_days: int = 7,
) -> tuple[int, int]:
    key = state.ensure(code, start, end)
    status = state.get_status(key)
    if status == "OK":
        # Rebuild phase will read file; return 0 here because task is already terminal.
        return 0, 0

    first = fetch_json(curl, code=code, start=start, end=end, page=1, timeout=timeout)

    if is_range_rejected(first):
        span = (end - start).days + 1
        if span <= min_days:
            state.update(
                key, status="FAILED", error=f"BSE rejected range even at {span} days: {first}"
            )
            raise RuntimeError(f"BSE rejected minimum chunk {code} {start}..{end}")

        mid = start + timedelta(days=(span // 2) - 1)
        left = (start, mid)
        right = (mid + timedelta(days=1), end)
        state.update(key, status="SPLIT", error="BSE rejected range; adaptively split")
        a1, r1 = fetch_chunk_adaptive(
            state, curl, code=code, start=left[0], end=left[1],
            raw_root=raw_root, timeout=timeout, delay=delay, min_days=min_days
        )
        time.sleep(delay + random.uniform(0, 0.4))
        a2, r2 = fetch_chunk_adaptive(
            state, curl, code=code, start=right[0], end=right[1],
            raw_root=raw_root, timeout=timeout, delay=delay, min_days=min_days
        )
        return a1 + a2, r1 + r2

    if "Table" not in first or not isinstance(first.get("Table"), list):
        state.update(key, status="FAILED", error=f"unexpected BSE schema: {first}")
        raise ValueError(f"unexpected BSE response for {code} {start}..{end}: {first}")

    pages = [first]
    rows = list(first["Table"])
    validate_rows(rows, code, start, end)
    total = total_count(first)

    page = 2
    while total and len(rows) < total:
        time.sleep(delay + random.uniform(0, 0.4))
        payload = fetch_json(curl, code=code, start=start, end=end, page=page, timeout=timeout)
        if "Table" not in payload or not isinstance(payload.get("Table"), list):
            raise ValueError(f"pagination schema failure on page {page}")
        page_rows = payload["Table"]
        if not page_rows:
            break
        validate_rows(page_rows, code, start, end)
        pages.append(payload)
        rows.extend(page_rows)
        page += 1
        if page > 500:
            raise RuntimeError("pagination exceeded 500 pages")

    relevant = sum(1 for row in rows if classify(row))
    output = raw_root / code / f"{start.isoformat()}_{end.isoformat()}.json"
    save_chunk(output, pages)
    state.update(
        key,
        status="OK",
        pages=len(pages),
        announcements=len(rows),
        relevant=relevant,
        output_file=str(output),
        error=None,
    )
    return len(rows), relevant


def rebuild(raw_root: Path, selected_codes: set[str], out_csv: Path) -> list[dict]:
    result: dict[tuple[str, ...], dict] = {}
    for code in sorted(selected_codes):
        folder = raw_root / code
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.json")):
            try:
                pages = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(pages, list):
                continue
            for payload in pages:
                for row in payload.get("Table", []) if isinstance(payload, dict) else []:
                    if not isinstance(row, dict):
                        continue
                    n = normalize(row, code)
                    if n["bse_code"] != code or not n["event_types"]:
                        continue
                    result[event_key(n)] = n

    rows = sorted(
        result.values(),
        key=lambda x: (x["bse_code"], x["announcement_datetime"], x["news_id"])
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
        description="Adaptive historical BSE corporate-announcement downloader. "
                    "Starts with one-year chunks and automatically splits any range BSE rejects."
    )
    p.add_argument("--mode", choices=("probe", "full"), required=True)
    p.add_argument("--downloads-root", type=Path, default=downloads_root())
    p.add_argument("--source", type=Path)
    p.add_argument(
        "--output-root",
        type=Path,
        default=downloads_root() / "BSE_Historical_Announcements_v2",
    )
    p.add_argument("--from-date", type=date.fromisoformat, default=DEFAULT_FROM)
    p.add_argument("--to-date", type=date.fromisoformat, default=DEFAULT_TO)
    p.add_argument("--delay-seconds", type=float, default=0.8)
    p.add_argument("--timeout-seconds", type=int, default=45)
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.from_date > args.to_date:
        parser().error("--from-date must be <= --to-date")
    if args.delay_seconds < 0.5:
        parser().error("--delay-seconds must be >= 0.5")

    try:
        source = args.source.resolve() if args.source else discover_source(args.downloads_root.resolve())
        codes = extract_codes(source)
        if len(codes) != 228:
            print(f"WARNING: exact target code count={len(codes)}; expected 228", file=sys.stderr)

        selected = set(PROBE_CODES) if args.mode == "probe" else set(codes)
        missing = selected - set(codes)
        if missing:
            raise ValueError(f"probe codes missing from source: {sorted(missing)}")

        chunks = initial_year_chunks(args.from_date, args.to_date)
        root = args.output_root.resolve()
        raw_root = root / "raw" / "announcements"
        out_csv = root / "normalized" / "relevant_events.csv"
        state = State(root / "state" / "progress.sqlite", source, codes, args.from_date, args.to_date)
        curl = curl_executable()

        total_top_level = len(selected) * len(chunks)
        done = 0
        print(f"Exact target codes: {len(codes)}; selected scrips: {len(selected)}")
        print(f"Historical range: {args.from_date}..{args.to_date}")
        print(f"Initial chunks: {len(chunks)} per scrip; top-level tasks: {total_top_level}")
        print("Adaptive rule: if BSE rejects a range, split it automatically; no manual babysitting.")

        for code in sorted(selected):
            code_ann = 0
            code_rel = 0
            for start, end in chunks:
                done += 1
                key = state.ensure(code, start, end)
                if state.get_status(key) == "OK":
                    print(f"[{done}/{total_top_level}] {code} {start}..{end}: RESUME_OK")
                    continue
                try:
                    a, r = fetch_chunk_adaptive(
                        state, curl,
                        code=code, start=start, end=end,
                        raw_root=raw_root,
                        timeout=args.timeout_seconds,
                        delay=args.delay_seconds,
                    )
                    code_ann += a
                    code_rel += r
                    final_status = state.get_status(key)
                    if final_status == "SPLIT":
                        print(
                            f"[{done}/{total_top_level}] {code} {start}..{end}: "
                            f"SPLIT_RECOVERED announcements={a} relevant={r}"
                        )
                    else:
                        print(
                            f"[{done}/{total_top_level}] {code} {start}..{end}: "
                            f"OK announcements={a} relevant={r}"
                        )
                except Exception as exc:
                    print(
                        f"[{done}/{total_top_level}] {code} {start}..{end}: "
                        f"FAILED {type(exc).__name__}: {exc}"
                    )
                time.sleep(args.delay_seconds + random.uniform(0.0, 0.4))

        events = rebuild(raw_root, selected, out_csv)
        by_type: dict[str, int] = {}
        for row in events:
            for label in row["event_types"].split("|"):
                if label:
                    by_type[label] = by_type.get(label, 0) + 1

        print(json.dumps({
            "relevant_events": len(events),
            "by_type": by_type,
            "selected_scrips": len(selected),
            "state_statuses": state.summary(),
        }, sort_keys=True))
        print(f"Normalized: {out_csv}")
        print(f"State: {root / 'state' / 'progress.sqlite'}")
        state.close()
        return 0

    except (FileNotFoundError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"BSE historical-announcement acquisition failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
