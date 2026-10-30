"""Acquire official daily exchange closes and audit V13 Yahoo extension."""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import pandas as pd
import requests
from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot

OUT = ROOT / "experiments/personalized-v13-20261002/prospective-2025-09-30"
DATES = ("2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24",
         "2026-09-25", "2026-09-28", "2026-09-29", "2026-09-30")


def sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def download(day: str, exchange: str) -> Path:
    compact = day.replace("-", "")
    if exchange == "NSE":
        name = f"BhavCopy_NSE_CM_0_0_0_{compact}_F_0000.csv.zip"
        url = f"https://nsearchives.nseindia.com/content/cm/{name}"
    else:
        name = f"BhavCopy_BSE_CM_0_0_0_{compact}_F_0000.csv"
        url = f"https://www.bseindia.com/download/BhavCopy/Equity/{name}"
    path = OUT / "official_prices" / name
    if not path.exists():
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"}, timeout=30)
        response.raise_for_status()
        payload = response.content
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return path


def main() -> None:
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
    lookup = facts[["isin", "ticker", "primary_exchange"]].rename(columns={"primary_exchange": "exchange"})
    overlay_parts = []
    for path in (OUT / "prices/history_overlay").glob("*.csv"):
        prices = pd.read_csv(path, usecols=["date", "raw_close"])
        prices = prices.loc[prices.date.isin(DATES)].copy()
        if len(prices):
            prices["ticker"] = path.stem
            overlay_parts.append(prices)
    overlay_prices = pd.concat(overlay_parts, ignore_index=True).rename(columns={"date": "day", "raw_close": "yahoo_close"})
    audits, checks = [], []
    for day in DATES:
        for exchange in ("NSE", "BSE"):
            path = download(day, exchange)
            if path.suffix == ".zip":
                with ZipFile(BytesIO(path.read_bytes())) as archive:
                    if len(archive.namelist()) != 1:
                        raise ValueError("unexpected NSE archive")
                    frame = pd.read_csv(BytesIO(archive.read(archive.namelist()[0])), low_memory=False)
            else:
                frame = pd.read_csv(path, low_memory=False)
            if not {"TradDt", "ISIN", "ClsPric", "SctySrs"}.issubset(frame):
                raise ValueError("invalid official bhavcopy schema")
            if set(frame.TradDt.astype(str)) != {day}:
                raise ValueError("wrong official bhavcopy trade date")
            frame["exchange"] = exchange
            frame = frame.merge(lookup, left_on=["ISIN", "exchange"],
                                right_on=["isin", "exchange"], how="inner", validate="many_to_one")
            if frame.duplicated(["isin", "exchange"]).any():
                frame = frame.loc[frame.SctySrs.eq("EQ")].drop_duplicates(["isin", "exchange"])
            official = frame[["isin", "ticker", "ClsPric"]].copy()
            official["ClsPric"] = pd.to_numeric(official.ClsPric, errors="coerce")
            official = official.loc[official.ClsPric.gt(0)]
            official["day"] = day
            matched = official.merge(overlay_prices, on=["ticker", "day"], how="inner", validate="one_to_one")
            matched["exchange"] = exchange
            matched = matched.rename(columns={"ClsPric": "official_close"})
            matched["relative_gap"] = (matched.yahoo_close - matched.official_close).abs() / matched.official_close
            rows = matched[["isin", "ticker", "day", "exchange", "official_close", "yahoo_close", "relative_gap"]].to_dict("records")
            checks.extend(rows)
            audits.append({"day": day, "exchange": exchange, "source_url": (
                f"https://nsearchives.nseindia.com/content/cm/{path.name}" if exchange == "NSE" else
                f"https://www.bseindia.com/download/BhavCopy/Equity/{path.name}"),
                "source_sha256": sha(path), "official_rows": len(official), "matched_overlay_rows": len(rows)})
            print(json.dumps({"day": day, "exchange": exchange, "matched": len(rows)}), flush=True)
    pd.DataFrame(checks).to_csv(OUT / "official_price_comparison.csv", index=False)
    pd.DataFrame(audits).to_csv(OUT / "official_price_sources.csv", index=False)
    c = pd.DataFrame(checks)
    summary = {"schema": "v13_prospective_official_price_audit_v1",
               "dates": list(DATES), "comparison_rows": len(c),
               "exact_within_1pct": int(c.relative_gap.le(.01).sum()),
               "over_1pct": int(c.relative_gap.gt(.01).sum()),
               "over_5pct": int(c.relative_gap.gt(.05).sum()),
               "endpoint_matched": int(c.day.eq("2026-09-30").sum()),
               "official_source_manifest_sha256": sha(OUT / "official_price_sources.csv")}
    (OUT / "official_price_audit.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
