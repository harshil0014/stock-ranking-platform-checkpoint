"""Official-exchange evidence contracts for the self-completing fact layer.

The module deliberately contains no network client.  Acquisition runners land
immutable NSE/BSE responses, while these pure functions validate, normalize,
supersede and expose evidence to the product.  This keeps product imports
offline and makes every provider response reproducible in tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable
import xml.etree.ElementTree as ET

import pandas as pd


BACKBONE_VERSION = "official_exchange_backbone_v1"
CLASSIFICATION_AUDIT_VERSION = "derived_classification_audit_v1"
NORMALIZED_FACT_VERSION = "normalized_exchange_fact_v1"

CLASSIFICATION_STATES = {
    "OFFICIAL",
    "DERIVED_PRIMARY_EVIDENCE",
    "DERIVED_SECONDARY_REFERENCE_ONLY",
    "UNCLASSIFIED",
}

FINANCIAL_COLUMNS = (
    "ticker", "isin", "exchange", "accounting_family", "statement_basis",
    "period_type", "period_start", "period_end", "available_at", "revision_at",
    "revision_status", "filing_id", "canonical_concept", "source_concept",
    "value", "unit", "context_id", "source_url", "source_sha256",
)
SHAREHOLDING_COLUMNS = (
    "ticker", "isin", "exchange", "as_of_date", "available_at", "revision_at",
    "revision_status", "filing_id", "promoter_pct", "public_pct",
    "employee_trust_pct", "fii_pct", "dii_pct", "institutional_pct",
    "promoter_pledge_pct", "total_shares", "source_url", "source_sha256",
)
ACTION_COLUMNS = (
    "ticker", "isin", "exchange", "action_type", "subject", "ex_date",
    "record_date", "book_closure_start", "book_closure_end", "face_value",
    "available_at", "source_url", "source_sha256",
)
DOCUMENT_COLUMNS = (
    "ticker", "isin", "exchange", "document_type", "subject", "available_at",
    "reporting_period", "filing_id", "source_url", "source_sha256",
)
BACKLOG_COLUMNS = (
    "ticker", "isin", "provider_symbol", "priority", "attempt_count",
    "last_attempt", "next_eligible_attempt", "error_class", "retry_after",
    "completion_status",
)


@dataclass(frozen=True, slots=True)
class OfficialBackboneBundle:
    path: Path
    financial_facts: pd.DataFrame
    shareholding: pd.DataFrame
    corporate_actions: pd.DataFrame
    documents: pd.DataFrame
    classification_audit: pd.DataFrame
    manifest: dict[str, Any]
    fingerprint: str


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256_file(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    result = str(value).strip()
    return result or None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool) or pd.isna(value):
        return None
    try:
        result = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _date(value: Any) -> str | None:
    text = _text(value)
    if not text or text in {"-", "NA", "N.A."}:
        return None
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=not bool(re.match(r"\d{4}-\d{2}-\d{2}", text)))
    return None if pd.isna(parsed) else parsed.date().isoformat()


def _timestamp(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=not bool(re.match(r"\d{4}-\d{2}-\d{2}", text)))
    if pd.isna(parsed):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize("Asia/Kolkata")
    return parsed.tz_convert("UTC").isoformat()


def validate_columns(frame: pd.DataFrame, columns: Iterable[str], name: str) -> pd.DataFrame:
    expected = tuple(columns)
    missing = [column for column in expected if column not in frame]
    if missing:
        raise ValueError(f"{name} is missing columns: {missing}")
    return frame.loc[:, expected].copy()


def normalize_nse_shareholding(rows: list[dict[str, Any]], *, source_sha256: str) -> pd.DataFrame:
    """Normalize the bulk NSE Regulation 31 catalogue.

    The catalogue itself contains authoritative promoter/public totals.  More
    granular institutional and pledge values remain blank until the linked
    XBRL has actually been parsed; they are never inferred.
    """

    output: list[dict[str, Any]] = []
    for row in rows:
        ticker = _text(row.get("symbol"))
        isin = _text(row.get("isin"))
        as_of = _date(row.get("date"))
        if not ticker or not isin or not as_of:
            continue
        output.append({
            "ticker": ticker, "isin": isin, "exchange": "NSE",
            "as_of_date": as_of,
            "available_at": _timestamp(row.get("broadcastDate") or row.get("submissionDate")),
            "revision_at": _timestamp(row.get("revisionDate") or row.get("revisedDate")),
            "revision_status": "REVISED" if str(row.get("revisedData", "N")).upper() == "Y" else "ORIGINAL",
            "filing_id": _text(row.get("recordId")),
            "promoter_pct": _number(row.get("pr_and_prgrp")),
            "public_pct": _number(row.get("public_val")),
            "employee_trust_pct": _number(row.get("employeeTrusts")),
            "fii_pct": None, "dii_pct": None, "institutional_pct": None,
            "promoter_pledge_pct": None, "total_shares": None,
            "source_url": _text(row.get("xbrl")), "source_sha256": source_sha256,
        })
    frame = pd.DataFrame(output, columns=SHAREHOLDING_COLUMNS)
    return select_latest_revisions(frame, key=("ticker", "as_of_date"))


def normalize_oss_shareholding(frame: pd.DataFrame, market: pd.DataFrame, *,
                               source_url: str, source_sha256: str) -> pd.DataFrame:
    """Normalize CC-BY facts parsed from official NSE SHP XBRLs.

    Identity is rejoined against the accepted NSE security master.  Rows that
    cannot be reconciled exactly are excluded instead of name-matched.
    """

    required = {"ticker", "period", "promoter_pct", "fii_pct", "dii_pct",
                "public_pct", "total_shares", "source_filename"}
    if not required.issubset(frame.columns):
        raise ValueError("NSE shareholding history is missing required columns")
    identity = market.loc[market["primary_exchange"].eq("NSE"), ["ticker", "isin"]].copy()
    identity["ticker"] = identity["ticker"].astype(str).str.upper()
    joined = frame.copy()
    joined["ticker"] = joined["ticker"].astype(str).str.upper()
    joined = joined.merge(identity, on="ticker", how="inner", validate="many_to_one")
    rows = []
    for item in joined.itertuples(index=False):
        period = _text(item.period)
        if not period or not re.fullmatch(r"\d{4}-\d{2}", period):
            continue
        as_of = (pd.Timestamp(period + "-01") + pd.offsets.MonthEnd(0)).date().isoformat()
        rows.append({
            "ticker": item.ticker, "isin": item.isin, "exchange": "NSE",
            "as_of_date": as_of,
            "available_at": _timestamp(getattr(item, "submission_date", None)),
            "revision_at": None, "revision_status": "DERIVED_FROM_OFFICIAL_XBRL",
            "filing_id": _text(item.source_filename),
            "promoter_pct": _number(item.promoter_pct), "public_pct": _number(item.public_pct),
            "employee_trust_pct": None, "fii_pct": _number(item.fii_pct),
            "dii_pct": _number(item.dii_pct), "institutional_pct": None,
            "promoter_pledge_pct": _number(getattr(item, "pledge_pct", None)),
            "total_shares": _number(item.total_shares),
            "source_url": source_url.rstrip("/") + "/shareholding_history/data/xbrl/" + str(item.source_filename),
            "source_sha256": source_sha256,
        })
    return pd.DataFrame(rows, columns=SHAREHOLDING_COLUMNS)


def _action_type(subject: str) -> str:
    value = subject.lower()
    rules = (
        ("DIVIDEND", ("dividend",)), ("SPLIT", ("split", "sub-division", "subdivision")),
        ("BONUS", ("bonus",)), ("RIGHTS", ("rights",)),
        ("MERGER", ("merger", "amalgamation")), ("DEMERGER", ("demerger", "de-merger")),
        ("NAME_CHANGE", ("name change",)), ("ISIN_CHANGE", ("isin change",)),
        ("FACE_VALUE_CHANGE", ("face value",)),
    )
    return next((kind for kind, needles in rules if any(n in value for n in needles)), "OTHER")


def normalize_nse_actions(rows: list[dict[str, Any]], *, source_sha256: str) -> pd.DataFrame:
    output = []
    for row in rows:
        ticker, isin = _text(row.get("symbol")), _text(row.get("isin"))
        subject = _text(row.get("subject"))
        if not ticker or not isin or not subject:
            continue
        output.append({
            "ticker": ticker, "isin": isin, "exchange": "NSE",
            "action_type": _action_type(subject), "subject": subject,
            "ex_date": _date(row.get("exDate")), "record_date": _date(row.get("recDate")),
            "book_closure_start": _date(row.get("bcStartDate")),
            "book_closure_end": _date(row.get("bcEndDate")),
            "face_value": _number(row.get("faceVal")),
            "available_at": _timestamp(row.get("caBroadcastDate")),
            "source_url": "https://www.nseindia.com/companies-listing/corporate-filings-actions",
            "source_sha256": source_sha256,
        })
    result = pd.DataFrame(output, columns=ACTION_COLUMNS)
    return result.drop_duplicates(["ticker", "action_type", "subject", "ex_date", "record_date"]).sort_values(
        ["ticker", "ex_date", "action_type"], kind="stable", na_position="last"
    ).reset_index(drop=True)


def normalize_bse_actions(rows: list[dict[str, Any]], market: pd.DataFrame, *, source_sha256: str) -> pd.DataFrame:
    ids = market.loc[market["exchange_security_id"].notna(), ["exchange_security_id", "ticker", "isin"]].copy()
    ids["exchange_security_id"] = ids["exchange_security_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    by_id = {row.exchange_security_id: row for row in ids.itertuples(index=False)}
    output = []
    for row in rows:
        code = str(row.get("scrip_code", "")).replace(".0", "")
        identity = by_id.get(code)
        if identity is None:
            continue
        subject = _text(row.get("Purpose")) or "Other corporate action"
        output.append({
            "ticker": identity.ticker, "isin": identity.isin, "exchange": "BSE",
            "action_type": _action_type(subject), "subject": subject,
            "ex_date": _date(row.get("Ex_date")), "record_date": _date(row.get("RD_Date")),
            "book_closure_start": _date(row.get("BCRD_FROM")),
            "book_closure_end": _date(row.get("BCRD_TO")), "face_value": None,
            "available_at": None,
            "source_url": "https://www.bseindia.com/corporates/corporate_act.aspx",
            "source_sha256": source_sha256,
        })
    return pd.DataFrame(output, columns=ACTION_COLUMNS)


def normalize_nse_documents(rows: list[dict[str, Any]], *, source_sha256: str) -> pd.DataFrame:
    output = []
    for row in rows:
        ticker, isin = _text(row.get("symbol")), _text(row.get("sm_isin"))
        url = _text(row.get("attchmntFile"))
        if not ticker or not isin or not url:
            continue
        subject = " ".join(filter(None, (_text(row.get("desc")), _text(row.get("attchmntText")))))
        lowered = subject.lower()
        if "annual report" in lowered:
            kind = "ANNUAL_REPORT"
        elif "financial result" in lowered or "results" in lowered:
            kind = "FINANCIAL_RESULT"
        elif "brsr" in lowered or "business responsibility" in lowered:
            kind = "BRSR"
        elif "shareholding" in lowered:
            kind = "SHAREHOLDING"
        else:
            kind = "ANNOUNCEMENT"
        output.append({
            "ticker": ticker, "isin": isin, "exchange": "NSE", "document_type": kind,
            "subject": subject, "available_at": _timestamp(row.get("an_dt") or row.get("sort_date")),
            "reporting_period": None, "filing_id": _text(row.get("seq_id")),
            "source_url": url, "source_sha256": source_sha256,
        })
    return pd.DataFrame(output, columns=DOCUMENT_COLUMNS).drop_duplicates(
        ["ticker", "filing_id", "source_url"]
    ).sort_values(["ticker", "available_at", "filing_id"], kind="stable").reset_index(drop=True)


def select_latest_revisions(frame: pd.DataFrame, *, key: tuple[str, ...]) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    result = frame.copy()
    result["_revision_sort"] = pd.to_datetime(result.get("revision_at"), errors="coerce", utc=True)
    result["_available_sort"] = pd.to_datetime(result.get("available_at"), errors="coerce", utc=True)
    result = result.sort_values([*key, "_revision_sort", "_available_sort", "filing_id"],
                                kind="stable", na_position="first")
    return result.drop_duplicates(list(key), keep="last").drop(
        columns=["_revision_sort", "_available_sort"]
    ).reset_index(drop=True)


def audit_derived_classifications(facts: pd.DataFrame, *,
                                  segment_evidence: pd.DataFrame | None = None,
                                  business_evidence: pd.DataFrame | None = None) -> pd.DataFrame:
    """Audit every non-official classification without promoting references.

    Primary-evidence assignment is intentionally conservative: a supplied
    evidence row must explicitly name a reproducible NSE-methodology rule and
    carry an audited segment/business source URL.  Yahoo/Screener alone never
    satisfies that boundary.
    """

    segment = {} if segment_evidence is None else {
        str(row.isin): row for row in segment_evidence.itertuples(index=False)
    }
    business = {} if business_evidence is None else {
        str(row.isin): row for row in business_evidence.itertuples(index=False)
    }
    rows = []
    for row in facts.itertuples(index=False):
        official = _text(getattr(row, "official_sector", None))
        derived = _text(getattr(row, "derived_research_sector", None))
        evidence = segment.get(str(row.isin)) or business.get(str(row.isin))
        if official:
            status = "OFFICIAL"
            evidence_type = "OFFICIAL_EXCHANGE_OR_NSE_INDICES_TAXONOMY"
            derivation_rule = "DIRECT_OFFICIAL_CLASSIFICATION"
        elif evidence is not None and _text(getattr(evidence, "source_url", None)) and _text(getattr(evidence, "derivation_rule", None)):
            status = "DERIVED_PRIMARY_EVIDENCE"
            evidence_type = _text(getattr(evidence, "evidence_type", None)) or "AUDITED_BUSINESS_EVIDENCE"
            derivation_rule = _text(getattr(evidence, "derivation_rule", None))
        elif derived:
            status = "DERIVED_SECONDARY_REFERENCE_ONLY"
            evidence_type = "IDENTITY_VALIDATED_SECONDARY_PROVIDER_CLASSIFICATION"
            derivation_rule = "NO_RANKING_GRADE_DERIVATION; DISPLAY_REFERENCE_ONLY"
        else:
            status = "UNCLASSIFIED"
            evidence_type = "NONE"
            derivation_rule = "NONE"
        if status not in CLASSIFICATION_STATES:
            raise AssertionError(status)
        rows.append({
            "security": str(row.ticker), "isin": str(row.isin),
            "macro_economic_sector": _text(getattr(evidence, "macro_economic_sector", None)) if evidence else None,
            "sector": official or (derived if status != "UNCLASSIFIED" else None),
            "industry": _text(getattr(row, "official_industry", None)) or _text(getattr(row, "derived_research_industry", None)),
            "basic_industry": _text(getattr(row, "official_basic_industry", None)) or _text(getattr(row, "derived_research_basic_industry", None)),
            "sources": _text(getattr(row, "official_classification_source", None)) or _text(getattr(row, "secondary_source", None)),
            "evidence_type": evidence_type,
            "evidence_date": _text(getattr(evidence, "evidence_date", None)) if evidence else _text(getattr(row, "secondary_source_as_of", None)),
            "derivation_rule": derivation_rule,
            "segment_revenue_evidence_exists": bool(evidence is not None and "SEGMENT" in str(evidence_type).upper()),
            "annual_report_business_evidence_exists": bool(evidence is not None and "BUSINESS" in str(evidence_type).upper()),
            "yahoo_classification": " / ".join(filter(None, (_text(getattr(row, "secondary_sector", None)), _text(getattr(row, "secondary_industry", None))))) or None,
            "screener_cross_check": None,
            "official_taxonomy_match": official,
            "confidence_status": status,
            "ranking_grade": status in {"OFFICIAL", "DERIVED_PRIMARY_EVIDENCE"},
        })
    return pd.DataFrame(rows).sort_values(["confidence_status", "security"], kind="stable").reset_index(drop=True)


def initialize_backlog(candidates: pd.DataFrame, prior: pd.DataFrame | None = None) -> pd.DataFrame:
    required = {"ticker", "isin", "provider_symbol", "priority"}
    if not required.issubset(candidates.columns):
        raise ValueError("backlog candidates are missing required columns")
    previous = {} if prior is None or prior.empty else {
        str(row.isin): row for row in validate_columns(prior, BACKLOG_COLUMNS, "backlog").itertuples(index=False)
    }
    rows = []
    for row in candidates.sort_values(["priority", "ticker"], kind="stable").itertuples(index=False):
        old = previous.get(str(row.isin))
        rows.append({
            "ticker": str(row.ticker), "isin": str(row.isin),
            "provider_symbol": str(row.provider_symbol), "priority": int(row.priority),
            "attempt_count": int(getattr(old, "attempt_count", 0)),
            "last_attempt": getattr(old, "last_attempt", None),
            "next_eligible_attempt": getattr(old, "next_eligible_attempt", None),
            "error_class": getattr(old, "error_class", None),
            "retry_after": getattr(old, "retry_after", None),
            "completion_status": getattr(old, "completion_status", "PENDING"),
        })
    return pd.DataFrame(rows, columns=BACKLOG_COLUMNS)


def update_backlog(backlog: pd.DataFrame, ticker: str, *, status: str, error_class: str | None,
                   attempted_at: str, retry_after: str | None = None) -> pd.DataFrame:
    if status not in {"ACCEPTED", "TRANSIENT_FAILED", "PERMANENTLY_REJECTED"}:
        raise ValueError("invalid backlog status")
    result = validate_columns(backlog, BACKLOG_COLUMNS, "backlog")
    matched = result["ticker"].astype(str).eq(str(ticker))
    if matched.sum() != 1:
        raise ValueError("backlog ticker must identify exactly one row")
    result.loc[matched, "attempt_count"] = result.loc[matched, "attempt_count"].astype(int) + 1
    result.loc[matched, "last_attempt"] = attempted_at
    result.loc[matched, "error_class"] = error_class
    result.loc[matched, "retry_after"] = retry_after
    result.loc[matched, "next_eligible_attempt"] = retry_after
    result.loc[matched, "completion_status"] = status
    return result


def due_backlog(backlog: pd.DataFrame, *, now: str, limit: int) -> pd.DataFrame:
    if limit < 1:
        raise ValueError("backlog limit must be positive")
    frame = validate_columns(backlog, BACKLOG_COLUMNS, "backlog")
    due = pd.to_datetime(frame["next_eligible_attempt"], errors="coerce", utc=True)
    moment = pd.Timestamp(now)
    if moment.tzinfo is None:
        moment = moment.tz_localize("UTC")
    eligible = frame["completion_status"].isin(["PENDING", "TRANSIENT_FAILED"]) & (due.isna() | due.le(moment))
    return frame.loc[eligible].sort_values(["priority", "attempt_count", "ticker"], kind="stable").head(limit).reset_index(drop=True)


def load_official_backbone(directory: str | Path) -> OfficialBackboneBundle:
    root = Path(directory)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != BACKBONE_VERSION:
        raise ValueError("unsupported official backbone schema")
    artifacts = manifest.get("artifacts", {})
    for name, expected in artifacts.items():
        path = root / name
        if not path.is_file() or sha256_file(path) != expected:
            raise ValueError(f"official backbone artifact failed hash validation: {name}")
    read = lambda name, cols: validate_columns(pd.read_csv(root / name, low_memory=False), cols, name)
    financial = read("financial_facts.csv", FINANCIAL_COLUMNS)
    shareholding = read("shareholding.csv", SHAREHOLDING_COLUMNS)
    actions = read("corporate_actions.csv", ACTION_COLUMNS)
    documents = read("documents.csv", DOCUMENT_COLUMNS)
    audit = pd.read_csv(root / "classification_audit.csv", low_memory=False)
    payload = {key: value for key, value in manifest.items() if key != "fingerprint"}
    fingerprint = sha256(canonical_json_bytes(payload)).hexdigest()
    if fingerprint != manifest.get("fingerprint"):
        raise ValueError("official backbone manifest fingerprint mismatch")
    return OfficialBackboneBundle(root, financial, shareholding, actions, documents, audit, manifest, fingerprint)


def accounting_family(filename: str, concepts: Iterable[str] = ()) -> str:
    value = filename.upper()
    if any(token in value.replace("-", "_") for token in ("REIT", "INVIT")):
        return "REIT_INVIT"
    for family in ("NBFC_INDAS", "GENERAL_INSURANCE", "LIFE_INSURANCE", "BANKING", "INDAS"):
        if family in value.replace("-", "_"):
            return family
    joined = " ".join(concepts).upper()
    if any(token in joined for token in ("PREMIUM", "POLICYHOLDER", "INSURANCE")):
        return "INSURANCE"
    if any(token in joined for token in ("INTERESTEARNED", "DEPOSITS", "ADVANCES")):
        return "BANKING"
    return "INDAS"


CANONICAL_CONCEPTS = {
    "revenue": ("RevenueFromOperations", "Revenue", "InterestEarned", "GrossPremium"),
    "total_income": ("TotalIncome", "RevenueFromOperationsAndOtherIncome"),
    "finance_costs": ("FinanceCosts", "InterestExpense"),
    "depreciation": ("DepreciationDepletionAndAmortisationExpense", "DepreciationAndAmortisationExpense"),
    "pbt": ("ProfitBeforeTax", "ProfitLossBeforeTax"),
    "tax": ("TaxExpense", "TotalTaxExpense"),
    "pat": ("ProfitLossForPeriod", "ProfitLossForThePeriod", "ProfitForPeriod", "NetProfitLossForThePeriod"),
    "eps": ("BasicEarningsLossPerShare", "BasicEarningsPerShare",
            "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
            "BasicEarningsPerShareAfterExtraordinaryItems"),
    "equity_share_capital": ("EquityShareCapital", "PaidUpEquityShareCapital"),
    "assets": ("Assets", "TotalAssets"),
    "liabilities": ("Liabilities", "TotalLiabilities"),
    "equity": ("Equity", "TotalEquity", "NetWorth"),
    "borrowings": ("Borrowings", "TotalBorrowings", "DebtSecurities"),
    "debt_to_equity": ("DebtEquityRatio",),
    "cash": ("CashAndCashEquivalents", "CashAndBankBalances"),
    "operating_cash_flow": ("CashFlowsFromUsedInOperatingActivities", "NetCashFlowsFromUsedInOperatingActivities"),
    "investing_cash_flow": ("CashFlowsFromUsedInInvestingActivities", "NetCashFlowsFromUsedInInvestingActivities"),
    "financing_cash_flow": ("CashFlowsFromUsedInFinancingActivities", "NetCashFlowsFromUsedInFinancingActivities"),
}


def parse_exchange_xbrl(data: bytes, *, filename: str, metadata: dict[str, Any]) -> pd.DataFrame:
    """Taxonomy-tolerant fact extraction with raw concepts preserved.

    Recognised concepts are normalized; every numeric unknown is retained as
    ``unknown:<source concept>`` so future parser versions can revisit it.
    """

    if not data or len(data) > 25_000_000 or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("invalid or unsafe XBRL payload")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"malformed XBRL: {exc}") from exc
    local = lambda tag: tag.rsplit("}", 1)[-1]
    contexts: dict[str, dict[str, Any]] = {}
    for element in root.iter():
        if local(element.tag) != "context":
            continue
        cid = _text(element.get("id"))
        if not cid:
            continue
        values: dict[str, Any] = {"dimensions": []}
        for child in element.iter():
            name, text = local(child.tag), _text(child.text)
            if name in {"startDate", "endDate", "instant"}:
                values[name] = text
            elif name in {"explicitMember", "typedMember"}:
                values["dimensions"].append((_text(child.get("dimension")), text))
        contexts[cid] = values
    reverse = {source: canonical for canonical, names in CANONICAL_CONCEPTS.items() for source in names}
    detected_family = accounting_family(filename, (local(element.tag) for element in root.iter()))
    rows = []
    digest = sha256(data).hexdigest()
    for element in root.iter():
        cid = _text(element.get("contextRef"))
        concept = local(element.tag)
        if not cid or cid not in contexts:
            continue
        value = _number(element.text)
        if value is None:
            continue
        context = contexts[cid]
        period_end = context.get("endDate") or context.get("instant")
        if not period_end:
            continue
        start = context.get("startDate")
        if start:
            days = (pd.Timestamp(period_end) - pd.Timestamp(start)).days
            period_type = "ANNUAL" if 350 <= days <= 380 else "QUARTERLY" if 75 <= days <= 105 else "YTD"
        else:
            period_type = "INSTANT"
        rows.append({
            "ticker": _text(metadata.get("symbol")), "isin": _text(metadata.get("isin")),
            "exchange": _text(metadata.get("exchange")) or "NSE",
            "accounting_family": detected_family,
            "statement_basis": (_text(metadata.get("consolidated")) or "UNKNOWN").upper(),
            "period_type": period_type, "period_start": start, "period_end": period_end,
            "available_at": _timestamp(metadata.get("available_at")),
            "revision_at": _timestamp(metadata.get("revision_at")),
            "revision_status": _text(metadata.get("revision_status")) or "ORIGINAL",
            "filing_id": _text(metadata.get("filing_id")) or filename,
            "canonical_concept": reverse.get(concept, "unknown:" + concept),
            "source_concept": concept, "value": value,
            "unit": _text(element.get("unitRef")), "context_id": cid,
            "source_url": _text(metadata.get("source_url")), "source_sha256": digest,
        })
    return pd.DataFrame(rows, columns=FINANCIAL_COLUMNS)


def parse_shareholding_inline_xbrl(data: bytes, *, metadata: dict[str, Any]) -> dict[str, Any]:
    """Extract only explicitly filed roll-ups from NSE/BSE SHP iXBRL.

    Context names are part of the official SHP taxonomy.  Ambiguous matches
    remain null rather than being forced into FII/DII categories.
    """

    if not data or len(data) > 8_000_000:
        raise ValueError("shareholding iXBRL is empty or too large")
    text = data.decode("utf-8", errors="replace")
    if "ShareholdingAsAPercentageOfTotalNumberOfShares" not in text:
        raise ValueError("unrecognised shareholding iXBRL")
    pattern = re.compile(
        r"<ix:nonFraction\s+([^>]*name=['\"](?:in-bse-shp:)?"
        r"ShareholdingAsAPercentageOfTotalNumberOfShares['\"][^>]*)>"
        r"(.*?)</ix:nonFraction>", re.I | re.S,
    )
    by_context: dict[str, list[float]] = {}
    for attrs, body in pattern.findall(text):
        match = re.search(r"contextRef=['\"]([^'\"]+)", attrs, re.I)
        value = _number(re.sub(r"<[^>]+>", "", body))
        if match and value is not None:
            by_context.setdefault(match.group(1), []).append(value)

    def exact_context(*needles: str) -> float | None:
        candidates = []
        for context, values in by_context.items():
            lowered = context.lower()
            distinct_values = sorted(set(values))
            if any(needle.lower() in lowered for needle in needles) and len(distinct_values) == 1:
                candidates.append(distinct_values[0])
        distinct = sorted(set(candidates))
        return distinct[0] if len(distinct) == 1 else None

    promoter = exact_context("ShareholdingOfPromoterAndPromoterGroup_Context")
    public = exact_context("PublicShareholding_Context")
    if promoter is None and public is None:
        raise ValueError("shareholding iXBRL has no unambiguous promoter/public roll-up")
    return {
        "ticker": _text(metadata.get("ticker")), "isin": _text(metadata.get("isin")),
        "exchange": _text(metadata.get("exchange")) or "BSE",
        "as_of_date": _date(metadata.get("as_of_date")),
        "available_at": _timestamp(metadata.get("available_at")),
        "revision_at": _timestamp(metadata.get("revision_at")),
        "revision_status": _text(metadata.get("revision_status")) or "ORIGINAL",
        "filing_id": _text(metadata.get("filing_id")),
        "promoter_pct": promoter, "public_pct": public,
        "employee_trust_pct": exact_context("EmployeeTrust"),
        "fii_pct": exact_context("ForeignPortfolioInvestor", "InstitutionsForeign"),
        "dii_pct": exact_context("InstitutionsDomestic"),
        "institutional_pct": exact_context("Institutions_Context"),
        "promoter_pledge_pct": None, "total_shares": None,
        "source_url": _text(metadata.get("source_url")),
        "source_sha256": sha256(data).hexdigest(),
    }
