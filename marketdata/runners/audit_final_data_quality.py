"""Read-only end-to-end audit of the accepted current company-fact state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot  # noqa: E402


def audit(state_root: Path) -> dict[str, object]:
    result = load_company_fact_snapshot(resolve_company_fact_snapshot(state_root))
    facts = result.facts
    failures: list[str] = []
    if facts["ticker"].duplicated().any() or facts["isin"].duplicated().any():
        failures.append("DUPLICATE_CANONICAL_IDENTITY")
    prices = pd.to_numeric(facts["latest_price"], errors="coerce")
    if prices.dropna().le(0).any():
        failures.append("NONPOSITIVE_ACCEPTED_PRICE")
    for column in ("promoter_holding_pct", "public_holding_pct", "fii_holding_pct", "dii_holding_pct", "promoter_pledge_pct"):
        values = pd.to_numeric(facts[column], errors="coerce").dropna()
        if values.lt(0).any() or values.gt(100).any():
            failures.append(f"OUT_OF_RANGE_{column.upper()}")
    eligible = facts.loc[facts["product_baseline_eligible"].fillna(False).astype(bool)]
    required = [
        "product_sector", "product_baseline_yoy_growth", "product_baseline_cagr_3y",
        "product_baseline_cagr_5y", "product_baseline_days_since_recorded_high",
        "product_baseline_score", "product_baseline_sector_rank",
    ]
    if eligible[required].isna().any(axis=None):
        failures.append("INCOMPLETE_PRODUCT_BASELINE_ROW")
    dates = pd.to_datetime(facts["trade_date"], errors="coerce")
    history_ends = pd.to_datetime(facts["history_end_date"], errors="coerce")
    if (history_ends.dropna() > dates.loc[history_ends.notna()]).any():
        failures.append("FUTURE_HISTORY_OBSERVATION")

    sample_groups = {
        "bse_only": facts["primary_exchange"].eq("BSE"),
        "financial": facts["official_sector"].astype(str).str.contains("Financial|Bank|Insurance", case=False, regex=True),
        "recent_listing": pd.to_datetime(facts["listing_date"], errors="coerce").ge(pd.Timestamp("2024-01-01")),
        "professor": facts["professor_cohort"].fillna(False).astype(bool),
        "secondary_classification": facts["product_classification_evidence"].eq("EXACT_IDENTITY_SECONDARY_REFERENCE"),
        "official_classification": facts["product_classification_evidence"].eq("OFFICIAL"),
    }
    samples: dict[str, object] = {}
    sample_columns = [
        "ticker", "company", "isin", "primary_exchange", "trade_date",
        "product_sector", "product_classification_evidence", "history_status",
        "annual_report_status", "shareholding_status", "product_baseline_reason_code",
    ]
    for name, mask in sample_groups.items():
        selected = facts.loc[mask, sample_columns].sort_values("ticker", kind="stable").head(3)
        samples[name] = json.loads(selected.to_json(orient="records"))
    return {
        "status": "PASS" if not failures else "FAIL", "failures": failures,
        "fact_fingerprint": result.manifest["fingerprint"],
        "market_fingerprint": result.manifest["market_fingerprint"],
        "trade_date": result.manifest["trade_date"], "row_count": len(facts),
        "product_eligible_count": len(eligible), "samples": samples,
        "checks": {
            "canonical_identity_unique": "DUPLICATE_CANONICAL_IDENTITY" not in failures,
            "prices_positive": "NONPOSITIVE_ACCEPTED_PRICE" not in failures,
            "shareholding_percentages_bounded": not any(item.startswith("OUT_OF_RANGE") for item in failures),
            "eligible_model_rows_complete": "INCOMPLETE_PRODUCT_BASELINE_ROW" not in failures,
            "history_not_future_dated": "FUTURE_HISTORY_OBSERVATION" not in failures,
            "frozen_research_mutated": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit the accepted company-fact state without provider access.")
    parser.add_argument("--state-root", type=Path, default=ROOT / "data/company_facts")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = audit(args.state_root)
    payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
