"""Canonical import and presentation boundary for the local research website."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from io import StringIO
import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_ranker.baseline import (
    calculate_baseline_rankings,
    get_top_stocks_by_sector,
)
from stock_ranker.config import BaselineConfig
from stock_ranker.contracts import METRIC_COLUMNS, RANK_COLUMNS
from stock_ranker.historical_baseline import (
    PRICE_SERIES,
    PROVIDER,
    calculate_prepared_real_rankings,
    load_historical_baseline_bundle,
)
from stock_ranker.nse_snapshot import parse_nse_snapshot
from stock_ranker.real_research_v2 import load_real_research_v2_bundle
from stock_ranker.research_v2 import (
    ResearchV2Inputs,
    calculate_research_v2,
    get_top_research_v2_by_sector,
)
from stock_ranker.v2_config import ResearchV2Config, ResearchV2Weights
from stock_ranker.v2_contracts import (
    V2_CONTRIBUTION_COLUMNS,
    V2_METRIC_COLUMNS,
    V2_SCORE_COLUMNS,
)
from stock_ranker.runtime import PROJECT_ROOT, data_root


METHOD_BASELINE = "baseline_v1"
METHOD_RESEARCH_V2 = "research_v2"
METHODS = (METHOD_BASELINE, METHOD_RESEARCH_V2)
INPUT_OFFICIAL_NSE_SNAPSHOT = "official_nse_snapshot"
INPUT_PREPARED_REAL_BASELINE = "prepared_real_baseline"
INPUT_PREPARED_REAL_RESEARCH_V2 = "prepared_real_research_v2"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

DATA_MODE_LABELS = {
    "real_current_snapshot": "REAL CURRENT SNAPSHOT",
    "real_historical_point_in_time": "REAL HISTORICAL / POINT-IN-TIME",
    "real_point_in_time_research_v2": "REAL POINT-IN-TIME RESEARCH V2",
    "real_historical_price_research": "REAL HISTORICAL PRICE RESEARCH",
    "synthetic_research_test": "SYNTHETIC RESEARCH TEST",
}

DATA_ROOT = data_root()
PREPARED_REAL_BASELINE_BUNDLE = (
    DATA_ROOT / "marketdata/nifty50-baseline-2026-08-07"
)
PREPARED_REAL_RESEARCH_V2_BUNDLE = (
    DATA_ROOT
    / "marketdata/nifty50-research-v2-2026-08-07/standalone-contract-reason-fix-run-01"
)
SYNTHETIC_FILES = {
    METHOD_BASELINE: {"baseline": DATA_ROOT / "input/synthetic_stocks.csv"},
    METHOD_RESEARCH_V2: {
        "universe": DATA_ROOT / "input/v2_universe.csv",
        "prices": DATA_ROOT / "input/v2_prices.csv",
        "fundamentals": DATA_ROOT / "input/v2_fundamentals.csv",
    },
}


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must not be blank")
    return value.strip()


def _parse_csv_text(value: Any, label: str) -> pd.DataFrame:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} CSV is required and must not be empty")
    try:
        frame = pd.read_csv(StringIO(value))
    except (pd.errors.ParserError, UnicodeError, ValueError) as exc:
        raise ValueError(f"Could not parse {label} CSV: {exc}") from exc
    if frame.empty:
        raise ValueError(f"{label} CSV must contain at least one row")
    return frame


def _iso_date(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must use valid ISO YYYY-MM-DD format")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field} must use valid ISO YYYY-MM-DD format") from exc
    return parsed.isoformat()


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    normalized = frame.copy()
    for column in normalized.select_dtypes(include=["datetime", "datetimetz"]):
        normalized[column] = normalized[column].dt.strftime("%Y-%m-%d")
    return json.loads(normalized.to_json(orient="records", double_precision=15))


def _display_percent(value: Any) -> str | None:
    if value is None:
        return None
    rendered = f"{float(value) * 100:.4f}".rstrip("0").rstrip(".")
    return f"{rendered}%"


def _display_report_amount(value: Any, unit: Any) -> str | None:
    if value is None:
        return None
    rendered = f"{float(value):,.15g}"
    return f"{rendered} {unit}" if unit else rendered


def _fair_baseline_comparison_group(comparison: dict[str, Any]) -> dict[str, Any]:
    """Present the frozen matched-cohort comparison without recalculating it."""

    movement = comparison.get("rank_movement")
    if comparison.get("comparison_status") != "MATCHED_COHORT" or movement is None:
        rendered_movement: str | None = None
    else:
        numeric = float(movement)
        rendered = str(int(numeric)) if numeric.is_integer() else str(numeric)
        rendered_movement = f"+{rendered}" if numeric > 0 else rendered
    return {
        "original_baseline_sector_rank": comparison.get(
            "original_baseline_sector_rank"
        ),
        "matched_cohort_baseline_sector_rank": comparison.get(
            "matched_baseline_sector_rank"
        ),
        "research_v2_sector_rank": comparison.get("research_v2_sector_rank"),
        "matched_cohort_rank_movement": rendered_movement,
        "eligible_peer_count": comparison.get("eligible_peer_count"),
        "comparison_status": comparison.get("comparison_status"),
        "comparison_explanation": (
            "Rank movement compares Research V2 only with Baseline V1 reranked "
            "on the same Research-V2-eligible sector cohort. The original "
            "Baseline rank is shown for context and is not used to calculate "
            "movement."
        ),
    }


def _real_v2_provenance_groups(
    filing: dict[str, Any],
    ranking: dict[str, Any] | None,
    contract_label: str | None,
) -> dict[str, dict[str, Any]]:
    """Separate final annual-report donors from corroborating XBRL evidence."""

    xbrl = {
        "xbrl_selection_status": filing.get("selection_status"),
        "xbrl_stage_reason_code": filing.get("reason_code"),
        "xbrl_statement_basis": filing.get("statement_basis"),
        "xbrl_exchange_dissemination_timestamp": filing.get(
            "exchange_dissemination_timestamp"
        ),
        "xbrl_source_url": filing.get("source_xbrl_url"),
        "xbrl_sha_256": filing.get("xbrl_sha256"),
    }
    annual = {
        "annual_report_selection_status": filing.get("annual_report_selection_status"),
        "annual_report_audit_status": filing.get("annual_report_audit_status"),
        "annual_report_source_url": filing.get("annual_report_source_url"),
        "annual_report_pdf_filename": filing.get("annual_report_pdf_filename"),
        "annual_report_pdf_sha_256": filing.get("annual_report_pdf_sha256"),
        "financial_year": filing.get("annual_report_financial_year"),
        "submission_type": filing.get("annual_report_submission_type"),
        "broadcast_timestamp": filing.get("annual_report_broadcast_timestamp"),
        "exchange_dissemination_timestamp": filing.get(
            "annual_report_exchange_dissemination_timestamp"
        ),
        "reporting_basis": filing.get("annual_report_reporting_basis"),
        "fundamental_data_contract_version": filing.get(
            "fundamental_data_contract_version"
        ),
    }
    groups: dict[str, dict[str, Any]] = {
        "integrated_filing_xbrl_evidence_corroborating": xbrl,
        "nse_annual_report_fundamental_provenance": annual,
    }
    roce = filing.get("annual_report_roce")
    leverage = filing.get("annual_report_debt_to_equity")
    profit = filing.get("annual_report_profit")
    if ranking is not None and all(isinstance(value, dict) for value in (roce, leverage, profit)):
        basis = filing.get("annual_report_reporting_basis")
        groups = {
            "final_research_v2_fundamentals": {
                "fundamental_data_contract": contract_label,
                "reporting_basis": basis,
                "roce_value": _display_percent(roce.get("canonical_decimal")),
                "roce_exact_disclosure_label": roce.get("label"),
                "roce_source_page": roce.get("page"),
                "roce_source_section_or_table": roce.get("table"),
                "roce_reporting_basis": basis,
                "roce_issuer_formula_or_basis": roce.get("formula"),
                "debt_to_equity_value": leverage.get("canonical_decimal"),
                "debt_to_equity_exact_disclosure_label": leverage.get("label"),
                "debt_to_equity_source_page": leverage.get("page"),
                "debt_to_equity_source_section_or_table": leverage.get("table"),
                "debt_to_equity_reporting_basis": basis,
                "debt_to_equity_issuer_formula_or_basis": leverage.get("formula"),
                "fy2025_26_pat_or_profit": _display_report_amount(
                    profit.get("current_value"), profit.get("unit")
                ),
                "fy2024_25_pat_or_profit": _display_report_amount(
                    profit.get("prior_value"), profit.get("unit")
                ),
                "profit_growth_yoy": _display_percent(ranking.get("profit_growth_yoy")),
                "profit_exact_disclosure_label": profit.get("label"),
                "profit_source_page": profit.get("page"),
                "profit_source_section_or_table": profit.get("table"),
                "profit_reporting_basis": basis,
                "profit_comparability_warning": profit.get("comparability_warning"),
            },
            **groups,
        }
    return groups


def _decode_upload(files: dict[str, Any], field: str) -> bytes:
    value = files.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} is required")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"{field} must be valid base64 data") from exc
    if not decoded:
        raise ValueError(f"{field} must not be empty")
    if len(decoded) > MAX_UPLOAD_BYTES:
        raise ValueError(f"{field} exceeds the 25 MiB decoded upload limit")
    return decoded


def _official_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    files = payload.get("files")
    if not isinstance(files, dict):
        raise ValueError("files must be supplied for the official snapshot")
    nifty_name = _required_text(files, "nifty_filename")
    bhavcopy_name = _required_text(files, "bhavcopy_filename")
    result = parse_nse_snapshot(
        _decode_upload(files, "nifty_base64"),
        _decode_upload(files, "bhavcopy_base64"),
        nifty_filename=nifty_name,
        bhavcopy_filename=bhavcopy_name,
    )
    trade_date = result.provenance["trade_date"]
    return {
        "mode": "real_snapshot",
        "analysis_available": False,
        "ranking_notice": (
            "Ranking unavailable for this snapshot alone. Historical price "
            "data is required for Baseline V1. Historical point-in-time prices "
            "and fundamentals are required for Research V2."
        ),
        "snapshot": _records(result.snapshot),
        "export_csv": result.snapshot.to_csv(index=False, lineterminator="\n"),
        "export_filename": f"nifty50_nse_snapshot_{trade_date}.csv",
        "provenance": result.provenance,
    }


def _common_provenance(
    *, source_label: str, data_mode: str, as_of_date: str, method: str,
    universe: str, company_count: int, eligible_count: int, ineligible_count: int,
) -> dict[str, Any]:
    warnings = [
        "Research screening only; not investment advice or a recommendation.",
        "Inputs are processed locally. No live market data is fetched.",
    ]
    if data_mode == "synthetic_research_test":
        warnings.append(
            "Synthetic research test: all companies and values are fictional."
        )
    elif data_mode == "real_current_snapshot":
        warnings.append(
            "Current-snapshot mode is not a point-in-time historical claim."
        )
    elif data_mode == "real_historical_price_research":
        warnings.append(
            "Real historical price research on a current universe; not a point-in-time backtest."
        )
    else:
        warnings.append(
            "Point-in-time behavior relies on supplied availability dates and source accuracy."
        )
    if method == METHOD_BASELINE:
        warnings.append(
            "Baseline V1 uses the project's equal-rank-mean approximation; it is not claimed as the paper's exact final formula."
        )
    else:
        warnings.append(
            "Research V2 scores are relative within sectors and are not comparable across sectors."
        )
    return {
        "source_label": source_label,
        "data_mode": DATA_MODE_LABELS[data_mode],
        "data_mode_key": data_mode,
        "as_of_date": as_of_date,
        "methodology": (
            "Baseline V1 / Original Paper signals (project approximation)"
            if method == METHOD_BASELINE
            else "Research V2 point-in-time weighted scoring"
        ),
        "universe": universe,
        "company_count": company_count,
        "eligible_count": eligible_count,
        "ineligible_count": ineligible_count,
        "warnings": warnings,
    }


def _baseline(payload: dict[str, Any], files: dict[str, Any]) -> dict[str, Any]:
    data = _parse_csv_text(files.get("baseline"), "Baseline V1 input")
    rankings = calculate_baseline_rankings(data, BaselineConfig(top_n=5))
    dates = sorted(rankings["as_of_date"].unique().tolist())
    if len(dates) != 1:
        raise ValueError(
            "Website Baseline V1 input must contain exactly one as_of_date"
        )
    requested_date = payload.get("ranking_date")
    if requested_date and _iso_date(requested_date, "ranking_date") != dates[0]:
        raise ValueError("ranking_date does not match the Baseline V1 as_of_date")

    top = get_top_stocks_by_sector(rankings, 5)
    selected = set(top["ticker"].tolist())
    rows: list[dict[str, Any]] = []
    for row in _records(rankings):
        rows.append({
            "ticker": row["ticker"],
            "company": row["company"],
            "sector": row["sector"],
            "rank": row["sector_rank"],
            "score": row["baseline_score"],
            "eligible": True,
            "status": "Eligible",
            "selected_top_5": row["ticker"] in selected,
            "reason": "Ranked from the four accepted Baseline V1 signals.",
            "explanation": {
                "metrics": {name: row[name] for name in METRIC_COLUMNS},
                "metric_ranks": {name: row[name] for name in RANK_COLUMNS},
                "combined_score": row["baseline_score"],
                "method_version": row["method_version"],
                "interpretation": "Lower Baseline V1 score and sector rank are better.",
            },
        })

    export = rankings.copy()
    export.insert(len(export.columns) - 1, "eligible", True)
    export.insert(len(export.columns) - 1, "status", "Eligible")
    source = _required_text(payload, "source_label")
    universe = str(payload.get("universe") or "Uploaded Baseline V1 universe").strip()
    return {
        "method": METHOD_BASELINE,
        "results": rows,
        "export_csv": export.to_csv(index=False, lineterminator="\n"),
        "export_filename": f"baseline_v1_rankings_{dates[0]}.csv",
        "provenance": _common_provenance(
            source_label=source, data_mode=payload["data_mode"],
            as_of_date=dates[0], method=METHOD_BASELINE, universe=universe,
            company_count=len(rankings), eligible_count=len(rankings),
            ineligible_count=0,
        ),
    }


def _prepared_real_baseline() -> dict[str, Any]:
    bundle = load_historical_baseline_bundle(PREPARED_REAL_BASELINE_BUNDLE)
    rankings, top = calculate_prepared_real_rankings(bundle, 5)
    selected = set(top["ticker"].tolist())
    ranked = {row["ticker"]: row for row in _records(rankings)}
    anchors = {row["ticker"]: row for row in _records(bundle.anchors)}
    mapping = {row["ticker"]: row for row in _records(bundle.symbol_map)}
    results: list[dict[str, Any]] = []
    export_rows: list[dict[str, Any]] = []
    for status in _records(bundle.eligibility):
        ticker = status["ticker"]
        row = ranked.get(ticker)
        if row is None:
            results.append({
                "ticker": ticker, "company": status["company"],
                "sector": status["sector"], "rank": None, "score": None,
                "eligible": False, "status": "Excluded",
                "reason": status["reason"], "selected_top_5": False,
                "explanation": {
                    "eligibility": {"reason_code": status["reason_code"], "reason": status["reason"]},
                    "interpretation": "No price or score was fabricated for this excluded company.",
                },
            })
            export_rows.append({**status, "provider": PROVIDER,
                                "adjustment_series": PRICE_SERIES,
                                "as_of_date": bundle.metadata["as_of_date"],
                                "bundle_fingerprint": bundle.fingerprint})
            continue
        anchor = anchors[ticker]
        results.append({
            "ticker": ticker, "company": row["company"], "sector": row["sector"],
            "rank": row["sector_rank"], "score": row["baseline_score"],
            "eligible": True, "status": "Eligible", "reason": status["reason"],
            "selected_top_5": ticker in selected,
            "explanation": {
                "data_derived": {
                    "current_date": anchor["current_date"], "current_price": anchor["current_price"],
                    "close_1y_date": anchor["close_1y_date"], "close_1y_ago": anchor["close_1y_ago"],
                    "close_3y_date": anchor["close_3y_date"], "close_3y_ago": anchor["close_3y_ago"],
                    "close_5y_date": anchor["close_5y_date"], "close_5y_ago": anchor["close_5y_ago"],
                    "recorded_high_date": anchor["recorded_high_date"],
                    "recorded_high_price": anchor["recorded_high_price"],
                    "recorded_high_search_start_date": anchor.get("recorded_high_search_start_date"),
                    "recorded_high_search_start_basis": anchor.get("recorded_high_search_start_basis"),
                    "recorded_high_search_start_evidence": anchor.get("recorded_high_search_start_evidence"),
                    "provider_symbol": mapping[ticker]["provider_symbol"],
                    "provider_status": mapping[ticker]["status"],
                },
                "ranking_derived_metrics": {name: row[name] for name in METRIC_COLUMNS},
                "ranking_derived_metric_ranks": {name: row[name] for name in RANK_COLUMNS},
                "combined_score": row["baseline_score"], "sector_rank": row["sector_rank"],
                "method_version": row["method_version"],
                "interpretation": "Lower Baseline V1 score and sector rank are better within this sector.",
            },
        })
        export_rows.append({
            **row, **anchor, "eligible": True, "reason_code": "ELIGIBLE",
            "reason": status["reason"], "provider": PROVIDER,
            "provider_symbol": mapping[ticker]["provider_symbol"],
            "provider_status": mapping[ticker]["status"],
            "adjustment_series": PRICE_SERIES, "bundle_fingerprint": bundle.fingerprint,
        })
    results.sort(key=lambda item: (
        item["sector"], not item["eligible"], item["score"] is None,
        item["score"] if item["score"] is not None else float("inf"), item["ticker"],
    ))
    eligible_count = sum(item["eligible"] for item in results)
    provenance = _common_provenance(
        source_label=("Yahoo Finance historical prices through yfinance 1.5.1; "
                      "official supplied NSE snapshot used for terminal validation"),
        data_mode="real_historical_price_research",
        as_of_date=str(bundle.metadata["as_of_date"]), method=METHOD_BASELINE,
        universe="Current NIFTY 50 universe as of supplied constituent file",
        company_count=len(results), eligible_count=eligible_count,
        ineligible_count=len(results) - eligible_count,
    )
    provenance.update({
        "bundle_fingerprint": bundle.fingerprint,
        "historical_provider": PROVIDER,
        "adjustment_series": PRICE_SERIES,
        "reliance_audit_status": bundle.metadata.get("reliance_audit_status"),
    })
    provenance["warnings"].extend([
        "Real historical prices use the current NIFTY 50 universe; this is not a survivorship-bias-free historical universe.",
        "This is not a walk-forward backtest and makes no profitability claim.",
        "Corporate-action handling comes from the selected upstream adjusted series; this project applies no custom adjustment.",
        "Yahoo adjusted prices include upstream dividend adjustments and are not claimed to reproduce the paper's source-price semantics.",
    ])
    return {
        "method": METHOD_BASELINE, "results": results,
        "export_csv": pd.DataFrame(export_rows).to_csv(index=False, lineterminator="\n"),
        "export_filename": "real_nifty50_baseline_v1_2026-08-07.csv",
        "provenance": provenance,
    }


def _prepared_real_research_v2() -> dict[str, Any]:
    bundle = load_real_research_v2_bundle(PREPARED_REAL_RESEARCH_V2_BUNDLE)
    metadata = bundle.metadata
    ranked = {row["ticker"]: row for row in _records(bundle.rankings)}
    comparison_by_ticker = {
        row["ticker"]: row for row in _records(bundle.comparison)
    }
    provenance_by_ticker = {}
    for item in _records(bundle.provenance):
        raw_facts = item.get("fact_provenance")
        if isinstance(raw_facts, str):
            item["fact_provenance"] = json.loads(raw_facts)
        for field in (
            "annual_report_roce", "annual_report_debt_to_equity",
            "annual_report_profit",
        ):
            value = item.get(field)
            if isinstance(value, str) and value.strip():
                item[field] = json.loads(value)
        provenance_by_ticker[item["ticker"]] = item
    weights = {
        name: float(value) for name, value in ResearchV2Weights().as_dict().items()
    }
    results: list[dict[str, Any]] = []
    export_rows: list[dict[str, Any]] = []
    for status in _records(bundle.eligibility):
        ticker = status["ticker"]
        row = ranked.get(ticker)
        filing = provenance_by_ticker.get(ticker, {})
        comparison = comparison_by_ticker.get(ticker, {})
        if row is None:
            display = {
                "ticker": ticker, "company": status["company"],
                "sector": status["sector"], "rank": None, "score": None,
                "eligible": False, "status": "Ineligible",
                "reason": status["reason"], "selected_top_5": False,
                "explanation": {
                    "eligibility": {
                        "reason_code": status["reason_code"],
                        "reason": status["reason"],
                    },
                    "fair_baseline_comparison": _fair_baseline_comparison_group(
                        comparison
                    ),
                    **_real_v2_provenance_groups(
                        filing, None, metadata.get("fundamental_data_contract_label")
                    ),
                    "interpretation": (
                        "No fundamental value, component score, or final score was "
                        "fabricated for this excluded company."
                    ),
                },
            }
            export_rows.append({
                **status, **filing,
                # Filing provenance retains the earlier XBRL-stage status,
                # but the canonical export reason is the final standalone
                # annual-report contract decision.
                "reason_code": status["reason_code"],
                "reason": status["reason"],
                "research_v2_score": None, "sector_rank": None,
            })
        else:
            display = {
                "ticker": ticker, "company": row["company"],
                "sector": row["sector"], "rank": row["sector_rank"],
                "score": row["research_v2_score"], "eligible": True,
                "status": "Eligible", "reason": status["reason"],
                "selected_top_5": bool(row["sector_rank"] <= 5),
                "explanation": {
                    "price_derived_metrics": {
                        name: row[name] for name in V2_METRIC_COLUMNS[:6]
                    },
                    "fundamental_metrics": {
                        name: row[name] for name in V2_METRIC_COLUMNS[6:]
                    },
                    "component_scores": {
                        name: row[name] for name in V2_SCORE_COLUMNS
                    },
                    "weights_percent": weights,
                    "contributions": {
                        name: row[name] for name in V2_CONTRIBUTION_COLUMNS
                    },
                    "final_score": row["research_v2_score"],
                    "sector_rank": row["sector_rank"],
                    "fair_baseline_comparison": _fair_baseline_comparison_group(
                        comparison
                    ),
                    **_real_v2_provenance_groups(
                        filing, row, metadata.get("fundamental_data_contract_label")
                    ),
                    "method_version": row["method_version"],
                    "interpretation": (
                        "Higher Research V2 score is better only within this sector."
                    ),
                },
            }
            export_rows.append({**row, **filing, "reason_code": "ELIGIBLE",
                                "reason": status["reason"]})
        results.append(display)
    results.sort(key=lambda item: (
        item["sector"], not item["eligible"], item["score"] is None,
        -(item["score"] or 0), item["ticker"],
    ))
    provenance = _common_provenance(
        source_label="Official NSE annual reports and Integrated Filing evidence; accepted frozen Yahoo adjusted-price bundle",
        data_mode="real_point_in_time_research_v2",
        as_of_date=str(metadata["ranking_date"]), method=METHOD_RESEARCH_V2,
        universe="Current NIFTY 50 universe from the accepted 2026-08-07 snapshot",
        company_count=len(results), eligible_count=int(metadata["eligible_count"]),
        ineligible_count=int(metadata["excluded_count"]),
    )
    provenance.update({
        "bundle_fingerprint": bundle.fingerprint,
        "filing_cutoff": metadata["filing_cutoff"],
        "bundle_status": metadata["status"],
        "baseline_bundle_fingerprint": metadata["baseline_bundle_fingerprint"],
        "scoring_model": "Research V2",
        "fundamental_data_contract": metadata.get("fundamental_data_contract_label"),
        "fundamental_data_contract_version": metadata.get("fundamental_data_contract_version"),
        "matched_cohort_methodology": "Baseline V1 is recalculated without formula changes on exactly the Research-V2-eligible tickers in each sector; movement uses that matched rank only.",
    })
    provenance["warnings"].extend([
        "The current NIFTY 50 universe creates survivorship bias; this is one as-of snapshot, not a walk-forward backtest.",
        "Standalone was selected for broad internally consistent audited statutory-ratio coverage, not because standalone economics are universally superior.",
        "Issuer ROCE definitions vary and are retained in provenance; missing accepted facts cause exclusion, never substitution or imputation.",
        "Yahoo adjusted-price semantics are inherited from the accepted Baseline bundle.",
        "No transaction-cost, liquidity, portfolio-optimization, profitability, or investment-performance claim is made.",
    ])
    return {
        "method": METHOD_RESEARCH_V2, "results": results,
        "comparison": _records(bundle.comparison),
        "comparison_sector_summary": _records(bundle.comparison_sector_summary),
        "comparison_export_csv": bundle.comparison.to_csv(index=False, lineterminator="\n"),
        "comparison_export_filename": "real_nifty50_baseline_v1_vs_research_v2_2026-08-07.csv",
        "export_csv": pd.DataFrame(export_rows).to_csv(index=False, lineterminator="\n"),
        "export_filename": "real_nifty50_research_v2_2026-08-07.csv",
        "provenance": provenance,
    }


def _research_v2(payload: dict[str, Any], files: dict[str, Any]) -> dict[str, Any]:
    ranking_date = _iso_date(payload.get("ranking_date"), "ranking_date")
    config = ResearchV2Config(
        ranking_date=datetime.strptime(ranking_date, "%Y-%m-%d").date(), top_n=5
    )
    inputs = ResearchV2Inputs(
        universe=_parse_csv_text(files.get("universe"), "universe"),
        prices=_parse_csv_text(files.get("prices"), "prices"),
        fundamentals=_parse_csv_text(files.get("fundamentals"), "fundamentals"),
    )
    result = calculate_research_v2(inputs, config)
    top = get_top_research_v2_by_sector(result.rankings, 5)
    selected = set(top["ticker"].tolist())
    ranked = {row["ticker"]: row for row in _records(result.rankings)}
    eligibility = _records(result.eligibility)
    rows: list[dict[str, Any]] = []
    export_rows: list[dict[str, Any]] = []
    for status_row in eligibility:
        row = ranked.get(status_row["ticker"])
        if row:
            explanation = {
                "metrics": {name: row[name] for name in V2_METRIC_COLUMNS},
                "component_scores": {name: row[name] for name in V2_SCORE_COLUMNS},
                "contributions": {
                    name: row[name] for name in V2_CONTRIBUTION_COLUMNS
                },
                "combined_score": row["research_v2_score"],
                "method_version": row["method_version"],
                "interpretation": "Higher Research V2 score is better within this sector.",
            }
            display = {
                "ticker": row["ticker"], "company": row["company"],
                "sector": row["sector"], "rank": row["sector_rank"],
                "score": row["research_v2_score"], "eligible": True,
                "status": "Eligible", "reason": status_row["reason"],
                "selected_top_5": row["ticker"] in selected,
                "explanation": explanation,
            }
            export_rows.append({**row, "status": "Eligible", "reason_code": "ELIGIBLE", "reason": status_row["reason"]})
        else:
            display = {
                "ticker": status_row["ticker"],
                "company": status_row["company"],
                "sector": status_row["sector"],
                "rank": None, "score": None, "eligible": False,
                "status": "Ineligible", "reason": status_row["reason"],
                "selected_top_5": False,
                "explanation": {
                    "reason_code": status_row["reason_code"],
                    "reason": status_row["reason"],
                    "interpretation": "No score was fabricated for an ineligible company.",
                },
            }
            export_rows.append({
                **status_row, "status": "Ineligible", "sector_rank": None,
                "research_v2_score": None,
            })
        rows.append(display)
    rows.sort(key=lambda item: (
        item["sector"], not item["eligible"],
        item["score"] is None, -(item["score"] or 0), item["ticker"],
    ))

    source = _required_text(payload, "source_label")
    universe_label = str(payload.get("universe") or "Uploaded Research V2 universe").strip()
    ineligible = sum(not row["eligible"] for row in rows)
    return {
        "method": METHOD_RESEARCH_V2,
        "results": rows,
        "export_csv": pd.DataFrame(export_rows).to_csv(
            index=False, lineterminator="\n"
        ),
        "export_filename": f"research_v2_rankings_{ranking_date}.csv",
        "provenance": _common_provenance(
            source_label=source, data_mode=payload["data_mode"],
            as_of_date=ranking_date, method=METHOD_RESEARCH_V2,
            universe=universe_label, company_count=len(rows),
            eligible_count=len(rows) - ineligible, ineligible_count=ineligible,
        ),
    }


def analyze_website_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a website request and dispatch to an accepted ranking engine."""

    if not isinstance(payload, dict):
        raise TypeError("request must be a JSON object")
    if payload.get("input_source") == INPUT_OFFICIAL_NSE_SNAPSHOT:
        return _official_snapshot(payload)
    if payload.get("input_source") == INPUT_PREPARED_REAL_BASELINE:
        if payload.get("method", METHOD_BASELINE) != METHOD_BASELINE:
            raise ValueError("prepared real historical data supports Baseline V1 only")
        return _prepared_real_baseline()
    if payload.get("input_source") == INPUT_PREPARED_REAL_RESEARCH_V2:
        if payload.get("method", METHOD_RESEARCH_V2) != METHOD_RESEARCH_V2:
            raise ValueError("prepared real Research V2 data supports Research V2 only")
        return _prepared_real_research_v2()
    method = payload.get("method")
    if method not in METHODS:
        raise ValueError("method must be baseline_v1 or research_v2")

    if payload.get("use_synthetic_sample") is True:
        files = {
            name: path.read_text(encoding="utf-8")
            for name, path in SYNTHETIC_FILES[method].items()
        }
        payload = {
            **payload,
            "source_label": "Committed fictional research sample",
            "data_mode": "synthetic_research_test",
            "universe": "Fictional companies committed for automated research tests",
        }
        if method == METHOD_RESEARCH_V2:
            payload["ranking_date"] = "2026-06-30"
    else:
        raw_files = payload.get("files")
        if not isinstance(raw_files, dict):
            raise ValueError("files must be supplied for an uploaded dataset")
        files = raw_files

    data_mode = payload.get("data_mode")
    if data_mode not in DATA_MODE_LABELS:
        raise ValueError("data_mode is invalid")
    if method == METHOD_BASELINE and data_mode == "real_historical_point_in_time":
        raise ValueError(
            "Baseline V1 snapshot input cannot be labelled point-in-time historical"
        )
    return _baseline(payload, files) if method == METHOD_BASELINE else _research_v2(payload, files)
