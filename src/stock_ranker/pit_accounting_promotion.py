"""Build versioned PIT fundamental candidates from independently validated evidence."""

from __future__ import annotations

from datetime import date, datetime, time
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from stock_ranker.v2_contracts import FUNDAMENTAL_COLUMNS


INDEPENDENT_SCHEMA = "pit_independent_accounting_validation_v1"
CANDIDATE_SCHEMA = "pit_validated_fundamental_candidate_v1"
PROMOTED_SPEC_SCHEMA = "pit_independently_validated_additions_v1"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def file_sha256(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validated_fundamental_candidates(
    records: list[dict[str, Any]], *, ranking_date: date
) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert only complete pre-cutoff evidence into the unchanged V2 schema."""

    rows: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in sorted(records, key=lambda row: row["ticker"]):
        ticker = str(item["ticker"])
        if ticker in seen:
            raise ValueError(f"duplicate independent validation ticker: {ticker}")
        seen.add(ticker)
        if item.get("validation_status") != "INDEPENDENTLY_VALIDATED":
            continue
        if item.get("identity_chain_status") != "EXACT_NSE_METADATA_PACKET_ISIN_AND_PDF_HASH":
            raise ValueError(f"{ticker}: incomplete exact identity chain")
        disclosed = item["selected"]
        if set(disclosed) != {"roce", "debt_to_equity", "profit"} or any(value is None for value in disclosed.values()):
            raise ValueError(f"{ticker}: incomplete selected accounting evidence")
        timestamp = datetime.strptime(
            item["exchange_dissemination_timestamp"], "%d-%b-%Y %H:%M:%S"
        )
        if timestamp.date() > ranking_date:
            deferred.append({
                "ticker": ticker,
                "reason": "OFFICIAL_REPORT_AVAILABLE_AFTER_RANKING_DATE",
                "available_date": timestamp.date().isoformat(),
            })
            continue
        # Exchange timestamps in this evidence schema are local IST, not UTC.
        # A calendar-day comparison alone admits after-close disclosures.
        if timestamp.date() == ranking_date and timestamp.time() > time(15, 30):
            deferred.append({
                "ticker": ticker,
                "reason": "OFFICIAL_REPORT_AVAILABLE_AFTER_RANKING_CUTOFF",
                "available_date": timestamp.date().isoformat(),
            })
            continue
        roce = float(disclosed["roce"]["current_value"])
        debt = float(disclosed["debt_to_equity"]["current_value"])
        current = float(disclosed["profit"]["current_value"])
        prior = float(disclosed["profit"]["prior_value"])
        if not all(math.isfinite(value) for value in (roce, debt, current, prior)):
            raise ValueError(f"{ticker}: non-finite validated accounting value")
        if debt < 0:
            raise ValueError(f"{ticker}: negative leverage cannot enter V2")
        if prior == 0:
            raise ValueError(f"{ticker}: prior profit is zero")
        growth = current / prior - 1.0
        rows.append({
            "ticker": ticker,
            "period_end": "2026-03-31",
            "available_date": timestamp.date().isoformat(),
            "roce": roce,
            "debt_to_equity": debt,
            "profit_growth_yoy": growth,
        })
        accepted.append({
            "ticker": ticker, "company": item["company"], "isin": item["isin"],
            "sector": item["sector"], "period_end": "2026-03-31",
            "available_date": timestamp.date().isoformat(),
            "exchange_dissemination_timestamp": item["exchange_dissemination_timestamp"],
            "source_url": item["source_url"], "pdf_sha256": item["pdf_sha256"],
            "roce": disclosed["roce"], "debt_to_equity": disclosed["debt_to_equity"],
            "profit": disclosed["profit"], "profit_growth_yoy": growth,
            "reporting_basis": "STANDALONE",
            "fundamental_data_contract_version": "nse_audited_standalone_fundamentals_v1",
        })
    frame = pd.DataFrame(rows, columns=list(FUNDAMENTAL_COLUMNS))
    return frame, accepted, deferred


def merge_candidate_fundamentals(existing: pd.DataFrame, additions: pd.DataFrame) -> pd.DataFrame:
    if list(existing.columns) != list(FUNDAMENTAL_COLUMNS) or list(additions.columns) != list(FUNDAMENTAL_COLUMNS):
        raise ValueError("candidate fundamental schemas do not match Research V2")
    overlap = sorted(set(existing["ticker"].astype(str)) & set(additions["ticker"].astype(str)))
    if overlap:
        raise ValueError(f"candidate additions overlap accepted fundamentals: {overlap}")
    return pd.concat([existing.copy(), additions.copy()], ignore_index=True).sort_values(
        ["ticker", "period_end", "available_date"], kind="stable"
    ).reset_index(drop=True)


def load_promoted_additions(path: str | Path, *, ranking_date: date) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    """Load reviewed independent additions while enforcing their PIT boundary."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != PROMOTED_SPEC_SCHEMA:
        raise ValueError("unexpected promoted-addition schema")
    if payload.get("fundamental_data_contract_version") != "nse_audited_standalone_fundamentals_v1":
        raise ValueError("promoted additions use the wrong fundamental contract")
    if payload.get("reporting_basis") != "STANDALONE":
        raise ValueError("promoted additions must be standalone")
    rows: list[dict[str, Any]] = []
    identity: list[dict[str, str]] = []
    deferred: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in payload.get("records", []):
        ticker = str(item.get("ticker", "")).strip()
        if not ticker or ticker in seen:
            raise ValueError(f"invalid or duplicate promoted ticker: {ticker}")
        seen.add(ticker)
        if not all(str(item.get(key, "")).strip() for key in ("company", "isin", "sector", "source_url", "pdf_sha256")):
            raise ValueError(f"{ticker}: incomplete promoted provenance")
        available = date.fromisoformat(str(item["available_date"]))
        if available > ranking_date:
            deferred.append({"ticker": ticker, "available_date": available.isoformat(), "reason": "OFFICIAL_REPORT_AVAILABLE_AFTER_RANKING_DATE"})
            continue
        if available == ranking_date:
            # These reviewed specifications only certify an availability date.
            # Do not invent a midnight dissemination time for same-day use.
            deferred.append({
                "ticker": ticker, "available_date": available.isoformat(),
                "reason": "OFFICIAL_DISSEMINATION_TIME_UNVERIFIED",
            })
            continue
        roce = float(item["roce"]["value"])
        debt = float(item["debt_to_equity"]["value"])
        current = float(item["profit"]["value"])
        prior = float(item["profit"]["prior"])
        if not all(math.isfinite(value) for value in (roce, debt, current, prior)) or debt < 0 or prior == 0:
            raise ValueError(f"{ticker}: promoted numeric policy failure")
        rows.append({
            "ticker": ticker, "period_end": str(payload["period_end"]),
            "available_date": available.isoformat(), "roce": roce,
            "debt_to_equity": debt, "profit_growth_yoy": current / prior - 1.0,
        })
        identity.append({"ticker": ticker, "company": str(item["company"]), "sector": str(item["sector"])})
    return (
        pd.DataFrame(rows, columns=list(FUNDAMENTAL_COLUMNS)),
        pd.DataFrame(identity, columns=["ticker", "company", "sector"]),
        deferred,
    )
