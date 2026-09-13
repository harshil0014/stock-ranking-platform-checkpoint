"""Seed an exact listing-day price anchor from accepted official product state."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot  # noqa: E402
from stock_ranker.data_state import atomic_write_json  # noqa: E402


def run(state_root: Path, source: Path, output: Path, ticker: str) -> dict[str, object]:
    if output.exists():
        raise FileExistsError(f"output must be fresh: {output}")
    bundle = load_company_fact_snapshot(resolve_company_fact_snapshot(state_root))
    matches = bundle.facts.loc[bundle.facts["ticker"].astype(str).eq(ticker)]
    if len(matches) != 1:
        raise ValueError("ticker does not resolve to exactly one accepted ISIN")
    row = matches.iloc[0]
    trade_date = str(row["trade_date"])
    if str(row.get("listing_date") or "") != trade_date:
        raise ValueError("listing-day anchor requires listing_date == trade_date")
    price = float(row["latest_price"])
    if not math.isfinite(price) or price <= 0:
        raise ValueError("accepted listing-day price is unavailable")
    if str(row["history_status"]) != "NO_ACCEPTED_ADJUSTED_HISTORY":
        raise ValueError("security already has accepted adjusted history")

    shutil.copytree(source, output)
    target = output / f"{ticker}.csv"
    if target.exists():
        raise ValueError("listing anchor would overwrite history")
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["date", "raw_close", "adjusted_close"], lineterminator="\n"
        )
        writer.writeheader()
        writer.writerow({
            "date": trade_date,
            "raw_close": format(price, ".17g"),
            "adjusted_close": format(price, ".17g"),
        })

    audit_root = output.parent / f"{output.name}_audit"
    audit_root.mkdir(parents=True, exist_ok=False)
    with (audit_root / "per_code_decision.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["ticker", "status", "isin", "reason"], lineterminator="\n"
        )
        writer.writeheader()
        writer.writerow({
            "ticker": ticker,
            "status": "PROMOTED_TO_CANDIDATE",
            "isin": str(row["isin"]),
            "reason": "Exact accepted official listing-day observation; no earlier history asserted.",
        })
    report = {
        "ticker": ticker,
        "isin": str(row["isin"]),
        "exchange": str(row["primary_exchange"]),
        "listing_date": trade_date,
        "price": price,
        "source": "accepted official listing-day market observation",
        "company_fact_fingerprint": bundle.manifest["fingerprint"],
        "market_fingerprint": bundle.manifest["market_fingerprint"],
        "historical_periods_fabricated": False,
    }
    atomic_write_json(output.parent / f"{output.name}_listing_anchor.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, default=ROOT / "data/company_facts")
    parser.add_argument("--source-cache", type=Path, required=True)
    parser.add_argument("--output-cache", type=Path, required=True)
    parser.add_argument("--ticker", required=True)
    args = parser.parse_args(argv)
    report = run(
        args.state_root.resolve(), args.source_cache.resolve(),
        args.output_cache.resolve(), args.ticker,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
