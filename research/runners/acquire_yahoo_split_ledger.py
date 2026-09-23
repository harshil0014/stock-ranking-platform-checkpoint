"""Acquire a resumable provider split ledger for the frozen executable study."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import requests

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot


URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
PARAMS = {
    "period1": 1262304000,  # 2010-01-01 UTC
    "period2": 1789776000,  # 2026-09-19 UTC, one day after the frozen as-of date
    "interval": "3mo",
    "events": "splits",
    "includeAdjustedClose": "false",
}


def provider_symbol(row: dict) -> str:
    accepted = row.get("accepted_provider_symbol")
    if isinstance(accepted, str) and accepted.endswith((".NS", ".BO")):
        return accepted
    ticker = str(row["ticker"])
    return f"{ticker[4:]}.BO" if ticker.startswith("BSE-") else f"{ticker}.NS"


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def acquire_one(row: dict, raw: Path, retries: int) -> dict:
    symbol = provider_symbol(row)
    target = raw / f"{symbol}.json"
    source_url = URL.format(symbol=symbol)
    error = None
    if not target.is_file():
        for attempt in range(retries):
            try:
                response = requests.get(
                    source_url,
                    params=PARAMS,
                    headers={"User-Agent": "Mozilla/5.0 whole-share-research/1.0"},
                    timeout=30,
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("chart", {}).get("error") is not None:
                    raise ValueError(str(payload["chart"]["error"]))
                if not payload.get("chart", {}).get("result"):
                    raise ValueError("empty chart result")
                temporary = target.with_suffix(".json.tmp")
                temporary.write_text(
                    json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
                )
                temporary.replace(target)
                break
            except Exception as exc:  # acquisition audit retains the exact failure
                error = f"{type(exc).__name__}: {exc}"
                if attempt + 1 < retries:
                    time.sleep(1 + attempt)
    if not target.is_file():
        return {**row, "provider_symbol": symbol, "status": "FAILED", "event_count": 0,
                "response_sha256": None, "source_url": source_url, "reason": error}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        result = payload["chart"]["result"][0]
        splits = result.get("events", {}).get("splits", {})
        events = []
        for value in splits.values():
            numerator = float(value["numerator"])
            denominator = float(value["denominator"])
            events.append({
                "isin": row["isin"], "ticker": row["ticker"], "provider_symbol": symbol,
                "event_date": pd.to_datetime(int(value["date"]), unit="s", utc=True).tz_convert("Asia/Kolkata").date().isoformat(),
                "numerator": numerator, "denominator": denominator,
                "split_ratio": numerator / denominator, "source_url": source_url,
                "response_sha256": digest(target),
            })
        return {**row, "provider_symbol": symbol, "status": "SUCCESS", "event_count": len(events),
                "response_sha256": digest(target), "source_url": source_url, "reason": None,
                "events": events}
    except Exception as exc:
        return {**row, "provider_symbol": symbol, "status": "INVALID_RESPONSE", "event_count": 0,
                "response_sha256": digest(target), "source_url": source_url,
                "reason": f"{type(exc).__name__}: {exc}"}


def main(args) -> None:
    output = args.output.resolve()
    raw = output / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    members = []
    for months in (12, 36, 60):
        frame = pd.read_csv(args.frozen_root / f"frozen_cohort_{months}m.csv.gz", usecols=["isin", "ticker", "freeze_status"])
        members.append(frame.loc[frame.freeze_status.eq("INCLUDE_GLOBAL"), ["isin", "ticker"]])
    universe = pd.concat(members).drop_duplicates().sort_values(["ticker", "isin"], kind="stable")
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(args.company_facts_root)).facts
    provider = facts[["isin", "bulk_classification_provider_symbol"]].rename(
        columns={"bulk_classification_provider_symbol": "accepted_provider_symbol"}
    )
    universe = universe.merge(provider, on="isin", how="left", validate="one_to_one")
    if universe["isin"].duplicated().any() or universe["ticker"].duplicated().any():
        raise ValueError("frozen executable universe requires unique exact identities")
    rows = universe.to_dict("records")
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(acquire_one, row, raw, args.retries) for row in rows]
        for index, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if index % 100 == 0:
                print(json.dumps({"completed": index, "total": len(rows)}), flush=True)
    events = [event for result in results for event in result.pop("events", [])]
    audit = pd.DataFrame(results).sort_values(["ticker", "isin"], kind="stable")
    ledger_columns = ["isin", "ticker", "provider_symbol", "event_date", "numerator", "denominator",
                      "split_ratio", "source_url", "response_sha256"]
    ledger = pd.DataFrame(events, columns=ledger_columns).sort_values(
        ["ticker", "event_date"], kind="stable"
    ) if events else pd.DataFrame(columns=ledger_columns)
    audit.to_csv(output / "acquisition_audit.csv", index=False, lineterminator="\n")
    ledger.to_csv(output / "split_ledger.csv", index=False, lineterminator="\n")
    summary = {
        "schema_version": "yahoo_split_ledger_v1",
        "universe_count": len(universe),
        "status_counts": audit.status.value_counts().sort_index().to_dict(),
        "split_event_count": len(ledger),
        "complex_ratio_count": int((~ledger.split_ratio.round().eq(ledger.split_ratio)).sum()) if len(ledger) else 0,
        "audit_sha256": digest(output / "acquisition_audit.csv"),
        "ledger_sha256": digest(output / "split_ledger.csv"),
        "source": "Yahoo Finance chart splits exposed through the provider used by yfinance",
        "parameters": PARAMS,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--company-facts-root", type=Path, default=ROOT / "data/company_facts")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--retries", type=int, default=3)
    main(parser.parse_args())
