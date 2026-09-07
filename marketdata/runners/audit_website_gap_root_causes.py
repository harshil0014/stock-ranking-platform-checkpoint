"""Classify website missing-data gaps by root cause and recovery route.

This audit is read-only. It never mutates accepted market/company-fact state and
never turns secondary/current product evidence into Research V2 evidence.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stock_ranker.company_facts import (  # noqa: E402
    load_company_fact_snapshot,
    resolve_company_fact_snapshot,
)


CATEGORIES = (
    "current_price", "classification", "market_cap", "valuation",
    "annual_financials", "quarterly_financials", "balance_sheet", "cash_flow",
    "shareholding", "accepted_history", "history_1y", "history_3y", "history_5y",
    "roce", "roe", "debt_to_equity", "profit_growth", "documents", "company_profile",
)

CRITICAL = {
    "current_price", "classification", "market_cap", "valuation",
    "annual_financials", "quarterly_financials", "balance_sheet", "cash_flow",
    "shareholding", "accepted_history", "roce", "roe", "debt_to_equity", "profit_growth",
}


def _present(value: Any) -> bool:
    return value is not None and not pd.isna(value) and str(value).strip() not in {"", "nan", "None"}


def _truth(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _first(row: pd.Series, *names: str) -> Any:
    for name in names:
        if name in row and _present(row.get(name)):
            return row.get(name)
    return None


def _available(row: pd.Series, category: str) -> bool:
    if category == "current_price":
        return _present(row.get("latest_price"))
    if category == "classification":
        return _present(_first(row, "product_sector", "official_sector", "secondary_sector", "bulk_classification_sector", "screener_industry_group"))
    if category == "market_cap":
        return _present(_first(row, "official_market_cap", "market_cap", "screener_market_cap_crore"))
    if category == "valuation":
        return any(_present(_first(row, name)) for name in (
            "official_pe_ratio", "official_pb_ratio", "pe_ratio", "pb_ratio", "screener_pe_ratio", "screener_pb_ratio"
        ))
    if category == "annual_financials":
        return any(_present(_first(row, name)) for name in (
            "official_annual_revenue", "official_annual_pat", "secondary_annual_revenue", "secondary_annual_net_income"
        )) or str(row.get("annual_report_status", "")).startswith("ACCEPTED")
    if category == "quarterly_financials":
        return any(_present(_first(row, name)) for name in (
            "official_quarterly_revenue", "official_quarterly_pat", "secondary_quarterly_revenue", "secondary_quarterly_net_income"
        )) or str(row.get("quarterly_results_status", "")).startswith("AVAILABLE")
    if category == "balance_sheet":
        return any(_present(_first(row, name)) for name in (
            "official_total_assets", "official_equity", "official_borrowings", "secondary_total_assets", "secondary_total_debt", "secondary_stockholders_equity"
        )) or str(row.get("balance_sheet_status", "")).startswith("AVAILABLE")
    if category == "cash_flow":
        return _present(_first(row, "official_operating_cash_flow", "secondary_operating_cash_flow", "secondary_free_cash_flow")) or str(row.get("cash_flow_status", "")).startswith("AVAILABLE")
    if category == "shareholding":
        return any(_present(_first(row, name)) for name in (
            "official_total_shares", "promoter_holding_pct", "public_holding_pct", "fii_holding_pct", "dii_holding_pct",
            "screener_promoter_holding_pct", "screener_public_holding_pct"
        )) or str(row.get("shareholding_status", "")).startswith("AVAILABLE")
    if category == "accepted_history":
        return str(row.get("history_status", "")) == "ACCEPTED_ADJUSTED_HISTORY"
    if category == "history_1y":
        return _truth(row.get("history_1y_usable"))
    if category == "history_3y":
        return _truth(row.get("history_3y_usable"))
    if category == "history_5y":
        return _truth(row.get("history_5y_usable"))
    if category == "roce":
        return _present(_first(row, "roce", "screener_roce_pct"))
    if category == "roe":
        return _present(_first(row, "official_return_on_equity", "return_on_equity", "screener_roe_pct"))
    if category == "debt_to_equity":
        return _present(_first(row, "official_debt_to_equity", "debt_to_equity", "secondary_debt_to_equity", "screener_debt_to_equity"))
    if category == "profit_growth":
        return _present(_first(row, "official_profit_growth_yoy", "profit_growth_yoy", "secondary_profit_growth", "screener_profit_growth_pct"))
    if category == "documents":
        return _present(_first(row, "latest_document_url", "annual_report_source_url"))
    if category == "company_profile":
        # Every accepted security has enough canonical identity for a useful
        # deterministic structured profile; provider prose is optional.
        return _present(row.get("company")) and _present(row.get("isin")) and _present(row.get("primary_exchange"))
    raise KeyError(category)


def _listing_age_years(row: pd.Series, as_of: date) -> float | None:
    raw = row.get("listing_date")
    if not _present(raw):
        return None
    parsed = pd.to_datetime(raw, errors="coerce")
    if pd.isna(parsed):
        return None
    return max(0.0, (as_of - parsed.date()).days / 365.2425)


def _cause(row: pd.Series, category: str, as_of: date) -> tuple[str, str, str]:
    """Return root_cause, recovery_route, terminal_state."""
    age = _listing_age_years(row, as_of)
    if category.startswith("history_") and category != "accepted_history":
        years = int(category.split("_")[1].replace("y", ""))
        if age is not None and age < years:
            return (
                "LISTING_HORIZON_TOO_SHORT",
                "NO_ACQUISITION_NEEDED",
                f"INSUFFICIENT_LISTING_HISTORY_{years}Y",
            )
        if str(row.get("history_status", "")) != "ACCEPTED_ADJUSTED_HISTORY":
            return (
                "HISTORY_NOT_ACQUIRED",
                "EXACT_IDENTITY_NSE_BSE_HISTORY_RECOVERY",
                "ACTION_REQUIRED",
            )
        return (
            "HISTORY_ANCHOR_OR_CONTINUITY_GAP",
            "REVALIDATE_ADJUSTED_HISTORY_ANCHORS_AND_CORPORATE_ACTIONS",
            "ACTION_REQUIRED",
        )
    if category == "accepted_history":
        reason = str(row.get("history_reason", ""))
        if "corporate" in reason.lower() or "adjust" in reason.lower():
            return "CORPORATE_ACTION_UNRESOLVED", "OFFICIAL_ACTION_LEDGER_REVIEW", "ACTION_REQUIRED"
        return "HISTORY_NOT_ACQUIRED", "EXACT_IDENTITY_NSE_BSE_HISTORY_RECOVERY", "ACTION_REQUIRED"
    if category == "current_price":
        return "NO_TRADE_ON_AS_OF_DATE", "PRIMARY_THEN_SAME_ISIN_SECONDARY_EXCHANGE_THEN_PRIOR_TRADE_STATE", "NEEDS_TRADE_STATE"
    if category == "classification":
        return "CLASSIFICATION_NOT_ACQUIRED", "OFFICIAL_THEN_EXACT_IDENTITY_SECONDARY_CLASSIFICATION", "ACTION_REQUIRED"
    if category == "company_profile":
        return "RESOLVED_STRUCTURED_PROFILE", "BUILD_DETERMINISTIC_IDENTITY_PROFILE", "VALUE_AVAILABLE"
    if category == "documents":
        return "OFFICIAL_DOCUMENT_NOT_INDEXED", "CURRENT_NSE_BSE_DOCUMENT_DISCOVERY", "ACTION_REQUIRED"
    if category == "shareholding":
        return "SHAREHOLDING_NOT_ACQUIRED", "NSE_BSE_SHAREHOLDING_XBRL_FULL_RESIDUAL_PASS", "ACTION_REQUIRED"
    if category in {"annual_financials", "quarterly_financials", "balance_sheet", "cash_flow"}:
        status = " ".join(str(row.get(name, "")) for name in (
            "annual_report_status", "quarterly_results_status", "balance_sheet_status", "cash_flow_status"
        ))
        if "PARSE" in status.upper():
            return "OFFICIAL_XBRL_PARSE_GAP", "REPARSE_ACCEPTED_XBRL_WITH_ACCOUNTING_FAMILY_TAXONOMY", "ACTION_REQUIRED"
        return "OFFICIAL_XBRL_NOT_ACQUIRED", "QUERY_BOTH_EXCHANGES_BY_EXACT_ISIN_AND_PARSE_LATEST_FILINGS", "ACTION_REQUIRED"
    if category == "market_cap":
        if _present(row.get("latest_price")) and _present(row.get("official_total_shares")):
            return "RESOLVER_BUG", "DERIVE_MARKET_CAP_FROM_ACCEPTED_PRICE_X_OFFICIAL_SHARES", "ACTION_REQUIRED"
        return "SHARE_COUNT_OR_PROVIDER_FACT_MISSING", "SHAREHOLDING_THEN_EXACT_ISIN_CURRENT_REFERENCE", "ACTION_REQUIRED"
    if category == "valuation":
        return "VALUATION_INPUTS_MISSING_OR_NOT_MEANINGFUL", "OFFICIAL_STATEMENTS_PLUS_SHARES_THEN_EXACT_ISIN_REFERENCE", "ACTION_REQUIRED"
    if category in {"roce", "roe", "debt_to_equity", "profit_growth"}:
        return "RATIO_INPUT_OR_SEMANTIC_GAP", "OFFICIAL_STATEMENTS_OR_EXACT_ISIN_CURRENT_RATIO_WITH_ACCOUNTING_FAMILY_RULES", "ACTION_REQUIRED"
    return "NO_ACCEPTED_EVIDENCE_FOUND", "SOURCE_PRECEDENCE_RECOVERY", "ACTION_REQUIRED"


def build_audit(facts: pd.DataFrame, *, as_of: date) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    gap_rows: list[dict[str, Any]] = []
    display_rows: list[dict[str, Any]] = []
    for _, row in facts.iterrows():
        identity = {
            "ticker": row.get("ticker"), "company": row.get("company"), "isin": row.get("isin"),
            "primary_exchange": row.get("primary_exchange"), "exchange_security_id": row.get("exchange_security_id"),
            "listing_date": row.get("listing_date"), "size_segment": row.get("size_segment"),
        }
        for category in CATEGORIES:
            available = _available(row, category)
            if available:
                display_rows.append({**identity, "category": category, "display_state": "VALUE_AVAILABLE", "reason": "Accepted provenance-backed value or structured identity state is available."})
                continue
            cause, route, terminal = _cause(row, category, as_of)
            gap_rows.append({
                **identity, "category": category, "critical": category in CRITICAL,
                "root_cause": cause, "recovery_route": route, "terminal_state": terminal,
                "history_status": row.get("history_status"), "history_reason": row.get("history_reason"),
                "screener_current_status": row.get("screener_current_status"),
                "secondary_identity_status": row.get("secondary_identity_status"),
                "shareholding_status": row.get("shareholding_status"),
                "annual_report_status": row.get("annual_report_status"),
                "quarterly_results_status": row.get("quarterly_results_status"),
                "balance_sheet_status": row.get("balance_sheet_status"),
                "cash_flow_status": row.get("cash_flow_status"),
                "product_classification_evidence": row.get("product_classification_evidence"),
            })
            display_state = terminal if terminal != "ACTION_REQUIRED" else "ACCEPTED_EVIDENCE_NOT_FOUND"
            reason = (
                f"{cause}; deterministic recovery route: {route}."
                if terminal == "ACTION_REQUIRED" else cause.replace("_", " ").title()
            )
            display_rows.append({**identity, "category": category, "display_state": display_state, "reason": reason})
    gaps = pd.DataFrame(gap_rows)
    display = pd.DataFrame(display_rows)
    summary = {
        "schema_version": "website_gap_root_cause_v1",
        "as_of": as_of.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "security_count": int(len(facts)),
        "gap_rows": int(len(gaps)),
        "critical_gap_rows": int(gaps["critical"].sum()) if len(gaps) else 0,
        "companies_with_any_gap": int(gaps["isin"].nunique()) if len(gaps) else 0,
        "companies_with_critical_gap": int(gaps.loc[gaps["critical"], "isin"].nunique()) if len(gaps) else 0,
        "display_state_rows": int(len(display)),
        "display_state_coverage_pct": 100.0 if len(display) == len(facts) * len(CATEGORIES) else 0.0,
        "root_cause_counts": gaps["root_cause"].value_counts().sort_index().astype(int).to_dict() if len(gaps) else {},
        "category_gap_counts": gaps["category"].value_counts().sort_index().astype(int).to_dict() if len(gaps) else {},
        "research_v2_modified": False,
    }
    return gaps, display, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit website gaps by deterministic root cause.")
    parser.add_argument("--state-root", type=Path, default=ROOT / "data/company_facts")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/diagnostics/website_gap_root_causes_current")
    parser.add_argument("--as-of")
    args = parser.parse_args(argv)

    snapshot = resolve_company_fact_snapshot(args.state_root)
    result = load_company_fact_snapshot(snapshot)
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    gaps, display, summary = build_audit(result.facts, as_of=as_of)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    gaps.to_csv(args.output_dir / "root_cause_gaps.csv", index=False, encoding="utf-8", lineterminator="\n")
    gaps.loc[gaps["critical"]].to_csv(args.output_dir / "critical_recovery_queue.csv", index=False, encoding="utf-8", lineterminator="\n")
    display.to_csv(args.output_dir / "display_states.csv", index=False, encoding="utf-8", lineterminator="\n")
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({**summary, "accepted_snapshot": str(snapshot), "output_dir": str(args.output_dir)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
