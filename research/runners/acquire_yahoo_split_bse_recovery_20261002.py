"""Recover Yahoo split receipts for BSE identities using frozen official symbols."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import requests

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
PARAMS = {
    "period1": 1262304000,
    "period2": 1789776000,
    "interval": "3mo",
    "events": "splits",
    "includeAdjustedClose": "false",
}
CANDIDATES = ROOT / "experiments/personalized-deep-history-20261002/bse-yahoo-symbol-recovery-candidates.csv"
OUTPUT = ROOT / "experiments/personalized-deep-history-20261002/yahoo-split-bse-recovery-v1"

def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()

def acquire(row: dict, raw: Path, retries: int = 3) -> dict:
    symbol = str(row["candidate_provider"]).upper()
    if not re.fullmatch(r"[A-Z0-9&_-]+\.BO", symbol):
        raise ValueError(f"invalid official provider symbol: {symbol}")
    url = URL.format(symbol=symbol)
    target = raw / f"{symbol}.json"
    error = None
    for attempt in range(retries):
        try:
            response = requests.get(
                url, params=PARAMS,
                headers={"User-Agent": "Mozilla/5.0 exact-bse-split-recovery/1.0"},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            chart = payload.get("chart", {})
            if chart.get("error") is not None or not chart.get("result"):
                raise ValueError(f"invalid chart result: {chart.get('error')}")
            result = chart["result"][0]
            meta = result.get("meta", {})
            returned = str(meta.get("symbol", "")).upper()
            if returned != symbol:
                raise ValueError(f"returned symbol mismatch: {returned!r} != {symbol!r}")
            instrument = str(meta.get("instrumentType", "")).upper()
            if instrument and instrument != "EQUITY":
                raise ValueError(f"returned instrument is {instrument}")
            target.write_text(
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            events = []
            for value in result.get("events", {}).get("splits", {}).values():
                numerator = float(value["numerator"])
                denominator = float(value["denominator"])
                events.append({
                    "isin": row["isin"], "ticker": row["ticker"],
                    "provider_symbol": symbol,
                    "event_date": pd.to_datetime(
                        int(value["date"]), unit="s", utc=True
                    ).tz_convert("Asia/Kolkata").date().isoformat(),
                    "numerator": numerator, "denominator": denominator,
                    "split_ratio": numerator / denominator,
                    "source_url": url, "response_sha256": digest(target),
                })
            return {
                "ticker": row["ticker"], "isin": row["isin"],
                "official_bse_code": row["code"], "official_bse_symbol": row["symbol"],
                "provider_symbol": symbol, "status": "SUCCESS",
                "event_count": len(events), "response_sha256": digest(target),
                "source_url": url, "reason": None, "events": events,
            }
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if attempt + 1 < retries:
                time.sleep(1 + attempt)
    return {
        "ticker": row["ticker"], "isin": row["isin"],
        "official_bse_code": row["code"], "official_bse_symbol": row["symbol"],
        "provider_symbol": symbol, "status": "FAILED", "event_count": 0,
        "response_sha256": None, "source_url": url, "reason": error,
    }

def main() -> int:
    if OUTPUT.exists():
        raise FileExistsError(f"fresh output required: {OUTPUT}")
    OUTPUT.mkdir(parents=True)
    raw = OUTPUT / "raw"
    raw.mkdir()
    candidates = pd.read_csv(CANDIDATES, low_memory=False)
    exact = (
        candidates["code_found"].eq(True)
        & candidates["isin_exact"].eq(True)
        & candidates["equity"].eq(True)
        & candidates["symbol_valid"].eq(True)
    )
    work = candidates.loc[exact].copy()
    unresolved = candidates.loc[~exact].copy()
    results = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(acquire, row, raw) for row in work.to_dict("records")]
        for i, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if i % 10 == 0:
                print(json.dumps({"completed": i, "total": len(work)}), flush=True)
    events = [event for result in results for event in result.pop("events", [])]
    audit = pd.DataFrame(results)
    for row in unresolved.to_dict("records"):
        audit.loc[len(audit)] = {
            "ticker": row["ticker"], "isin": row["isin"],
            "official_bse_code": row["code"], "official_bse_symbol": row.get("symbol"),
            "provider_symbol": None, "status": "UNRESOLVED_OFFICIAL_IDENTITY",
            "event_count": 0, "response_sha256": None, "source_url": None,
            "reason": "official BSE code/ISIN/equity/symbol contract not fully satisfied",
        }
    audit = audit.sort_values(["ticker", "isin"], kind="stable")
    audit.to_csv(OUTPUT / "recovery_audit.csv", index=False, lineterminator="\n")
    ledger_columns = [
        "isin", "ticker", "provider_symbol", "event_date", "numerator",
        "denominator", "split_ratio", "source_url", "response_sha256",
    ]
    ledger = (
        pd.DataFrame(events, columns=ledger_columns)
        .sort_values(["ticker", "event_date"], kind="stable")
    )
    ledger.to_csv(OUTPUT / "split_ledger_recovered.csv", index=False, lineterminator="\n")
    success = int(audit.status.eq("SUCCESS").sum())
    failed = int(audit.status.eq("FAILED").sum())
    unresolved_count = int(audit.status.eq("UNRESOLVED_OFFICIAL_IDENTITY").sum())
    summary = {
        "schema_version": "yahoo_split_bse_official_symbol_recovery_v1",
        "source": "Yahoo Finance chart splits using exact BSE ListofScripData symbol",
        "official_identity_source": "frozen bulk-classification BSE master retrieved 2026-08-23",
        "parameters": PARAMS,
        "original_failed_identities": int(len(candidates)),
        "exact_official_symbol_candidates": int(len(work)),
        "successful_responses": success,
        "failed_responses": failed,
        "unresolved_official_identity": unresolved_count,
        "recovered_split_event_count": int(len(ledger)),
        "audit_sha256": digest(OUTPUT / "recovery_audit.csv"),
        "ledger_sha256": digest(OUTPUT / "split_ledger_recovered.csv"),
        "returned_symbol_exact_required": True,
        "accepted_state_mutated": False,
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
