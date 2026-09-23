"""Download a dated exact-identity cohort from official BSE CM UDiFF files."""
from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import sys
import time

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from recover_bse_history_from_bhavcopy import (  # noqa: E402
    classify_html_response, fetch, parse_udiff_csv, curl_exe,
)


def load_cohort(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or not {"bse_code", "isin"}.issubset(rows[0]):
        raise ValueError("cohort CSV requires bse_code and isin")
    result: dict[str, str] = {}
    for row in rows:
        code = str(row["bse_code"]).strip().removesuffix(".0").zfill(6)
        isin = str(row["isin"]).strip()
        if not (code.isdigit() and len(code) == 6 and isin.startswith("INE")):
            raise ValueError(f"invalid exact identity {code}/{isin}")
        if code in result and result[code] != isin:
            raise ValueError(f"duplicate BSE code maps to multiple ISINs: {code}")
        result[code] = isin
    return result


def weekdays(start: date, end: date):
    current = start
    while current <= end:
        if current.weekday() < 5:
            yield current
        current += timedelta(days=1)


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS days(day TEXT PRIMARY KEY,status TEXT NOT NULL,http INTEGER,error TEXT,source_file TEXT,sha256 TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS rows(day TEXT NOT NULL,bse_code TEXT NOT NULL,isin TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(day,bse_code))")
        self.db.commit()

    def complete(self, day: date) -> bool:
        row = self.db.execute("SELECT status FROM days WHERE day=?", (day.isoformat(),)).fetchone()
        return bool(row and row[0] in {"OK", "NO_FILE"})

    def save(self, day: date, status: str, *, http=None, error=None, source=None, rows=()):
        digest = hashlib.sha256(source.read_bytes()).hexdigest() if source and source.is_file() else None
        self.db.execute("INSERT OR REPLACE INTO days VALUES(?,?,?,?,?,?)", (day.isoformat(), status, http, error, str(source) if source else None, digest))
        if status == "OK":
            for row in rows:
                self.db.execute("INSERT OR REPLACE INTO rows VALUES(?,?,?,?)", (row["date"], row["bse_code"], row["isin"], json.dumps(row, sort_keys=True)))
        self.db.commit()

    def export(self, root: Path, cohort: dict[str, str]):
        fields = ["date", "bse_code", "isin", "ticker", "open", "high", "low", "close", "volume", "trades", "turnover", "source", "source_file"]
        audits = []
        for code, expected in sorted(cohort.items()):
            records = [json.loads(x[0]) for x in self.db.execute("SELECT payload FROM rows WHERE bse_code=? AND isin=? ORDER BY day", (code, expected))]
            conflicts = self.db.execute("SELECT COUNT(*) FROM rows WHERE bse_code=? AND isin<>?", (code, expected)).fetchone()[0]
            if records:
                target = root / "normalized" / f"BSE-{code}.csv"
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader(); writer.writerows(records)
            audits.append({"bse_code": code, "isin": expected, "rows": len(records), "first_date": records[0]["date"] if records else "", "last_date": records[-1]["date"] if records else "", "identity_conflicts": conflicts})
        with (root / "per_code_audit.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(audits[0])); writer.writeheader(); writer.writerows(audits)
        statuses = dict(self.db.execute("SELECT status,COUNT(*) FROM days GROUP BY status"))
        summary = {"cohort_size": len(cohort), "day_statuses": statuses, "codes_with_rows": sum(x["rows"] > 0 for x in audits), "rows": sum(x["rows"] for x in audits), "identity_conflicts": sum(x["identity_conflicts"] for x in audits), "official_source": "BSE CM UDiFF daily bhavcopy"}
        (root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return summary


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cohort", type=Path, required=True)
    p.add_argument("--output-root", type=Path, required=True)
    p.add_argument("--from-date", type=date.fromisoformat, required=True)
    p.add_argument("--to-date", type=date.fromisoformat, required=True)
    p.add_argument("--delay-seconds", type=float, default=.2)
    p.add_argument("--timeout-seconds", type=int, default=30)
    args = p.parse_args(argv)
    if args.from_date < date(2024, 7, 8) or args.from_date > args.to_date or args.delay_seconds < .15:
        p.error("invalid UDiFF range or delay")
    cohort = load_cohort(args.cohort.resolve())
    root = args.output_root.resolve(); root.mkdir(parents=True, exist_ok=True)
    store = Store(root / "state.sqlite")
    pending = [d for d in weekdays(args.from_date, args.to_date) if not store.complete(d)]
    curl = curl_exe()
    for index, day in enumerate(pending, 1):
        name = f"BhavCopy_BSE_CM_0_0_0_{day:%Y%m%d}_F_0000.CSV"
        target = root / "raw" / str(day.year) / name
        url = f"https://www.bseindia.com/download/BhavCopy/Equity/{name}"
        http, rc, error = fetch(curl, url, target, args.timeout_seconds)
        if http in (404, 410):
            target.unlink(missing_ok=True); store.save(day, "NO_FILE", http=http, error="not published")
        elif rc != 0 or http != 200:
            store.save(day, "FAILED", http=http, error=f"curl={rc}:{error[:250]}", source=target if target.exists() else None)
        else:
            raw = target.read_bytes(); html = classify_html_response(raw)
            if html == "NO_FILE":
                target.unlink(missing_ok=True); store.save(day, "NO_FILE", http=http, error="BSE homepage for unpublished file")
            elif html:
                store.save(day, "FAILED", http=http, error=html, source=target)
            else:
                try:
                    rows = parse_udiff_csv(raw, day, set(cohort))
                    store.save(day, "OK", http=http, source=target, rows=rows)
                except Exception as exc:
                    store.save(day, "VALIDATION_FAILED", http=http, error=f"{type(exc).__name__}:{exc}", source=target)
        if index % 25 == 0:
            print(f"{index}/{len(pending)}", flush=True)
        if index < len(pending):
            time.sleep(args.delay_seconds + random.uniform(0, .1))
    print(json.dumps(store.export(root, cohort), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
