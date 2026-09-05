"""Official NSE symbol/name history and conservative ISIN-continuity evidence."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

import pandas as pd


SYMBOL_HISTORY_URL = "https://nsearchives.nseindia.com/content/equities/symbolchange.csv"
NAME_HISTORY_URL = "https://nsearchives.nseindia.com/content/equities/namechange.csv"


def parse_nse_symbol_history(content: bytes) -> pd.DataFrame:
    frame = pd.read_csv(
        __import__("io").BytesIO(content), header=None,
        names=["company", "old_symbol", "new_symbol", "effective_date"],
        dtype=str, encoding="utf-8-sig", on_bad_lines="error",
    ).fillna("")
    for column in frame.columns:
        frame[column] = frame[column].str.strip()
    frame["effective_date"] = pd.to_datetime(
        frame["effective_date"], format="%d-%b-%Y", errors="coerce"
    )
    frame = frame.loc[
        frame["old_symbol"].ne("") & frame["new_symbol"].ne("")
        & frame["effective_date"].notna()
    ].copy()
    frame["effective_date"] = frame["effective_date"].dt.strftime("%Y-%m-%d")
    return frame.drop_duplicates(
        ["old_symbol", "new_symbol", "effective_date"], keep="last"
    ).sort_values(["effective_date", "old_symbol", "new_symbol"], kind="mergesort").reset_index(drop=True)


def parse_nse_name_history(content: bytes) -> pd.DataFrame:
    frame = pd.read_csv(__import__("io").BytesIO(content), dtype=str, encoding="utf-8-sig").fillna("")
    frame.columns = [str(column).strip() for column in frame.columns]
    expected = {"NCH_SYMBOL", "NCH_PREV_NAME", "NCH_NEW_NAME", "NCH_DT"}
    if not expected.issubset(frame.columns):
        raise ValueError("official NSE name-history schema changed")
    frame = frame.rename(columns={
        "NCH_SYMBOL": "symbol", "NCH_PREV_NAME": "old_company_name",
        "NCH_NEW_NAME": "new_company_name", "NCH_DT": "effective_date",
    })[["symbol", "old_company_name", "new_company_name", "effective_date"]]
    for column in frame.columns:
        frame[column] = frame[column].str.strip()
    frame["effective_date"] = pd.to_datetime(
        frame["effective_date"], format="%d-%b-%Y", errors="coerce"
    )
    frame = frame.loc[frame["symbol"].ne("") & frame["effective_date"].notna()].copy()
    frame["effective_date"] = frame["effective_date"].dt.strftime("%Y-%m-%d")
    return frame.drop_duplicates(
        ["symbol", "old_company_name", "new_company_name", "effective_date"], keep="last"
    ).sort_values(["effective_date", "symbol"], kind="mergesort").reset_index(drop=True)


def build_identity_continuity(
    current_securities: pd.DataFrame,
    symbol_history: pd.DataFrame,
    name_history: pd.DataFrame,
    corporate_actions: pd.DataFrame | None = None,
    *,
    symbol_source_sha256: str,
    name_source_sha256: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    required = {"ticker", "company", "isin", "primary_exchange"}
    missing = sorted(required.difference(current_securities.columns))
    if missing:
        raise ValueError(f"current security master missing columns: {', '.join(missing)}")
    current = current_securities.loc[current_securities["primary_exchange"].eq("NSE")].copy()
    if current["ticker"].duplicated().any() or current["isin"].duplicated().any():
        raise ValueError("current NSE identities must have unique ticker and ISIN")
    by_ticker = current.set_index("ticker").to_dict("index")

    # Resolve official symbol chains backwards from each current symbol.  No fuzzy
    # company-name matching is used; every edge is an exchange-published transition.
    edges = {
        str(row.new_symbol): [] for row in symbol_history.itertuples(index=False)
    }
    for row in symbol_history.itertuples(index=False):
        edges.setdefault(str(row.new_symbol), []).append(row)
    rows: list[dict[str, Any]] = []
    for current_symbol, identity in sorted(by_ticker.items()):
        queue = [(current_symbol, 0)]
        visited = {current_symbol}
        while queue:
            new_symbol, distance = queue.pop(0)
            for edge in sorted(edges.get(new_symbol, []), key=lambda item: (item.effective_date, item.old_symbol)):
                old_symbol = str(edge.old_symbol)
                rows.append({
                    "canonical_ticker": current_symbol, "canonical_isin": identity["isin"],
                    "canonical_company": identity["company"], "evidence_type": "SYMBOL_CHANGE",
                    "historical_symbol": old_symbol, "successor_symbol": str(edge.new_symbol),
                    "historical_company_name": str(edge.company), "successor_company_name": None,
                    "effective_date": str(edge.effective_date), "chain_distance": distance + 1,
                    "continuity_status": "OFFICIAL_NSE_SYMBOL_TRANSITION",
                    "source_url": SYMBOL_HISTORY_URL, "source_sha256": symbol_source_sha256,
                })
                if old_symbol not in visited:
                    visited.add(old_symbol)
                    queue.append((old_symbol, distance + 1))

    for row in name_history.itertuples(index=False):
        symbol = str(row.symbol)
        identity = by_ticker.get(symbol)
        if identity is None:
            continue
        rows.append({
            "canonical_ticker": symbol, "canonical_isin": identity["isin"],
            "canonical_company": identity["company"], "evidence_type": "COMPANY_NAME_CHANGE",
            "historical_symbol": symbol, "successor_symbol": symbol,
            "historical_company_name": str(row.old_company_name),
            "successor_company_name": str(row.new_company_name),
            "effective_date": str(row.effective_date), "chain_distance": 0,
            "continuity_status": "OFFICIAL_NSE_NAME_TRANSITION",
            "source_url": NAME_HISTORY_URL, "source_sha256": name_source_sha256,
        })

    isin_candidate_count = 0
    if corporate_actions is not None and not corporate_actions.empty:
        action_required = {"ticker", "isin", "action_type", "subject", "ex_date", "source_url", "source_sha256"}
        if action_required.issubset(corporate_actions.columns):
            for action in corporate_actions.itertuples(index=False):
                ticker = str(action.ticker)
                identity = by_ticker.get(ticker)
                old_isin = str(action.isin)
                if identity is None or old_isin == str(identity["isin"]) or not old_isin.startswith("INE"):
                    continue
                isin_candidate_count += 1
                rows.append({
                    "canonical_ticker": ticker, "canonical_isin": identity["isin"],
                    "canonical_company": identity["company"], "evidence_type": "HISTORICAL_ACTION_ISIN",
                    "historical_symbol": ticker, "successor_symbol": ticker,
                    "historical_company_name": None, "successor_company_name": None,
                    "effective_date": str(action.ex_date), "chain_distance": 0,
                    "continuity_status": "REVIEW_ISIN_TRANSITION_FROM_OFFICIAL_ACTION",
                    "source_url": action.source_url, "source_sha256": action.source_sha256,
                    "historical_isin": old_isin, "action_type": action.action_type,
                    "action_subject": action.subject,
                })
    result = pd.DataFrame(rows)
    if result.empty:
        result = pd.DataFrame(columns=(
            "canonical_ticker", "canonical_isin", "canonical_company", "evidence_type",
            "historical_symbol", "successor_symbol", "historical_company_name",
            "successor_company_name", "effective_date", "chain_distance",
            "continuity_status", "source_url", "source_sha256", "historical_isin",
            "action_type", "action_subject",
        ))
    else:
        for column in ("historical_isin", "action_type", "action_subject"):
            if column not in result.columns:
                result[column] = None
        result = result.sort_values(
            ["canonical_ticker", "effective_date", "evidence_type", "historical_symbol"],
            kind="mergesort",
        ).reset_index(drop=True)
    summary = {
        "current_nse_security_count": len(current),
        "identity_evidence_row_count": len(result),
        "current_securities_with_history_count": int(result["canonical_isin"].nunique()),
        "symbol_transition_count": int(result["evidence_type"].eq("SYMBOL_CHANGE").sum()),
        "name_transition_count": int(result["evidence_type"].eq("COMPANY_NAME_CHANGE").sum()),
        "isin_transition_review_count": isin_candidate_count,
        "automatic_price_series_merge_count": 0,
        "scientific_boundary": "Only official symbol/name edges are accepted automatically; action-linked historical ISINs remain review evidence and do not splice prices.",
    }
    summary["continuity_fingerprint"] = sha256(
        result.to_csv(index=False, lineterminator="\n").encode("utf-8")
    ).hexdigest()
    return result, summary
