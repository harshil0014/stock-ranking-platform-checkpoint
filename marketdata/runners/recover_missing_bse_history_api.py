"""Recover missing BSE price history from BSE's official Stock Prices API.

Research/recovery only. Writes isolated raw evidence and audit files; never mutates
accepted live-market state or a frozen personalized runtime.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot  # noqa: E402

API = "https://api.bseindia.com/BseIndiaAPI/api/StockpricesearchData/w"
REFERER = "https://www.bseindia.com/markets/equity/eqreports/stockprchistori?flag=sp"
DEFAULT_CUTOFF = date(2026, 9, 18)
DEFAULT_START = date(2021, 9, 1)


def read_codes(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    values = []
    for row in rows:
        raw = str(row.get("bse_code", "")).strip()
        if raw:
            values.append(raw.zfill(6))
    return sorted(set(values))


def load_bse_facts(root: Path) -> tuple[dict[str, dict[str, Any]], str]:
    snapshot = root if (root / "manifest.json").is_file() else resolve_company_fact_snapshot(root)
    bundle = load_company_fact_snapshot(snapshot)
    mapping: dict[str, dict[str, Any]] = {}
    frame = bundle.facts.loc[bundle.facts["primary_exchange"].astype(str).str.upper().eq("BSE")]
    for row in frame.to_dict("records"):
        code = str(row["exchange_security_id"]).strip().split(".", 1)[0].zfill(6)
        if str(row["ticker"]) != f"BSE-{code}":
            raise ValueError(f"accepted BSE identity mismatch for {code}")
        mapping[code] = row
    return mapping, str(bundle.manifest["fingerprint"])


def year_windows(start: date, cutoff: date) -> list[tuple[date, date]]:
    result = []
    cursor = start
    while cursor <= cutoff:
        end = min(date(cursor.year + 1, cursor.month, cursor.day) - timedelta(days=1), cutoff)
        result.append((cursor, end))
        cursor = end + timedelta(days=1)
    return result


def api_get(session: requests.Session, code: str, start: date, end: date, attempts: int) -> dict[str, Any]:
    params = {
        "MonthDate": start.strftime("%d/%m/%Y"),
        "YearDate": end.strftime("%d/%m/%Y"),
        "pageType": "sp",
        "Scode": code,
        "Seg": "C",
        "rbType": "D",
        "SortOrder": "true",
    }
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = session.get(API, params=params, timeout=45)
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            payload = response.json()
            if str(payload.get("scrip_cd", "")).strip().zfill(6) != code:
                raise RuntimeError(
                    f"API identity mismatch: requested {code}, got {payload.get('scrip_cd')!r}"
                )
            return payload
        except Exception as exc:
            last = exc
            if attempt < attempts:
                time.sleep(min(5.0, 0.8 * (2 ** (attempt - 1))))
    assert last is not None
    raise last


def normalize_rows(payloads: list[dict[str, Any]], code: str, isin: str, cutoff: date) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for row in payload.get("StockData") or []:
            raw_day = str(row.get("RealDate", "")).strip()
            try:
                day = datetime.fromisoformat(raw_day).date()
            except ValueError:
                continue
            if day > cutoff:
                continue
            close = float(str(row.get("qe_close", "")).replace(",", ""))
            if close <= 0:
                continue
            by_date[day.isoformat()] = {
                "date": day.isoformat(),
                "bse_code": code,
                "isin": isin,
                "close": f"{close:.10f}",
                "open": str(row.get("qe_open", "")).replace(",", ""),
                "high": str(row.get("qe_high", "")).replace(",", ""),
                "low": str(row.get("qe_low", "")).replace(",", ""),
                "volume": str(row.get("no_of_shrs", "")).replace(",", ""),
                "trade_count": str(row.get("no_trades", "")).replace(",", ""),
                "source": "BSE_STOCK_PRICE_API_EXACT_SCRIP",
            }
    return [by_date[key] for key in sorted(by_date)]


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    with pending.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    pending.replace(path)


def run(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output_root.resolve()
    raw_root = output / "raw"
    evidence_root = output / "evidence"
    output.mkdir(parents=True, exist_ok=True)
    raw_root.mkdir(exist_ok=True)
    evidence_root.mkdir(exist_ok=True)

    codes = read_codes(args.codes.resolve())
    facts, fingerprint = load_bse_facts(args.company_fact_root.resolve())
    cutoff = date.fromisoformat(args.cutoff)
    start = date.fromisoformat(args.start)
    if cutoff > DEFAULT_CUTOFF:
        raise ValueError("cutoff must not pass frozen 2026-09-18 state")
    windows = year_windows(start, cutoff)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": REFERER,
        "Accept": "application/json, text/plain, */*",
    })

    audit: list[dict[str, Any]] = []
    for position, code in enumerate(codes, 1):
        fact = facts.get(code)
        if fact is None:
            audit.append({
                "bse_code": code, "ticker": f"BSE-{code}", "isin": "", "status": "FAILED",
                "rows": 0, "udiff_isin_conflicts": 1, "error": "accepted BSE identity absent",
            })
            continue
        isin = str(fact["isin"]).strip()
        payloads = []
        evidence_hashes = []
        error = ""
        try:
            for first, last in windows:
                payload = api_get(session, code, first, last, args.attempts)
                canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                digest = hashlib.sha256(canonical).hexdigest()
                evidence_name = f"{code}_{first.isoformat()}_{last.isoformat()}_{digest[:12]}.json"
                (evidence_root / evidence_name).write_bytes(canonical)
                evidence_hashes.append(digest)
                payloads.append(payload)
                time.sleep(args.delay_seconds)

            rows = normalize_rows(payloads, code, isin, cutoff)
            if not rows:
                raise RuntimeError("official API returned no positive daily closes through cutoff")
            raw_path = raw_root / f"BSE-{code}.csv"
            write_csv(
                raw_path,
                rows,
                ["date", "bse_code", "isin", "close", "open", "high", "low", "volume", "trade_count", "source"],
            )
            raw_sha = hashlib.sha256(raw_path.read_bytes()).hexdigest()
            accepted_price = float(fact["latest_price"])
            terminal = float(rows[-1]["close"])
            terminal_diff = abs(terminal / accepted_price - 1) if accepted_price > 0 else float("inf")
            terminal_lag = (cutoff - date.fromisoformat(rows[-1]["date"])).days
            # The accepted price may be a different same-day snapshot convention for
            # a very illiquid BSE name. Keep the audit quantitative; builder will pin
            # the accepted trade-date price after adjustment.
            status = "RECOVERED" if terminal_lag <= 31 else "RECOVERED_STALE_TERMINAL"
            audit.append({
                "bse_code": code,
                "ticker": fact["ticker"],
                "isin": isin,
                "status": status,
                "rows": len(rows),
                "first_date": rows[0]["date"],
                "last_date": rows[-1]["date"],
                "terminal_lag_days": terminal_lag,
                "accepted_trade_date": str(fact["trade_date"]),
                "accepted_latest_price": accepted_price,
                "api_terminal_close": terminal,
                "terminal_relative_difference": terminal_diff,
                "udiff_isin_conflicts": 0,
                "raw_sha256": raw_sha,
                "evidence_response_count": len(evidence_hashes),
                "evidence_sha256_chain": hashlib.sha256("".join(evidence_hashes).encode()).hexdigest(),
                "error": "",
            })
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            audit.append({
                "bse_code": code,
                "ticker": fact["ticker"],
                "isin": isin,
                "status": "FAILED",
                "rows": 0,
                "udiff_isin_conflicts": 0,
                "error": error,
            })
        print(f"[{position}/{len(codes)}] {code}: {audit[-1]['status']} rows={audit[-1]['rows']}", flush=True)

    fields = [
        "bse_code", "ticker", "isin", "status", "rows", "first_date", "last_date",
        "terminal_lag_days", "accepted_trade_date", "accepted_latest_price",
        "api_terminal_close", "terminal_relative_difference", "udiff_isin_conflicts",
        "raw_sha256", "evidence_response_count", "evidence_sha256_chain", "error",
    ]
    write_csv(output / "audit.csv", audit, fields)
    summary = {
        "schema_version": "bse_official_missing_history_recovery_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "cutoff": cutoff.isoformat(),
        "start": start.isoformat(),
        "company_fact_fingerprint": fingerprint,
        "requested_codes": len(codes),
        "recovered": sum(str(row["status"]).startswith("RECOVERED") for row in audit),
        "failed": sum(row["status"] == "FAILED" for row in audit),
        "raw_rows": sum(int(row["rows"]) for row in audit),
        "official_source": API,
        "exact_scrip_code_requested": True,
        "post_cutoff_rows_retained": 0,
        "accepted_state_mutated": False,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--codes", type=Path, required=True)
    value.add_argument("--company-fact-root", type=Path, default=ROOT / "data/company_facts")
    value.add_argument("--output-root", type=Path, required=True)
    value.add_argument("--start", default=DEFAULT_START.isoformat())
    value.add_argument("--cutoff", default=DEFAULT_CUTOFF.isoformat())
    value.add_argument("--attempts", type=int, default=3)
    value.add_argument("--delay-seconds", type=float, default=0.15)
    return value


def main(argv: list[str] | None = None) -> int:
    try:
        result = run(parser().parse_args(argv))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["failed"] == 0 else 2
    except Exception as exc:
        print(f"BSE missing-history recovery failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
