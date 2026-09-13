"""Provider-independent company facts built from accepted local evidence.

This layer enriches company pages without changing Baseline V1 or Research V2.
Missing evidence remains an explicit, field-specific state; it is never imputed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import uuid
from typing import Any

import pandas as pd

from stock_ranker.data_state import atomic_write_json


FACT_SCHEMA_VERSION = "company_fact_layer_v2"
FACT_COLUMNS = (
    "ticker", "company", "isin", "primary_exchange", "exchange_security_id",
    "series", "listing_date", "identity_status", "trade_date", "latest_price",
    "previous_close", "day_change", "day_change_pct", "open", "high", "low",
    "volume", "traded_value", "transaction_count", "snapshot_source",
    "official_sector", "official_industry", "official_basic_industry",
    "official_classification_status", "official_classification_source",
    "derived_research_sector", "derived_research_industry",
    "derived_research_basic_industry", "classification_reason", "size_segment",
    "history_status", "history_reason", "history_start_date", "history_end_date",
    "history_observation_count", "history_1y_usable", "history_3y_usable",
    "history_5y_usable", "high_52w", "high_52w_date", "low_52w",
    "low_52w_date", "recorded_high", "recorded_high_date", "history_price_basis",
    "corporate_action_history_status", "market_cap", "pe_ratio", "pb_ratio",
    "trailing_eps", "book_value", "dividend_yield", "beta",
    "shares_outstanding", "company_profile", "secondary_sector",
    "secondary_industry", "secondary_identity_status", "secondary_source",
    "secondary_source_as_of", "secondary_freshness_status", "secondary_reason",
    "secondary_high_52w", "secondary_low_52w", "return_on_equity",
    "secondary_debt_to_equity", "revenue_growth", "secondary_profit_growth",
    "operating_margin", "profit_margin", "valuation_status", "valuation_reason",
    "secondary_annual_period_end", "secondary_annual_revenue",
    "secondary_annual_ebitda", "secondary_annual_net_income", "secondary_annual_eps",
    "secondary_quarterly_period_end", "secondary_quarterly_revenue",
    "secondary_quarterly_net_income", "secondary_balance_period_end",
    "secondary_total_assets", "secondary_total_debt", "secondary_stockholders_equity",
    "secondary_cash_balance", "secondary_cash_flow_period_end",
    "secondary_operating_cash_flow", "secondary_free_cash_flow",
    "secondary_capital_expenditure", "secondary_reporting_basis",
    "bulk_classification_sector", "bulk_classification_industry",
    "bulk_classification_status", "bulk_classification_source",
    "bulk_classification_identity_source", "bulk_classification_identity_method",
    "bulk_classification_provider_symbol", "bulk_classification_retrieved_at",
    "bulk_classification_fingerprint",
    "screener_bundle_fingerprint", "screener_source_observed_at",
    "screener_current_status", "screener_match_method", "screener_source_isin",
    "screener_company_name", "screener_nse_code",
    "screener_bse_code", "screener_industry_group", "screener_industry",
    "screener_market_cap_crore", "screener_current_price", "screener_pe_ratio",
    "screener_pb_ratio", "screener_dividend_yield_pct", "screener_eps",
    "screener_profit_after_tax_crore", "screener_sales_crore",
    "screener_roce_pct", "screener_roe_pct", "screener_debt_to_equity",
    "screener_profit_growth_pct", "screener_sales_growth_pct",
    "screener_operating_margin_pct", "screener_return_on_assets_pct",
    "screener_current_ratio", "screener_interest_coverage",
    "screener_cash_conversion_quality", "screener_operating_cash_flow_crore",
    "screener_free_cash_flow_crore", "screener_working_capital_days",
    "screener_debtor_days", "screener_inventory_days",
    "screener_asset_turnover", "screener_latest_quarter_sales_crore",
    "screener_latest_quarter_pat_crore", "screener_quarterly_sales_growth_pct",
    "screener_quarterly_profit_growth_pct", "screener_promoter_holding_pct",
    "screener_public_holding_pct", "screener_fii_holding_pct",
    "screener_dii_holding_pct", "screener_pledged_pct",
    "screener_total_debt_crore", "screener_cash_conversion_cycle_days",
    "screener_roce_3y_avg_pct", "screener_roic_pct", "screener_croic_pct",
    "screener_sales_growth_3y_pct", "screener_sales_growth_5y_pct",
    "screener_profit_growth_3y_pct", "screener_profit_growth_5y_pct",
    "screener_roe_3y_avg_pct", "screener_roe_5y_avg_pct",
    "screener_return_3m_pct", "screener_return_6m_pct",
    "screener_return_1y_pct", "screener_return_3y_pct",
    "screener_return_5y_pct", "screener_peg_ratio",
    "screener_enterprise_value_crore", "screener_ev_ebitda",
    "screener_price_to_free_cash_flow", "screener_price_to_sales",
    "screener_industry_pe", "screener_earnings_yield_pct",
    "screener_fii_holding_change_pct", "screener_dii_holding_change_pct",
    "screener_promoter_holding_change_pct",
    "screener_historical_financials_available", "screener_workbook_available",
    "roce", "debt_to_equity", "profit_growth_yoy", "annual_profit_current",
    "annual_profit_prior", "annual_profit_unit", "annual_profit_label",
    "annual_report_status", "annual_report_reason", "annual_report_financial_year",
    "annual_report_reporting_basis", "annual_report_source_url",
    "annual_report_pdf_sha256", "fundamental_contract", "quarterly_results_status",
    "balance_sheet_status", "cash_flow_status", "shareholding_status",
    "corporate_actions_status", "announcements_status", "documents_status",
    "classification_evidence_status", "ranking_classification_grade",
    "official_annual_period_end", "official_annual_reporting_basis",
    "official_annual_revenue", "official_annual_pat", "official_annual_eps",
    "official_quarterly_period_end", "official_quarterly_reporting_basis",
    "official_quarterly_revenue", "official_quarterly_pat",
    "official_balance_period_end", "official_total_assets", "official_borrowings",
    "official_equity", "official_cash", "official_cash_flow_period_end",
    "official_operating_cash_flow", "shareholding_as_of", "promoter_holding_pct",
    "public_holding_pct", "fii_holding_pct", "dii_holding_pct",
    "promoter_pledge_pct", "official_total_shares", "latest_document_type",
    "latest_document_date", "latest_document_url", "latest_document_source_sha256", "official_action_count",
    "latest_corporate_action_date", "official_evidence_freshness",
    "official_market_cap", "official_pe_ratio", "official_pb_ratio",
    "official_return_on_equity", "official_debt_to_equity",
    "official_revenue_growth", "official_profit_growth_yoy",
    "official_net_margin", "official_ratio_formula_version",
    "official_ratio_reporting_basis",
    "professor_cohort", "professor_supplied_rank", "workbook_strategy_rank",
    "professor_industry", "professor_workbook_current_price",
    "professor_workbook_market_cap", "professor_workbook_cagr_10y",
    "professor_workbook_cagr_5y", "professor_workbook_cagr_3y",
    "professor_workbook_cagr_1y", "professor_evidence_status", "baseline_eligible",
    "baseline_yoy_growth", "baseline_cagr_3y", "baseline_cagr_5y",
    "baseline_days_since_recorded_high",
    "baseline_score", "baseline_sector_rank", "baseline_reason_code",
    "v2_eligible", "research_v2_score", "research_v2_sector_rank",
    "v2_reason_code",
    "product_classification_version", "product_sector", "product_industry",
    "product_basic_industry", "product_classification_evidence",
    "product_classification_source", "product_classification_as_of",
    "product_baseline_yoy_growth", "product_baseline_cagr_3y",
    "product_baseline_cagr_5y", "product_baseline_days_since_recorded_high",
    "product_baseline_score", "product_baseline_sector_rank",
    "product_baseline_eligible", "product_baseline_reason_code",
    "product_baseline_reason",
)


@dataclass(frozen=True)
class CompanyFactResult:
    facts: pd.DataFrame
    coverage: dict[str, Any]
    manifest: dict[str, Any]


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _missing(value: Any) -> bool:
    return value is None or pd.isna(value) or str(value).strip() == ""


def _number(value: Any) -> float | None:
    return None if _missing(value) else float(value)


def _text(value: Any) -> str | None:
    return None if _missing(value) else str(value).strip()


def _history_facts(path: Path, trade_date: pd.Timestamp) -> dict[str, Any]:
    if not path.is_file():
        return {
            "history_status": "NO_ACCEPTED_ADJUSTED_HISTORY",
            "history_reason": "No identity-verified adjusted history is present in the accepted local evidence store.",
            "history_start_date": None, "history_end_date": None,
            "history_observation_count": 0, "history_1y_usable": False,
            "history_3y_usable": False, "history_5y_usable": False,
            "high_52w": None, "high_52w_date": None, "low_52w": None,
            "low_52w_date": None, "recorded_high": None,
            "recorded_high_date": None, "history_price_basis": None,
            "corporate_action_history_status": "NO_VERIFIED_ACTION_AWARE_HISTORY",
        }
    frame = pd.read_csv(path, usecols=["date", "adjusted_close"])
    frame["date"] = pd.to_datetime(frame["date"], format="%Y-%m-%d", errors="coerce")
    frame["adjusted_close"] = pd.to_numeric(frame["adjusted_close"], errors="coerce")
    frame = frame.dropna().loc[lambda item: item["adjusted_close"].gt(0)]
    frame = frame.loc[frame["date"].le(trade_date)].drop_duplicates("date", keep="last")
    frame = frame.sort_values("date", kind="stable")
    if frame.empty:
        return _history_facts(Path("__missing__"), trade_date)
    end = frame.iloc[-1]
    start = frame.iloc[0]
    recent = frame.loc[frame["date"].ge(trade_date - pd.Timedelta(days=365))]
    high_row = frame.loc[frame["adjusted_close"].eq(frame["adjusted_close"].max())].iloc[-1]
    high_52 = recent.loc[recent["adjusted_close"].eq(recent["adjusted_close"].max())].iloc[-1]
    low_52 = recent.loc[recent["adjusted_close"].eq(recent["adjusted_close"].min())].iloc[-1]
    fresh = (trade_date - end["date"]).days <= 7
    usable = {
        years: bool(fresh and start["date"] <= trade_date - pd.DateOffset(years=years))
        for years in (1, 3, 5)
    }
    return {
        "history_status": "ACCEPTED_ADJUSTED_HISTORY",
        "history_reason": "Identity-matched adjusted research history is cached locally; provider adjustment semantics are preserved.",
        "history_start_date": start["date"].date().isoformat(),
        "history_end_date": end["date"].date().isoformat(),
        "history_observation_count": int(len(frame)),
        "history_1y_usable": usable[1], "history_3y_usable": usable[3],
        "history_5y_usable": usable[5],
        "high_52w": float(high_52["adjusted_close"]),
        "high_52w_date": high_52["date"].date().isoformat(),
        "low_52w": float(low_52["adjusted_close"]),
        "low_52w_date": low_52["date"].date().isoformat(),
        "recorded_high": float(high_row["adjusted_close"]),
        "recorded_high_date": high_row["date"].date().isoformat(),
        "history_price_basis": "Yahoo adjusted close via accepted yfinance research cache",
        "corporate_action_history_status": "PROVIDER_ADJUSTED_NOT_OFFICIAL_ACTION_LEDGER",
    }


def _load_optional(path: str | Path | None) -> pd.DataFrame:
    return pd.DataFrame() if path is None or not Path(path).is_file() else pd.read_csv(path, low_memory=False)


def _parse_json_fact(value: Any) -> dict[str, Any]:
    if _missing(value):
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build_company_facts(
    market: pd.DataFrame,
    *,
    history_root: str | Path,
    filing_provenance_path: str | Path | None = None,
    professor_strategy_path: str | Path | None = None,
    yahoo_observations_path: str | Path | None = None,
    yahoo_financial_facts_path: str | Path | None = None,
    bulk_classifications_path: str | Path | None = None,
    bulk_classification_fingerprint: str | None = None,
    screener_market_path: str | Path | None = None,
    screener_history_path: str | Path | None = None,
    screener_workbook_audit_path: str | Path | None = None,
    screener_workbook_isins: set[str] | frozenset[str] | None = None,
    screener_bundle_fingerprint: str | None = None,
    screener_source_observed_at: str | None = None,
    official_backbone_path: str | Path | None = None,
    market_fingerprint: str,
) -> CompanyFactResult:
    """Build one deterministic fact row per canonical ISIN from accepted evidence."""

    required = {"ticker", "company", "isin", "trade_date", "primary_exchange"}
    missing = sorted(required.difference(market.columns))
    if missing:
        raise ValueError(f"market evidence is missing columns: {missing}")
    if market.empty or market["ticker"].duplicated().any() or market["isin"].duplicated().any():
        raise ValueError("market evidence must contain unique ticker and ISIN rows")
    trade_dates = pd.to_datetime(market["trade_date"], format="%Y-%m-%d", errors="coerce")
    if trade_dates.isna().any():
        raise ValueError("market trade_date must be valid ISO dates")
    filings = _load_optional(filing_provenance_path)
    filing_by_ticker = ({str(row.ticker): row for row in filings.itertuples(index=False)}
                        if not filings.empty and "ticker" in filings else {})
    strategy = _load_optional(professor_strategy_path)
    yahoo = _load_optional(yahoo_observations_path)
    yahoo_by_isin: dict[str, Any] = {}
    if not yahoo.empty and "isin" in yahoo:
        from stock_ranker.secondary_facts import validate_yahoo_observations

        yahoo = validate_yahoo_observations(yahoo)
        yahoo_by_isin = {str(row.isin): row for row in yahoo.itertuples(index=False)}
    if yahoo_financial_facts_path is None and yahoo_observations_path is not None:
        yahoo_financial_facts_path = Path(yahoo_observations_path).with_name("financial_facts.csv")
    yahoo_financials = _load_optional(yahoo_financial_facts_path)
    financial_by_ticker: dict[str, pd.DataFrame] = {}
    if not yahoo_financials.empty:
        required_financial = {"ticker", "statement", "canonical_concept", "period_end", "value", "reporting_basis"}
        if not required_financial.issubset(yahoo_financials.columns):
            raise ValueError("Yahoo financial facts are missing required columns")
        yahoo_financials["period_end"] = pd.to_datetime(yahoo_financials["period_end"], errors="coerce")
        yahoo_financials["value"] = pd.to_numeric(yahoo_financials["value"], errors="coerce")
        if yahoo_financials[["period_end", "value"]].isna().any(axis=None):
            raise ValueError("Yahoo financial facts contain invalid periods or values")
        financial_by_ticker = {str(key): value.copy() for key, value in yahoo_financials.groupby("ticker", sort=False)}
    bulk = _load_optional(bulk_classifications_path)
    bulk_by_isin: dict[str, Any] = {}
    if not bulk.empty:
        from stock_ranker.bulk_classification import validate_bulk_classifications

        bulk = validate_bulk_classifications(bulk)
        bulk_by_isin = {str(row.isin): row for row in bulk.itertuples(index=False)}
    screener = _load_optional(screener_market_path)
    screener_by_isin: dict[str, Any] = {}
    screener_by_exchange_code: dict[tuple[str, str], dict[str, Any]] = {}

    def screener_exchange_key(exchange: Any, security_id: Any) -> tuple[str, str] | None:
        if _missing(exchange) or _missing(security_id):
            return None
        exchange_text = str(exchange).strip().upper()
        security_text = str(security_id).strip().upper()
        if security_text.endswith(".0") and security_text[:-2].isdigit():
            security_text = security_text[:-2]
        if not exchange_text or not security_text:
            return None
        return exchange_text, security_text
    if not screener.empty:
        if not {"isin", "market_merge_status"}.issubset(screener.columns):
            raise ValueError("accepted Screener market data are missing identity/status columns")
        if screener["isin"].duplicated().any():
            raise ValueError("accepted Screener market data contain duplicate ISINs")
        screener = screener.loc[screener["market_merge_status"].eq("ACCEPTED")].copy()
        screener_records = screener.to_dict("records")
        screener_by_isin = {str(row["isin"]): row for row in screener_records}
        exchange_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in screener_records:
            key = screener_exchange_key(row.get("primary_exchange"), row.get("exchange_security_id"))
            if key is not None:
                exchange_groups.setdefault(key, []).append(row)
        screener_by_exchange_code = {
            key: rows[0] for key, rows in exchange_groups.items() if len(rows) == 1
        }
    screener_history = _load_optional(screener_history_path)
    screener_history_isins = set(screener_history["isin"].dropna().astype(str)) if "isin" in screener_history else set()
    screener_audit = _load_optional(screener_workbook_audit_path)
    accepted_workbook_isins = set(
        screener_audit.loc[screener_audit["file_status"].eq("ACCEPTED"), "isin"].dropna().astype(str)
    ) if {"file_status", "isin"}.issubset(screener_audit.columns) else set()
    if screener_workbook_isins is not None:
        accepted_workbook_isins.update(
            str(isin).strip().upper()
            for isin in screener_workbook_isins
            if str(isin).strip()
        )
    official_financials = pd.DataFrame()
    official_shareholding = pd.DataFrame()
    official_actions = pd.DataFrame()
    official_documents = pd.DataFrame()
    classification_audit = pd.DataFrame()
    if official_backbone_path is not None:
        from stock_ranker.exchange_backbone import load_official_backbone

        backbone = load_official_backbone(official_backbone_path)
        official_financials = backbone.financial_facts.copy()
        official_shareholding = backbone.shareholding.copy()
        official_actions = backbone.corporate_actions.copy()
        official_documents = backbone.documents.copy()
        classification_audit = backbone.classification_audit.copy()
        from stock_ranker.product_evidence import official_document_index

        official_documents = official_document_index(
            official_documents, official_financials, official_shareholding)
    official_financial_by_isin = {
        str(key): value.copy() for key, value in official_financials.groupby("isin", sort=False)
    } if not official_financials.empty else {}
    official_shareholding_by_isin = {
        str(key): value.sort_values(["as_of_date", "available_at"], kind="stable", na_position="first").iloc[-1]
        for key, value in official_shareholding.groupby("isin", sort=False)
    } if not official_shareholding.empty else {}
    official_actions_by_isin = {
        str(key): value.copy() for key, value in official_actions.groupby("isin", sort=False)
    } if not official_actions.empty else {}
    official_documents_by_isin = {
        str(key): value.sort_values("available_at", kind="stable", na_position="first").iloc[-1]
        for key, value in official_documents.groupby("isin", sort=False)
    } if not official_documents.empty else {}
    classification_by_isin = {
        str(row.isin): row for row in classification_audit.itertuples(index=False)
    } if not classification_audit.empty else {}
    strategy_by_isin: dict[str, Any] = {}
    if not strategy.empty and "isin" in strategy:
        for row in strategy.itertuples(index=False):
            if not _missing(row.isin):
                strategy_by_isin.setdefault(str(row.isin), row)
    histories = Path(history_root)
    rows: list[dict[str, Any]] = []
    for source in market.sort_values(["primary_exchange", "ticker"], kind="stable").itertuples(index=False):
        get = lambda name, default=None: getattr(source, name, default)
        ticker = str(get("ticker"))
        trade_date = pd.Timestamp(str(get("trade_date")))
        official_sector = _text(get("sector"))
        classification_source = _text(get("classification_source"))
        official_industry = _text(get("industry"))
        if classification_source and "Sector-tier label" in classification_source:
            official_industry = None
        official_basic = _text(get("basic_industry"))
        classified = official_sector is not None
        item: dict[str, Any] = {
            "ticker": ticker, "company": str(get("company")), "isin": str(get("isin")),
            "primary_exchange": str(get("primary_exchange")),
            "exchange_security_id": _text(get("exchange_security_id")),
            "series": _text(get("series")), "listing_date": _text(get("listing_date")),
            "identity_status": str(get("identity_status")), "trade_date": str(get("trade_date")),
            "latest_price": _number(get("latest_price")), "previous_close": _number(get("previous_close")),
            "day_change": _number(get("day_change")), "day_change_pct": _number(get("day_change_pct")),
            "open": _number(get("open")), "high": _number(get("high")), "low": _number(get("low")),
            "volume": _number(get("volume")), "traded_value": _number(get("traded_value")),
            "transaction_count": _number(get("transaction_count")),
            "snapshot_source": _text(get("snapshot_source")), "official_sector": official_sector,
            "official_industry": official_industry, "official_basic_industry": official_basic,
            "official_classification_status": _text(get("classification_status")),
            "official_classification_source": classification_source,
            "derived_research_sector": None, "derived_research_industry": None,
            "derived_research_basic_industry": None,
            "classification_reason": (
                "Official sector-tier classification is available; a missing basic-industry tier remains explicit and professor taxonomy stays separate."
                if classified else "NO AUTHORITATIVE CLASSIFICATION YET; no company-name inference is permitted."
            ),
            "size_segment": _text(get("size_segment")),
            "market_cap": None, "pe_ratio": None, "pb_ratio": None,
            "trailing_eps": None, "book_value": None, "dividend_yield": None,
            "beta": None, "shares_outstanding": None, "company_profile": None,
            "secondary_sector": None, "secondary_industry": None,
            "secondary_identity_status": "NOT_CHECKED", "secondary_source": None,
            "secondary_source_as_of": None, "secondary_freshness_status": "NOT_CHECKED",
            "secondary_reason": "No identity-validated secondary observation is present in the accepted local evidence store.",
            "secondary_high_52w": None, "secondary_low_52w": None,
            "return_on_equity": None, "secondary_debt_to_equity": None,
            "revenue_growth": None, "secondary_profit_growth": None,
            "operating_margin": None, "profit_margin": None,
            "secondary_annual_period_end": None, "secondary_annual_revenue": None,
            "secondary_annual_ebitda": None, "secondary_annual_net_income": None,
            "secondary_annual_eps": None, "secondary_quarterly_period_end": None,
            "secondary_quarterly_revenue": None, "secondary_quarterly_net_income": None,
            "secondary_balance_period_end": None, "secondary_total_assets": None,
            "secondary_total_debt": None, "secondary_stockholders_equity": None,
            "secondary_cash_balance": None, "secondary_cash_flow_period_end": None,
            "secondary_operating_cash_flow": None, "secondary_free_cash_flow": None,
            "secondary_capital_expenditure": None, "secondary_reporting_basis": None,
            "bulk_classification_sector": None, "bulk_classification_industry": None,
            "bulk_classification_status": "NOT_CHECKED", "bulk_classification_source": None,
            "bulk_classification_identity_source": None,
            "bulk_classification_identity_method": None,
            "bulk_classification_provider_symbol": None,
            "bulk_classification_retrieved_at": None,
            "bulk_classification_fingerprint": None,
            "valuation_status": "NO_VERIFIED_SHARE_COUNT_OR_VALUATION_FACTS",
            "valuation_reason": "Price is available, but valuation is not calculated without point-in-time shares and compatible financial facts.",
            "roce": _number(get("roce")), "debt_to_equity": _number(get("debt_to_equity")),
            "profit_growth_yoy": _number(get("profit_growth_yoy")),
            "baseline_eligible": bool(get("baseline_eligible", False)),
            "baseline_yoy_growth": _number(get("baseline_yoy_growth")),
            "baseline_cagr_3y": _number(get("baseline_cagr_3y")),
            "baseline_cagr_5y": _number(get("baseline_cagr_5y")),
            "baseline_days_since_recorded_high": _number(get("baseline_days_since_recorded_high")),
            "baseline_score": _number(get("baseline_score")),
            "baseline_sector_rank": _number(get("baseline_sector_rank")),
            "baseline_reason_code": _text(get("baseline_reason_code")),
            "v2_eligible": bool(get("v2_eligible", False)),
            "research_v2_score": _number(get("research_v2_score")),
            "research_v2_sector_rank": _number(get("research_v2_sector_rank")),
            "v2_reason_code": _text(get("v2_reason_code")),
            "quarterly_results_status": "OFFICIAL_DISCOVERY_ROUTE_AVAILABLE_NOT_NORMALIZED",
            "balance_sheet_status": "NO_NORMALIZED_POINT_IN_TIME_BALANCE_SHEET",
            "cash_flow_status": "NO_NORMALIZED_POINT_IN_TIME_CASH_FLOW",
            "shareholding_status": "OFFICIAL_NSE_OR_BSE_DISCOVERY_ROUTE_AVAILABLE_NOT_CACHED",
            "corporate_actions_status": "OFFICIAL_EXCHANGE_DISCOVERY_ROUTE_AVAILABLE_NOT_NORMALIZED",
            "announcements_status": "OFFICIAL_EXCHANGE_DISCOVERY_ROUTE_AVAILABLE_NOT_CACHED",
            "classification_evidence_status": "OFFICIAL" if classified else "UNCLASSIFIED",
            "ranking_classification_grade": bool(classified),
            "official_annual_period_end": None, "official_annual_reporting_basis": None,
            "official_annual_revenue": None, "official_annual_pat": None,
            "official_annual_eps": None, "official_quarterly_period_end": None,
            "official_quarterly_reporting_basis": None,
            "official_quarterly_revenue": None, "official_quarterly_pat": None,
            "official_balance_period_end": None, "official_total_assets": None,
            "official_borrowings": None, "official_equity": None, "official_cash": None,
            "official_cash_flow_period_end": None, "official_operating_cash_flow": None,
            "shareholding_as_of": None, "promoter_holding_pct": None,
            "public_holding_pct": None, "fii_holding_pct": None,
            "dii_holding_pct": None, "promoter_pledge_pct": None,
            "official_total_shares": None, "latest_document_type": None,
            "latest_document_date": None, "latest_document_url": None,
            "latest_document_source_sha256": None,
            "official_action_count": 0, "latest_corporate_action_date": None,
            "official_evidence_freshness": "NO_ACCEPTED_OFFICIAL_CORPORATE_EVIDENCE",
            "official_market_cap": None, "official_pe_ratio": None,
            "official_pb_ratio": None, "official_return_on_equity": None,
            "official_debt_to_equity": None, "official_revenue_growth": None,
            "official_profit_growth_yoy": None, "official_net_margin": None,
            "official_ratio_formula_version": None,
            "official_ratio_reporting_basis": None,
        }
        item.update({
            name: False if name in {
                "screener_historical_financials_available", "screener_workbook_available"
            } else None
            for name in FACT_COLUMNS if name.startswith("screener_")
        })
        item.update(_history_facts(histories / f"{ticker}.csv", trade_date))
        secondary = yahoo_by_isin.get(str(get("isin")))
        if secondary is not None:
            identity_status = str(getattr(secondary, "identity_status"))
            accepted_secondary = identity_status == "EXCHANGE_SYMBOL_MATCH"
            item.update({
                "secondary_identity_status": identity_status,
                "secondary_source": "Yahoo Finance via yfinance" if accepted_secondary else None,
                "secondary_source_as_of": _text(getattr(secondary, "source_as_of", None)),
                "secondary_freshness_status": _text(getattr(secondary, "freshness_status", None)),
                "secondary_reason": _text(getattr(secondary, "identity_reason", None)),
            })
            if accepted_secondary:
                item.update({
                    "market_cap": _number(getattr(secondary, "market_cap", None)),
                    "pe_ratio": _number(getattr(secondary, "trailing_pe", None)),
                    "pb_ratio": _number(getattr(secondary, "price_to_book", None)),
                    "trailing_eps": _number(getattr(secondary, "trailing_eps", None)),
                    "book_value": _number(getattr(secondary, "book_value", None)),
                    "dividend_yield": _number(getattr(secondary, "dividend_yield_decimal", None)),
                    "beta": _number(getattr(secondary, "beta", None)),
                    "shares_outstanding": _number(getattr(secondary, "shares_outstanding", None)),
                    "company_profile": _text(getattr(secondary, "company_profile", None)),
                    "secondary_sector": _text(getattr(secondary, "sector", None)),
                    "secondary_industry": _text(getattr(secondary, "industry", None)),
                    "secondary_high_52w": _number(getattr(secondary, "fifty_two_week_high", None)),
                    "secondary_low_52w": _number(getattr(secondary, "fifty_two_week_low", None)),
                    "return_on_equity": _number(getattr(secondary, "return_on_equity", None)),
                    "secondary_debt_to_equity": _number(getattr(secondary, "debt_to_equity_decimal", None)),
                    "revenue_growth": _number(getattr(secondary, "revenue_growth", None)),
                    "secondary_profit_growth": _number(getattr(secondary, "earnings_growth", None)),
                    "operating_margin": _number(getattr(secondary, "operating_margin", None)),
                    "profit_margin": _number(getattr(secondary, "profit_margin", None)),
                    "quarterly_results_status": _text(getattr(secondary, "quarterly_income_status", None)) or item["quarterly_results_status"],
                    "balance_sheet_status": _text(getattr(secondary, "balance_sheet_status", None)) or item["balance_sheet_status"],
                    "cash_flow_status": _text(getattr(secondary, "cash_flow_status", None)) or item["cash_flow_status"],
                    "shareholding_status": _text(getattr(secondary, "holder_data_status", None)) or item["shareholding_status"],
                    "corporate_actions_status": _text(getattr(secondary, "corporate_actions_status", None)) or item["corporate_actions_status"],
                })
                if item["official_sector"] is None and item["secondary_sector"] is not None:
                    item["derived_research_sector"] = item["secondary_sector"]
                    item["derived_research_industry"] = item["secondary_industry"]
                    item["classification_reason"] = (
                        "Derived Research Classification v1 retains the identity-validated Yahoo sector/industry as secondary single-source evidence. "
                        "It is not labelled official and is not used by Baseline V1 or Research V2."
                    )
                has_valuation = any(item[name] is not None for name in ("market_cap", "pe_ratio", "pb_ratio", "trailing_eps", "book_value", "dividend_yield"))
                item["valuation_status"] = "SECONDARY_REFERENCE_FACTS_AVAILABLE" if has_valuation else "NO_USEFUL_SECONDARY_VALUATION_FACTS"
                item["valuation_reason"] = (
                    "Identity-validated provider observations are displayed as secondary current reference evidence; they do not alter either ranking model."
                    if has_valuation else "The identity matched, but the provider returned no usable valuation facts."
                )
                financial = financial_by_ticker.get(ticker)
                if financial is not None:
                    def latest(statement: str, concepts: tuple[str, ...]) -> tuple[str | None, dict[str, float]]:
                        subset = financial.loc[financial["statement"].eq(statement) & financial["canonical_concept"].isin(concepts)]
                        if subset.empty:
                            return None, {}
                        period = subset["period_end"].max()
                        values_for_period = subset.loc[subset["period_end"].eq(period)].drop_duplicates("canonical_concept", keep="last")
                        return period.date().isoformat(), dict(zip(values_for_period["canonical_concept"], values_for_period["value"].astype(float)))

                    annual_period, annual = latest("annual_income", ("total_revenue", "operating_revenue", "ebitda", "net_income", "basic_eps"))
                    quarter_period, quarter = latest("quarterly_income", ("total_revenue", "operating_revenue", "net_income"))
                    balance_period, balance = latest("balance_sheet", ("total_assets", "total_debt", "stockholders_equity", "cash_cash_equivalents_and_short_term_investments"))
                    cash_period, cash = latest("cash_flow", ("operating_cash_flow", "free_cash_flow", "capital_expenditure"))
                    item.update({
                        "secondary_annual_period_end": annual_period,
                        "secondary_annual_revenue": annual.get("total_revenue", annual.get("operating_revenue")),
                        "secondary_annual_ebitda": annual.get("ebitda"),
                        "secondary_annual_net_income": annual.get("net_income"),
                        "secondary_annual_eps": annual.get("basic_eps"),
                        "secondary_quarterly_period_end": quarter_period,
                        "secondary_quarterly_revenue": quarter.get("total_revenue", quarter.get("operating_revenue")),
                        "secondary_quarterly_net_income": quarter.get("net_income"),
                        "secondary_balance_period_end": balance_period,
                        "secondary_total_assets": balance.get("total_assets"),
                        "secondary_total_debt": balance.get("total_debt"),
                        "secondary_stockholders_equity": balance.get("stockholders_equity"),
                        "secondary_cash_balance": balance.get("cash_cash_equivalents_and_short_term_investments"),
                        "secondary_cash_flow_period_end": cash_period,
                        "secondary_operating_cash_flow": cash.get("operating_cash_flow"),
                        "secondary_free_cash_flow": cash.get("free_cash_flow"),
                        "secondary_capital_expenditure": cash.get("capital_expenditure"),
                        "secondary_reporting_basis": "YAHOO_PROVIDER_BASIS_UNSPECIFIED",
                    })
                    if (
                        item["return_on_equity"] is None
                        and item["secondary_annual_net_income"] is not None
                        and item["secondary_stockholders_equity"] not in (None, 0)
                    ):
                        item["return_on_equity"] = (
                            item["secondary_annual_net_income"]
                            / item["secondary_stockholders_equity"]
                        )
        isin = str(get("isin"))
        screener_match_method: str | None = None
        screener_row = screener_by_isin.get(isin)
        if screener_row is not None:
            screener_match_method = "EXACT_ISIN"
        else:
            exchange_key = screener_exchange_key(
                get("primary_exchange"), get("exchange_security_id")
            )
            if exchange_key is not None:
                screener_row = screener_by_exchange_code.get(exchange_key)
                if screener_row is not None:
                    screener_match_method = "UNIQUE_PRIMARY_EXCHANGE_SECURITY_ID"
        if screener_row is not None:
            screener_match_label = (
                "exact ISIN"
                if screener_match_method == "EXACT_ISIN"
                else "unique primary-exchange security ID"
            )

            def screener_value(*names: str) -> Any:
                for name in names:
                    value = screener_row.get(name)
                    if not _missing(value):
                        return value
                return None

            screener_fields = {
                "screener_company_name": screener_value("snapshot__Name", "operational__Name"),
                "screener_nse_code": screener_value("snapshot__NSE Code", "operational__NSE Code"),
                "screener_bse_code": screener_value("snapshot__BSE Code", "operational__BSE Code"),
                "screener_industry_group": screener_value("snapshot__Industry Group", "operational__Industry Group"),
                "screener_industry": screener_value("snapshot__Industry", "operational__Industry"),
                "screener_market_cap_crore": screener_value("snapshot__Market Capitalization", "operational__Market Capitalization"),
                "screener_current_price": screener_value("snapshot__Current Price", "operational__Current Price"),
                "screener_pe_ratio": screener_value("snapshot__Price to Earning"),
                "screener_pb_ratio": screener_value("snapshot__Price to book value"),
                "screener_dividend_yield_pct": screener_value("snapshot__Dividend yield"),
                "screener_eps": screener_value("snapshot__EPS", "operational__EPS"),
                "screener_profit_after_tax_crore": screener_value("snapshot__Profit after tax", "operational__Profit after tax"),
                "screener_sales_crore": screener_value("snapshot__Sales", "operational__Sales"),
                "screener_roce_pct": screener_value("snapshot__Return on capital employed", "operational__Return on capital employed"),
                "screener_roe_pct": screener_value("snapshot__Return on equity", "operational__Return on equity"),
                "screener_debt_to_equity": screener_value("snapshot__Debt to equity", "operational__Debt to equity"),
                "screener_profit_growth_pct": screener_value("snapshot__Profit growth", "operational__Profit growth"),
                "screener_sales_growth_pct": screener_value("snapshot__Sales growth", "operational__Sales growth"),
                "screener_operating_margin_pct": screener_value("snapshot__OPM", "operational__OPM"),
                "screener_return_on_assets_pct": screener_value("snapshot__Return on assets", "operational__Return on assets"),
                "screener_current_ratio": screener_value("snapshot__Current ratio", "operational__Current ratio"),
                "screener_interest_coverage": screener_value("snapshot__Interest Coverage Ratio", "operational__Interest Coverage Ratio"),
                "screener_cash_conversion_quality": screener_value("operational__Cash Conversion Quality"),
                "screener_operating_cash_flow_crore": screener_value("operational__Cash from operations last year"),
                "screener_free_cash_flow_crore": screener_value("operational__Free cash flow last year"),
                "screener_working_capital_days": screener_value("operational__Working Capital Days"),
                "screener_debtor_days": screener_value("operational__Debtor days"),
                "screener_inventory_days": screener_value("operational__Days Inventory Outstanding"),
                "screener_asset_turnover": screener_value("operational__Asset Turnover Ratio"),
                "screener_latest_quarter_sales_crore": screener_value("snapshot__Sales latest quarter"),
                "screener_latest_quarter_pat_crore": screener_value("snapshot__Profit after tax latest quarter"),
                "screener_quarterly_sales_growth_pct": screener_value("snapshot__YOY Quarterly sales growth"),
                "screener_quarterly_profit_growth_pct": screener_value("snapshot__YOY Quarterly profit growth"),
                "screener_promoter_holding_pct": screener_value("snapshot__Promoter holding"),
                "screener_public_holding_pct": screener_value("operational__Public holding"),
                "screener_fii_holding_pct": screener_value("operational__FII holding"),
                "screener_dii_holding_pct": screener_value("operational__DII holding"),
                "screener_pledged_pct": screener_value("snapshot__Pledged percentage"),
                "screener_total_debt_crore": screener_value("snapshot__Debt", "operational__Debt"),
                "screener_cash_conversion_cycle_days": screener_value("operational__Cash Conversion Cycle"),
                "screener_roce_3y_avg_pct": screener_value("operational__ROCE3yr avg"),
                "screener_roic_pct": screener_value("operational__Return on invested capital"),
                "screener_croic_pct": screener_value("operational__CROIC"),
                "screener_sales_growth_3y_pct": screener_value("snapshot__Sales growth 3Years"),
                "screener_sales_growth_5y_pct": screener_value("snapshot__Sales growth 5Years"),
                "screener_profit_growth_3y_pct": screener_value("snapshot__Profit growth 3Years"),
                "screener_profit_growth_5y_pct": screener_value("snapshot__Profit growth 5Years"),
                "screener_roe_3y_avg_pct": screener_value("snapshot__Average return on equity 3Years"),
                "screener_roe_5y_avg_pct": screener_value("snapshot__Average return on equity 5Years"),
                "screener_return_3m_pct": screener_value("snapshot__Return over 3months"),
                "screener_return_6m_pct": screener_value("snapshot__Return over 6months"),
                "screener_return_1y_pct": screener_value("snapshot__Return over 1year"),
                "screener_return_3y_pct": screener_value("snapshot__Return over 3years"),
                "screener_return_5y_pct": screener_value("snapshot__Return over 5years"),
                "screener_peg_ratio": screener_value("snapshot__PEG Ratio"),
                "screener_enterprise_value_crore": screener_value("snapshot__Enterprise Value"),
                "screener_ev_ebitda": screener_value("snapshot__EVEBITDA"),
                "screener_price_to_free_cash_flow": screener_value("snapshot__Price to Free Cash Flow"),
                "screener_price_to_sales": screener_value("snapshot__Price to Sales"),
                "screener_industry_pe": screener_value("snapshot__Industry PE"),
                "screener_earnings_yield_pct": screener_value("snapshot__Earnings yield"),
                "screener_fii_holding_change_pct": screener_value("operational__Change in FII holding"),
                "screener_dii_holding_change_pct": screener_value("operational__Change in DII holding"),
                "screener_promoter_holding_change_pct": screener_value("snapshot__Change in promoter holding"),
            }
            item.update({name: _text(value) if name in {
                "screener_company_name", "screener_nse_code", "screener_bse_code",
                "screener_industry_group", "screener_industry",
            } else _number(value) for name, value in screener_fields.items()})
            item.update({
                "screener_bundle_fingerprint": screener_bundle_fingerprint,
                "screener_source_observed_at": screener_source_observed_at,
                "screener_current_status": (
                    "ACCEPTED_EXACT_ISIN_CURRENT_REFERENCE"
                    if screener_match_method == "EXACT_ISIN"
                    else "ACCEPTED_UNIQUE_EXCHANGE_CODE_CURRENT_REFERENCE"
                ),
                "screener_match_method": screener_match_method,
                "screener_source_isin": _text(screener_row.get("isin")),
            })
            if item["market_cap"] is None and item["screener_market_cap_crore"] is not None:
                item["market_cap"] = item["screener_market_cap_crore"] * 10_000_000
                item["valuation_status"] = "SCREENER_CURRENT_REFERENCE_AVAILABLE"
                item["valuation_reason"] = f"Accepted Screener current market data matched by {screener_match_label}; values do not enter frozen research models."
            for target, source_name in (
                ("pe_ratio", "screener_pe_ratio"), ("pb_ratio", "screener_pb_ratio"),
                ("trailing_eps", "screener_eps"),
            ):
                if item[target] is None:
                    item[target] = item[source_name]
            for target, source_name in (
                ("return_on_equity", "screener_roe_pct"),
                ("revenue_growth", "screener_sales_growth_pct"),
                ("secondary_profit_growth", "screener_profit_growth_pct"),
                ("operating_margin", "screener_operating_margin_pct"),
            ):
                if item[target] is None and item[source_name] is not None:
                    item[target] = item[source_name] / 100
            if (
                item["return_on_equity"] is None
                and item["screener_eps"] is not None
                and item["screener_pb_ratio"] is not None
                and item["screener_current_price"] not in (None, 0)
            ):
                item["return_on_equity"] = (
                    item["screener_eps"]
                    * item["screener_pb_ratio"]
                    / item["screener_current_price"]
                )
            if item["secondary_debt_to_equity"] is None:
                item["secondary_debt_to_equity"] = item["screener_debt_to_equity"]
            if item["derived_research_sector"] is None and item["screener_industry_group"] is not None:
                item["derived_research_sector"] = item["screener_industry_group"]
                item["derived_research_industry"] = item["screener_industry"]
                item["classification_reason"] = (
                    f"Accepted Screener market-wide classification is matched by {screener_match_label} for current-product browsing only; "
                    "it does not replace frozen research classifications."
                )
        item["screener_historical_financials_available"] = isin in screener_history_isins
        item["screener_workbook_available"] = isin in accepted_workbook_isins
        if item["screener_workbook_available"]:
            item["quarterly_results_status"] = "SCREENER_STANDALONE_HISTORY_AVAILABLE"
            item["balance_sheet_status"] = "SCREENER_STANDALONE_HISTORY_AVAILABLE"
            item["cash_flow_status"] = "SCREENER_STANDALONE_HISTORY_AVAILABLE"
        if any(item[name] is not None for name in (
            "screener_promoter_holding_pct", "screener_public_holding_pct",
            "screener_fii_holding_pct", "screener_dii_holding_pct",
        )):
            item["shareholding_status"] = "SCREENER_CURRENT_REFERENCE_AVAILABLE"
        bulk_classification = bulk_by_isin.get(str(get("isin")))
        if bulk_classification is not None:
            item.update({
                "bulk_classification_sector": _text(getattr(bulk_classification, "sector", None)),
                "bulk_classification_industry": _text(getattr(bulk_classification, "industry", None)),
                "bulk_classification_status": "ACCEPTED",
                "bulk_classification_source": _text(getattr(bulk_classification, "source", None)),
                "bulk_classification_identity_source": _text(getattr(bulk_classification, "identity_source", None)),
                "bulk_classification_identity_method": _text(getattr(bulk_classification, "identity_method", None)),
                "bulk_classification_provider_symbol": _text(getattr(bulk_classification, "provider_symbol", None)),
                "bulk_classification_retrieved_at": _text(getattr(bulk_classification, "retrieved_at", None)),
                "bulk_classification_fingerprint": bulk_classification_fingerprint,
            })
            if item["official_sector"] is None and item["secondary_sector"] is None:
                item["derived_research_sector"] = item["bulk_classification_sector"]
                item["classification_reason"] = (
                    "Current-product-only Yahoo broad-sector evidence is accepted through exact exchange identity. "
                    "It is not official BSE taxonomy and does not alter frozen research classifications."
                )
        classification = classification_by_isin.get(isin)
        if classification is not None:
            item["classification_evidence_status"] = str(classification.confidence_status)
            item["ranking_classification_grade"] = bool(classification.ranking_grade)
        elif item.get("derived_research_sector") is not None:
            item["classification_evidence_status"] = "DERIVED_SECONDARY_REFERENCE_ONLY"
            item["ranking_classification_grade"] = False

        official = official_financial_by_isin.get(isin)
        official_accounting_family = None
        if official is not None and not official.empty:
            official = official.copy()
            official["period_end"] = pd.to_datetime(official["period_end"], errors="coerce")
            official["value"] = pd.to_numeric(official["value"], errors="coerce")
            official = official.dropna(subset=["period_end", "value"])

            def official_period(period_types: tuple[str, ...]) -> tuple[str | None, str | None, dict[str, float]]:
                subset = official.loc[official["period_type"].isin(period_types)]
                if subset.empty:
                    return None, None, {}
                period = subset["period_end"].max()
                current = subset.loc[subset["period_end"].eq(period)]
                basis_order = ["CONSOLIDATED", "STANDALONE"]
                basis = next((candidate for candidate in basis_order if current["statement_basis"].eq(candidate).any()), str(current.iloc[0]["statement_basis"]))
                current = current.loc[current["statement_basis"].eq(basis)]
                values: dict[str, float] = {}
                for concept, group in current.loc[~current["canonical_concept"].astype(str).str.startswith("unknown:")].groupby("canonical_concept", sort=False):
                    distinct = group["value"].astype(float).drop_duplicates().tolist()
                    if len(distinct) == 1:
                        values[str(concept)] = distinct[0]
                return period.date().isoformat(), basis, values

            annual_period, annual_basis, annual = official_period(("ANNUAL",))
            if annual_period and annual_basis:
                family_rows = official.loc[
                    official["period_end"].eq(pd.Timestamp(annual_period))
                    & official["statement_basis"].eq(annual_basis)
                ]
                if not family_rows.empty:
                    official_accounting_family = str(family_rows.iloc[0]["accounting_family"])
            quarter_period, quarter_basis, quarter = official_period(("QUARTERLY", "YTD"))
            balance_period, balance_basis, balance = official_period(("INSTANT",))
            item.update({
                "official_annual_period_end": annual_period,
                "official_annual_reporting_basis": annual_basis,
                "official_annual_revenue": annual.get("revenue", annual.get("total_income")),
                "official_annual_pat": annual.get("pat"), "official_annual_eps": annual.get("eps"),
                "official_quarterly_period_end": quarter_period,
                "official_quarterly_reporting_basis": quarter_basis,
                "official_quarterly_revenue": quarter.get("revenue", quarter.get("total_income")),
                "official_quarterly_pat": quarter.get("pat"),
                "official_balance_period_end": balance_period,
                "official_total_assets": balance.get("assets"),
                "official_borrowings": balance.get("borrowings"),
                "official_equity": balance.get("equity"), "official_cash": balance.get("cash"),
                "quarterly_results_status": "NORMALIZED_OFFICIAL_FACTS_AVAILABLE" if quarter_period else item["quarterly_results_status"],
                "balance_sheet_status": "NORMALIZED_OFFICIAL_FACTS_AVAILABLE" if balance_period else item["balance_sheet_status"],
                "official_evidence_freshness": "ACCEPTED_OFFICIAL_EXCHANGE_EVIDENCE",
            })
            annual_periods = sorted(
                official.loc[official["period_type"].eq("ANNUAL"), "period_end"].dropna().unique(),
                reverse=True,
            )
            if len(annual_periods) >= 2 and annual_period and annual_basis:
                previous_rows = official.loc[
                    official["period_type"].eq("ANNUAL")
                    & official["period_end"].eq(annual_periods[1])
                    & official["statement_basis"].eq(annual_basis)
                    & ~official["canonical_concept"].astype(str).str.startswith("unknown:")
                ]
                previous: dict[str, float] = {}
                for concept, group in previous_rows.groupby("canonical_concept", sort=False):
                    distinct = group["value"].astype(float).drop_duplicates().tolist()
                    if len(distinct) == 1:
                        previous[str(concept)] = distinct[0]
                current_revenue = annual.get("revenue", annual.get("total_income"))
                prior_revenue = previous.get("revenue", previous.get("total_income"))
                if current_revenue is not None and prior_revenue not in (None, 0):
                    item["official_revenue_growth"] = current_revenue / prior_revenue - 1
                if annual.get("pat") is not None and previous.get("pat") not in (None, 0):
                    item["official_profit_growth_yoy"] = annual["pat"] / previous["pat"] - 1
            if annual.get("pat") is not None and annual.get("revenue", annual.get("total_income")) not in (None, 0):
                item["official_net_margin"] = annual["pat"] / annual.get("revenue", annual.get("total_income"))
            cash_subset = official.loc[official["canonical_concept"].eq("operating_cash_flow")]
            if not cash_subset.empty:
                cash_row = cash_subset.sort_values("period_end", kind="stable").iloc[-1]
                item["official_cash_flow_period_end"] = cash_row["period_end"].date().isoformat()
                item["official_operating_cash_flow"] = float(cash_row["value"])
                item["cash_flow_status"] = "NORMALIZED_OFFICIAL_FACTS_AVAILABLE"

        holding = official_shareholding_by_isin.get(isin)
        if holding is not None:
            item.update({
                "shareholding_as_of": _text(holding.get("as_of_date")),
                "promoter_holding_pct": _number(holding.get("promoter_pct")),
                "public_holding_pct": _number(holding.get("public_pct")),
                "fii_holding_pct": _number(holding.get("fii_pct")),
                "dii_holding_pct": _number(holding.get("dii_pct")),
                "promoter_pledge_pct": _number(holding.get("promoter_pledge_pct")),
                "official_total_shares": _number(holding.get("total_shares")),
                "shareholding_status": "NORMALIZED_OFFICIAL_FACTS_AVAILABLE",
                "official_evidence_freshness": "ACCEPTED_OFFICIAL_EXCHANGE_EVIDENCE",
            })
            if item["official_total_shares"] is not None:
                item["shares_outstanding"] = item["official_total_shares"]
                if item["latest_price"] is not None:
                    item["market_cap"] = item["latest_price"] * item["official_total_shares"]
                    item["official_market_cap"] = item["market_cap"]
                    item["valuation_status"] = "DERIVED_FROM_OFFICIAL_SHARES_AND_ACCEPTED_PRICE"
                    item["valuation_reason"] = "Market capitalization is accepted price multiplied by explicit official shareholding-filing shares."
        if item["official_annual_eps"] not in (None, 0) and item["latest_price"] is not None:
            item["trailing_eps"] = item["official_annual_eps"]
            item["pe_ratio"] = item["latest_price"] / item["official_annual_eps"]
            item["official_pe_ratio"] = item["pe_ratio"]
        if (
            item["official_annual_pat"] is not None
            and item["official_equity"] not in (None, 0)
        ):
            item["official_return_on_equity"] = (
                item["official_annual_pat"]
                / item["official_equity"]
            )
            item["return_on_equity"] = item["official_return_on_equity"]
        if item["official_equity"] is not None and item["official_total_shares"] not in (None, 0):
            item["book_value"] = item["official_equity"] / item["official_total_shares"]
            if item["book_value"] != 0 and item["latest_price"] is not None:
                item["pb_ratio"] = item["latest_price"] / item["book_value"]
                item["official_pb_ratio"] = item["pb_ratio"]
            if item["official_annual_pat"] is not None and item["official_equity"] != 0:
                item["return_on_equity"] = item["official_annual_pat"] / item["official_equity"]
                item["official_return_on_equity"] = item["return_on_equity"]
            if (official_accounting_family not in {"BANKING", "NBFC_INDAS", "LIFE_INSURANCE", "GENERAL_INSURANCE", "INSURANCE"}
                    and item["official_borrowings"] is not None and item["official_equity"] != 0):
                item["official_debt_to_equity"] = item["official_borrowings"] / item["official_equity"]
        if any(item[name] is not None for name in (
            "official_market_cap", "official_pe_ratio", "official_pb_ratio",
            "official_return_on_equity", "official_debt_to_equity",
            "official_revenue_growth", "official_profit_growth_yoy", "official_net_margin",
        )):
            item["official_ratio_formula_version"] = "official_informational_ratios_v1"
            item["official_ratio_reporting_basis"] = item["official_annual_reporting_basis"]

        action_group = official_actions_by_isin.get(isin)
        if action_group is not None and not action_group.empty:
            dates = pd.to_datetime(action_group["ex_date"], errors="coerce")
            item["official_action_count"] = int(len(action_group))
            item["latest_corporate_action_date"] = None if dates.isna().all() else dates.max().date().isoformat()
            item["corporate_actions_status"] = "NORMALIZED_OFFICIAL_FACTS_AVAILABLE"
            item["official_evidence_freshness"] = "ACCEPTED_OFFICIAL_EXCHANGE_EVIDENCE"
        document = official_documents_by_isin.get(isin)
        if document is not None:
            item.update({
                "latest_document_type": _text(document.get("document_type")),
                "latest_document_date": _text(document.get("available_at")),
                "latest_document_url": _text(document.get("source_url")),
                "latest_document_source_sha256": _text(document.get("source_sha256")),
                "documents_status": "OFFICIAL_DOCUMENT_INDEX_AVAILABLE",
                "announcements_status": "OFFICIAL_DOCUMENT_INDEX_AVAILABLE",
                "official_evidence_freshness": "ACCEPTED_OFFICIAL_EXCHANGE_EVIDENCE",
            })

        filing = filing_by_ticker.get(ticker)
        if filing is None:
            item.update({
                "annual_profit_current": None, "annual_profit_prior": None,
                "annual_profit_unit": None, "annual_profit_label": None,
                "annual_report_status": "NO_VERIFIED_FILING", "annual_report_reason": "No accepted audited annual-report record is linked to this security.",
                "annual_report_financial_year": None, "annual_report_reporting_basis": None,
                "annual_report_source_url": None, "annual_report_pdf_sha256": None,
                "fundamental_contract": None,
                "documents_status": "OFFICIAL_DOCUMENT_INDEX_AVAILABLE" if document is not None else "OFFICIAL_DISCOVERY_ROUTE_AVAILABLE_NOT_CACHED",
            })
        else:
            profit = _parse_json_fact(getattr(filing, "annual_report_profit", None))
            selected = str(getattr(filing, "annual_report_selection_status", "")) == "SELECTED"
            extracted = str(getattr(filing, "annual_report_audit_status", "")) == "EXTRACTED"
            item.update({
                "annual_profit_current": _number(profit.get("current_value")),
                "annual_profit_prior": _number(profit.get("prior_value")),
                "annual_profit_unit": _text(profit.get("unit")),
                "annual_profit_label": _text(profit.get("label")),
                "annual_report_status": "NORMALIZED_AUDITED_FACTS_AVAILABLE" if selected and extracted else str(getattr(filing, "annual_report_audit_status", "NO_VERIFIED_FILING")),
                "annual_report_reason": "Accepted audited standalone evidence; period, basis, source and hashes are preserved." if selected and extracted else "The filing audit did not produce accepted normalized facts.",
                "annual_report_financial_year": _text(getattr(filing, "annual_report_financial_year", None)),
                "annual_report_reporting_basis": _text(getattr(filing, "annual_report_reporting_basis", None)),
                "annual_report_source_url": _text(getattr(filing, "annual_report_source_url", None)),
                "annual_report_pdf_sha256": _text(getattr(filing, "annual_report_pdf_sha256", None)),
                "fundamental_contract": _text(getattr(filing, "fundamental_data_contract_version", None)),
                "documents_status": "VERIFIED_ANNUAL_REPORT_LINK" if selected else "OFFICIAL_DISCOVERY_ROUTE_AVAILABLE_NOT_CACHED",
            })
        professor = strategy_by_isin.get(str(get("isin")))
        item.update({
            "professor_cohort": professor is not None,
            "professor_supplied_rank": _number(getattr(professor, "reference_rank", None)) if professor else None,
            "workbook_strategy_rank": _number(getattr(professor, "workbook_sip_rank", None)) if professor else None,
            "professor_industry": _text(getattr(professor, "workbook_industry", None)) if professor else None,
            "professor_workbook_current_price": _number(getattr(professor, "workbook_current_price", None)) if professor else None,
            "professor_workbook_market_cap": _number(getattr(professor, "workbook_market_cap", None)) if professor else None,
            "professor_workbook_cagr_10y": _number(getattr(professor, "workbook_cagr_10y", None)) if professor else None,
            "professor_workbook_cagr_5y": _number(getattr(professor, "workbook_cagr_5y", None)) if professor else None,
            "professor_workbook_cagr_3y": _number(getattr(professor, "workbook_cagr_3y", None)) if professor else None,
            "professor_workbook_cagr_1y": _number(getattr(professor, "workbook_cagr_1y", None)) if professor else None,
            "professor_evidence_status": _text(getattr(professor, "workbook_evidence_status", None)) if professor else "NOT_IN_PROFESSOR_COHORT",
        })
        rows.append(item)
    facts = pd.DataFrame(rows)
    from stock_ranker.product_classification import add_product_classification_and_baseline

    facts = add_product_classification_and_baseline(facts, history_root=history_root)
    facts = facts.loc[:, list(FACT_COLUMNS)]
    total = len(facts)

    def count(column: str) -> int:
        return int(facts[column].notna().sum())

    def true_count(column: str) -> int:
        return int(facts[column].astype(bool).sum())

    def any_count(*columns: str) -> int:
        return int(facts[list(columns)].notna().any(axis=1).sum())

    metrics = {
        "identity": int(facts[["ticker", "company", "isin", "primary_exchange"]].notna().all(axis=1).sum()),
        "current_price": count("latest_price"),
        "classification": count("official_sector"),
        "derived_classification": count("derived_research_sector"),
        "market_cap": count("market_cap"), "history_1y": true_count("history_1y_usable"),
        "company_profile": count("company_profile"), "shares_outstanding": count("shares_outstanding"),
        "pe": count("pe_ratio"), "pb": count("pb_ratio"), "eps": count("trailing_eps"),
        "book_value": count("book_value"), "dividend_yield": count("dividend_yield"),
        "roe": count("return_on_equity"), "revenue_growth": count("revenue_growth"),
        "secondary_profit_growth": count("secondary_profit_growth"),
        "high_low_52w": int(facts[["secondary_high_52w", "secondary_low_52w"]].notna().all(axis=1).sum()),
        "history_3y": true_count("history_3y_usable"), "history_5y": true_count("history_5y_usable"),
        "corporate_action_aware_history": int(facts["corporate_action_history_status"].eq("PROVIDER_ADJUSTED_NOT_OFFICIAL_ACTION_LEDGER").sum()),
        "valuation": int(facts[["pe_ratio", "pb_ratio", "book_value", "dividend_yield"]].notna().any(axis=1).sum()),
        "quarterly_financials": int((facts["quarterly_results_status"].isin(["NORMALIZED_FACTS_AVAILABLE", "NORMALIZED_OFFICIAL_FACTS_AVAILABLE", "USEFUL_FACTS"]) | facts["screener_workbook_available"]).sum()),
        "official_quarterly_financials": count("official_quarterly_period_end"),
        "annual_financials": int((facts["annual_report_status"].eq("NORMALIZED_AUDITED_FACTS_AVAILABLE") | facts["secondary_annual_period_end"].notna() | facts["official_annual_period_end"].notna() | facts["screener_historical_financials_available"]).sum()),
        "official_annual_financials": count("official_annual_period_end"),
        "balance_sheet": int((facts["balance_sheet_status"].isin(["NORMALIZED_FACTS_AVAILABLE", "NORMALIZED_OFFICIAL_FACTS_AVAILABLE", "USEFUL_FACTS"]) | facts["screener_workbook_available"]).sum()),
        "official_balance_sheet": count("official_balance_period_end"),
        "cash_flow": int((facts["cash_flow_status"].isin(["NORMALIZED_FACTS_AVAILABLE", "NORMALIZED_OFFICIAL_FACTS_AVAILABLE", "USEFUL_FACTS"]) | facts["screener_workbook_available"]).sum()),
        "official_cash_flow": count("official_cash_flow_period_end"),
        "roce": any_count("roce", "screener_roce_pct"),
        "roe": any_count("official_return_on_equity", "return_on_equity", "screener_roe_pct"),
        "debt_to_equity": any_count("debt_to_equity", "official_debt_to_equity", "secondary_debt_to_equity", "screener_debt_to_equity"),
        "profit_growth": any_count("profit_growth_yoy", "official_profit_growth_yoy", "secondary_profit_growth", "screener_profit_growth_pct"),
        "operational_cash_flow": any_count("official_operating_cash_flow", "secondary_operating_cash_flow", "screener_operating_cash_flow_crore"),
        "screener_exact_isin_current": int(
            facts["screener_current_status"].eq("ACCEPTED_EXACT_ISIN_CURRENT_REFERENCE").sum()
        ),
        "screener_unique_exchange_code_current": int(
            facts["screener_current_status"].eq("ACCEPTED_UNIQUE_EXCHANGE_CODE_CURRENT_REFERENCE").sum()
        ),
        "screener_current_reference": count("screener_current_status"),
        "screener_historical_financials": true_count("screener_historical_financials_available"),
        "screener_detailed_workbooks": true_count("screener_workbook_available"),
        "screener_industry_group": count("screener_industry_group"),
        "screener_ownership": any_count("screener_promoter_holding_pct", "screener_public_holding_pct", "screener_fii_holding_pct", "screener_dii_holding_pct"),
        "shareholding": int((facts["shareholding_status"].isin(["NORMALIZED_FACTS_AVAILABLE", "NORMALIZED_OFFICIAL_FACTS_AVAILABLE", "USEFUL_FACTS"]) | facts[["screener_promoter_holding_pct", "screener_public_holding_pct", "screener_fii_holding_pct", "screener_dii_holding_pct"]].notna().any(axis=1)).sum()),
        "corporate_actions": int(facts["corporate_actions_status"].isin(["USEFUL_FACTS", "NORMALIZED_OFFICIAL_FACTS_AVAILABLE"]).sum()),
        "annual_report_or_document_link": int(facts[["annual_report_source_url", "latest_document_url"]].notna().any(axis=1).sum()),
        "baseline_eligible": true_count("baseline_eligible"), "strict_v2_eligible": true_count("v2_eligible"),
        "product_classified": count("product_sector"),
        "product_baseline_eligible": true_count("product_baseline_eligible"),
    }
    professor_facts = facts.loc[facts["professor_cohort"]]
    if strategy.empty:
        professor_metrics = {"cohort_size": 0, "unique_security_count": 0, "supported_requests": 0}
    else:
        cohort = strategy[["isin"]].merge(facts, on="isin", how="left", suffixes=("", "_fact"))
        professor_metrics = {
            "cohort_size": int(len(strategy)),
            "unique_security_count": int(strategy["isin"].nunique()),
            "supported_requests": int(cohort["ticker"].notna().sum()),
            "supported_unique_securities": int(professor_facts["isin"].nunique()),
            "identity": int(cohort["ticker"].notna().sum()),
            "current_price": int(cohort["latest_price"].notna().sum()),
            "classification": int(cohort["official_sector"].notna().sum()),
            "history_1y": int(cohort["history_1y_usable"].fillna(False).astype(bool).sum()),
            "history_3y": int(cohort["history_3y_usable"].fillna(False).astype(bool).sum()),
            "history_5y": int(cohort["history_5y_usable"].fillna(False).astype(bool).sum()),
            "baseline_eligible": int(cohort["baseline_eligible"].fillna(False).astype(bool).sum()),
            "strict_v2_eligible": int(cohort["v2_eligible"].fillna(False).astype(bool).sum()),
            "unsupported_requests": int(cohort["ticker"].isna().sum()),
        }
    coverage = {
        "schema_version": FACT_SCHEMA_VERSION, "universe_count": total,
        "metrics": {key: {"count": value, "percent": round(100 * value / total, 4)} for key, value in metrics.items()},
        "professor_cohort": professor_metrics,
        "classification_boundary": "Only official or independently evidenced derived taxonomy may populate classifications; name guessing is forbidden.",
        "strict_v2_boundary": "Page completeness does not alter Research V2 eligibility or scoring.",
        "unresolved_external_data_limitations": {
            "valuation_without_verified_share_count_and_facts": total - metrics["valuation"],
            "quarterly_statements_not_available_from_accepted_sources": total - metrics["quarterly_financials"],
            "shareholding_not_available_from_accepted_sources": total - metrics["shareholding"],
            "broad_bse_adjusted_history_not_yet_accepted": int((facts["primary_exchange"].eq("BSE") & ~facts["history_1y_usable"]).sum()),
        },
    }
    canonical_rows = json.loads(facts.to_json(orient="records", date_format="iso", double_precision=15))
    fingerprint = _sha256_bytes(_json_bytes({
        "schema_version": FACT_SCHEMA_VERSION, "market_fingerprint": market_fingerprint,
        "screener_bundle_fingerprint": screener_bundle_fingerprint,
        "facts": canonical_rows, "coverage": coverage,
    }))
    manifest = {
        "schema_version": FACT_SCHEMA_VERSION, "fingerprint": fingerprint,
        "market_fingerprint": market_fingerprint, "trade_date": str(facts["trade_date"].max()),
        "screener_bundle_fingerprint": screener_bundle_fingerprint,
        "row_count": total, "canonical_key": "isin", "frozen_research_unchanged": True,
        "build_policy": "offline accepted evidence only; no provider request during page navigation",
    }
    return CompanyFactResult(facts=facts, coverage=coverage, manifest=manifest)


def write_company_fact_snapshot(result: CompanyFactResult, directory: str | Path) -> Path:
    target = Path(directory)
    if target.exists() and any(target.iterdir()):
        raise ValueError("company-fact output directory must be fresh")
    target.mkdir(parents=True, exist_ok=True)
    result.facts.to_csv(target / "company_facts.csv", index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")
    atomic_write_json(target / "coverage_summary.json", result.coverage)
    manifest = dict(result.manifest)
    manifest["artifacts"] = {
        name: _file_sha256(target / name) for name in ("company_facts.csv", "coverage_summary.json")
    }
    atomic_write_json(target / "manifest.json", manifest)
    return target / "manifest.json"


def load_company_fact_snapshot(directory: str | Path) -> CompanyFactResult:
    root = Path(directory)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["artifacts"].items():
        if _file_sha256(root / name) != expected:
            raise ValueError(f"company-fact artifact hash mismatch: {name}")
    facts = pd.read_csv(root / "company_facts.csv", low_memory=False)
    required_identity = {"ticker", "company", "isin", "primary_exchange", "trade_date"}
    if (len(facts) != int(manifest["row_count"])
            or any(column not in FACT_COLUMNS for column in facts.columns)
            or not required_identity.issubset(facts.columns)):
        raise ValueError("company-fact schema or row count is inconsistent")
    # Version-one snapshots created before official-exchange enrichment remain
    # valid last-known-good states.  New nullable presentation fields are
    # materialized in memory; the immutable accepted artifact is not rewritten.
    for column in FACT_COLUMNS:
        if column not in facts:
            facts[column] = 0 if column == "official_action_count" else False if column == "ranking_classification_grade" else None
    facts = facts.loc[:, FACT_COLUMNS]
    if facts["isin"].duplicated().any() or facts["ticker"].duplicated().any():
        raise ValueError("company-fact identities are not unique")
    coverage = json.loads((root / "coverage_summary.json").read_text(encoding="utf-8"))
    return CompanyFactResult(facts=facts, coverage=coverage, manifest=manifest)


def promote_company_fact_snapshot(result: CompanyFactResult, state_root: str | Path) -> dict[str, Any]:
    """Atomically promote a validated immutable snapshot; prior state survives failure."""

    root = Path(state_root)
    staging = root / "staging" / str(uuid.uuid4())
    write_company_fact_snapshot(result, staging)
    validated = load_company_fact_snapshot(staging)
    destination = root / "snapshots" / f"{validated.manifest['trade_date']}-{validated.manifest['fingerprint']}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        existing = load_company_fact_snapshot(destination)
        if existing.manifest["fingerprint"] != validated.manifest["fingerprint"]:
            raise ValueError("immutable company-fact snapshot conflicts")
        shutil.rmtree(staging)
    else:
        staging.replace(destination)
    pointer = {
        "schema_version": FACT_SCHEMA_VERSION,
        "accepted_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_path": destination.relative_to(root).as_posix(),
        "fingerprint": validated.manifest["fingerprint"],
        "trade_date": validated.manifest["trade_date"],
        "market_fingerprint": validated.manifest["market_fingerprint"],
    }
    atomic_write_json(root / "accepted_state.json", pointer)
    return pointer


def resolve_company_fact_snapshot(state_root: str | Path) -> Path:
    root = Path(state_root)
    state = json.loads((root / "accepted_state.json").read_text(encoding="utf-8"))
    path = (root / str(state["snapshot_path"])).resolve()
    if (root / "snapshots").resolve() not in path.parents:
        raise ValueError("company-fact snapshot escapes its store")
    loaded = load_company_fact_snapshot(path)
    if loaded.manifest["fingerprint"] != state["fingerprint"]:
        raise ValueError("accepted company-fact fingerprint mismatch")
    return path