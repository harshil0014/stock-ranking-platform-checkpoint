"""Build deterministic review packets without accepting accounting values."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd


_NUMBER = re.compile(r"(?<![A-Za-z0-9])(?:\(?-?\d[\d,]*(?:\.\d+)?\)?%?)(?![A-Za-z0-9])")


def _load_unique(path: Path, label: str) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{label} must be a list")
    result: dict[str, dict[str, Any]] = {}
    for item in payload:
        ticker = str(item.get("ticker", ""))
        if not ticker or ticker in result:
            raise ValueError(f"{label} contains blank or duplicate ticker")
        result[ticker] = item
    return result


def build_annual_report_review_packets(
    cohort: pd.DataFrame, acquisition_root: str | Path, audit_root: str | Path,
) -> tuple[pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    """Create a page-level evidence queue; never produce accepted V2 values."""

    required = {"ticker", "company", "isin", "sector"}
    missing = sorted(required.difference(cohort.columns))
    if missing:
        raise ValueError(f"cohort missing columns: {', '.join(missing)}")
    if cohort["ticker"].duplicated().any() or cohort["isin"].duplicated().any():
        raise ValueError("review cohort requires unique ticker and ISIN")
    acquisition = Path(acquisition_root)
    audit = Path(audit_root)
    provenance = _load_unique(acquisition / "annual_report_provenance.json", "provenance")
    audits = _load_unique(audit / "candidate_audit.json", "candidate audit")
    matrix: list[dict[str, Any]] = []
    packets: list[dict[str, Any]] = []
    for identity in cohort.sort_values("ticker", kind="mergesort").to_dict("records"):
        ticker = str(identity["ticker"])
        source = provenance.get(ticker, {})
        audited = audits.get(ticker, {})
        text_path = audit / str(audited.get("text_path", ""))
        exact_isin = False
        if audited.get("audit_status") == "EXTRACTED" and text_path.is_file():
            exact_isin = str(identity["isin"]) in re.sub(
                r"\s+", "", text_path.read_text(encoding="utf-8", errors="strict")
            )
        candidate_pages = audited.get("candidate_pages") or []
        candidate_fields = {
            "roce": [page for page in candidate_pages if page.get("roce")],
            "debt_to_equity": [page for page in candidate_pages if page.get("debt_to_equity")],
            "profit": [page for page in candidate_pages if page.get("profit")],
        }
        complete_locator = exact_isin and all(candidate_fields.values())
        if complete_locator:
            status = "REVIEW_PACKET_COMPLETE"
        elif source.get("selection_status") != "SELECTED":
            status = str(source.get("selection_status") or "NO_ELIGIBLE_ANNUAL_REPORT")
        elif audited.get("audit_status") != "EXTRACTED":
            status = str(audited.get("audit_status") or "PDF_EXTRACTION_FAILED")
        elif not exact_isin:
            status = "ISIN_NOT_PROVEN_IN_REPORT_TEXT"
        else:
            absent = [name.upper() for name, pages in candidate_fields.items() if not pages]
            status = "MISSING_DIRECT_" + "_AND_".join(absent)
        matrix.append({
            **identity,
            "packet_status": status,
            "pdf_extracted": audited.get("audit_status") == "EXTRACTED",
            "exact_isin_in_document": exact_isin,
            "roce_candidate_pages": len(candidate_fields["roce"]),
            "debt_equity_candidate_pages": len(candidate_fields["debt_to_equity"]),
            "profit_candidate_pages": len(candidate_fields["profit"]),
            "source_url": source.get("source_url"),
            "pdf_sha256": source.get("pdf_sha256"),
            "exchange_dissemination_timestamp": (source.get("selected_metadata") or {}).get("disseminationDateTime"),
            "acceptance_status": "NOT_ACCEPTED_REQUIRES_ACCOUNTING_REVIEW",
        })
        if complete_locator:
            evidence: dict[str, Any] = {}
            for field, pages in candidate_fields.items():
                evidence[field] = [{
                    "page": page["page"],
                    "snippets": page[field],
                    "numeric_tokens_untrusted_locator_only": sorted({
                        token for snippet in page[field] for token in _NUMBER.findall(snippet)
                    }),
                    "formula_language": bool(page.get("formula_language")),
                } for page in pages]
            packets.append({
                "ticker": ticker, "company": identity["company"], "isin": identity["isin"],
                "sector": identity["sector"], "source_url": source.get("source_url"),
                "pdf_sha256": source.get("pdf_sha256"), "text_sha256": audited.get("text_sha256"),
                "exchange_dissemination_timestamp": (source.get("selected_metadata") or {}).get("disseminationDateTime"),
                "evidence": evidence,
                "scientific_boundary": "Numbers are search aids only. A reviewer must verify table, basis, units, periods, formula, and current/prior profit before acceptance.",
            })
    result = pd.DataFrame(matrix).sort_values("ticker", kind="mergesort").reset_index(drop=True)
    summary = {
        "schema_version": "pit_annual_report_review_packets_v1",
        "attempted_count": len(result),
        "extracted_count": int(result["pdf_extracted"].sum()),
        "exact_isin_count": int(result["exact_isin_in_document"].sum()),
        "complete_review_packet_count": len(packets),
        "accepted_record_count": 0,
        "automatic_promotion_permitted": False,
    }
    summary["packet_fingerprint"] = sha256(
        json.dumps(packets, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return result, packets, summary
