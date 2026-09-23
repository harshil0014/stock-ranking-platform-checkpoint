"""Conservative, point-in-time data repair for personalized simulations."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from typing import Mapping

import numpy as np
import pandas as pd

from stock_ranker.personalized import HistoryBook, InvestorProfile


@dataclass(frozen=True)
class RecoveryResult:
    book: HistoryBook
    repairs: pd.DataFrame
    history_audit: pd.DataFrame


def _date(value):
    value = pd.to_datetime(value, errors="coerce")
    return value.normalize() if pd.notna(value) else pd.NaT


def recover_history_book(
    facts: pd.DataFrame,
    history_root: str | Path,
    live_market: pd.DataFrame,
    corporate_actions: pd.DataFrame,
    *,
    as_of_date: str,
    official_price_bridge: pd.DataFrame | None = None,
) -> RecoveryResult:
    """Remove impossible price observations and append a verified official terminal close.

    A terminal close is appended only for the same ISIN/exchange, at or before the
    declared cutoff, when no exchange-published action falls in the uncovered gap.
    Existing files are never changed.
    """
    required = {"ticker", "isin", "primary_exchange", "listing_date"}
    if not required.issubset(facts) or facts["isin"].isna().any() or facts["isin"].duplicated().any():
        raise ValueError("unique complete current identities required")
    if live_market["isin"].duplicated().any():
        raise ValueError("live market identities must be unique")
    cutoff = _date(as_of_date)
    live = live_market.set_index("isin", drop=False)
    actions = corporate_actions.copy()
    actions["ex_date"] = pd.to_datetime(actions["ex_date"], errors="coerce").dt.normalize()
    root = Path(history_root).resolve()
    bridge = official_price_bridge.copy() if official_price_bridge is not None else pd.DataFrame()
    if not bridge.empty:
        bridge["trade_date"] = pd.to_datetime(bridge["trade_date"], errors="coerce").dt.normalize()
        bridge["close"] = pd.to_numeric(bridge["close"], errors="coerce")
    frames: dict[str, pd.DataFrame] = {}
    audits, repairs = [], []
    allowed = {"AVAILABLE", "AVAILABLE_PRIOR_TRADE"}

    for item in facts.sort_values("isin").itertuples(index=False):
        path = (root / f"{item.ticker}.csv").resolve()
        audit = {"isin": item.isin, "ticker": item.ticker, "history_file": path.name,
                 "history_file_sha256": None, "invalid_observations_removed": 0,
                 "terminal_repair_status": "NOT_ATTEMPTED", "terminal_repair_reason": None}
        if path.parent != root:
            raise ValueError("unsafe history filename")
        if not path.is_file():
            audit.update(history_status="MISSING", terminal_repair_status="NOT_POSSIBLE",
                         terminal_repair_reason="HISTORY_FILE_MISSING")
            audits.append(audit)
            continue
        raw = path.read_bytes()
        audit["history_file_sha256"] = sha256(raw).hexdigest()
        try:
            frame = pd.read_csv(path, usecols=lambda c: c in {"date", "raw_close", "adjusted_close"})
            frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
            frame["adjusted_close"] = pd.to_numeric(frame["adjusted_close"], errors="coerce")
            valid = frame["date"].notna() & np.isfinite(frame["adjusted_close"]) & frame["adjusted_close"].gt(0)
            audit["invalid_observations_removed"] = int((~valid).sum())
            frame = frame.loc[valid].copy()
            listing = _date(item.listing_date)
            if pd.notna(listing):
                frame = frame.loc[frame["date"].ge(listing)]
            if frame.empty:
                audit.update(history_status="NO_VALID_OBSERVATIONS", terminal_repair_status="NOT_POSSIBLE",
                             terminal_repair_reason="NO_VALID_OBSERVATIONS")
                audits.append(audit)
                continue
            if frame["date"].duplicated().any() or not frame["date"].is_monotonic_increasing:
                audit.update(history_status="INVALID_DATES", terminal_repair_status="NOT_POSSIBLE",
                             terminal_repair_reason="DATES_NOT_UNIQUE_INCREASING")
                audits.append(audit)
                continue
            last_date = frame["date"].iat[-1]
            audit.update(history_status="VALID", first_valid_date=frame["date"].iat[0].date().isoformat(),
                         last_original_date=last_date.date().isoformat(), valid_observation_count=len(frame))
            market = live.loc[item.isin] if item.isin in live.index else None
            if market is None:
                audit.update(terminal_repair_status="NOT_POSSIBLE", terminal_repair_reason="LIVE_IDENTITY_MISSING")
            else:
                market_date, price = _date(market.trade_date), pd.to_numeric(market.latest_price, errors="coerce")
                exact_exchange = str(market.primary_exchange) == str(item.primary_exchange)
                gap_actions = actions.loc[
                    actions["isin"].eq(item.isin) & actions["exchange"].eq(item.primary_exchange)
                    & actions["ex_date"].gt(last_date) & actions["ex_date"].le(market_date)
                ]
                raw_terminal = pd.to_numeric(frame.get("raw_close", pd.Series([np.nan] * len(frame))), errors="coerce").iat[-1]
                terminal_basis_ok = np.isfinite(raw_terminal) and np.isclose(raw_terminal, frame["adjusted_close"].iat[-1], rtol=1e-9, atol=1e-9)
                if market_date <= last_date:
                    audit.update(terminal_repair_status="CURRENT", terminal_repair_reason="NO_APPEND_REQUIRED")
                elif market_date > cutoff:
                    audit.update(terminal_repair_status="NOT_POSSIBLE", terminal_repair_reason="FUTURE_LIVE_PRICE")
                elif str(market.snapshot_status) not in allowed or not np.isfinite(price) or price <= 0:
                    audit.update(terminal_repair_status="NOT_POSSIBLE", terminal_repair_reason="OFFICIAL_PRICE_UNAVAILABLE")
                elif not exact_exchange:
                    audit.update(terminal_repair_status="NOT_POSSIBLE", terminal_repair_reason="CROSS_EXCHANGE_PRICE_REQUIRES_REVIEW")
                elif not terminal_basis_ok:
                    audit.update(terminal_repair_status="NOT_POSSIBLE", terminal_repair_reason="TERMINAL_ADJUSTMENT_BASIS_UNRESOLVED")
                elif not gap_actions.empty:
                    kinds = set(gap_actions["action_type"])
                    prices = bridge.loc[
                        bridge["isin"].eq(item.isin) & bridge["ticker"].eq(item.ticker)
                        & bridge["trade_date"].gt(last_date) & bridge["trade_date"].le(market_date)
                    ].sort_values("trade_date") if not bridge.empty else pd.DataFrame()
                    amounts = []
                    if kinds == {"DIVIDEND"}:
                        for subject in gap_actions["subject"].astype(str):
                            found = re.findall(r"\bR(?:s|e)\.?\s*([0-9]+(?:\.[0-9]+)?)", subject, flags=re.I)
                            amounts.append(sum(map(float, found)) if found else np.nan)
                    bridge_ok = (
                        kinds == {"DIVIDEND"} and amounts and np.isfinite(amounts).all()
                        and not prices.empty and prices["trade_date"].iat[-1] == market_date
                        and prices["trade_date"].is_unique and prices["close"].gt(0).all()
                        and int(prices["trade_date"].diff().dropna().dt.days.max() or 0) <= 7
                    )
                    if bridge_ok:
                        index_level, previous_raw, previous_date = frame["adjusted_close"].iat[-1], raw_terminal, last_date
                        additions = []
                        event_amounts = list(zip(gap_actions["ex_date"], amounts))
                        for point in prices.itertuples(index=False):
                            cash = sum(amount for day, amount in event_amounts if previous_date < day <= point.trade_date)
                            index_level *= (float(point.close) + cash) / previous_raw
                            additions.append({"date": point.trade_date, "raw_close": float(point.close),
                                              "adjusted_close": index_level})
                            previous_raw, previous_date = float(point.close), point.trade_date
                        frame = pd.concat([frame, pd.DataFrame(additions)], ignore_index=True)
                        audit.update(terminal_repair_status="APPENDED_OFFICIAL_TOTAL_RETURN_BRIDGE",
                                     terminal_repair_reason="OFFICIAL_DIVIDEND_AND_DAILY_CLOSES")
                        repairs.append({"isin": item.isin, "ticker": item.ticker, "exchange": item.primary_exchange,
                                        "prior_date": last_date.date().isoformat(), "appended_date": market_date.date().isoformat(),
                                        "appended_price": float(index_level), "snapshot_status": market.snapshot_status,
                                        "snapshot_source": "Official NSE CM-UDiFF daily bridge + official action ledger",
                                        "action_rows_in_gap": len(gap_actions), "history_file_sha256": audit["history_file_sha256"]})
                    else:
                        audit.update(terminal_repair_status="NOT_POSSIBLE", terminal_repair_reason="CORPORATE_ACTION_IN_GAP")
                else:
                    frame = pd.concat([frame, pd.DataFrame({"date": [market_date], "raw_close": [price],
                                                            "adjusted_close": [price]})], ignore_index=True)
                    audit.update(terminal_repair_status="APPENDED_OFFICIAL_CLOSE", terminal_repair_reason="VERIFIED_NO_ACTION_GAP")
                    repairs.append({"isin": item.isin, "ticker": item.ticker, "exchange": item.primary_exchange,
                                    "prior_date": last_date.date().isoformat(), "appended_date": market_date.date().isoformat(),
                                    "appended_price": float(price), "snapshot_status": market.snapshot_status,
                                    "snapshot_source": market.snapshot_source, "action_rows_in_gap": 0,
                                    "history_file_sha256": audit["history_file_sha256"]})
            frames[item.isin] = frame[["date", "adjusted_close"]]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            audit.update(history_status="INVALID", terminal_repair_status="NOT_POSSIBLE",
                         terminal_repair_reason=f"{type(exc).__name__}:{exc}")
        audits.append(audit)

    book = HistoryBook(frames)
    for audit in audits:
        if audit["isin"] not in book.arrays and audit["isin"] not in book.errors:
            book.errors[audit["isin"]] = audit.get("terminal_repair_reason") or audit.get("history_status") or "HISTORY_UNAVAILABLE"
    return RecoveryResult(book, pd.DataFrame(repairs), pd.DataFrame(audits))


def classify_profile_eligibility(
    simulation: pd.DataFrame, facts: pd.DataFrame, history_audit: pd.DataFrame,
    profile: InvestorProfile, *, as_of_date: str,
    official_history_evidence: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Separate repaired, genuinely young, and unresolved histories."""
    end = _date(as_of_date)
    start = end - pd.DateOffset(months=profile.lookback_months)
    simulation = simulation.copy()
    for column in ("reason", "terminal_price_date"):
        if column not in simulation:
            simulation[column] = None
    result = facts[["isin", "ticker", "company", "primary_exchange", "listing_date"]].merge(
        simulation[["isin", "status", "reason", "terminal_price_date"]], on="isin", how="left", validate="one_to_one"
    ).merge(history_audit, on=["isin", "ticker"], how="left", validate="one_to_one")
    if official_history_evidence is not None:
        if official_history_evidence["isin"].duplicated().any():
            raise ValueError("official history evidence identities must be unique")
        result = result.merge(official_history_evidence, on="isin", how="left", validate="one_to_one")
    listing = pd.to_datetime(result["listing_date"], errors="coerce")
    first = pd.to_datetime(result["first_valid_date"], errors="coerce")
    result["lookback_months"] = profile.lookback_months
    result["eligibility_class"] = "UNRESOLVED"
    result.loc[result["status"].eq("AVAILABLE"), "eligibility_class"] = "ELIGIBLE"
    young = result["status"].isin(["INSUFFICIENT_HISTORY", "INVALID_HISTORY"]) & listing.gt(start)
    result.loc[young, "eligibility_class"] = "LEGITIMATE_INELIGIBILITY"
    result.loc[young, "classification_reason"] = "LISTED_AFTER_PROFILE_START"
    unresolved_start = result["status"].eq("INSUFFICIENT_HISTORY") & ~young
    result.loc[unresolved_start, "classification_reason"] = "HISTORY_STARTS_AFTER_PROFILE_START_WITHOUT_RECENT_LISTING_EVIDENCE"
    invalid = result["status"].eq("INVALID_HISTORY") & ~young
    result.loc[invalid, "classification_reason"] = result.loc[invalid, "reason"]
    result.loc[result["status"].eq("MISSING_EXECUTION_PRICE"), "classification_reason"] = "INTERNAL_PRICE_GAP_EXCEEDS_TOLERANCE"
    result.loc[result["status"].eq("STALE_TERMINAL"), "classification_reason"] = "TERMINAL_PRICE_NOT_DEFENSIBLY_REPAIRED"
    result.loc[result["status"].eq("AVAILABLE"), "classification_reason"] = "PROFILE_COMPLETE"
    if official_history_evidence is not None:
        complete = result["official_archive_complete"].fillna(False).astype(bool)
        promoted = result["official_recovery_status"].eq("PROMOTED_TO_CANDIDATE")
        first_official = pd.to_datetime(result["first_official_date"], errors="coerce")
        late = complete & promoted & result["status"].eq("INSUFFICIENT_HISTORY") & first_official.gt(start)
        result.loc[late, "eligibility_class"] = "LEGITIMATE_INELIGIBILITY"
        result.loc[late, "classification_reason"] = "OFFICIAL_HISTORY_BEGINS_AFTER_PROFILE_START"
        illiquid = complete & promoted & result["status"].eq("MISSING_EXECUTION_PRICE")
        result.loc[illiquid, "eligibility_class"] = "LEGITIMATE_INELIGIBILITY"
        result.loc[illiquid, "classification_reason"] = "OFFICIAL_NO_TRADE_WITHIN_EXECUTION_TOLERANCE"
        stale = complete & promoted & result["status"].eq("STALE_TERMINAL")
        result.loc[stale, "eligibility_class"] = "LEGITIMATE_INELIGIBILITY"
        result.loc[stale, "classification_reason"] = "OFFICIAL_NO_RECENT_TERMINAL_TRADE"
        no_trades = complete & result["official_recovery_status"].eq("NO_OFFICIAL_RAW_HISTORY") & result["status"].eq("INVALID_HISTORY")
        result.loc[no_trades, "eligibility_class"] = "LEGITIMATE_INELIGIBILITY"
        result.loc[no_trades, "classification_reason"] = "NO_OFFICIAL_TRADES_IN_ARCHIVE_WINDOW"
        quarantined = result["official_recovery_status"].eq("QUARANTINED")
        result.loc[quarantined, "eligibility_class"] = "UNRESOLVED"
        result.loc[quarantined, "classification_reason"] = (
            "OFFICIAL_HISTORY_QUARANTINED:"
            + result.loc[quarantined, "official_recovery_reason"].fillna("UNKNOWN")
        )
    result["first_valid_after_profile_start_days"] = (first - start).dt.days
    return result


