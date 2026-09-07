from __future__ import annotations

import argparse
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
from zipfile import ZipFile, BadZipFile


LEGACY_LAST = date(2024, 7, 5)
UDIFF_FIRST = date(2024, 7, 8)

LEGACY_BASE = "https://www.bseindia.com/download/BhavCopy/Equity"
UDIFF_BASE = LEGACY_BASE

DEFAULT_DIRECT_DB = Path.home() / "Downloads" / "BSE_History_Direct" / "state" / "progress.sqlite"
DEFAULT_OUTPUT = Path.home() / "Downloads" / "BSE_History_Bhavcopy_Fallback"

PROBE_DATES = (
    date(2023, 9, 5),   # legacy ZIP
    date(2024, 9, 5),   # UDiFF CSV
)

DIRECT_NEEDS = "NEEDS_BHAVCOPY_CHECK"

LEGACY_REQUIRED = {
    "SC_CODE", "OPEN", "HIGH", "LOW", "CLOSE", "NO_TRADES", "NO_OF_SHRS",
}
UDIFF_REQUIRED = {
    "TradDt", "Sgmt", "Src", "FinInstrmId", "ISIN", "TckrSymb",
    "OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol",
}

OUT_FIELDS = (
    "date", "bse_code", "isin", "ticker",
    "open", "high", "low", "close",
    "volume", "trades", "turnover",
    "source", "source_file",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def curl_exe() -> str:
    value = shutil.which("curl.exe") or shutil.which("curl")
    if not value:
        raise RuntimeError("curl.exe not found")
    return value


def parse_ddmmyyyy(value: str) -> date:
    return datetime.strptime(value, "%d/%m/%Y").date()


def legacy_url(d: date) -> str:
    return f"{LEGACY_BASE}/EQ{d:%d%m%y}_CSV.ZIP"


def udiff_url(d: date) -> str:
    return f"{UDIFF_BASE}/BhavCopy_BSE_CM_0_0_0_{d:%Y%m%d}_F_0000.CSV"


def url_for(d: date) -> tuple[str, str]:
    if d <= LEGACY_LAST:
        return "LEGACY", legacy_url(d)
    if d >= UDIFF_FIRST:
        return "UDIFF", udiff_url(d)
    raise ValueError(f"{d} is inside the 6–7 Jul 2024 weekend transition gap")


def clean_num(value: str) -> str:
    return str(value or "").strip().replace(",", "")


def finite_nonnegative(value: str, label: str) -> float:
    try:
        x = float(clean_num(value))
    except ValueError as exc:
        raise ValueError(f"non-numeric {label}: {value!r}") from exc
    if x < 0 or x != x or x in (float("inf"), float("-inf")):
        raise ValueError(f"invalid {label}: {value!r}")
    return x


def normalize_code(value: object) -> str:
    s = str(value or "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    if s.isdigit():
        s = s.zfill(6)
    return s


def decode_csv(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    raise ValueError("CSV bytes are not decodable text")


def classify_html_response(raw: bytes) -> str | None:
    """
    Classify BSE HTML accidentally returned for a static Bhavcopy path.

    Observed empirically on a market holiday: BSE returns HTTP 200 with its
    ordinary homepage HTML instead of 404 for a nonexistent Bhavcopy file.
    Return:
      - "NO_FILE" for the ordinary BSE homepage/missing-static-file response.
      - "BLOCKED" for obvious access-denied / anti-bot HTML.
      - None for non-HTML or unrecognized HTML.
    """
    head = raw[:20000].decode("utf-8", errors="replace").lower()
    stripped = head.lstrip()
    if not (stripped.startswith("<!doctype html") or stripped.startswith("<html") or "<html" in stripped[:500]):
        return None

    block_markers = (
        "access denied",
        "captcha",
        "request blocked",
        "forbidden",
        "cloudflare",
        "akamai",
        "bot detection",
    )
    if any(marker in head for marker in block_markers):
        return "BLOCKED"

    homepage_markers = (
        "live stock/share market",
        "indian stock/share market live",
        "bse sensex",
        "formerly bombay stock exchange",
    )
    if sum(marker in head for marker in homepage_markers) >= 2:
        return "NO_FILE"

    return None


def parse_legacy_zip(raw: bytes, d: date, wanted: set[str]) -> list[dict]:
    try:
        with ZipFile(io.BytesIO(raw)) as zf:
            members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not members:
                raise ValueError("legacy Bhavcopy ZIP contains no CSV")
            # Legacy ZIP normally has exactly one CSV.
            data = zf.read(members[0])
    except BadZipFile as exc:
        raise ValueError("legacy response is not a valid ZIP") from exc

    text = decode_csv(data)
    reader = csv.DictReader(io.StringIO(text))
    fields = {str(x or "").strip().lstrip("\ufeff") for x in (reader.fieldnames or [])}
    missing = LEGACY_REQUIRED - fields
    if missing:
        raise ValueError(f"legacy schema missing {sorted(missing)}")

    result = []
    for raw_row in reader:
        row = {
            str(k or "").strip().lstrip("\ufeff"): str(v or "").strip()
            for k, v in raw_row.items()
        }
        code = normalize_code(row.get("SC_CODE"))
        if code not in wanted:
            continue

        o = finite_nonnegative(row["OPEN"], "OPEN")
        h = finite_nonnegative(row["HIGH"], "HIGH")
        l = finite_nonnegative(row["LOW"], "LOW")
        c = finite_nonnegative(row["CLOSE"], "CLOSE")
        v = finite_nonnegative(row["NO_OF_SHRS"], "NO_OF_SHRS")
        if h < l or h < max(o, c) or l > min(o, c):
            raise ValueError(f"legacy impossible OHLC for {code} on {d}")

        result.append({
            "date": d.isoformat(),
            "bse_code": code,
            "isin": "",
            "ticker": str(row.get("SC_NAME", "")).strip(),
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": int(v),
            "trades": int(finite_nonnegative(row.get("NO_TRADES", "0"), "NO_TRADES")),
            "turnover": finite_nonnegative(row.get("NET_TURNOV", "0"), "NET_TURNOV"),
            "source": "BSE_LEGACY_BHAVCOPY",
            "source_file": f"EQ{d:%d%m%y}_CSV.ZIP",
        })
    return result


def parse_udiff_csv(raw: bytes, d: date, wanted: set[str]) -> list[dict]:
    text = decode_csv(raw)
    head = text.lstrip()[:500].lower()
    if head.startswith("<") or "<html" in head or "access denied" in head:
        raise ValueError("UDiFF response is HTML/block page")

    reader = csv.DictReader(io.StringIO(text))
    fields = {str(x or "").strip().lstrip("\ufeff") for x in (reader.fieldnames or [])}
    missing = UDIFF_REQUIRED - fields
    if missing:
        raise ValueError(f"UDiFF schema missing {sorted(missing)}")

    result = []
    for raw_row in reader:
        row = {
            str(k or "").strip().lstrip("\ufeff"): str(v or "").strip()
            for k, v in raw_row.items()
        }
        if row.get("Sgmt", "").strip().upper() != "CM":
            continue
        if row.get("Src", "").strip().upper() != "BSE":
            continue

        # BSE's own EOD/member format defines FinInstrmId as the BSE scrip code.
        code = normalize_code(row.get("FinInstrmId"))
        if code not in wanted:
            continue

        trad = str(row.get("TradDt", "")).strip()
        try:
            trad_date = date.fromisoformat(trad)
        except ValueError as exc:
            raise ValueError(f"bad UDiFF TradDt {trad!r}") from exc
        if trad_date != d:
            raise ValueError(f"UDiFF TradDt {trad_date} != filename date {d}")

        o = finite_nonnegative(row["OpnPric"], "OpnPric")
        h = finite_nonnegative(row["HghPric"], "HghPric")
        l = finite_nonnegative(row["LwPric"], "LwPric")
        c = finite_nonnegative(row["ClsPric"], "ClsPric")
        v = finite_nonnegative(row["TtlTradgVol"], "TtlTradgVol")
        if h < l or h < max(o, c) or l > min(o, c):
            raise ValueError(f"UDiFF impossible OHLC for {code} on {d}")

        result.append({
            "date": d.isoformat(),
            "bse_code": code,
            "isin": str(row.get("ISIN", "")).strip(),
            "ticker": str(row.get("TckrSymb", "")).strip(),
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": int(v),
            "trades": int(finite_nonnegative(row.get("TtlNbOfTxsExctd", "0") or "0", "TtlNbOfTxsExctd")),
            "turnover": finite_nonnegative(row.get("TtlTrfVal", "0") or "0", "TtlTrfVal"),
            "source": "BSE_UDIFF_BHAVCOPY",
            "source_file": f"BhavCopy_BSE_CM_0_0_0_{d:%Y%m%d}_F_0000.CSV",
        })
    return result


def fetch(curl: str, url: str, target: Path, timeout: int) -> tuple[int | None, int, str]:
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.with_suffix(target.suffix + ".pending")
    if pending.exists():
        pending.unlink()

    cmd = [
        curl, "--http1.1", "--location", "--silent", "--show-error",
        "--connect-timeout", "10", "--max-time", str(timeout),
        "--retry", "2", "--retry-all-errors", "--retry-delay", "1",
        "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "-H", "Accept: text/csv,application/zip,application/octet-stream,*/*;q=0.8",
        "-H", "Referer: https://www.bseindia.com/",
        "-o", str(pending),
        "--write-out", "%{http_code}",
        url,
    ]
    res = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=timeout + 20
    )
    status_s = res.stdout.decode("ascii", errors="ignore").strip()
    http = int(status_s[-3:]) if len(status_s) >= 3 and status_s[-3:].isdigit() else None
    err = res.stderr.decode("utf-8", errors="replace").strip()

    if pending.exists():
        pending.replace(target)
    return http, res.returncode, err


def load_unresolved_tasks(direct_db: Path) -> list[dict]:
    if not direct_db.is_file():
        raise FileNotFoundError(f"direct state DB not found: {direct_db}")
    conn = sqlite3.connect(str(direct_db))
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()]
        required = {"task_key", "bse_code", "from_date", "to_date", "status"}
        if not required.issubset(cols):
            raise ValueError(f"direct DB tasks schema missing {sorted(required - set(cols))}")
        rows = conn.execute(
            """
            SELECT task_key,bse_code,from_date,to_date,status
            FROM tasks
            WHERE status=?
            ORDER BY bse_code,from_date
            """,
            (DIRECT_NEEDS,),
        ).fetchall()
    finally:
        conn.close()

    result = []
    for key, code, from_s, to_s, status in rows:
        result.append({
            "task_key": key,
            "bse_code": normalize_code(code),
            "from_date": parse_ddmmyyyy(from_s),
            "to_date": parse_ddmmyyyy(to_s),
            "status": status,
        })
    return result


def wanted_by_date(tasks: list[dict]) -> dict[date, set[str]]:
    wanted: dict[date, set[str]] = {}
    for task in tasks:
        d = task["from_date"]
        while d <= task["to_date"]:
            # Exchange is closed on normal weekends. 6–7 Jul 2024 is also the transition weekend.
            if d.weekday() < 5:
                wanted.setdefault(d, set()).add(task["bse_code"])
            d += timedelta(days=1)
    return wanted


class State:
    def __init__(self, db: Path):
        db.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_files(
                trade_date TEXT PRIMARY KEY,
                format TEXT NOT NULL,
                status TEXT NOT NULL,
                http_status INTEGER,
                wanted_codes INTEGER NOT NULL,
                matched_rows INTEGER,
                raw_file TEXT,
                error TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS recovered_rows(
                trade_date TEXT NOT NULL,
                bse_code TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY(trade_date,bse_code)
            )
        """)
        self.conn.commit()

    def status(self, d: date) -> str | None:
        row = self.conn.execute(
            "SELECT status FROM daily_files WHERE trade_date=?", (d.isoformat(),)
        ).fetchone()
        return row[0] if row else None

    def save_day(self, d: date, fmt: str, status: str, wanted: int,
                 matched: list[dict], http_status=None, raw_file=None, error=None):
        self.conn.execute("""
            INSERT INTO daily_files(
                trade_date,format,status,http_status,wanted_codes,matched_rows,
                raw_file,error,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(trade_date) DO UPDATE SET
                format=excluded.format,status=excluded.status,
                http_status=excluded.http_status,wanted_codes=excluded.wanted_codes,
                matched_rows=excluded.matched_rows,raw_file=excluded.raw_file,
                error=excluded.error,updated_at=excluded.updated_at
        """, (
            d.isoformat(), fmt, status, http_status, wanted, len(matched),
            str(raw_file) if raw_file else None, error, utc_now()
        ))
        if status == "OK":
            for row in matched:
                self.conn.execute("""
                    INSERT INTO recovered_rows(trade_date,bse_code,payload_json)
                    VALUES (?,?,?)
                    ON CONFLICT(trade_date,bse_code) DO UPDATE SET
                        payload_json=excluded.payload_json
                """, (d.isoformat(), row["bse_code"], json.dumps(row, sort_keys=True)))
        self.conn.commit()

    def rows_for(self, code: str, start: date, end: date) -> list[dict]:
        rows = self.conn.execute("""
            SELECT payload_json FROM recovered_rows
            WHERE bse_code=? AND trade_date BETWEEN ? AND ?
            ORDER BY trade_date
        """, (code, start.isoformat(), end.isoformat())).fetchall()
        return [json.loads(r[0]) for r in rows]

    def errors_in_range(self, start: date, end: date) -> int:
        row = self.conn.execute("""
            SELECT COUNT(*) FROM daily_files
            WHERE trade_date BETWEEN ? AND ?
              AND status IN ('FAILED','VALIDATION_FAILED')
        """, (start.isoformat(), end.isoformat())).fetchone()
        return int(row[0])

    def summary(self) -> dict[str, int]:
        return dict(self.conn.execute(
            "SELECT status,COUNT(*) FROM daily_files GROUP BY status"
        ).fetchall())

    def close(self):
        self.conn.close()


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    with pending.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        w.writeheader()
        w.writerows(rows)
        f.flush()
        os.fsync(f.fileno())
    os.replace(pending, path)


def write_coverage(path: Path, records: list[dict]) -> None:
    fields = (
        "task_key", "bse_code", "from_date", "to_date",
        "recovered_rows", "result", "error_days", "output_file",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(records)


def reconstruct(tasks: list[dict], state: State, output_root: Path) -> dict[str, int]:
    report = []
    counts: dict[str, int] = {}

    for task in tasks:
        code = task["bse_code"]
        start = task["from_date"]
        end = task["to_date"]
        rows = state.rows_for(code, start, end)
        errors = state.errors_in_range(start, end)

        if rows:
            year = f"{start.year}-{end.year}"
            path = (
                output_root / "normalized" / "windows" / year /
                f"BSE_{code}_{start.isoformat()}_to_{end.isoformat()}.csv"
            )
            write_rows(path, rows)
            result = "BHAVCOPY_RECOVERED" if errors == 0 else "BHAVCOPY_PARTIAL_WITH_ERRORS"
            output_file = str(path)
        else:
            result = "NO_RECORD_CONFIRMED" if errors == 0 else "UNRESOLVED_BHAVCOPY_ERRORS"
            output_file = ""

        counts[result] = counts.get(result, 0) + 1
        report.append({
            "task_key": task["task_key"],
            "bse_code": code,
            "from_date": start.isoformat(),
            "to_date": end.isoformat(),
            "recovered_rows": len(rows),
            "result": result,
            "error_days": errors,
            "output_file": output_file,
        })

    write_coverage(output_root / "reports" / "coverage.csv", report)
    return counts


def probe(curl: str, root: Path, timeout: int) -> int:
    wanted = {"500500"}
    for d in PROBE_DATES:
        fmt, url = url_for(d)
        suffix = ".zip" if fmt == "LEGACY" else ".csv"
        target = root / "probe" / f"{d.isoformat()}_{fmt}{suffix}"
        http, rc, err = fetch(curl, url, target, timeout)
        if rc != 0 or http != 200:
            print(f"{d} {fmt}: FAILED http={http} curl={rc} {err[:200]}")
            return 2
        raw = target.read_bytes()
        html_kind = classify_html_response(raw)
        if html_kind == "NO_FILE":
            print(f"{d} {fmt}: NO_FILE http=200 homepage url={url}")
            continue
        if html_kind == "BLOCKED":
            print(f"{d} {fmt}: FAILED blocked HTML url={url}")
            return 2
        try:
            rows = parse_legacy_zip(raw, d, wanted) if fmt == "LEGACY" else parse_udiff_csv(raw, d, wanted)
        except Exception as exc:
            print(f"{d} {fmt}: VALIDATION_FAILED {type(exc).__name__}: {exc}")
            return 2
        print(f"{d} {fmt}: OK parsed_target_rows={len(rows)} url={url}")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Recover NEEDS_BHAVCOPY_CHECK BSE history windows from official daily BSE Bhavcopies."
    )
    p.add_argument("--mode", choices=("probe", "full"), required=True)
    p.add_argument("--direct-db", type=Path, default=DEFAULT_DIRECT_DB)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--delay-seconds", type=float, default=0.35)
    p.add_argument("--timeout-seconds", type=int, default=30)
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.delay_seconds < 0.15:
        parser().error("--delay-seconds must be >= 0.15")

    try:
        curl = curl_exe()
        root = args.output_root.resolve()
        root.mkdir(parents=True, exist_ok=True)

        if args.mode == "probe":
            return probe(curl, root, args.timeout_seconds)

        tasks = load_unresolved_tasks(args.direct_db.resolve())
        if not tasks:
            print("No NEEDS_BHAVCOPY_CHECK tasks found in direct state DB.")
            return 0

        wanted = wanted_by_date(tasks)
        dates = sorted(wanted)
        state = State(root / "state" / "bhavcopy.sqlite")
        pending = [d for d in dates if state.status(d) not in {"OK", "NO_FILE"}]

        print(f"Unresolved direct windows: {len(tasks)}")
        print(f"Distinct exact BSE codes involved: {len({t['bse_code'] for t in tasks})}")
        print(f"Weekday Bhavcopy dates needed: {len(dates)}")
        print(f"Resume-skipped daily files: {len(dates)-len(pending)}")
        print("Official sources: legacy BSE Equity Bhavcopy through 2024-07-05; UDiFF from 2024-07-08.")

        for idx, d in enumerate(pending, 1):
            try:
                fmt, url = url_for(d)
            except ValueError:
                continue

            suffix = ".zip" if fmt == "LEGACY" else ".csv"
            raw_dir = root / "raw" / ("legacy" if fmt == "LEGACY" else "udiff") / str(d.year)
            target = raw_dir / (
                f"EQ{d:%d%m%y}_CSV.ZIP" if fmt == "LEGACY"
                else f"BhavCopy_BSE_CM_0_0_0_{d:%Y%m%d}_F_0000.CSV"
            )

            http, rc, err = fetch(curl, url, target, args.timeout_seconds)

            # 404/410 is expected for weekends/holidays/archive-absent dates.
            if http in (404, 410):
                try:
                    target.unlink(missing_ok=True)
                except Exception:
                    pass
                state.save_day(
                    d, fmt, "NO_FILE", len(wanted[d]), [],
                    http_status=http, error="official BSE file not published for this date"
                )
                print(f"[{idx}/{len(pending)}] {d} {fmt}: NO_FILE http={http}")
            elif rc != 0 or http != 200:
                state.save_day(
                    d, fmt, "FAILED", len(wanted[d]), [],
                    http_status=http, raw_file=target if target.exists() else None,
                    error=f"curl={rc} {err[:300]}"
                )
                print(f"[{idx}/{len(pending)}] {d} {fmt}: FAILED http={http} curl={rc}")
            else:
                raw = target.read_bytes()
                html_kind = classify_html_response(raw)

                if html_kind == "NO_FILE":
                    # BSE sometimes returns HTTP 200 + the ordinary BSE homepage
                    # for a missing static Bhavcopy (observed on market holidays).
                    try:
                        target.unlink(missing_ok=True)
                    except Exception:
                        pass
                    state.save_day(
                        d, fmt, "NO_FILE", len(wanted[d]), [],
                        http_status=http,
                        error="HTTP 200 BSE homepage returned for unpublished Bhavcopy date"
                    )
                    print(f"[{idx}/{len(pending)}] {d} {fmt}: NO_FILE http=200 homepage")
                elif html_kind == "BLOCKED":
                    state.save_day(
                        d, fmt, "FAILED", len(wanted[d]), [],
                        http_status=http, raw_file=target,
                        error="BSE returned access-denied/anti-bot HTML"
                    )
                    print(f"[{idx}/{len(pending)}] {d} {fmt}: FAILED blocked HTML")
                else:
                    try:
                        matched = (
                            parse_legacy_zip(raw, d, wanted[d])
                            if fmt == "LEGACY"
                            else parse_udiff_csv(raw, d, wanted[d])
                        )
                        state.save_day(
                            d, fmt, "OK", len(wanted[d]), matched,
                            http_status=http, raw_file=target, error=None
                        )
                        print(
                            f"[{idx}/{len(pending)}] {d} {fmt}: "
                            f"OK wanted={len(wanted[d])} matched={len(matched)}"
                        )
                    except Exception as exc:
                        state.save_day(
                            d, fmt, "VALIDATION_FAILED", len(wanted[d]), [],
                            http_status=http, raw_file=target,
                            error=f"{type(exc).__name__}: {exc}"
                        )
                        print(
                            f"[{idx}/{len(pending)}] {d} {fmt}: "
                            f"VALIDATION_FAILED {type(exc).__name__}: {exc}"
                        )

            if idx < len(pending):
                time.sleep(args.delay_seconds + random.uniform(0.0, 0.25))

        recovery = reconstruct(tasks, state, root)
        print("Daily file status:", json.dumps(state.summary(), sort_keys=True))
        print("Window recovery:", json.dumps(recovery, sort_keys=True))
        print(f"Coverage report: {root / 'reports' / 'coverage.csv'}")
        print(f"Normalized windows: {root / 'normalized' / 'windows'}")
        print(f"State: {root / 'state' / 'bhavcopy.sqlite'}")
        state.close()
        return 0

    except (FileNotFoundError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"BSE Bhavcopy recovery failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
