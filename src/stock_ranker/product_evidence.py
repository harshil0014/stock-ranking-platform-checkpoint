"""Presentation and document indexing from accepted evidence only."""

from __future__ import annotations

import math
from typing import Any
from urllib.parse import urlsplit

import pandas as pd


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {"", "nan", "none", "null"}
    try:
        return bool(pd.notna(value)) and (not isinstance(value, float) or math.isfinite(value))
    except (TypeError, ValueError):
        return False


def official_document_index(documents: pd.DataFrame, financials: pd.DataFrame,
                            holdings: pd.DataFrame) -> pd.DataFrame:
    """Expose original filing links already pinned in accepted normalized facts.

    Existing document records retain precedence. Newly indexed records require
    exact ISIN, source hash, official URL and a parseable availability time.
    """
    from stock_ranker.exchange_backbone import DOCUMENT_COLUMNS

    known = set(documents["isin"].dropna()) if "isin" in documents else set()
    additions = []
    for frame, kind in ((financials, "FINANCIAL_RESULTS_XBRL"), (holdings, "SHAREHOLDING")):
        if frame.empty:
            continue
        for raw in frame.drop_duplicates(["isin", "source_url", "available_at"]).to_dict("records"):
            if raw.get("isin") in known:
                continue
            url = str(raw.get("source_url") or "")
            parsed = urlsplit(url)
            host = (parsed.hostname or "").lower()
            digest = str(raw.get("source_sha256") or "")
            if (parsed.scheme != "https" or not any(host == d or host.endswith("." + d)
                    for d in ("nseindia.com", "bseindia.com"))
                    or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
                    or not present(raw.get("isin"))
                    or pd.isna(pd.to_datetime(raw.get("available_at"), errors="coerce", utc=True))):
                continue
            additions.append({**{key: raw.get(key) for key in DOCUMENT_COLUMNS},
                              "document_type": kind, "subject": "Accepted official filing",
                              "reporting_period": raw.get("period_end", raw.get("as_of_date"))})
    extra = pd.DataFrame(additions, columns=DOCUMENT_COLUMNS)
    return pd.concat([documents, extra], ignore_index=True).drop_duplicates(
        ["isin", "source_url", "available_at"], keep="first")


def field_display_state(name: str, value: Any, fact: dict[str, Any]) -> dict[str, str]:
    """Describe missing evidence without asserting an unverified cause."""
    if present(value):
        return {"state": "VALUE_AVAILABLE", "reason": "Accepted source value available."}
    if name in {"latest_price", "open", "high", "low", "volume", "previous_close"}:
        return {"state": "ACCEPTED_EVIDENCE_NOT_FOUND",
                "reason": f"No accepted {name.replace('_', ' ')} for snapshot {fact.get('trade_date', '')}."}
    if name.startswith("history_") or name in {"high_52w", "low_52w", "recorded_high", "recorded_high_date"}:
        reason = fact.get("history_reason")
        status = str(fact.get("corporate_action_history_status", ""))
        return {"state": "CORPORATE_ACTION_UNRESOLVED" if "UNRESOLVED" in status else "ACCEPTED_EVIDENCE_NOT_FOUND",
                "reason": str(reason) if present(reason) else "No accepted price-history evidence for this field."}
    if "document" in name or name.endswith("_url") or name.startswith("annual_report_"):
        reason = "No accepted source document for this field."
    elif "holding" in name or "pledge" in name:
        reason = "No accepted ownership disclosure for this field."
    elif "industry" in name or "sector" in name:
        reason = "No accepted classification at this taxonomy level."
    else:
        reason = "No accepted value for this field and reporting basis."
    return {"state": "ACCEPTED_EVIDENCE_NOT_FOUND", "reason": reason}


def enrich_presentation(sections: dict[str, Any], fact: dict[str, Any]) -> None:
    """Attach field states and a factual identity profile; never mutate numbers."""
    profile = sections.get("company_profile_secondary_reference")
    if profile is not None:
        identity = {key: fact.get(key) for key in ("company", "isin", "primary_exchange", "listing_date",
                    "product_sector", "product_industry", "trade_date") if present(fact.get(key))}
        profile["structured_identity"] = identity
        if all(key in identity for key in ("company", "isin", "primary_exchange")):
            profile["status"] = "STRUCTURED_IDENTITY_PROFILE_AVAILABLE"
            profile["reason"] = "Company identity from the accepted snapshot. Provider description is optional."
            profile["values"] = {**identity, **profile.get("values", {})}
    for section in sections.values():
        if not isinstance(section, dict) or "values" not in section:
            continue
        section["field_states"] = {key: field_display_state(key, value, fact)
                                   for key, value in section["values"].items()}
