from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

PROJECT = Path.home() / "Downloads" / "stock-ranking-platform"
TARGET_ISIN = "INE076C01018"

CURRENT_FACTS = PROJECT / "data/company_facts/snapshots/2026-09-07-62a07661b9ca51a7aee8a5c438a0a6669ad133a332e1eb2dda7c2c261cae3fb7/company_facts.csv"
PREVIOUS_FACTS = PROJECT / "data/company_facts/snapshots/2026-09-02-e4350c05db81377bbac176a6e43e7bee2761c622060b5e559d2019eb6266cc24/company_facts.csv"
CURRENT_LIVE = PROJECT / "data/live_market/snapshots/2026-09-07-4565a7d0b547bbdd09ad7560b659e9dbf50970b18b8da9bfdc93c43a85911ece/live_market.csv"
HISTORY_ROOT = PROJECT / "data/live_market/history_cache"
FROZEN_V2 = PROJECT / "data/marketdata/nifty50-research-v2-2026-08-07/standalone-contract-reason-fix-run-01"
ADDITIONS = PROJECT / "marketdata/specifications/pit_independently_validated_additions_v1.json"

OUTPUT = PROJECT / "data/diagnostics/v2_missing_isin_INE076C01018_20260907"


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def one_by_isin(path: Path, isin: str) -> dict:
    rows = [r for r in read_csv(path) if str(r.get("isin", "")).strip().upper() == isin]
    if len(rows) != 1:
        raise ValueError(f"{path}: expected exactly one row for {isin}, found {len(rows)}")
    return rows[0]


def select(r: dict) -> dict:
    wanted = [
        "ticker","company","isin","primary_exchange","exchange_security_id","series",
        "trade_date","latest_price","snapshot_status","snapshot_source",
        "history_status","history_reason","history_start_date","history_end_date",
        "history_observation_count","history_1y_usable","history_3y_usable","history_5y_usable",
        "baseline_eligible","baseline_reason_code",
        "v2_eligible","v2_reason_code","research_v2_score","research_v2_sector_rank",
        "roce","debt_to_equity","profit_growth_yoy","annual_report_status","annual_report_reason",
    ]
    return {k: r.get(k, "") for k in wanted if k in r}


def find_ticker_in_csvs(root: Path, ticker: str) -> dict:
    result = {}
    if not root.is_dir():
        return result
    for p in sorted(root.glob("*.csv")):
        try:
            rows = read_csv(p)
        except Exception:
            continue
        if not rows:
            continue
        matches = [r for r in rows if str(r.get("ticker", "")).strip() == ticker]
        if matches:
            result[p.name] = matches
    return result


def history_summary(path: Path) -> dict:
    if not path.is_file():
        return {"exists": False}
    rows = read_csv(path)
    if not rows:
        return {"exists": True, "rows": 0}
    return {
        "exists": True,
        "rows": len(rows),
        "first_date": rows[0].get("date"),
        "last_date": rows[-1].get("date"),
        "first_adjusted_close": rows[0].get("adjusted_close"),
        "last_adjusted_close": rows[-1].get("adjusted_close"),
        "last_raw_close": rows[-1].get("raw_close"),
    }


def main() -> int:
    try:
        current_fact = one_by_isin(CURRENT_FACTS, TARGET_ISIN)
        previous_fact = one_by_isin(PREVIOUS_FACTS, TARGET_ISIN)
        current_live = one_by_isin(CURRENT_LIVE, TARGET_ISIN)

        ticker = str(current_live.get("ticker") or current_fact.get("ticker") or previous_fact.get("ticker")).strip()
        if not ticker:
            raise ValueError("target ticker could not be resolved")

        frozen_hits = find_ticker_in_csvs(FROZEN_V2, ticker)

        additions_hit = None
        if ADDITIONS.is_file():
            raw = json.loads(ADDITIONS.read_text(encoding="utf-8"))
            blob = json.dumps(raw)
            additions_hit = ticker in blob or TARGET_ISIN in blob

        summary = {
            "target_isin": TARGET_ISIN,
            "ticker": ticker,
            "previous_company_facts": select(previous_fact),
            "current_company_facts": select(current_fact),
            "current_live_market": select(current_live),
            "current_history_cache": history_summary(HISTORY_ROOT / f"{ticker}.csv"),
            "frozen_v2_hits": frozen_hits,
            "present_in_current_additions_spec": additions_hit,
        }

        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        print(json.dumps(summary, indent=2, sort_keys=True))
        print(f"Saved: {OUTPUT / 'summary.json'}")
        print("TARGET V2 ISIN DIAGNOSTIC: PASS")
        print("No data or tests were modified.")
        return 0

    except Exception as exc:
        print(f"TARGET V2 ISIN DIAGNOSTIC FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
