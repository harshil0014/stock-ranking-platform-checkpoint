"""Post-reveal structural repair: official closes for the Sep 1-18 gap.

This does not change scores or the first reveal. It creates a separate overlay
for sensitivity analysis after the weekly execution-gap defect was identified.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import numpy as np
import pandas as pd
import requests
from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot

BASE = ROOT / "experiments/personalized-v13-20261002/prospective-2025-09-30"
OUT = BASE / "post_reveal_price_repair_20260901_18"
DATES = [d.date().isoformat() for d in pd.bdate_range("2026-09-01", "2026-09-18")]


def sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def download(day: str, exchange: str) -> tuple[Path | None, str]:
    compact = day.replace("-", "")
    if exchange == "NSE":
        name = f"BhavCopy_NSE_CM_0_0_0_{compact}_F_0000.csv.zip"
        url = f"https://nsearchives.nseindia.com/content/cm/{name}"
    else:
        name = f"BhavCopy_BSE_CM_0_0_0_{compact}_F_0000.csv"
        url = f"https://www.bseindia.com/download/BhavCopy/Equity/{name}"
    path = OUT / "official_prices" / name
    if not path.exists():
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"}, timeout=25)
        if response.status_code in (404, 400):
            return None, url
        response.raise_for_status()
        if response.content.lstrip().startswith(b"<"):
            return None, url
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
    if path.read_bytes()[:100].lstrip().startswith(b"<"):
        return None, url
    return path, url


def main() -> None:
    if not (BASE / "evaluation_record.json").exists():
        raise ValueError("repair must remain explicitly post-reveal")
    if (OUT / "summary.json").exists():
        raise FileExistsError("repair already complete")
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
    locator = facts[["isin", "ticker", "primary_exchange"]].rename(columns={"primary_exchange": "exchange"})
    sources, pieces, absent = [], [], []
    for day in DATES:
        daily = []
        for exchange in ("NSE", "BSE"):
            path, url = download(day, exchange)
            if path is None:
                absent.append({"day": day, "exchange": exchange, "source_url": url})
                continue
            if path.suffix == ".zip":
                with ZipFile(BytesIO(path.read_bytes())) as archive:
                    frame = pd.read_csv(BytesIO(archive.read(archive.namelist()[0])), low_memory=False)
            else:
                frame = pd.read_csv(path, low_memory=False)
            if set(frame.TradDt.astype(str)) != {day}:
                raise ValueError("wrong official date")
            frame["exchange"] = exchange
            frame = frame.merge(locator, left_on=["ISIN", "exchange"],
                                right_on=["isin", "exchange"], how="inner", validate="many_to_one")
            frame = frame.sort_values("SctySrs", key=lambda s: s.ne("EQ"), kind="stable")
            frame = frame.drop_duplicates("isin")
            frame["close"] = pd.to_numeric(frame.ClsPric, errors="coerce")
            frame = frame.loc[frame.close.gt(0), ["isin", "ticker", "exchange", "close"]]
            frame["date"] = day
            daily.append(frame)
            sources.append({"day": day, "exchange": exchange, "source_url": url,
                            "source_sha256": sha(path), "matched_identities": len(frame)})
        if len(daily) == 1:
            raise ValueError(f"only one exchange had official prices on {day}")
        if daily:
            pieces.extend(daily)
        print(json.dumps({"day": day, "files": len(daily)}), flush=True)
    official = pd.concat(pieces, ignore_index=True)
    if official.duplicated(["isin", "date"]).any():
        raise ValueError("duplicate official repair price")
    pd.DataFrame(sources).to_csv(OUT / "official_price_sources.csv", index=False)
    official.to_csv(OUT / "official_prices_mapped.csv.gz", index=False,
                    compression={"method": "gzip", "mtime": 0})
    splits = pd.read_csv(BASE / "provider_split_ledger/split_ledger.csv")
    recovery = pd.read_csv(ROOT / "research/data/ownership-recovery-20260925/history_recovery_audit.csv")
    adjustment = recovery.dropna(subset=["provider_adjustment_through"]).set_index("ticker").provider_adjustment_through.to_dict()
    nominal = set(recovery.loc[recovery.raw_basis.eq("OFFICIAL_NOMINAL"), "ticker"])
    for ticker in splits.loc[splits.event_date.gt("2026-09-18"), "ticker"]:
        adjustment[ticker] = "2026-09-30"
    split_groups = {k: g for k, g in splits.groupby("isin")}
    root = OUT / "history_overlay"
    root.mkdir(parents=True, exist_ok=True)
    inserted = overwritten = files = 0
    for isin, group in official.groupby("isin"):
        ticker = group.ticker.iloc[0]
        base = BASE / "official_execution_overlay" / f"{ticker}.csv"
        if not base.exists():
            continue
        history = pd.read_csv(base)
        cutoff = adjustment.get(ticker, "2026-09-30")
        events = split_groups.get(isin, pd.DataFrame())
        events = events.loc[events.event_date.le(cutoff)] if len(events) else events
        extra = group[["date", "close"]].copy()
        factors = np.ones(len(extra))
        if ticker not in nominal:
            for event in events.itertuples(index=False):
                factors[extra.date.lt(event.event_date).to_numpy()] *= event.split_ratio
        extra["raw_close"] = extra.close.to_numpy() / factors
        extra["adjusted_close"] = extra.raw_close
        extra = extra[["date", "raw_close", "adjusted_close"]]
        dates = set(history.date)
        inserted += int((~extra.date.isin(dates)).sum())
        overwritten += int(extra.date.isin(dates).sum())
        history = pd.concat([history.loc[~history.date.isin(set(extra.date))], extra], ignore_index=True)
        history = history.sort_values("date", kind="stable")
        if history.date.duplicated().any() or history.raw_close.le(0).any():
            raise ValueError(f"invalid repaired history {ticker}")
        history.to_csv(root / f"{ticker}.csv", index=False, float_format="%.17g")
        files += 1
    summary = {"schema": "v13_post_reveal_execution_price_repair_v1",
               "reason": "September 1-18 daily price gaps cause weekly MISSING_EXECUTION_PRICE",
               "first_reveal_sha256": sha(BASE / "evaluation_record.json"),
               "locked_scores_sha256": sha(BASE / "scores_before_reveal.csv.gz"),
               "official_source_files": len(sources), "absent_exchange_days": absent,
               "official_price_rows": len(official), "overlay_files": files,
               "newly_filled_dates": inserted, "official_replacements": overwritten,
               "first_reveal_overwritten": False, "selection_changed": False,
               "accepted_data_mutated": False}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
