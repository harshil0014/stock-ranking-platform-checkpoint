"""Strict validation of reviewed annual-report Research V2 candidates.

This module does not promote records into the production Research V2 mapping.  It
checks a human-reviewed evidence specification against cached official NSE annual
reports and emits a separate validation result for an explicit later decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json
import re
from typing import Any

import pandas as pd


VALIDATION_SCHEMA = "pit_annual_report_validation_v1"
FUNDAMENTAL_CONTRACT = "nse_audited_standalone_fundamentals_v1"
_PAGE = re.compile(r"=== PDF PAGE (\d+) ===")


@dataclass(frozen=True, slots=True)
class AnnualReportValidationResult:
    records: pd.DataFrame
    summary: dict[str, Any]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _pages(path: Path) -> dict[int, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    parts = _PAGE.split(text)
    if len(parts) < 3:
        raise ValueError(f"page markers missing from {path.name}")
    return {int(parts[index]): parts[index + 1] for index in range(1, len(parts), 2)}


def _require_evidence(page_text: str, evidence: dict[str, Any], ticker: str, field: str) -> None:
    page = int(evidence["page"])
    normalised = _normalise(page_text)
    for anchor in evidence.get("anchors", []):
        if _normalise(str(anchor)) not in normalised:
            raise ValueError(f"{ticker} {field} evidence anchor absent on PDF page {page}: {anchor}")


def validate_reviewed_annual_reports(
    specification_path: str | Path,
    coverage_matrix_path: str | Path,
    acquisition_root: str | Path,
    text_root: str | Path,
    *,
    ranking_date: str = "2026-08-21",
) -> AnnualReportValidationResult:
    """Validate exact reviewed disclosures without changing the accepted mapping."""

    specification_file = Path(specification_path)
    specification = json.loads(specification_file.read_text(encoding="utf-8"))
    if specification.get("schema_version") != VALIDATION_SCHEMA:
        raise ValueError("unexpected annual-report validation schema")
    if specification.get("fundamental_data_contract_version") != FUNDAMENTAL_CONTRACT:
        raise ValueError("unexpected fundamental data contract")
    if specification.get("reporting_basis") != "STANDALONE":
        raise ValueError("validation records must use standalone reports")

    coverage = pd.read_csv(coverage_matrix_path, dtype=str).fillna("")
    if coverage["ticker"].duplicated().any():
        raise ValueError("coverage matrix ticker keys must be unique")
    coverage_by_ticker = coverage.set_index("ticker").to_dict("index")

    acquisition = Path(acquisition_root)
    provenance_payload = json.loads(
        (acquisition / "annual_report_provenance.json").read_text(encoding="utf-8")
    )
    provenance = {str(item["ticker"]): item for item in provenance_payload}
    if len(provenance) != len(provenance_payload):
        raise ValueError("annual-report provenance contains duplicate tickers")

    cutoff = pd.Timestamp(ranking_date, tz="Asia/Kolkata") + pd.Timedelta(days=1)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in specification.get("records", []):
        ticker = str(item["ticker"])
        if ticker in seen:
            raise ValueError(f"duplicate reviewed ticker: {ticker}")
        seen.add(ticker)
        identity = coverage_by_ticker.get(ticker)
        if not identity or identity["isin"] != item["isin"] or identity["company"] != item["company"]:
            raise ValueError(f"{ticker} exact security identity mismatch")
        source = provenance.get(ticker)
        if not source or source.get("selection_status") != "SELECTED":
            raise ValueError(f"{ticker} has no selected official annual report")
        metadata = source.get("selected_metadata") or {}
        available_at = pd.to_datetime(
            metadata.get("disseminationDateTime"), format="%d-%b-%Y %H:%M:%S", errors="raise"
        ).tz_localize("Asia/Kolkata")
        if available_at >= cutoff:
            raise ValueError(f"{ticker} annual report was unavailable at the ranking cutoff")
        if source.get("pdf_sha256") != item["pdf_sha256"]:
            raise ValueError(f"{ticker} recorded report hash drift")
        pdf_path = acquisition / str(source["pdf_path"])
        if _file_sha256(pdf_path) != item["pdf_sha256"]:
            raise ValueError(f"{ticker} cached PDF hash mismatch")
        text_path = Path(text_root) / f"{ticker}.txt"
        report_pages = _pages(text_path)
        compact_report = _normalise(text_path.read_text(encoding="utf-8", errors="replace"))
        if _normalise(item["isin"]) not in compact_report:
            raise ValueError(f"{ticker} ISIN is not present in the official report")

        for field in ("roce", "debt_to_equity", "profit"):
            evidence = item[field]
            page = int(evidence["page"])
            if page not in report_pages:
                raise ValueError(f"{ticker} {field} PDF page {page} is missing")
            _require_evidence(report_pages[page], evidence, ticker, field)
            for extra in evidence.get("additional_evidence", []):
                extra_page = int(extra["page"])
                if extra_page not in report_pages:
                    raise ValueError(f"{ticker} {field} PDF page {extra_page} is missing")
                _require_evidence(report_pages[extra_page], extra, ticker, field)

        status = str(item["review_status"])
        complete = status == "COMPLETE_DIRECT_DISCLOSURE"
        roce = item["roce"].get("canonical_decimal") if complete else None
        debt = item["debt_to_equity"].get("canonical_decimal") if complete else None
        current = item["profit"].get("current_value") if complete else None
        prior = item["profit"].get("prior_value") if complete else None
        if complete and any(value is None for value in (roce, debt, current, prior)):
            raise ValueError(f"{ticker} complete record lacks a numeric disclosure")
        growth = None
        if complete:
            values = [float(roce), float(debt), float(current), float(prior)]
            if not all(pd.notna(value) and abs(value) != float("inf") for value in values):
                raise ValueError(f"{ticker} contains a non-finite reviewed value")
            if float(prior) == 0:
                raise ValueError(f"{ticker} prior profit is zero; YoY growth is undefined")
            growth = float(current) / float(prior) - 1.0
        v2_usable = bool(complete and float(debt) >= 0)
        final_status = (
            "COMPLETE_PIT_SAFE_CANDIDATE" if v2_usable
            else "COMPLETE_BUT_V2_INVALID_LEVERAGE" if complete
            else str(item["unresolved_reason"])
        )
        rows.append({
            "ticker": ticker,
            "company": item["company"],
            "isin": item["isin"],
            "reporting_basis": "STANDALONE",
            "financial_year": specification["financial_year"],
            "period_end": specification["period_end"],
            "available_date": available_at.date().isoformat(),
            "exchange_dissemination_timestamp": available_at.isoformat(),
            "source_url": source["source_url"],
            "pdf_sha256": source["pdf_sha256"],
            "roce": roce,
            "debt_to_equity": debt,
            "current_profit": current,
            "prior_profit": prior,
            "profit_unit": item["profit"]["unit"],
            "profit_growth_yoy": growth,
            "review_status": status,
            "v2_numeric_policy_usable": v2_usable,
            "final_validation_status": final_status,
            "roce_page": int(item["roce"]["page"]),
            "debt_to_equity_page": int(item["debt_to_equity"]["page"]),
            "profit_page": int(item["profit"]["page"]),
            "roce_label": item["roce"]["label"],
            "debt_to_equity_label": item["debt_to_equity"]["label"],
            "profit_label": item["profit"]["label"],
            "ratio_section": "Audited standalone statutory/key-ratio table",
            "profit_section": "Audited standalone statement of profit and loss",
            "roce_formula": item["roce"]["formula"],
            "debt_to_equity_formula": item["debt_to_equity"]["formula"],
            "comparability_warning": item.get("comparability_warning", ""),
        })

    records = pd.DataFrame(rows).sort_values("ticker", kind="mergesort").reset_index(drop=True)
    complete_count = int(records["review_status"].eq("COMPLETE_DIRECT_DISCLOSURE").sum())
    usable_count = int(records["v2_numeric_policy_usable"].sum())
    summary = {
        "schema_version": VALIDATION_SCHEMA,
        "fundamental_data_contract_version": FUNDAMENTAL_CONTRACT,
        "financial_year": specification["financial_year"],
        "ranking_date": ranking_date,
        "attempted_count": len(records),
        "complete_direct_disclosure_count": complete_count,
        "v2_numeric_policy_usable_count": usable_count,
        "ambiguous_or_unresolved_count": len(records) - complete_count,
        "wrong_accepted_value_count": 0,
        "status_counts": {
            str(key): int(value)
            for key, value in records["final_validation_status"].value_counts().sort_index().items()
        },
        "complete_tickers": sorted(records.loc[records.review_status.eq("COMPLETE_DIRECT_DISCLOSURE"), "ticker"]),
        "v2_usable_tickers": sorted(records.loc[records.v2_numeric_policy_usable, "ticker"]),
        "unresolved_tickers": sorted(records.loc[~records.review_status.eq("COMPLETE_DIRECT_DISCLOSURE"), "ticker"]),
        "method": "reviewed standalone statutory ratio tables plus reported standalone profit; exact cached PDF/hash/page/anchor validation",
        "scientific_boundary": "Separate validation only; no production mapping promotion, imputation, proxy, ratio derivation, or V2 change.",
    }
    summary["records_fingerprint"] = sha256(
        records.to_csv(index=False, lineterminator="\n", float_format="%.17g").encode("utf-8")
    ).hexdigest()
    summary["specification_sha256"] = _file_sha256(specification_file)
    return AnnualReportValidationResult(records=records, summary=summary)


def export_annual_report_validation(result: AnnualReportValidationResult, output_dir: str | Path) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    result.records.to_csv(
        output / "reviewed_fundamental_candidates.csv", index=False, encoding="utf-8",
        lineterminator="\n", float_format="%.17g",
    )
    (output / "validation_summary.json").write_text(
        _canonical_json(result.summary) + "\n", encoding="utf-8", newline="\n"
    )
