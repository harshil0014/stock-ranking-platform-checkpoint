"""Read-only adapters for the professor and competition research website."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd

from stock_ranker.v2_config import ResearchV2Weights
from stock_ranker.walk_forward_blind import validate_blind_snapshot_directory
from stock_ranker.website import _prepared_real_baseline, _prepared_real_research_v2


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BLIND_ROOT = PROJECT_ROOT / "data/walk_forward/blind_predictions_v1_run_01"
EVALUATION_ROOT = PROJECT_ROOT / "data/walk_forward/evaluation_v1_run_01"
PROTOCOL_SHA256 = "a81278b799e1a61c3684f3b319fb14e2f6f0db6a2bdad1cd79b2ce13fd6f8576"
AMENDMENT_SHA256 = "7f8c5d40de88077f3b6afcd471d0db4377fab567d2839e719a71ee6b11ae7163"
BLIND_FINGERPRINT = "c438c31967e1f2685bbe77d85db6ca44617e024c699dba3749ee3523af6e401d"
EVALUATION_FINGERPRINT = "04e29e8a0f641f900e2ef5ca6d6fe5252b75eff9b23a69fba3b6480f373606c1"
HISTORICAL_DATES = {
    "2022": "2022-08-05", "2023": "2023-08-07",
    "2024": "2024-08-07", "2025": "2025-08-07",
}
COHORT_COUNTS = {"2022": 8, "2023": 4, "2024": 8, "2025": 16}
SAFE_TICKER = re.compile(r"^[A-Z0-9&.-]{1,32}$")


class ResearchWebsiteError(ValueError):
    """Controlled website adapter error with no filesystem disclosure."""


def _unavailable(message: str, instruction: str) -> dict[str, Any]:
    return {
        "available": False, "status": "DATA NOT AVAILABLE",
        "message": message, "preparation_instruction": instruction,
    }


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records", double_precision=15))


def _safe_ticker(value: str) -> str:
    ticker = str(value).strip().upper()
    if not SAFE_TICKER.fullmatch(ticker):
        raise ResearchWebsiteError("ticker is not a recognized safe identifier")
    return ticker


def _current(model: str) -> dict[str, Any]:
    try:
        if model == "baseline_v1":
            return _prepared_real_baseline()
        if model == "research_v2":
            return _prepared_real_research_v2()
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return _unavailable(
            "The prepared current-ranking artifact is unavailable or invalid.",
            "Prepare the accepted local NIFTY 50 ranking bundle documented in README.md.",
        ) | {"diagnostic": type(exc).__name__}
    raise ResearchWebsiteError("model must be baseline_v1 or research_v2")


def overview() -> dict[str, Any]:
    return {
        "available": True,
        "title": "Indian Equity Research Platform",
        "subtitle": "Explainable, point-in-time Indian equity ranking and historical validation.",
        "models": [
            {
                "id": "baseline_v1", "name": "Baseline V1",
                "label": "Original-paper signals — project operationalization",
                "summary": "YoY growth, 3Y CAGR, 5Y CAGR, and recorded-high recency ranked within sector.",
            },
            {
                "id": "research_v2", "name": "Research V2",
                "label": "Nine-factor explainable project extension",
                "summary": "Price performance, risk, audited standalone fundamentals, point-in-time eligibility, and within-sector ranking.",
            },
        ],
        "research_status": {
            "current_research_cycle": "COMPLETE",
            "predictions_frozen_before_outcomes": "YES",
            "walk_forward_evaluation": "COMPLETE",
            "robustness_audit": "PASS",
            "primary_sample": "3 sector-date observations",
        },
        "story": [
            {"title": "Original method", "text": "Four price-history signals establish the research starting point."},
            {"title": "Software Baseline", "text": "The signals are implemented deterministically as Baseline V1."},
            {"title": "Research V2 extension", "text": "Risk, audited fundamentals and strict eligibility are added."},
            {"title": "Point-in-time reconstruction", "text": "Only information available at each historical cutoff is admitted."},
            {"title": "Freeze predictions", "text": "Ranks and cohorts are fixed before outcomes are inspected."},
            {"title": "Reveal outcomes", "text": "Future prices are added only after the prediction evidence is frozen."},
            {"title": "Compare rankings", "text": "Both methods are evaluated on matched sector cohorts."},
        ],
        "model_comparison": {
            "baseline": ["YoY", "3Y CAGR", "5Y CAGR", "recorded-high recency", "within-sector ranking"],
            "research_v2_adds": ["volatility", "drawdown", "ROCE", "debt/equity", "profit growth", "point-in-time eligibility", "provenance"],
            "boundary": "Baseline V1 is a deterministic project operationalization of the original paper's ranking signals. Research V2 is a project extension.",
        },
    }


def rankings(model: str) -> dict[str, Any]:
    data = _current(model)
    if not data.get("available", True):
        return data
    rows = data["results"]
    return {
        "available": True, "model": model, "rows": rows,
        "sectors": sorted({str(row["sector"]) for row in rows}),
        "provenance": data["provenance"],
        "sector_relative_warning": (
            "Scores and ranks are meaningful within sectors; raw scores should not be compared naively across unrelated sectors."
        ),
    }


def stock_explanation(model: str, ticker_value: str) -> dict[str, Any]:
    ticker = _safe_ticker(ticker_value)
    data = rankings(model)
    if not data.get("available"):
        return data
    row = next((item for item in data["rows"] if item["ticker"] == ticker), None)
    if row is None:
        raise ResearchWebsiteError("stock is not present in the prepared ranking universe")
    if model == "research_v2" and row.get("eligible"):
        explanation = row["explanation"]
        metrics = {**explanation["price_derived_metrics"], **explanation["fundamental_metrics"]}
        directions = {
            "return_1y": "Higher is preferred", "cagr_3y": "Higher is preferred",
            "cagr_5y": "Higher is preferred", "days_since_recorded_high": "Lower is preferred",
            "annualized_volatility_1y": "Lower is preferred", "max_drawdown_3y": "Higher (nearer zero) is preferred",
            "roce": "Higher is preferred", "debt_to_equity": "Lower is preferred",
            "profit_growth_yoy": "Higher is preferred",
        }
        factors = []
        for name, value in metrics.items():
            factors.append({
                "metric": name, "value": value, "direction": directions[name],
                "weight_percent": explanation["weights_percent"][name],
                "component_score": explanation["component_scores"][f"{name}_score"],
                "contribution": explanation["contributions"][f"{name}_contribution"],
            })
        row = {**row, "factors": factors}
    return {
        "available": True, "model": model, "stock": row,
        "baseline_caveat": (
            "Baseline final composite is a project operationalization of the original paper's ranking signals."
        ),
        "advice_warning": "Research explanation only; not investment advice.",
    }


def _validated_blind_manifest() -> dict[str, Any]:
    try:
        manifest = json.loads((BLIND_ROOT / "manifest.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ResearchWebsiteError("Historical research artifact has not been prepared locally.") from exc
    if manifest.get("protocol_sha256") != PROTOCOL_SHA256:
        raise ResearchWebsiteError("Historical artifact integrity error: protocol hash mismatch.")
    if manifest.get("blind_prediction_fingerprint") != BLIND_FINGERPRINT:
        raise ResearchWebsiteError("Historical artifact integrity error: blind fingerprint mismatch.")
    if manifest.get("future_outcome_data_present") is not False:
        raise ResearchWebsiteError("Historical artifact integrity error: prediction bundle is not outcome-blind.")
    return manifest


def historical(year_value: str) -> dict[str, Any]:
    year = str(year_value)
    if year not in HISTORICAL_DATES:
        raise ResearchWebsiteError("year must be one of 2022, 2023, 2024, or 2025")
    try:
        manifest = _validated_blind_manifest()
        ranking_date = HISTORICAL_DATES[year]
        root = BLIND_ROOT / ranking_date
        expected = next(item for item in manifest["date_manifests"] if item["ranking_date"] == ranking_date)
        if sha256((root / "manifest.json").read_bytes()).hexdigest() != expected["manifest_sha256"]:
            raise ResearchWebsiteError("Historical artifact integrity error: date manifest hash mismatch.")
        validate_blind_snapshot_directory(root, ranking_date)
        v2 = pd.read_csv(root / "research_v2.csv")
        matched = pd.read_csv(root / "matched_baseline.csv")
        exclusions = pd.read_csv(root / "exclusions.csv")
        provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    except ResearchWebsiteError:
        raise
    except (FileNotFoundError, ValueError, KeyError, StopIteration, json.JSONDecodeError) as exc:
        return _unavailable(
            "Historical research artifact has not been prepared locally or failed integrity validation.",
            "Run marketdata/runners/prepare_walk_forward_blind.py from the accepted local blind cache.",
        ) | {"diagnostic": type(exc).__name__}
    v2_by_ticker = v2.set_index("ticker").to_dict("index")
    v2_exclusions = exclusions.loc[exclusions["model"].eq("RESEARCH_V2")].set_index("ticker").to_dict("index")
    rows = []
    for item in matched.to_dict("records"):
        ticker = item["ticker"]
        ranked = v2_by_ticker.get(ticker)
        excluded = v2_exclusions.get(ticker, {})
        rows.append({
            "ticker": ticker, "company": item["company"],
            "historical_sector": item["historical_sector"],
            "historical_industry": item["historical_industry"],
            "eligible": ranked is not None,
            "research_v2_score": ranked.get("research_v2_score") if ranked else None,
            "research_v2_sector_rank": ranked.get("sector_rank") if ranked else None,
            "matched_baseline_sector_rank": item.get("matched_baseline_sector_rank"),
            "original_baseline_sector_rank": item.get("original_baseline_sector_rank"),
            "comparison_status": item.get("comparison_status"),
            "reason_code": "ELIGIBLE" if ranked else excluded.get("reason_code", "NOT_ELIGIBLE"),
            "reason": "Eligible under the frozen point-in-time contract." if ranked else excluded.get("reason", "No eligible Research V2 result."),
        })
    cutoff = provenance["annual_report_acquisition_summary"]["cutoff"]
    return {
        "available": True, "year": year, "ranking_date": ranking_date,
        "cutoff_timestamp": cutoff, "blind_fingerprint": BLIND_FINGERPRINT,
        "eligible_count": len(v2), "excluded_count": len(rows) - len(v2),
        "universe_source": "Official historical NIFTY 50 MCWB snapshot",
        "classification_document": provenance["classification_document"],
        "coverage_by_year": COHORT_COUNTS,
        "rows": _records(pd.DataFrame(rows)),
        "separation_warning": (
            "WHAT THE MODEL KNEW THEN. Future outcomes are deliberately excluded from this prediction table."
        ),
    }


def _validated_evaluation() -> tuple[dict[str, Any], Path]:
    try:
        manifest = json.loads((EVALUATION_ROOT / "manifest.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ResearchWebsiteError("Walk-forward evaluation artifact has not been prepared locally.") from exc
    if manifest.get("evaluation_fingerprint") != EVALUATION_FINGERPRINT:
        raise ResearchWebsiteError("Validation integrity error: evaluation fingerprint mismatch.")
    if manifest.get("blind_prediction_fingerprint") != BLIND_FINGERPRINT:
        raise ResearchWebsiteError("Validation integrity error: blind fingerprint mismatch.")
    for artifact in manifest.get("artifacts", []):
        path = EVALUATION_ROOT / str(artifact["path"])
        if not path.is_file() or path.stat().st_size != artifact["size"] or sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
            raise ResearchWebsiteError("Validation integrity error: artifact inventory mismatch.")
    summary = json.loads((EVALUATION_ROOT / "evaluation_summary.json").read_text(encoding="utf-8"))
    if summary.get("protocol_sha256") != PROTOCOL_SHA256 or summary.get("amendment_sha256") != AMENDMENT_SHA256:
        raise ResearchWebsiteError("Validation integrity error: protocol identity mismatch.")
    if summary.get("blind_prediction_fingerprint") != BLIND_FINGERPRINT:
        raise ResearchWebsiteError("Validation integrity error: summary blind fingerprint mismatch.")
    return summary, EVALUATION_ROOT


def validation() -> dict[str, Any]:
    try:
        summary, root = _validated_evaluation()
        observations = pd.read_csv(root / "sector_rank_ic.csv")
        pairwise = pd.read_csv(root / "pairwise_accuracy.csv")
        top = pd.read_csv(root / "top_stock_excess_return.csv")
        spread = pd.read_csv(root / "top_bottom_spread.csv")
    except ResearchWebsiteError:
        raise
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return _unavailable(
            "Walk-forward evaluation artifact has not been prepared locally.",
            "Run marketdata/runners/evaluate_walk_forward.py against the frozen blind bundle and cached outcomes.",
        ) | {"diagnostic": type(exc).__name__}
    horizons = {"3": summary["horizons"]["3"], "6": summary["horizons"]["6"], "12": summary["horizons"]["12"]}
    chart_data = [{
        "horizon_months": int(months), "status": "PRIMARY" if months == "12" else "SECONDARY",
        "research_v2_rank_ic": item["research_v2_rank_ic"]["mean"],
        "matched_baseline_rank_ic": item["matched_baseline_rank_ic"]["mean"],
        "research_v2_pairwise_accuracy": item["pairwise"]["research_v2"]["pairwise_accuracy"],
        "matched_baseline_pairwise_accuracy": item["pairwise"]["matched_baseline"]["pairwise_accuracy"],
    } for months, item in horizons.items()]
    return {
        "available": True,
        "protocol": {"identifier": "walk_forward_validation_protocol_v1", "sha256": PROTOCOL_SHA256},
        "amendment": {"identifier": "walk_forward_validation_protocol_amendment_001", "sha256": AMENDMENT_SHA256},
        "blind_fingerprint": BLIND_FINGERPRINT,
        "evaluation_fingerprint": EVALUATION_FINGERPRINT,
        "primary": summary["horizons"]["12"],
        "secondary": {"6": summary["horizons"]["6"], "3": summary["horizons"]["3"]},
        "observations": _records(observations),
        "pairwise": _records(pairwise),
        "top_stock_excess": _records(top),
        "top_bottom_spread": _records(spread),
        "chart_data": chart_data,
        "coverage_by_year": COHORT_COUNTS,
        "plain_findings": [
            "At 3 months, the Baseline performed somewhat better.",
            "At 6 months, Research V2 performed better in this small sample.",
            "At the preregistered 12-month horizon, Research V2 was only slightly higher.",
            "The 12-month primary test had only three valid sector observations, so the evidence is preliminary.",
        ],
        "rank_ic_definition": (
            "Rank IC asks whether stocks ranked higher by the model also tended to have higher future returns "
            "within the same sector. Positive values tended to align, zero indicates little ordering relationship, "
            "and negative values tended to oppose future ordering."
        ),
        "interpretation": (
            "The first historical experiment is horizon-dependent. Research V2 was weaker at 3 months, stronger at 6 months, and marginally stronger under the preregistered 12-month primary comparison. The primary comparison contains only three valid sector-date observations and is not statistically conclusive."
        ),
        "warning": "VERY LOW PRIMARY SAMPLE SIZE — 3 sector-date observations.",
    }


def provenance(ticker_value: str) -> dict[str, Any]:
    ticker = _safe_ticker(ticker_value)
    current = stock_explanation("research_v2", ticker)
    if not current.get("available"):
        return current
    stock = current["stock"]
    explanation = stock.get("explanation", {})
    fundamentals = explanation.get("final_research_v2_fundamentals") or {}
    report = explanation.get("nse_annual_report_fundamental_provenance") or {}
    return {
        "available": True, "ticker": ticker, "company": stock["company"],
        "eligible": stock["eligible"], "reason": stock["reason"],
        "market_universe": "Current NIFTY 50 accepted 2026-08-07 snapshot",
        "price_data": "Yahoo adjusted-price history via yfinance 1.5.1; retrospective donor series with accepted cutoff and repair policy.",
        "fundamental_contract": "NSE Audited Standalone Fundamentals v1",
        "annual_report": explanation.get("nse_annual_report_fundamental_provenance"),
        "final_fundamentals": explanation.get("final_research_v2_fundamentals"),
        "xbrl_corroboration": explanation.get("integrated_filing_xbrl_evidence_corroborating"),
        "unavailable_message": None if stock["eligible"] else "Accepted fundamental provenance is unavailable because this stock is excluded.",
        "simple_evidence": None if not stock["eligible"] else {
            "heading": "Verified Fundamental Evidence",
            "roce": {"value": fundamentals.get("roce_value"), "page": fundamentals.get("roce_source_page")},
            "debt_to_equity": {"value": fundamentals.get("debt_to_equity_value"), "page": fundamentals.get("debt_to_equity_source_page")},
            "profit_current": fundamentals.get("fy2025_26_pat_or_profit"),
            "profit_prior": fundamentals.get("fy2024_25_pat_or_profit"),
            "profit_growth": fundamentals.get("profit_growth_yoy"),
            "profit_page": fundamentals.get("profit_source_page"),
            "source": "NSE annual report",
            "available_before_ranking_date": "YES" if report.get("exchange_dissemination_timestamp") else None,
        },
    }


def methodology() -> dict[str, Any]:
    weights = {name: float(value) for name, value in ResearchV2Weights().as_dict().items()}
    return {
        "available": True,
        "progression": [
            "ORIGINAL PAPER", "BASELINE V1", "RESEARCH V2",
            "POINT-IN-TIME HISTORICAL RECONSTRUCTION", "BLIND PREDICTIONS",
            "OUTCOME REVEAL", "WALK-FORWARD EVALUATION", "ROBUSTNESS AUDIT",
        ],
        "original_signals": ["YoY growth", "3Y CAGR", "5Y CAGR", "recorded-high recency", "within-sector ranking"],
        "baseline_caveat": "Baseline V1 reproduces and operationalizes the original paper's ranking signals; its equal-rank-mean composite is a project approximation.",
        "research_v2_caveat": "Research V2 is the project's explainable nine-factor extension, not a formula attributed to the original paper.",
        "weights_percent": weights,
        "fundamental_contract": "NSE Audited Standalone Fundamentals v1",
        "point_in_time_rule": "For a historical ranking date, predictor data released after that cutoff is not allowed.",
    }


def status() -> dict[str, Any]:
    return {
        "available": True, "robustness_audit": "PASS",
        "accepted_test_milestone": "324 passed",
        "checks": {
            "Temporal leakage": "PASS", "Identity substitution": "PASS",
            "Sector/taxonomy": "PASS", "Missing/malformed data": "PASS",
            "Tie handling": "PASS", "Endpoint policy": "PASS",
            "Cache/fingerprint corruption": "PASS",
        },
        "plain_checks": [
            "No future information enters historical rankings.",
            "No company is silently replaced by a successor.",
            "Missing data is excluded rather than guessed.",
            "Repeated runs reproduce identical research artifacts.",
        ],
        "blind_reproduction": "46 files, byte-identical",
        "evaluation_reproduction": "9 files, byte-identical",
        "cohort_sizes": COHORT_COUNTS,
        "primary_groups": 3, "secondary_groups": 7,
        "fingerprints": {
            "protocol": PROTOCOL_SHA256, "amendment": AMENDMENT_SHA256,
            "blind": BLIND_FINGERPRINT, "evaluation": EVALUATION_FINGERPRINT,
        },
        "limitations": [
            "Only four annual historical ranking dates are available.",
            "Only three primary sector-date observations have at least three peers.",
            "Strict point-in-time fundamental availability reduced Research V2 coverage.",
            "Yahoo historical adjusted prices were retrospectively acquired and retain vendor-data risk.",
            "This evaluates ranking quality, not portfolio profitability.",
            "No transaction-cost, liquidity, or execution model is included.",
            "Weights are fixed research choices and are not proven optimal.",
        ],
    }
