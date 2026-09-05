"""Exact-ISIN BSE announcement fallback discovery for annual reports."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


_ANNUAL_REPORT = re.compile(r"\bannual\s+report\b|reg(?:ulation)?\.?\s*34\s*\(?1\)?", re.I)
_REGULATION_34 = re.compile(r"reg(?:ulation)?\.?\s*34\s*\(?1\)?", re.I)


def exact_bse_identity_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    ambiguous: set[str] = set()
    for row in rows:
        isin = str(row.get("ISIN_NUMBER") or "").strip()
        code = str(row.get("SCRIP_CD") or "").strip()
        if not re.fullmatch(r"INE[A-Z0-9]{9}", isin) or not re.fullmatch(r"\d{6}", code):
            continue
        normalized = {
            "bse_scrip_code": code, "bse_symbol": str(row.get("scrip_id") or "").strip(),
            "bse_company": str(row.get("Issuer_Name") or row.get("Scrip_Name") or "").strip(),
        }
        if isin in result and result[isin] != normalized:
            ambiguous.add(isin)
        else:
            result[isin] = normalized
    for isin in ambiguous:
        result.pop(isin, None)
    return result


def select_bse_annual_report_announcement(
    rows: list[dict[str, Any]], *, scrip_code: str, cutoff: str,
) -> tuple[dict[str, Any] | None, str]:
    cutoff_timestamp = pd.Timestamp(cutoff)
    candidates = []
    for row in rows:
        if str(row.get("SCRIP_CD") or "").strip() != scrip_code:
            continue
        text = " ".join(str(row.get(key) or "") for key in ("NEWSSUB", "HEADLINE", "SUBCATNAME"))
        attachment = str(row.get("ATTACHMENTNAME") or "").strip()
        timestamp = pd.to_datetime(row.get("DissemDT"), errors="coerce")
        if _ANNUAL_REPORT.search(text) and attachment.lower().endswith(".pdf") and not pd.isna(timestamp):
            if timestamp <= cutoff_timestamp:
                candidates.append((timestamp, bool(_REGULATION_34.search(text)), row))
    if not candidates:
        return None, "NO_EXACT_BSE_ANNUAL_REPORT_ANNOUNCEMENT"
    selected = max(candidates, key=lambda item: (item[0], str(item[2].get("NEWSID") or "")))
    status = (
        "SELECTED_BSE_EXACT_REGULATION_34_CANDIDATE" if selected[1]
        else "BSE_ANNUAL_REPORT_MENTION_REQUIRES_ATTACHMENT_REVIEW"
    )
    return selected[2], status
