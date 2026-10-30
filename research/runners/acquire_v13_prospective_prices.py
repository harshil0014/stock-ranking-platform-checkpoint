"""Research-only, resumable Yahoo extension to the reserved V13 endpoint.

The accepted cache is read-only. Each successful chart response is retained with
its hash. Existing Close observations are rebased only for observed new provider
splits, then new dated observations are appended. Ambiguous histories are
quarantined rather than filled.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import sys
import time
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "experiments/personalized-deep-history-20261002/yahoo-split-ledger-v2"
DEST = ROOT / "experiments/personalized-v13-20261002/prospective-2025-09-30/prices"
CACHE = ROOT / "data/live_market/history_cache"
START = "2026-09-01"
OLD_END = "2026-09-18"
END = "2026-09-30"


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def task(row: dict) -> dict:
    import pandas as pd

    identity, ticker, symbol = row["isin"], row["ticker"], row["provider_symbol"]
    raw_path = DEST / "raw" / f"{identity}.json"
    output = DEST / "history_overlay" / f"{ticker}.csv"
    receipt = DEST / "receipts" / f"{identity}.json"
    if receipt.exists():
        previous = json.loads(receipt.read_text())
        if (previous.get("status") == "SUCCESS" and output.is_file()
                and digest(output.read_bytes()) == previous.get("overlay_sha256")
                and digest(raw_path.read_bytes()) == previous.get("response_sha256")):
            return previous
    base = CACHE / f"{ticker}.csv"
    if not base.is_file():
        return {"isin": identity, "ticker": ticker, "status": "FAILED", "reason": "CACHE_MISSING"}
    old_bytes = base.read_bytes()
    old = pd.read_csv(base)
    if old.date.duplicated().any() or not {"date", "raw_close", "adjusted_close"}.issubset(old):
        return {"isin": identity, "ticker": ticker, "status": "FAILED", "reason": "CACHE_INVALID"}
    if not raw_path.exists():
        start = int(pd.Timestamp(START, tz="UTC").timestamp())
        end = int(pd.Timestamp("2026-10-01", tz="UTC").timestamp())
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}"
               f"?period1={start}&period2={end}&interval=1d&events=div%2Csplits")
        last = None
        for attempt in range(3):
            try:
                with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as response:
                    payload = response.read()
                parsed = json.loads(payload)
                if not parsed.get("chart", {}).get("result"):
                    raise ValueError(str(parsed.get("chart", {}).get("error")))
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_bytes(payload)
                break
            except Exception as exc:
                last = f"{type(exc).__name__}: {exc}"
                time.sleep(attempt + 1)
        else:
            return {"isin": identity, "ticker": ticker, "status": "FAILED", "reason": last}
    payload = raw_path.read_bytes()
    try:
        chart = json.loads(payload)["chart"]["result"][0]
        quoted = chart["indicators"]["quote"][0]["close"]
        adjusted = chart["indicators"].get("adjclose", [{}])[0].get("adjclose", quoted)
        new = pd.DataFrame({
            "date": pd.to_datetime(chart["timestamp"], unit="s", utc=True).tz_convert("Asia/Kolkata").strftime("%Y-%m-%d"),
            "raw_close": quoted, "adjusted_close": adjusted,
        })
        new = new.loc[new.date.le(END)].dropna().copy()
        if new.empty or new.date.duplicated().any() or new.raw_close.le(0).any():
            raise ValueError("INVALID_CHART_QUOTES")
        splits = []
        for event in chart.get("events", {}).get("splits", {}).values():
            day = pd.Timestamp(event["date"], unit="s", tz="UTC").tz_convert("Asia/Kolkata").date().isoformat()
            if OLD_END < day <= END:
                numerator = float(event["numerator"])
                denominator = float(event["denominator"])
                if numerator <= 0 or denominator <= 0:
                    raise ValueError("INVALID_SPLIT_RATIO")
                splits.append({"event_date": day, "numerator": numerator,
                               "denominator": denominator, "split_ratio": numerator / denominator})
        rebased = old.copy()
        for split in splits:
            before = rebased.date.lt(split["event_date"])
            rebased.loc[before, ["raw_close", "adjusted_close"]] /= split["split_ratio"]
        overlap = rebased.merge(new, on="date", suffixes=("_old", "_new"))
        overlap = overlap.loc[overlap.date.between(START, OLD_END)]
        if not overlap.empty:
            error = ((overlap.raw_close_old - overlap.raw_close_new).abs()
                     / overlap.raw_close_new).max()
            if error > 0.015:
                raise ValueError(f"OVERLAP_PRICE_BASIS_MISMATCH:{error:.6g}")
        extension = new.loc[new.date.gt(OLD_END)]
        combined = pd.concat([rebased, extension], ignore_index=True)
        combined = combined.sort_values("date", kind="stable")
        if combined.date.duplicated().any() or combined.raw_close.le(0).any():
            raise ValueError("OVERLAY_INVALID")
        output.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(output, index=False, float_format="%.17g")
        result = {"isin": identity, "ticker": ticker, "provider_symbol": symbol,
                  "status": "SUCCESS", "response_sha256": digest(payload),
                  "source_url": f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}",
                  "accepted_cache_sha256": digest(old_bytes), "overlay_sha256": digest(output.read_bytes()),
                  "observations_appended": len(extension), "last_observed_date": combined.date.max(),
                  "overlap_rows": len(overlap), "new_split_events": splits}
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(result, sort_keys=True) + "\n")
        return result
    except Exception as exc:
        return {"isin": identity, "ticker": ticker, "status": "FAILED",
                "response_sha256": digest(payload), "reason": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    import pandas as pd
    audit = pd.read_csv(SOURCE / "acquisition_audit.csv", low_memory=False)
    success = audit.loc[audit.status.eq("SUCCESS"), ["isin", "ticker", "provider_symbol"]]
    DEST.mkdir(parents=True, exist_ok=True)
    rows = []
    with ThreadPoolExecutor(max_workers=12) as executor:
        jobs = {executor.submit(task, row._asdict()): row.isin for row in success.itertuples(index=False)}
        for index, future in enumerate(as_completed(jobs), 1):
            result = future.result()
            rows.append(result)
            if index % 200 == 0:
                print(json.dumps({"completed": index, "total": len(jobs),
                                  "success": sum(x["status"] == "SUCCESS" for x in rows)}), flush=True)
    pd.DataFrame(rows).sort_values("isin").to_csv(DEST / "acquisition_audit.csv", index=False)
    summary = {"schema": "v13_prospective_price_overlay_v1", "retrieved_at": datetime.now(timezone.utc).isoformat(),
               "requested": len(success), "success": sum(x["status"] == "SUCCESS" for x in rows),
               "failed": sum(x["status"] != "SUCCESS" for x in rows),
               "append_rows": sum(x.get("observations_appended", 0) for x in rows),
               "new_split_events": sum(len(x.get("new_split_events", [])) for x in rows),
               "accepted_cache_mutated": False,
               "source_audit_sha256": digest((SOURCE / "acquisition_audit.csv").read_bytes())}
    (DEST / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
