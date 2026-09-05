"""Strict coverage probe for point-in-time Research V2 fundamentals.

The probe deliberately separates discovery from acceptance.  Text appearing in an
annual report is only a review candidate; it is never converted into a Research V2
input without the existing audited standalone mapping contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json
import re
from typing import Any

import pandas as pd


REQUIRED_V2_FUNDAMENTALS = ("roce", "debt_to_equity", "profit_growth_yoy")
ANNUAL_REPORT_CONTRACT = "nse_audited_standalone_fundamentals_v1"
_ISIN = re.compile(r"^INE[A-Z0-9]{9}$")


@dataclass(frozen=True, slots=True)
class PITFundamentalProbeConfig:
    sample_size: int = 50
    ranking_date: str = "2026-08-21"
    financial_year: str = "2025-26"
    minimum_reviewed_complete_rate: float = 0.20

    def __post_init__(self) -> None:
        if not 50 <= self.sample_size <= 100:
            raise ValueError("sample_size must be between 50 and 100")
        pd.Timestamp(self.ranking_date)
        if not re.fullmatch(r"\d{4}-\d{2}", self.financial_year):
            raise ValueError("financial_year must use YYYY-YY")
        if not 0 < self.minimum_reviewed_complete_rate <= 1:
            raise ValueError("minimum_reviewed_complete_rate must be in (0, 1]")


def select_probe_cohort(company_facts: pd.DataFrame, sample_size: int = 50) -> pd.DataFrame:
    """Select a repeatable exact-ISIN sample from Baseline-ready V2 gaps."""

    required = {
        "ticker", "company", "isin", "primary_exchange", "product_sector",
        "product_baseline_eligible", "v2_eligible",
    }
    missing = sorted(required.difference(company_facts.columns))
    if missing:
        raise ValueError(f"company facts missing columns: {', '.join(missing)}")
    if not 50 <= sample_size <= 100:
        raise ValueError("sample_size must be between 50 and 100")
    data = company_facts.copy(deep=True)
    mask = (
        data["primary_exchange"].eq("NSE")
        & data["product_baseline_eligible"].eq(True)
        & data["v2_eligible"].eq(False)
        & data["isin"].astype(str).map(lambda value: bool(_ISIN.fullmatch(value)))
    )
    candidates = data.loc[mask, ["ticker", "company", "isin", "product_sector"]].copy()
    if candidates["ticker"].duplicated().any() or candidates["isin"].duplicated().any():
        raise ValueError("probe candidates must have unique tickers and ISINs")
    candidates["selection_key"] = candidates["isin"].map(
        lambda value: sha256(str(value).encode("ascii")).hexdigest()
    )
    selected = candidates.sort_values(["selection_key", "isin"], kind="mergesort").head(sample_size)
    if len(selected) != sample_size:
        raise ValueError(f"only {len(selected)} eligible exact-identity candidates available")
    return selected.reset_index(drop=True)


def _load_by_ticker(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path.name} must contain a list")
    rows: dict[str, dict[str, Any]] = {}
    for item in payload:
        ticker = str(item.get("ticker", ""))
        if not ticker or ticker in rows:
            raise ValueError(f"{path.name} contains blank or duplicate ticker")
        rows[ticker] = item
    return rows


def summarize_structured_fact_coverage(
    facts: pd.DataFrame, cohort: pd.DataFrame, ranking_date: str,
) -> dict[str, Any]:
    """Summarize exact official XBRL concepts after point-in-time filtering."""

    required = {
        "ticker", "statement_basis", "period_type", "period_end", "available_at",
        "canonical_concept", "source_concept", "value",
    }
    missing = sorted(required.difference(facts.columns))
    if missing:
        raise ValueError(f"structured facts missing columns: {', '.join(missing)}")
    tickers = set(cohort["ticker"].astype(str))
    data = facts.loc[facts["ticker"].astype(str).isin(tickers)].copy()
    data["period_end"] = pd.to_datetime(data["period_end"], errors="coerce")
    data["available_at"] = pd.to_datetime(data["available_at"], errors="coerce", utc=True)
    cutoff = pd.Timestamp(ranking_date, tz="Asia/Kolkata").tz_convert("UTC") + pd.Timedelta(days=1)
    data = data.loc[
        data["statement_basis"].eq("STANDALONE")
        & data["period_type"].eq("ANNUAL")
        & data["period_end"].notna()
        & data["available_at"].notna()
        & data["period_end"].le(pd.Timestamp(ranking_date))
        & data["available_at"].lt(cutoff)
    ]
    concepts = data["source_concept"].astype(str)
    roce = set(data.loc[concepts.eq("ReturnOnCapitalEmployed"), "ticker"].astype(str))
    debt_equity = set(data.loc[concepts.eq("DebtEquityRatio"), "ticker"].astype(str))
    profit = set(data.loc[data["canonical_concept"].eq("pat"), "ticker"].astype(str))
    return {
        "source": "official NSE integrated financial-results XBRL",
        "point_in_time_filtered_row_count": len(data),
        "represented_security_count": int(data["ticker"].nunique()),
        "exact_return_on_capital_employed_count": len(roce),
        "exact_debt_equity_ratio_count": len(debt_equity),
        "annual_profit_count": len(profit),
        "complete_required_concept_count": len(roce & debt_equity & profit),
        "complete_required_tickers": sorted(roce & debt_equity & profit),
        "scientific_boundary": (
            "Only exact disclosed concepts are counted; no raw-fact ratio derivation, "
            "proxy, imputation, or basis mixing is performed."
        ),
    }


def assess_annual_report_probe(
    cohort: pd.DataFrame,
    acquisition_root: str | Path,
    audit_root: str | Path,
    reviewed_mapping_path: str | Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Measure evidence coverage without accepting unreviewed PDF extraction."""

    acquisition = Path(acquisition_root)
    audit = Path(audit_root)
    provenance = _load_by_ticker(acquisition / "annual_report_provenance.json")
    audits = _load_by_ticker(audit / "candidate_audit.json")
    mapping = json.loads(Path(reviewed_mapping_path).read_text(encoding="utf-8"))
    if mapping.get("fundamental_data_contract_version") != ANNUAL_REPORT_CONTRACT:
        raise ValueError("reviewed mapping uses an unexpected fundamental contract")
    accepted = {str(item["ticker"]): item for item in mapping.get("accepted", [])}

    rows: list[dict[str, Any]] = []
    for source in cohort.sort_values("selection_key", kind="mergesort").to_dict("records"):
        ticker = str(source["ticker"])
        acquired = provenance.get(ticker, {})
        audited = audits.get(ticker, {})
        text_path = audit / str(audited.get("text_path", ""))
        isin_in_document = False
        if audited.get("audit_status") == "EXTRACTED" and text_path.is_file():
            compact_text = re.sub(
                r"\s+", "", text_path.read_text(encoding="utf-8", errors="replace")
            )
            isin_in_document = str(source["isin"]) in compact_text
        selected = acquired.get("selected_metadata") or {}
        has_timestamp = bool(selected.get("disseminationDateTime"))
        has_roce = int(audited.get("roce_candidate_page_count", 0)) > 0
        has_de = int(audited.get("debt_equity_candidate_page_count", 0)) > 0
        has_profit = int(audited.get("profit_candidate_page_count", 0)) > 0
        candidate_complete = all((isin_in_document, has_timestamp, has_roce, has_de, has_profit))
        reviewed = accepted.get(ticker)
        selected_year = None
        if selected.get("fromYr") and selected.get("toYr"):
            selected_year = f"{selected['fromYr']}-{str(selected['toYr'])[-2:]}"
        reviewed_complete = bool(
            reviewed
            and candidate_complete
            and reviewed.get("reporting_basis") == "STANDALONE"
            and reviewed.get("financial_year") == selected_year
            and all(reviewed.get(field) for field in ("roce", "debt_to_equity", "profit"))
            and reviewed["roce"].get("classification") == "DIRECT_DISCLOSURE"
            and reviewed["debt_to_equity"].get("classification") == "DIRECT_DISCLOSURE"
            and reviewed["profit"].get("classification") == "DIRECT_DISCLOSURE"
        )
        if reviewed_complete:
            status = "REVIEWED_COMPLETE_PIT_SAFE"
        elif candidate_complete:
            status = "COMPLETE_DIRECT_DISCLOSURE_CANDIDATE_REQUIRES_REVIEW"
        elif acquired.get("selection_status") != "SELECTED":
            status = str(acquired.get("selection_status") or "NO_ELIGIBLE_ANNUAL_REPORT")
        elif audited.get("audit_status") != "EXTRACTED":
            status = str(audited.get("audit_status") or "PDF_EXTRACTION_FAILED")
        elif not isin_in_document:
            status = "ISIN_NOT_PROVEN_IN_REPORT_TEXT"
        else:
            missing = [
                name for name, present in (
                    ("ROCE", has_roce), ("DEBT_EQUITY", has_de), ("PROFIT", has_profit)
                ) if not present
            ]
            status = "MISSING_DIRECT_" + "_AND_".join(missing)
        rows.append({
            "ticker": ticker,
            "company": source["company"],
            "isin": source["isin"],
            "sector": source["product_sector"],
            "selection_key": source["selection_key"],
            "selection_status": acquired.get("selection_status"),
            "exchange_dissemination_timestamp": selected.get("disseminationDateTime"),
            "source_url": acquired.get("source_url"),
            "pdf_sha256": acquired.get("pdf_sha256"),
            "audit_status": audited.get("audit_status"),
            "isin_in_document": isin_in_document,
            "explicit_roce_candidate": has_roce,
            "explicit_debt_equity_candidate": has_de,
            "annual_profit_candidate": has_profit,
            "direct_disclosure_candidate_complete": candidate_complete,
            "reviewed_complete_pit_safe": reviewed_complete,
            "final_probe_status": status,
        })
    result = pd.DataFrame(rows)
    reviewed_count = int(result["reviewed_complete_pit_safe"].sum())
    sample_size = len(result)
    candidate_count = int(result["direct_disclosure_candidate_complete"].sum())
    summary = {
        "schema_version": "pit_fundamental_coverage_probe_v1",
        "fundamental_contract": ANNUAL_REPORT_CONTRACT,
        "required_v2_fundamentals": list(REQUIRED_V2_FUNDAMENTALS),
        "sample_size": sample_size,
        "sector_count": int(result["sector"].nunique()),
        "annual_report_selected_count": int(result["selection_status"].eq("SELECTED").sum()),
        "pdf_extracted_count": int(result["audit_status"].eq("EXTRACTED").sum()),
        "exact_isin_in_report_count": int(result["isin_in_document"].sum()),
        "explicit_roce_candidate_count": int(result["explicit_roce_candidate"].sum()),
        "explicit_debt_equity_candidate_count": int(result["explicit_debt_equity_candidate"].sum()),
        "annual_profit_candidate_count": int(result["annual_profit_candidate"].sum()),
        "complete_direct_disclosure_candidate_count": candidate_count,
        "reviewed_complete_pit_safe_count": reviewed_count,
        "reviewed_complete_rate": reviewed_count / sample_size if sample_size else 0.0,
        "candidate_complete_rate": candidate_count / sample_size if sample_size else 0.0,
        "status_counts": {
            str(key): int(value)
            for key, value in result["final_probe_status"].value_counts().sort_index().items()
        },
        "scale_gate_passed": False,
        "scale_gate_reason": (
            "Unreviewed PDF candidates cannot be promoted automatically; the configured "
            "reviewed-complete threshold must be evaluated by the runner."
        ),
    }
    return result, summary
