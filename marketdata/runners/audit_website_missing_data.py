from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

ROOT = Path.home() / "Downloads" / "stock-ranking-platform"
FACT_STATE = ROOT / "data" / "company_facts"
OUT = ROOT / "data" / "diagnostics" / "website_missing_data_audit_20260907"


def _is_true(series: pd.Series) -> pd.Series:
    return series.fillna(False).astype(str).str.strip().str.lower().isin({"1", "true", "yes"})


def _present(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    existing = [c for c in cols if c in df.columns]
    if not existing:
        return pd.Series(False, index=df.index)
    ok = pd.Series(False, index=df.index)
    for c in existing:
        s = df[c]
        if pd.api.types.is_bool_dtype(s):
            ok |= s.fillna(False)
        else:
            txt = s.astype("string").str.strip()
            ok |= s.notna() & txt.ne("") & ~txt.str.lower().isin({"nan", "none"})
    return ok


def _resolve_snapshot() -> Path:
    state_path = FACT_STATE / "accepted_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    snap = (FACT_STATE / state["snapshot_path"]).resolve()
    if not snap.is_dir():
        raise FileNotFoundError(snap)
    return snap


def main() -> int:
    snap = _resolve_snapshot()
    csv_path = snap / "company_facts.csv"
    df = pd.read_csv(csv_path, low_memory=False)

    current_price = _present(df, ["latest_price"])
    classification = _present(df, ["product_sector"])
    accepted_history = df.get("history_status", pd.Series("", index=df.index)).astype(str).eq("ACCEPTED_ADJUSTED_HISTORY")
    history_1y = _is_true(df.get("history_1y_usable", pd.Series(False, index=df.index)))
    history_3y = _is_true(df.get("history_3y_usable", pd.Series(False, index=df.index)))
    history_5y = _is_true(df.get("history_5y_usable", pd.Series(False, index=df.index)))

    market_cap = _present(df, ["market_cap", "official_market_cap", "screener_market_cap_crore"])
    valuation = _present(df, ["pe_ratio", "pb_ratio", "book_value", "dividend_yield",
                              "screener_pe_ratio", "screener_pb_ratio", "screener_dividend_yield_pct"])
    roce = _present(df, ["roce", "screener_roce_pct"])
    debt_equity = _present(df, ["debt_to_equity", "official_debt_to_equity",
                                "secondary_debt_to_equity", "screener_debt_to_equity"])
    profit_growth = _present(df, ["profit_growth_yoy", "official_profit_growth_yoy",
                                  "secondary_profit_growth", "screener_profit_growth_pct"])
    roe = _present(df, ["return_on_equity", "official_return_on_equity", "screener_roe_pct"])

    annual = (
        _present(df, ["official_annual_period_end", "secondary_annual_period_end"]) |
        _is_true(df.get("screener_historical_financials_available", pd.Series(False, index=df.index))) |
        df.get("annual_report_status", pd.Series("", index=df.index)).astype(str).eq("NORMALIZED_AUDITED_FACTS_AVAILABLE")
    )
    quarterly = (
        _present(df, ["official_quarterly_period_end", "secondary_quarterly_period_end"]) |
        _is_true(df.get("screener_workbook_available", pd.Series(False, index=df.index)))
    )
    balance = (
        _present(df, ["official_balance_period_end", "secondary_balance_period_end"]) |
        _is_true(df.get("screener_workbook_available", pd.Series(False, index=df.index)))
    )
    cashflow = (
        _present(df, ["official_cash_flow_period_end", "secondary_cash_flow_period_end"]) |
        _is_true(df.get("screener_workbook_available", pd.Series(False, index=df.index)))
    )
    shareholding = _present(df, ["shareholding_as_of", "promoter_holding_pct", "public_holding_pct",
                                 "fii_holding_pct", "dii_holding_pct",
                                 "screener_promoter_holding_pct", "screener_public_holding_pct",
                                 "screener_fii_holding_pct", "screener_dii_holding_pct"])
    documents = _present(df, ["latest_document_url", "annual_report_source_url"])
    profile = _present(df, ["company_profile"])

    availability = {
        "current_price": current_price,
        "classification": classification,
        "accepted_history": accepted_history,
        "history_1y": history_1y,
        "history_3y": history_3y,
        "history_5y": history_5y,
        "market_cap": market_cap,
        "valuation": valuation,
        "roce": roce,
        "debt_to_equity": debt_equity,
        "profit_growth": profit_growth,
        "roe": roe,
        "annual_financials": annual,
        "quarterly_financials": quarterly,
        "balance_sheet": balance,
        "cash_flow": cashflow,
        "shareholding": shareholding,
        "documents": documents,
        "company_profile": profile,
    }

    missing = pd.DataFrame({name: ~mask for name, mask in availability.items()}, index=df.index)
    identity_cols = [c for c in ["ticker", "company", "isin", "primary_exchange", "exchange_security_id"] if c in df.columns]
    detail = df[identity_cols].copy()

    detail["missing_categories"] = missing.apply(
        lambda row: ";".join(name for name, is_missing in row.items() if bool(is_missing)),
        axis=1,
    )
    detail["missing_count"] = missing.sum(axis=1)
    detail["critical_missing"] = missing["current_price"] | missing["classification"] | missing["accepted_history"]
    detail = pd.concat([detail, missing.add_prefix("missing_")], axis=1)
    detail = detail.sort_values(["critical_missing", "missing_count", "ticker"], ascending=[False, False, True])

    total = len(df)
    summary = pd.DataFrame([
        {
            "category": name,
            "available": int(mask.sum()),
            "missing": total - int(mask.sum()),
            "coverage_pct": round(100 * int(mask.sum()) / total, 2),
        }
        for name, mask in availability.items()
    ]).sort_values("missing", ascending=False)

    OUT.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUT / "coverage_by_category.csv", index=False)
    detail.to_csv(OUT / "companies_with_missing_data.csv", index=False)
    detail.loc[detail["critical_missing"]].to_csv(OUT / "critical_gaps.csv", index=False)

    category_dir = OUT / "by_category"
    category_dir.mkdir(exist_ok=True)
    for name in availability:
        cols = identity_cols + ["missing_categories", "missing_count"]
        detail.loc[detail[f"missing_{name}"], cols].to_csv(category_dir / f"{name}.csv", index=False)

    summary_json = {
        "accepted_snapshot": str(snap),
        "total_companies": total,
        "companies_with_any_missing_category": int(detail["missing_count"].gt(0).sum()),
        "companies_with_critical_missing": int(detail["critical_missing"].sum()),
        "coverage": summary.to_dict(orient="records"),
        "outputs": {
            "summary": str(OUT / "coverage_by_category.csv"),
            "all_companies": str(OUT / "companies_with_missing_data.csv"),
            "critical": str(OUT / "critical_gaps.csv"),
            "per_category_dir": str(category_dir),
        },
    }
    (OUT / "summary.json").write_text(json.dumps(summary_json, indent=2), encoding="utf-8")

    print(json.dumps(summary_json, indent=2))
    print("\nWEBSITE MISSING-DATA AUDIT: PASS")
    print("No accepted data was modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
