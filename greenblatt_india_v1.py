from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(".")
STATE = ROOT / "data" / "company_facts" / "accepted_state.json"
OUT_DIR = ROOT / "data" / "analysis"

# Greenblatt excludes financial companies and utilities because their accounting
# makes the return-on-capital comparison less comparable.
EXCLUDED_SECTOR_PATTERNS = (
    r"\bfinance\b",
    r"\bfinancial\b",
    r"\bbank",
    r"\binsurance\b",
    r"\bcapital markets?\b",
    r"\butilities?\b",
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Greenblatt-style Indian equity ranking using current/reference data."
    )
    p.add_argument(
        "--min-market-cap-crore",
        type=float,
        default=1000.0,
        help="Minimum market cap in INR crore. Default: 1000.",
    )
    p.add_argument(
        "--top-n",
        type=int,
        default=30,
        help="Number of top stocks to print. Default: 30.",
    )
    return p.parse_args()


def excluded_sector(value: object) -> bool:
    text = str(value or "").strip().lower()
    return any(re.search(pattern, text, flags=re.I) for pattern in EXCLUDED_SECTOR_PATTERNS)


def main() -> int:
    args = parse_args()

    state = json.loads(STATE.read_text(encoding="utf-8"))
    snapshot = (
        ROOT / "data" / "company_facts" / state["snapshot_path"] / "company_facts.csv"
    )
    d = pd.read_csv(snapshot, low_memory=False)

    needed = [
        "ticker",
        "company",
        "isin",
        "primary_exchange",
        "product_sector",
        "product_industry",
        "screener_market_cap_crore",
        "screener_roic_pct",
        "screener_earnings_yield_pct",
    ]
    missing = [c for c in needed if c not in d.columns]
    if missing:
        raise SystemExit("Missing columns: " + ", ".join(missing))

    x = d[needed].copy()
    x["market_cap_crore"] = pd.to_numeric(
        x["screener_market_cap_crore"], errors="coerce"
    )
    x["roic_pct"] = pd.to_numeric(x["screener_roic_pct"], errors="coerce")
    x["earnings_yield_pct"] = pd.to_numeric(
        x["screener_earnings_yield_pct"], errors="coerce"
    )

    for c in ["market_cap_crore", "roic_pct", "earnings_yield_pct"]:
        x.loc[~np.isfinite(x[c]), c] = np.nan

    x["excluded_financial_or_utility"] = x["product_sector"].map(excluded_sector)
    x["passes_market_cap"] = x["market_cap_crore"] >= args.min_market_cap_crore
    x["passes_positive_roic"] = x["roic_pct"] > 0
    x["passes_positive_earnings_yield"] = x["earnings_yield_pct"] > 0

    x["greenblatt_eligible"] = (
        ~x["excluded_financial_or_utility"]
        & x["passes_market_cap"]
        & x["passes_positive_roic"]
        & x["passes_positive_earnings_yield"]
    )

    eligible = x.loc[x["greenblatt_eligible"]].copy()

    # Core Greenblatt idea: rank companies independently on business quality
    # (return on capital) and cheapness (earnings yield), then combine ranks.
    eligible["roic_rank"] = eligible["roic_pct"].rank(
        method="min", ascending=False
    )
    eligible["earnings_yield_rank"] = eligible["earnings_yield_pct"].rank(
        method="min", ascending=False
    )
    eligible["combined_rank_sum"] = (
        eligible["roic_rank"] + eligible["earnings_yield_rank"]
    )
    eligible["greenblatt_rank"] = eligible["combined_rank_sum"].rank(
        method="min", ascending=True
    )

    # Diagnostics only. These do NOT alter ranking.
    eligible["review_flag"] = ""
    eligible.loc[
        eligible["roic_pct"] > 200, "review_flag"
    ] += "EXTREME_ROIC_REVIEW;"
    eligible.loc[
        eligible["earnings_yield_pct"] > 50, "review_flag"
    ] += "EXTREME_EARNINGS_YIELD_REVIEW;"

    eligible = eligible.sort_values(
        ["greenblatt_rank", "roic_rank", "earnings_yield_rank"],
        kind="stable",
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = OUT_DIR / "greenblatt_india_v1.csv"
    eligible.to_csv(out_csv, index=False)

    summary = {
        "model": "greenblatt_india_v1",
        "description": (
            "Greenblatt-style current/reference ranking for Indian equities "
            "using ROIC and earnings yield."
        ),
        "source_snapshot": str(snapshot),
        "source_fingerprint": state.get("fingerprint"),
        "minimum_market_cap_crore": args.min_market_cap_crore,
        "excluded_sector_patterns": list(EXCLUDED_SECTOR_PATTERNS),
        "universe_rows": int(len(x)),
        "eligible_rows": int(len(eligible)),
        "excluded_financial_or_utility": int(x["excluded_financial_or_utility"].sum()),
        "failed_market_cap": int((~x["passes_market_cap"]).sum()),
        "failed_positive_roic": int((~x["passes_positive_roic"]).sum()),
        "failed_positive_earnings_yield": int(
            (~x["passes_positive_earnings_yield"]).sum()
        ),
        "warning": (
            "Uses Screener current/reference ROIC and earnings-yield fields. "
            "This is not PIT-safe Research V2 and must not overwrite frozen PIT evidence. "
            "Because the exact accounting adjustments used by Greenblatt's proprietary "
            "database are not replicated here, present this as Greenblatt-style / "
            "Magic-Formula-inspired, not as an exact reproduction of the proprietary screener."
        ),
    }

    out_json = OUT_DIR / "greenblatt_india_v1_summary.json"
    out_json.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("GREENBLATT-STYLE INDIA V1")
    print(f"Source: {snapshot}")
    print(f"Minimum market cap: Rs {args.min_market_cap_crore:,.0f} crore")
    print(f"Universe: {len(x)}")
    print(f"Eligible: {len(eligible)}")
    print(f"Output: {out_csv}")
    print(f"Summary: {out_json}")

    print(f"\nTOP {min(args.top_n, len(eligible))}")
    show_cols = [
        "greenblatt_rank",
        "ticker",
        "company",
        "product_sector",
        "market_cap_crore",
        "roic_pct",
        "roic_rank",
        "earnings_yield_pct",
        "earnings_yield_rank",
        "combined_rank_sum",
        "review_flag",
    ]
    print(eligible[show_cols].head(args.top_n).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