def effective_dated_security_master(
    facts: pd.DataFrame, identity_evidence: pd.DataFrame, historical_dispositions: pd.DataFrame,
    *, as_of_date: str,
) -> pd.DataFrame:
    """Build dated identity intervals without fuzzy or inferred price-series splices."""
    rows = []
    cutoff = _date(as_of_date)
    symbols = identity_evidence.loc[identity_evidence["evidence_type"].eq("SYMBOL_CHANGE")].copy()
    for item in facts.sort_values("isin").itertuples(index=False):
        changes = symbols.loc[symbols["canonical_isin"].eq(item.isin)].sort_values("effective_date")
        last_change = pd.to_datetime(changes["effective_date"], errors="coerce").max() if not changes.empty else pd.NaT
        listed = _date(item.listing_date)
        valid_from = max([x for x in (listed, last_change) if pd.notna(x)], default=pd.NaT)
        rows.append({"canonical_isin": item.isin, "exchange": item.primary_exchange,
                     "security_id": item.exchange_security_id, "symbol": item.ticker, "company_name": item.company,
                     "valid_from": valid_from.date().isoformat() if pd.notna(valid_from) else None,
                     "valid_to": None, "lifecycle_status": "LISTED_AS_OF_CUTOFF",
                     "continuity_status": "CURRENT_EXACT_ISIN", "as_of_date": cutoff.date().isoformat(),
                     "sector": item.product_sector, "sector_valid_from": item.product_classification_as_of,
                     "historical_sector_status": "CURRENT_CLASSIFICATION_NOT_BACKPROJECTED"})
        for change in changes.itertuples(index=False):
            rows.append({"canonical_isin": item.isin, "exchange": "NSE", "security_id": change.historical_symbol,
                         "symbol": change.historical_symbol, "company_name": change.historical_company_name,
                         "valid_from": None, "valid_to": str(change.effective_date),
                         "lifecycle_status": "SUPERSEDED_SYMBOL", "continuity_status": change.continuity_status,
                         "as_of_date": cutoff.date().isoformat(), "sector": None, "sector_valid_from": None,
                         "historical_sector_status": "UNAVAILABLE"})
    for old in historical_dispositions.loc[
        historical_dispositions["disposition"].eq("EXCLUDED_FROM_FINAL_ACCEPTED_SNAPSHOT")
    ].itertuples(index=False):
        rows.append({"canonical_isin": old.isin, "exchange": old.primary_exchange,
                     "security_id": old.exchange_security_id, "symbol": old.ticker, "company_name": old.company,
                     "valid_from": None, "valid_to": cutoff.date().isoformat(),
                     "lifecycle_status": "NO_LONGER_IN_CURRENT_UNIVERSE_UNRESOLVED",
                     "continuity_status": "PRESERVED_NO_AUTOMATIC_TERMINAL_VALUE", "as_of_date": cutoff.date().isoformat(),
                     "sector": None, "sector_valid_from": None, "historical_sector_status": "UNAVAILABLE"})
    return pd.DataFrame(rows).sort_values(["canonical_isin", "valid_to", "symbol"], na_position="last", kind="mergesort").reset_index(drop=True)
