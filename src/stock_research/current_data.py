"""Read-only bridge from accepted product facts to model-neutral current evidence."""

from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_research.platform import FEATURE_EVIDENCE_COLUMNS, validate_feature_evidence


CURRENT_FEATURE_MAP: Mapping[str, str] = {
    "return_1y": "product_baseline_yoy_growth",
    "cagr_3y": "product_baseline_cagr_3y",
    "cagr_5y": "product_baseline_cagr_5y",
    "days_since_recorded_high": "product_baseline_days_since_recorded_high",
    "roce": "roce",
    "debt_to_equity": "debt_to_equity",
    "profit_growth_yoy": "profit_growth_yoy",
    "market_cap_crore": "screener_market_cap_crore",
    "current_price": "screener_current_price",
    "current_roce_pct": "screener_roce_pct",
    "roe_pct": "screener_roe_pct",
    "current_debt_to_equity": "screener_debt_to_equity",
    "current_profit_growth_pct": "screener_profit_growth_pct",
    "current_sales_growth_pct": "screener_sales_growth_pct",
    "current_eps": "screener_eps",
    "current_sales_crore": "screener_sales_crore",
    "current_pat_crore": "screener_profit_after_tax_crore",
    "current_total_debt_crore": "screener_total_debt_crore",
    "operating_cash_flow_crore": "screener_operating_cash_flow_crore",
    "free_cash_flow_crore": "screener_free_cash_flow_crore",
    "market_pe": "screener_pe_ratio",
    "market_pb": "screener_pb_ratio",
    "dividend_yield_pct": "screener_dividend_yield_pct",
    "earnings_yield_pct": "screener_earnings_yield_pct",
    "ev_ebitda": "screener_ev_ebitda",
    "price_to_sales": "screener_price_to_sales",
    "price_to_free_cash_flow": "screener_price_to_free_cash_flow",
    "operating_margin_pct": "screener_operating_margin_pct",
    "return_on_assets_pct": "screener_return_on_assets_pct",
    "current_ratio": "screener_current_ratio",
    "interest_coverage": "screener_interest_coverage",
    "asset_turnover": "screener_asset_turnover",
    "working_capital_days": "screener_working_capital_days",
    "debtor_days": "screener_debtor_days",
    "inventory_days": "screener_inventory_days",
    "sales_growth_3y_pct": "screener_sales_growth_3y_pct",
    "sales_growth_5y_pct": "screener_sales_growth_5y_pct",
    "profit_growth_3y_pct": "screener_profit_growth_3y_pct",
    "profit_growth_5y_pct": "screener_profit_growth_5y_pct",
    "roe_3y_avg_pct": "screener_roe_3y_avg_pct",
    "roe_5y_avg_pct": "screener_roe_5y_avg_pct",
    "roce_3y_avg_pct": "screener_roce_3y_avg_pct",
    "promoter_holding_pct": "screener_promoter_holding_pct",
    "public_holding_pct": "screener_public_holding_pct",
    "fii_holding_pct": "screener_fii_holding_pct",
    "dii_holding_pct": "screener_dii_holding_pct",
    "promoter_pledged_pct": "screener_pledged_pct",
    "quarterly_sales_growth_pct": "screener_quarterly_sales_growth_pct",
    "quarterly_profit_growth_pct": "screener_quarterly_profit_growth_pct",
}


def load_accepted_current_evidence(
    state_root: str | Path,
    *,
    feature_map: Mapping[str, str] = CURRENT_FEATURE_MAP,
) -> pd.DataFrame:
    """Expose accepted values as current-only observations without derivation."""

    root = Path(state_root).resolve()
    snapshot = resolve_company_fact_snapshot(root)
    loaded = load_company_fact_snapshot(snapshot)
    frame = loaded.facts.copy(deep=True)
    required = {"ticker", "product_sector", *feature_map.values()}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"accepted company facts missing mapped columns: {missing}")
    state = json.loads((root / "accepted_state.json").read_text(encoding="utf-8"))
    accepted_at = pd.Timestamp(state["accepted_at"])
    if accepted_at.tzinfo is None:
        raise ValueError("accepted snapshot timestamp must be timezone-aware")
    local = accepted_at.tz_convert(ZoneInfo("Asia/Kolkata"))
    decision_date = local.date() + (timedelta(days=1) if local.time().replace(tzinfo=None) > pd.Timestamp("15:30").time() else timedelta())
    rows = []
    for source in frame.sort_values("ticker", kind="mergesort").to_dict("records"):
        ticker = "" if pd.isna(source["ticker"]) else str(source["ticker"]).strip()
        sector = "" if pd.isna(source["product_sector"]) else str(source["product_sector"]).strip()
        if not ticker or not sector:
            continue
        for feature, column in feature_map.items():
            try:
                value = float(source[column])
            except (TypeError, ValueError):
                continue
            if not np.isfinite(value):
                continue
            contract = source.get("fundamental_contract")
            source_id = (
                "accepted_screener_exact_isin_current"
                if column.startswith("screener_")
                else "accepted_company_fact"
            )
            if (
                feature in {"roce", "debt_to_equity", "profit_growth_yoy"}
                and not pd.isna(contract) and str(contract).strip()
            ):
                source_id = str(contract).strip()
            rows.append({
                "as_of_date": decision_date.isoformat(), "ticker": ticker,
                "sector": sector, "feature": feature, "value": value,
                "available_at": accepted_at.isoformat(),
                "availability_status": "current_only", "source_id": source_id,
                "evidence_fingerprint": str(loaded.manifest["fingerprint"]),
            })
    return validate_feature_evidence(
        pd.DataFrame(rows, columns=FEATURE_EVIDENCE_COLUMNS), mode="current"
    )
