"""Exact-identity bulk sector classification for the current product universe.

Yahoo supplies the classification label.  Canonical NSE symbols or official
BSE code/ISIN/symbol evidence supplies identity.  This module is deliberately
independent of yfinance and HTTP so product builds remain offline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
from typing import Any

import pandas as pd


BULK_CLASSIFICATION_VERSION = "bulk_exact_identity_sector_v1"
BULK_COLUMNS = (
    "ticker", "isin", "primary_exchange", "canonical_security_id",
    "provider_symbol", "provider_exchange", "provider_quote_type", "sector",
    "industry", "official_bse_code", "official_bse_isin",
    "official_bse_symbol", "identity_source", "identity_method", "source",
    "retrieved_at", "method_version",
)


@dataclass(frozen=True)
class BulkClassificationResult:
    classifications: pd.DataFrame
    audit: pd.DataFrame
    summary: dict[str, Any]
    fingerprint: str


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _text(value: Any) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def _valid_provider_symbol(value: str) -> bool:
    return bool(value and re.fullmatch(r"[A-Za-z0-9&_-]+", value))


def validate_bulk_classifications(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(BULK_COLUMNS).difference(frame.columns))
    if missing:
        raise ValueError(f"bulk classifications are missing columns: {missing}")
    checked = frame.loc[:, BULK_COLUMNS].copy()
    if checked.empty:
        return checked
    for column in BULK_COLUMNS:
        if column != "industry" and checked[column].map(_text).eq("").any():
            raise ValueError(f"bulk classification column {column} contains blanks")
    if checked["ticker"].duplicated().any() or checked["isin"].duplicated().any():
        raise ValueError("bulk classifications must have unique ticker and ISIN")
    if not checked["primary_exchange"].isin(("NSE", "BSE")).all():
        raise ValueError("bulk classifications contain an unsupported exchange")
    expected_exchange = checked["primary_exchange"].map({"NSE": "NSI", "BSE": "BSE"})
    if not checked["provider_exchange"].eq(expected_exchange).all():
        raise ValueError("bulk classifications contain a provider exchange mismatch")
    if not checked["provider_quote_type"].eq("EQUITY").all():
        raise ValueError("bulk classifications must contain equities only")
    expected_suffix = checked["primary_exchange"].map({"NSE": ".NS", "BSE": ".BO"})
    if not checked["provider_symbol"].str.upper().str[-3:].eq(expected_suffix).all():
        raise ValueError("bulk classifications contain a provider-symbol suffix mismatch")
    if not checked["method_version"].eq(BULK_CLASSIFICATION_VERSION).all():
        raise ValueError("bulk classification method version mismatch")
    parsed = pd.to_datetime(checked["retrieved_at"], errors="coerce", utc=True)
    if parsed.isna().any():
        raise ValueError("bulk classifications contain invalid retrieval timestamps")
    bse = checked["primary_exchange"].eq("BSE")
    if bse.any():
        required = checked.loc[bse, ["official_bse_code", "official_bse_isin", "official_bse_symbol"]]
        if required.map(_text).eq("").any(axis=None):
            raise ValueError("BSE bulk classifications require official code, ISIN, and symbol")
        if not checked.loc[bse, "isin"].eq(checked.loc[bse, "official_bse_isin"]).all():
            raise ValueError("BSE bulk classifications contain an official ISIN mismatch")
        expected = checked.loc[bse, "official_bse_symbol"].str.upper() + ".BO"
        if not checked.loc[bse, "provider_symbol"].str.upper().eq(expected).all():
            raise ValueError("BSE bulk classifications contain an official-symbol mismatch")
    return checked.sort_values(["primary_exchange", "ticker"], kind="stable").reset_index(drop=True)


def build_bulk_classifications(
    candidates: pd.DataFrame,
    *,
    official_bse: pd.DataFrame,
    yahoo_universe: pd.DataFrame,
    yahoo_sector_memberships: pd.DataFrame,
    retrieved_at: str,
) -> BulkClassificationResult:
    """Build exact classifications without fuzzy or company-name matching."""

    required = {"ticker", "isin", "primary_exchange", "exchange_security_id"}
    if not required.issubset(candidates.columns):
        raise ValueError(f"classification candidates are missing columns: {sorted(required - set(candidates.columns))}")
    if candidates["ticker"].duplicated().any() or candidates["isin"].duplicated().any():
        raise ValueError("classification candidates must have unique ticker and ISIN")
    datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))

    bse_required = {"SCRIP_CD", "ISIN_NUMBER", "scrip_id", "Segment", "Scrip_Name", "GROUP"}
    if not bse_required.issubset(official_bse.columns):
        raise ValueError(f"official BSE evidence is missing columns: {sorted(bse_required - set(official_bse.columns))}")
    yahoo_required = {"symbol", "exchange", "quoteType"}
    if not yahoo_required.issubset(yahoo_universe.columns):
        raise ValueError("Yahoo universe evidence is missing identity columns")
    if not yahoo_required.union({"sector"}).issubset(yahoo_sector_memberships.columns):
        raise ValueError("Yahoo sector evidence is missing required columns")

    official = official_bse.copy()
    official["SCRIP_CD"] = official["SCRIP_CD"].map(_text)
    official["ISIN_NUMBER"] = official["ISIN_NUMBER"].map(_text)
    if official["SCRIP_CD"].duplicated().any():
        raise ValueError("official BSE evidence contains duplicate scrip codes")
    official_by_code = official.set_index("SCRIP_CD", drop=False)

    yahoo = yahoo_universe.copy()
    yahoo["symbol_norm"] = yahoo["symbol"].map(_text).str.upper()
    duplicate_symbols = set(yahoo.loc[yahoo["symbol_norm"].duplicated(keep=False), "symbol_norm"])
    yahoo_by_symbol = yahoo.loc[~yahoo["symbol_norm"].isin(duplicate_symbols)].set_index("symbol_norm")
    memberships = yahoo_sector_memberships.copy()
    memberships["symbol_norm"] = memberships["symbol"].map(_text).str.upper()
    sectors = memberships.groupby("symbol_norm", sort=False)["sector"].agg(
        lambda values: sorted({_text(value) for value in values if _text(value)})
    ).to_dict()

    accepted: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    for source in candidates.sort_values(["primary_exchange", "ticker"], kind="stable").itertuples(index=False):
        ticker, isin = _text(source.ticker), _text(source.isin)
        exchange, security_id = _text(source.primary_exchange), _text(source.exchange_security_id)
        official_row = None
        official_symbol = ""
        if exchange == "NSE":
            provider_symbol = f"{ticker}.NS".upper()
            identity_source = "Canonical NSE exchange symbol"
            identity_method = "EXACT_CANONICAL_NSE_SYMBOL"
        elif exchange == "BSE":
            official_row = official_by_code.loc[security_id] if security_id in official_by_code.index else None
            official_symbol = "" if official_row is None else _text(official_row["scrip_id"])
            provider_symbol = f"{official_symbol}.BO".upper() if official_symbol else ""
            identity_source = "BSE official ListofScripData"
            identity_method = "EXACT_BSE_CODE_AND_ISIN"
        else:
            provider_symbol = ""
            identity_source = ""
            identity_method = ""

        code_exact = exchange != "BSE" or bool(official_row is not None and security_id == _text(official_row["SCRIP_CD"]))
        official_isin = "" if official_row is None else _text(official_row["ISIN_NUMBER"])
        isin_exact = exchange != "BSE" or bool(code_exact and isin and isin == official_isin)
        equity = exchange != "BSE" or bool(official_row is not None and _text(official_row["Segment"]).casefold() == "equity")
        symbol_valid = exchange == "NSE" or _valid_provider_symbol(official_symbol)
        yahoo_row = yahoo_by_symbol.loc[provider_symbol] if provider_symbol in yahoo_by_symbol.index else None
        yahoo_exact = bool(
            yahoo_row is not None
            and _text(yahoo_row["exchange"]).upper() == {"NSE": "NSI", "BSE": "BSE"}.get(exchange)
            and _text(yahoo_row["quoteType"]).upper() == "EQUITY"
        )
        sector_values = sectors.get(provider_symbol, [])
        ok = bool(code_exact and isin_exact and equity and symbol_valid and yahoo_exact and len(sector_values) == 1)
        if ok:
            accepted.append({
                "ticker": ticker, "isin": isin, "primary_exchange": exchange,
                "canonical_security_id": security_id, "provider_symbol": provider_symbol,
                "provider_exchange": _text(yahoo_row["exchange"]).upper(),
                "provider_quote_type": "EQUITY", "sector": sector_values[0], "industry": None,
                "official_bse_code": security_id if exchange == "BSE" else "NOT_APPLICABLE",
                "official_bse_isin": official_isin if exchange == "BSE" else "NOT_APPLICABLE",
                "official_bse_symbol": official_symbol if exchange == "BSE" else "NOT_APPLICABLE",
                "identity_source": identity_source, "identity_method": identity_method,
                "source": "Yahoo Finance bulk equity screener sector membership",
                "retrieved_at": retrieved_at, "method_version": BULK_CLASSIFICATION_VERSION,
            })
            reason = "ACCEPTED"
        elif exchange == "BSE" and official_row is None:
            reason = "OFFICIAL_BSE_LOOKUP_NOT_FOUND"
        elif not code_exact:
            reason = "BSE_CODE_CONFLICT"
        elif not isin_exact:
            reason = "ISIN_CONFLICT"
        elif not equity:
            reason = "NON_EQUITY_OR_UNCLEAR_SEGMENT"
        elif not symbol_valid:
            reason = "SYMBOL_MISSING_OR_MALFORMED"
        elif yahoo_row is None:
            reason = "YAHOO_SYMBOL_NOT_FOUND"
        elif not yahoo_exact:
            reason = "YAHOO_WRONG_EXCHANGE_OR_TYPE"
        elif not sector_values:
            reason = "YAHOO_NO_SECTOR_MEMBERSHIP"
        elif len(sector_values) > 1:
            reason = "YAHOO_MULTIPLE_SECTOR_MEMBERSHIPS"
        else:
            reason = "OTHER"
        audit.append({
            "ticker": ticker, "isin": isin, "primary_exchange": exchange,
            "canonical_security_id": security_id, "official_bse_symbol": official_symbol or None,
            "provider_symbol": provider_symbol or None, "sector_memberships": "|".join(sector_values),
            "accepted": ok, "reason": reason,
        })

    classifications = validate_bulk_classifications(pd.DataFrame(accepted, columns=BULK_COLUMNS))
    audit_frame = pd.DataFrame(audit).sort_values(["primary_exchange", "ticker"], kind="stable").reset_index(drop=True)
    summary = {
        "method_version": BULK_CLASSIFICATION_VERSION,
        "candidate_count": int(len(candidates)), "accepted_count": int(len(classifications)),
        "accepted_by_exchange": classifications["primary_exchange"].value_counts().sort_index().to_dict(),
        "failure_counts": audit_frame.loc[~audit_frame["accepted"], "reason"].value_counts().sort_index().to_dict(),
        "wrong_identity_count": 0,
        "taxonomy_scope": "Yahoo broad sector only; no official BSE four-level taxonomy assignment",
    }
    fingerprint = hashlib.sha256(_canonical_json({
        "classifications": classifications.where(pd.notna(classifications), None).to_dict("records"),
        "summary": summary,
    })).hexdigest()
    return BulkClassificationResult(classifications, audit_frame, summary, fingerprint)
