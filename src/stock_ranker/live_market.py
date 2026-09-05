"""Prepared current-market product layer, separate from frozen research artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from zoneinfo import ZoneInfo
from zipfile import BadZipFile, ZipFile

import numpy as np
import pandas as pd


LIVE_BUNDLE_VERSION = "all_india_ordinary_equity_live_market_v2"
LEGACY_LIVE_BUNDLE_VERSION = "all_nse_live_market_v1"
SUPPORTED_LIVE_BUNDLE_VERSIONS = frozenset({LIVE_BUNDLE_VERSION, LEGACY_LIVE_BUNDLE_VERSION})
ORDINARY_EQUITY_SERIES = frozenset({"EQ", "BE", "BZ"})
ORDINARY_EQUITY_CONTRACT_VERSION = "listed_ordinary_company_equity_v1"
SEGMENT_ORDER = ("LARGE", "MID", "SMALL", "MICRO")
SEGMENT_FILES = {
    "LARGE": "nifty100.csv",
    "MID": "midcap150.csv",
    "SMALL": "smallcap250.csv",
    "MICRO": "microcap250.csv",
}
UNIVERSE_COLUMNS = (
    "SYMBOL", "NAME OF COMPANY", "SERIES", "DATE OF LISTING",
    "ISIN NUMBER",
)
INDEX_COLUMNS = ("Company Name", "Industry", "Symbol", "Series", "ISIN Code")
BHAV_COLUMNS = (
    "TradDt", "Sgmt", "Src", "ISIN", "TckrSymb", "SctySrs",
    "OpnPric", "HghPric", "LwPric", "ClsPric", "LastPric",
    "PrvsClsgPric", "TtlTradgVol", "TtlTrfVal", "TtlNbOfTxsExctd",
)
BSE_BHAV_COLUMNS = (*BHAV_COLUMNS, "FinInstrmTp", "FinInstrmId", "FinInstrmNm")
NSE_FULL_BHAV_COLUMNS = (
    "SYMBOL", "SERIES", "DATE1", "PREV_CLOSE", "OPEN_PRICE", "HIGH_PRICE",
    "LOW_PRICE", "LAST_PRICE", "CLOSE_PRICE", "TTL_TRD_QNTY", "TURNOVER_LACS",
    "NO_OF_TRADES",
)
REMOTE_MLFLOW_PREFIXES = ("http:", "https:", "sql:")


@dataclass(frozen=True, slots=True)
class LiveMarketBundle:
    path: Path
    market: pd.DataFrame
    manifest: dict[str, Any]
    fingerprint: str


def _require_columns(frame: pd.DataFrame, required: tuple[str, ...], label: str) -> pd.DataFrame:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"{label} missing required columns: " + ", ".join(missing))
    return frame.loc[:, list(required)].copy()


def _text(frame: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    for column in columns:
        if frame[column].isna().any():
            raise ValueError(f"{label}.{column} must not contain missing values")
        frame[column] = frame[column].astype(str).str.strip()
        if frame[column].eq("").any():
            raise ValueError(f"{label}.{column} must not contain blank values")


def classify_ranking_instruments(
    frame: pd.DataFrame,
    *,
    exchange: str,
    ticker_column: str,
    company_column: str,
    series_column: str,
    isin_column: str,
) -> pd.DataFrame:
    """Classify exchange securities under the ordinary-company-equity contract.

    The decision uses official security identity rather than company-name
    heuristics.  NSDL's ISIN structure identifies the issuer family in the
    third character and the security type in characters 8-9.  Ordinary company
    equity therefore requires an ``INE`` issuer prefix and security code
    ``01``.  Exchange series and explicit differential-voting-right symbols
    provide the remaining exchange-specific safeguards.
    """

    required = (ticker_column, company_column, series_column, isin_column)
    decisions = _require_columns(frame, required, f"{exchange} instrument classification")
    _text(decisions, required, f"{exchange} instrument classification")
    decisions = decisions.rename(columns={
        ticker_column: "ticker", company_column: "company",
        series_column: "series", isin_column: "isin",
    })
    decisions["ticker"] = decisions["ticker"].str.upper()
    decisions["series"] = decisions["series"].str.upper()
    decisions["isin"] = decisions["isin"].str.upper()
    decisions["ranking_universe_eligible"] = False
    decisions["ranking_universe_reason_code"] = "EXCLUDED_INVALID_SECURITY_IDENTITY"
    decisions["ranking_universe_reason"] = "The exchange row does not contain a valid Indian ISIN."

    valid_isin = decisions["isin"].str.fullmatch(r"IN[A-Z0-9]{9}[0-9]")
    issuer_family = decisions["isin"].str.slice(2, 3)
    security_code = decisions["isin"].str.slice(7, 9)

    def exclude(mask: pd.Series, code: str, reason: str) -> None:
        decisions.loc[valid_isin & mask, "ranking_universe_reason_code"] = code
        decisions.loc[valid_isin & mask, "ranking_universe_reason"] = reason

    company_equity = issuer_family.eq("E") & security_code.eq("01")
    if exchange.upper() == "NSE":
        exclude(
            ~decisions["series"].isin(ORDINARY_EQUITY_SERIES),
            "EXCLUDED_UNSUPPORTED_EXCHANGE_SERIES",
            "The NSE series is outside the supported main-board EQ/BE/BZ equity series.",
        )
        series_ok = decisions["series"].isin(ORDINARY_EQUITY_SERIES)
    elif exchange.upper() == "BSE":
        series_ok = ~decisions["series"].isin({"IF", "R", "G"})
        exclude(
            ~series_ok,
            "EXCLUDED_UNSUPPORTED_EXCHANGE_SERIES",
            "The BSE series is reserved for a non-ordinary exchange instrument.",
        )
    else:
        raise ValueError(f"unsupported exchange for ranking-universe classification: {exchange}")

    # Apply semantic identity reasons after the exchange-series gate so the
    # report explains what the instrument is, not merely where it traded.
    exclude(
        valid_isin & ~issuer_family.isin({"E", "F", "A", "B", "0", "9"}),
        "EXCLUDED_NON_COMPANY_SECURITY",
        "The ISIN issuer family is not an ordinary incorporated-company security.",
    )
    exclude(
        issuer_family.eq("E") & ~security_code.eq("01"),
        "EXCLUDED_NON_ORDINARY_COMPANY_SECURITY",
        "The company-issued ISIN is not security type 01 (equity).",
    )
    exclude(
        issuer_family.eq("F"), "EXCLUDED_FUND_OR_ETF",
        "The ISIN identifies a mutual-fund or exchange-traded-fund unit, not company equity.",
    )
    exclude(
        issuer_family.isin({"A", "B", "0"}), "EXCLUDED_GOVERNMENT_OR_DEBT",
        "The security identity belongs to a government/security instrument, not company equity.",
    )
    exclude(
        decisions["series"].eq("IF") | security_code.isin({"23", "25"}),
        "EXCLUDED_LISTED_TRUST_UNIT",
        "The security is an InvIT/REIT or other listed trust unit, not ordinary company equity.",
    )
    exclude(
        decisions["series"].eq("R") | security_code.eq("20"),
        "EXCLUDED_RIGHTS_ENTITLEMENT",
        "The security is a temporary rights entitlement, not an issued ordinary share.",
    )
    exclude(
        issuer_family.eq("9") | decisions["ticker"].str.contains("DVR", regex=False),
        "EXCLUDED_ALTERNATE_SECURITY_CLASS",
        "The security is an alternate/differential-right equity class rather than the canonical ordinary share.",
    )

    alternate_class = issuer_family.eq("9") | decisions["ticker"].str.contains("DVR", regex=False)
    eligible = valid_isin & company_equity & series_ok & ~alternate_class
    decisions.loc[eligible, "ranking_universe_eligible"] = True
    decisions.loc[eligible, "ranking_universe_reason_code"] = "ELIGIBLE_ORDINARY_EQUITY"
    decisions.loc[eligible, "ranking_universe_reason"] = (
        "Official exchange identity is a company-issued ordinary equity share eligible for ranking."
    )
    decisions["ranking_instrument_type"] = np.where(
        eligible, "ORDINARY_COMPANY_EQUITY", "EXCLUDED_EXCHANGE_INSTRUMENT"
    )
    decisions["ranking_universe_contract"] = ORDINARY_EQUITY_CONTRACT_VERSION
    return decisions


def audit_official_equity_universe(path: str | Path) -> pd.DataFrame:
    """Return one deterministic eligibility decision for every official NSE row."""

    frame = pd.read_csv(Path(path), encoding="utf-8-sig", skipinitialspace=True)
    frame.columns = frame.columns.astype(str).str.strip()
    return classify_ranking_instruments(
        frame, exchange="NSE", ticker_column="SYMBOL", company_column="NAME OF COMPANY",
        series_column="SERIES", isin_column="ISIN NUMBER",
    )


def load_official_equity_universe(path: str | Path) -> pd.DataFrame:
    """Load the official NSE equity-segment list and retain ordinary shares only."""

    source = Path(path)
    frame = pd.read_csv(source, encoding="utf-8-sig", skipinitialspace=True)
    frame.columns = frame.columns.astype(str).str.strip()
    frame = _require_columns(frame, UNIVERSE_COLUMNS, "NSE equity universe")
    _text(frame, UNIVERSE_COLUMNS, "NSE equity universe")
    decisions = classify_ranking_instruments(
        frame, exchange="NSE", ticker_column="SYMBOL", company_column="NAME OF COMPANY",
        series_column="SERIES", isin_column="ISIN NUMBER",
    )
    accepted = decisions.loc[decisions["ranking_universe_eligible"]].set_index("ticker")
    frame = frame.loc[frame["SYMBOL"].str.upper().isin(accepted.index)].copy()
    if frame.empty:
        raise ValueError("NSE equity universe contains no supported ordinary equity series")
    if frame["SYMBOL"].duplicated().any():
        raise ValueError("NSE equity universe symbols must be unique")
    listing = pd.to_datetime(frame["DATE OF LISTING"], format="%d-%b-%Y", errors="coerce")
    if listing.isna().any():
        raise ValueError("NSE equity universe DATE OF LISTING is malformed")
    return pd.DataFrame({
        "ticker": frame["SYMBOL"],
        "company": frame["NAME OF COMPANY"],
        "series": frame["SERIES"],
        "isin": frame["ISIN NUMBER"],
        "listing_date": listing.dt.strftime("%Y-%m-%d"),
        "universe": "ALL NSE",
        "universe_source": "NSE Securities available for Equity segment",
        "primary_exchange": "NSE",
        "exchange_security_id": frame["SYMBOL"],
        "identity_status": "OFFICIAL_NSE_MASTER",
        "ranking_instrument_type": "ORDINARY_COMPANY_EQUITY",
        "ranking_universe_eligible": True,
        "ranking_universe_reason_code": "ELIGIBLE_ORDINARY_EQUITY",
        "ranking_universe_contract": ORDINARY_EQUITY_CONTRACT_VERSION,
    }).sort_values("ticker", kind="stable").reset_index(drop=True)


def add_bse_traded_securities(
    nse_universe: pd.DataFrame,
    nse_snapshot: pd.DataFrame,
    bse_bhavcopy_csv: str | Path,
    *,
    exclusion_sink: list[pd.DataFrame] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Add exact-ISIN BSE-only traded securities without fuzzy substitutions."""

    path = Path(bse_bhavcopy_csv)
    bse = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    bse = _require_columns(bse, BSE_BHAV_COLUMNS, "BSE UDiFF bhavcopy")
    _text(
        bse,
        ("TradDt", "Sgmt", "Src", "FinInstrmTp", "ISIN", "TckrSymb", "SctySrs", "FinInstrmNm"),
        "BSE UDiFF bhavcopy",
    )
    dates = pd.to_datetime(bse["TradDt"], format="%Y-%m-%d", errors="coerce")
    if dates.isna().any() or dates.nunique() != 1:
        raise ValueError("BSE bhavcopy must contain one valid ISO trading date")
    trade_date = dates.iloc[0].date().isoformat()
    bse = bse.loc[
        bse["Sgmt"].eq("CM") & bse["Src"].eq("BSE") & bse["FinInstrmTp"].eq("STK")
    ].copy()
    bse_stock_rows = len(bse)
    bse["ISIN"] = bse["ISIN"].astype(str).str.strip()
    bse = bse.loc[bse["ISIN"].str.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")].copy()
    bse_invalid_identity_rows = bse_stock_rows - len(bse)
    bse["FinInstrmId"] = pd.to_numeric(bse["FinInstrmId"], errors="coerce").astype("Int64")
    if bse["FinInstrmId"].isna().any() or bse["ISIN"].duplicated().any():
        raise ValueError("BSE stock rows require unique ISIN and numeric scrip code")
    numeric = (
        "OpnPric", "HghPric", "LwPric", "ClsPric", "LastPric", "PrvsClsgPric",
        "TtlTradgVol", "TtlTrfVal", "TtlNbOfTxsExctd",
    )
    for column in numeric:
        bse[column] = pd.to_numeric(bse[column], errors="coerce")
    decisions = classify_ranking_instruments(
        bse, exchange="BSE", ticker_column="TckrSymb", company_column="FinInstrmNm",
        series_column="SctySrs", isin_column="ISIN",
    )
    decision_by_isin = decisions.set_index("isin")
    exclusion_counts = (
        decisions.loc[~decisions["ranking_universe_eligible"], "ranking_universe_reason_code"]
        .value_counts().sort_index().astype(int).to_dict()
    )
    if exclusion_sink is not None:
        excluded = decisions.loc[~decisions["ranking_universe_eligible"]].copy()
        excluded.insert(0, "exchange", "BSE")
        exclusion_sink.append(excluded)
    bse = bse.loc[
        bse["ISIN"].isin(decision_by_isin.index[decision_by_isin["ranking_universe_eligible"]])
    ].copy()
    known = set(nse_universe["isin"].astype(str))
    overlap = bse.loc[bse["ISIN"].isin(known)].copy()
    isin_to_ticker = nse_universe.set_index("isin")["ticker"]
    overlap["ticker"] = overlap["ISIN"].map(isin_to_ticker)
    snapshot_by_ticker = nse_snapshot.set_index("ticker", drop=False)
    fallback = overlap.loc[
        overlap["ticker"].isin(snapshot_by_ticker.index)
        & overlap["ClsPric"].notna() & overlap["ClsPric"].gt(0)
    ].copy()
    fallback = fallback.loc[fallback["ticker"].map(snapshot_by_ticker["latest_price"]).isna()]
    for _, row in fallback.iterrows():
        ticker = str(row["ticker"])
        previous = row["PrvsClsgPric"]
        values = {
            "snapshot_status": "AVAILABLE_CROSS_EXCHANGE",
            "latest_price": row["ClsPric"], "previous_close": previous,
            "day_change": row["ClsPric"] - previous,
            "day_change_pct": (row["ClsPric"] / previous - 1) * 100 if previous > 0 else np.nan,
            "open": row["OpnPric"], "high": row["HghPric"], "low": row["LwPric"],
            "last_price": row["LastPric"], "volume": row["TtlTradgVol"],
            "traded_value": row["TtlTrfVal"], "transaction_count": row["TtlNbOfTxsExctd"],
            "snapshot_source": "Official BSE CM-UDiFF fallback for exact dual-listed ISIN",
            "price_exchange": "BSE", "price_identity_status": "EXACT_CROSS_EXCHANGE_ISIN",
        }
        for column, value in values.items():
            nse_snapshot.loc[nse_snapshot["ticker"].eq(ticker), column] = value
    bse_only = bse.loc[~bse["ISIN"].isin(known)].copy()
    bse_only["ticker"] = "BSE-" + bse_only["FinInstrmId"].astype(str)
    universe_rows = pd.DataFrame({
        "ticker": bse_only["ticker"], "company": bse_only["FinInstrmNm"],
        "series": bse_only["SctySrs"], "isin": bse_only["ISIN"],
        "listing_date": pd.NA, "universe": "BSE TRADED",
        "universe_source": "Official BSE CM-UDiFF Common Bhavcopy Final",
        "primary_exchange": "BSE", "exchange_security_id": bse_only["FinInstrmId"].astype(str),
        "identity_status": "OFFICIAL_BSE_TRADE_RECORD",
        "size_segment": "OTHER BSE", "sector": pd.NA, "industry": pd.NA,
        "basic_industry": pd.NA, "classification_status": "UNCLASSIFIED",
        "classification_source": pd.NA,
        "ranking_instrument_type": "ORDINARY_COMPANY_EQUITY",
        "ranking_universe_eligible": True,
        "ranking_universe_reason_code": "ELIGIBLE_ORDINARY_EQUITY",
        "ranking_universe_contract": ORDINARY_EQUITY_CONTRACT_VERSION,
    })
    ready = bse_only["ClsPric"].notna() & np.isfinite(bse_only["ClsPric"]) & bse_only["ClsPric"].gt(0)
    previous = bse_only["PrvsClsgPric"]
    snapshot_rows = pd.DataFrame({
        "ticker": bse_only["ticker"], "trade_date": trade_date,
        "snapshot_status": np.where(ready, "AVAILABLE", "PRICE_UNAVAILABLE"),
        "latest_price": bse_only["ClsPric"], "previous_close": previous,
        "day_change": bse_only["ClsPric"] - previous,
        "day_change_pct": np.where(
            ready & previous.gt(0), (bse_only["ClsPric"] / previous - 1) * 100, np.nan
        ),
        "open": bse_only["OpnPric"], "high": bse_only["HghPric"], "low": bse_only["LwPric"],
        "last_price": bse_only["LastPric"], "volume": bse_only["TtlTradgVol"],
        "traded_value": bse_only["TtlTrfVal"], "transaction_count": bse_only["TtlNbOfTxsExctd"],
        "snapshot_source": "Official BSE CM-UDiFF Common Bhavcopy Final",
        "price_exchange": "BSE", "price_identity_status": "PRIMARY_EXCHANGE",
    })
    universe = pd.concat([nse_universe, universe_rows], ignore_index=True)
    snapshot = pd.concat([nse_snapshot, snapshot_rows], ignore_index=True)
    if universe["ticker"].duplicated().any() or universe["isin"].duplicated().any():
        raise ValueError("combined NSE/BSE universe identities must be unique")
    metadata = {
        "trade_date": trade_date, "bse_stock_rows": bse_stock_rows,
        "bse_ordinary_equity_rows": len(bse),
        "bse_excluded_nonordinary_rows": bse_stock_rows - len(bse),
        "bse_invalid_identity_rows": bse_invalid_identity_rows,
        "bse_exclusion_counts": exclusion_counts,
        "bse_only_rows": len(bse_only), "bse_only_price_ready": int(ready.sum()),
        "cross_exchange_isin_overlap": int(len(overlap)),
        "cross_exchange_price_fallbacks": int(len(fallback)),
        "source_filename": path.name, "source_sha256": sha256(path.read_bytes()).hexdigest(),
    }
    return (
        universe.sort_values(["primary_exchange", "ticker"], kind="stable").reset_index(drop=True),
        snapshot,
        metadata,
    )


def apply_nse_prior_trade_fallback(
    universe: pd.DataFrame,
    snapshot: pd.DataFrame,
    prior_full_bhavcopy_csv: str | Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fill absent same-day NSE quotes from one earlier official full bhavcopy."""

    path = Path(prior_full_bhavcopy_csv)
    prior = pd.read_csv(path, encoding="utf-8-sig", skipinitialspace=True, low_memory=False)
    prior.columns = prior.columns.astype(str).str.strip()
    prior = _require_columns(prior, NSE_FULL_BHAV_COLUMNS, "NSE full bhavcopy")
    _text(prior, ("SYMBOL", "SERIES", "DATE1"), "NSE full bhavcopy")
    dates = pd.to_datetime(prior["DATE1"], format="%d-%b-%Y", errors="coerce")
    if dates.isna().any() or dates.nunique() != 1:
        raise ValueError("NSE full bhavcopy must contain one valid trading date")
    prior_date = dates.iloc[0].date().isoformat()
    current_dates = pd.to_datetime(snapshot["trade_date"], format="%Y-%m-%d", errors="coerce")
    if current_dates.isna().any() or prior_date >= current_dates.max().date().isoformat():
        raise ValueError("prior-trade bhavcopy must predate the current snapshot")
    for column in NSE_FULL_BHAV_COLUMNS[3:]:
        prior[column] = pd.to_numeric(prior[column], errors="coerce")
    keys = universe.loc[universe["primary_exchange"].eq("NSE"), ["ticker", "series"]]
    prior = prior.merge(keys, left_on=["SYMBOL", "SERIES"], right_on=["ticker", "series"], how="inner")
    prior = prior.loc[prior["CLOSE_PRICE"].notna() & prior["CLOSE_PRICE"].gt(0)].copy()
    if prior["ticker"].duplicated().any():
        raise ValueError("NSE full bhavcopy contains duplicate supported identities")
    output = snapshot.copy()
    fallback_count = 0
    for _, row in prior.iterrows():
        mask = output["ticker"].eq(row["ticker"]) & output["latest_price"].isna()
        if not mask.any():
            continue
        previous = row["PREV_CLOSE"]
        values = {
            "trade_date": prior_date, "snapshot_status": "AVAILABLE_PRIOR_TRADE",
            "latest_price": row["CLOSE_PRICE"], "previous_close": previous,
            "day_change": row["CLOSE_PRICE"] - previous,
            "day_change_pct": (row["CLOSE_PRICE"] / previous - 1) * 100 if previous > 0 else np.nan,
            "open": row["OPEN_PRICE"], "high": row["HIGH_PRICE"], "low": row["LOW_PRICE"],
            "last_price": row["LAST_PRICE"], "volume": row["TTL_TRD_QNTY"],
            "traded_value": row["TURNOVER_LACS"], "transaction_count": row["NO_OF_TRADES"],
            "snapshot_source": "Official NSE Full Bhavcopy latest-prior-session fallback",
            "price_exchange": "NSE", "price_identity_status": "EXACT_SYMBOL_SERIES_PRIOR_TRADE",
        }
        for column, value in values.items():
            output.loc[mask, column] = value
        fallback_count += 1
    return output, {
        "trade_date": prior_date, "fallback_count": fallback_count,
        "source_filename": path.name, "source_sha256": sha256(path.read_bytes()).hexdigest(),
    }


def load_index_membership(path: str | Path, segment: str) -> pd.DataFrame:
    """Load one official NSE Indices constituent file without fuzzy identity matching."""

    if segment not in SEGMENT_ORDER:
        raise ValueError("segment must be LARGE, MID, SMALL, or MICRO")
    frame = pd.read_csv(path, encoding="utf-8-sig")
    frame = _require_columns(frame, INDEX_COLUMNS, f"{segment} constituent file")
    _text(frame, INDEX_COLUMNS, f"{segment} constituent file")
    if frame["Symbol"].duplicated().any():
        raise ValueError(f"{segment} constituent symbols must be unique")
    return pd.DataFrame({
        "ticker": frame["Symbol"], "series": frame["Series"],
        "isin": frame["ISIN Code"], "index_company": frame["Company Name"],
        "source_classification": frame["Industry"], "size_segment": segment,
    })


def apply_official_segments(
    universe: pd.DataFrame,
    memberships: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    """Add disjoint official size membership and source-driven classification."""

    result = universe.copy()
    result["size_segment"] = "OTHER NSE"
    result["sector"] = pd.NA
    result["industry"] = pd.NA
    result["basic_industry"] = pd.NA
    result["classification_status"] = "UNCLASSIFIED"
    result["classification_source"] = pd.NA
    assigned: set[str] = set()
    for segment in SEGMENT_ORDER:
        if segment not in memberships:
            raise ValueError(f"missing official {segment} membership")
        membership = memberships[segment]
        keys = membership.set_index("ticker")
        overlap = assigned.intersection(keys.index)
        if overlap:
            raise ValueError("official size memberships overlap: " + ", ".join(sorted(overlap)[:5]))
        assigned.update(keys.index)
        lookup = result["ticker"].isin(keys.index)
        result.loc[lookup, "size_segment"] = segment
    # The Total Market file's legacy `Industry` field contains the 22 current
    # NSE Indices Sector-tier labels.  Preserve that source label separately.
    combined = pd.concat([memberships[name] for name in SEGMENT_ORDER], ignore_index=True)
    combined = combined.drop_duplicates("ticker").set_index("ticker")
    classified = result["ticker"].isin(combined.index)
    values = result.loc[classified, "ticker"].map(combined["source_classification"])
    result.loc[classified, "sector"] = values.to_numpy()
    result.loc[classified, "industry"] = values.to_numpy()
    result.loc[classified, "classification_status"] = "CLASSIFIED"
    result.loc[classified, "classification_source"] = (
        "Official NSE Indices constituent classification (Sector-tier label)"
    )
    return result


def _zip_csv(path: Path) -> tuple[str, bytes]:
    try:
        with ZipFile(path) as archive:
            candidates = []
            for info in archive.infolist():
                item = PurePosixPath(info.filename.replace("\\", "/"))
                if item.is_absolute() or ".." in item.parts:
                    raise ValueError("unsafe bhavcopy ZIP member")
                if not info.is_dir() and item.suffix.lower() == ".csv":
                    candidates.append(info)
            if len(candidates) != 1:
                raise ValueError("bhavcopy ZIP must contain exactly one CSV")
            return candidates[0].filename, archive.read(candidates[0])
    except BadZipFile as exc:
        raise ValueError("bhavcopy is not a valid ZIP") from exc


def build_latest_snapshot(universe: pd.DataFrame, bhavcopy_zip: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Left-join the complete browsing universe to one official EOD snapshot."""

    archive = Path(bhavcopy_zip)
    inner_name, content = _zip_csv(archive)
    bhav = pd.read_csv(BytesIO(content), encoding="utf-8-sig")
    raw_count = len(bhav)
    bhav = _require_columns(bhav, BHAV_COLUMNS, "NSE UDiFF bhavcopy")
    _text(bhav, ("TradDt", "Sgmt", "Src"), "NSE UDiFF bhavcopy")
    dates = pd.to_datetime(bhav["TradDt"], format="%Y-%m-%d", errors="coerce")
    if dates.isna().any() or dates.nunique() != 1:
        raise ValueError("bhavcopy must contain one valid ISO trading date")
    trade_date = dates.iloc[0].date().isoformat()
    bhav = bhav.loc[bhav["Sgmt"].eq("CM") & bhav["Src"].eq("NSE")].copy()
    for column in ("ISIN", "TckrSymb", "SctySrs"):
        bhav[column] = bhav[column].astype("string").str.strip()
    official_keys = universe.rename(columns={
        "ticker": "TckrSymb", "series": "SctySrs", "isin": "ISIN",
    })[["TckrSymb", "SctySrs", "ISIN"]]
    bhav = bhav.merge(official_keys, on=["TckrSymb", "SctySrs", "ISIN"], how="inner", validate="one_to_one")
    _text(bhav, ("ISIN", "TckrSymb", "SctySrs"), "Matched NSE UDiFF bhavcopy")
    numeric = ("OpnPric", "HghPric", "LwPric", "ClsPric", "LastPric", "PrvsClsgPric", "TtlTradgVol", "TtlTrfVal", "TtlNbOfTxsExctd")
    for column in numeric:
        bhav[column] = pd.to_numeric(bhav[column], errors="coerce")
    if bhav.duplicated(["TckrSymb", "SctySrs", "ISIN"]).any():
        raise ValueError("bhavcopy contains duplicate security identities")
    joined = universe.merge(
        bhav, left_on=["ticker", "series", "isin"],
        right_on=["TckrSymb", "SctySrs", "ISIN"], how="left", validate="one_to_one",
    )
    ready = joined["ClsPric"].notna() & np.isfinite(joined["ClsPric"]) & joined["ClsPric"].gt(0)
    previous = joined["PrvsClsgPric"]
    pct = np.where(ready & previous.gt(0), (joined["ClsPric"] / previous - 1) * 100, np.nan)
    snapshot = pd.DataFrame({
        "ticker": joined["ticker"], "trade_date": trade_date,
        "snapshot_status": np.where(ready, "AVAILABLE", "PRICE_UNAVAILABLE"),
        "latest_price": joined["ClsPric"], "previous_close": previous,
        "day_change": joined["ClsPric"] - previous, "day_change_pct": pct,
        "open": joined["OpnPric"], "high": joined["HghPric"], "low": joined["LwPric"],
        "last_price": joined["LastPric"], "volume": joined["TtlTradgVol"],
        "traded_value": joined["TtlTrfVal"], "transaction_count": joined["TtlNbOfTxsExctd"],
        "snapshot_source": "Official NSE CM-UDiFF Common Bhavcopy Final",
        "price_exchange": "NSE", "price_identity_status": "PRIMARY_EXCHANGE",
    })
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    age = max(0, (today - date.fromisoformat(trade_date)).days)
    freshness = "LATEST TRADING SNAPSHOT" if age <= 3 else "STALE SNAPSHOT"
    metadata = {
        "trade_date": trade_date, "snapshot_row_count": raw_count,
        "matched_count": int(ready.sum()), "missing_count": int((~ready).sum()),
        "freshness": freshness, "age_calendar_days": age,
        "source": "Official NSE CM-UDiFF Common Bhavcopy Final",
        "source_filename": archive.name, "inner_csv_filename": inner_name,
        "source_sha256": sha256(archive.read_bytes()).hexdigest(),
    }
    return snapshot, metadata


def combine_live_market(
    universe: pd.DataFrame,
    snapshot: pd.DataFrame,
    *,
    baseline_rankings: pd.DataFrame | None = None,
    baseline_eligibility: pd.DataFrame | None = None,
    v2_rankings: pd.DataFrame | None = None,
    v2_eligibility: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Combine browsing, snapshot, and accepted model outputs without recalculation."""

    market = universe.merge(snapshot, on="ticker", how="left", validate="one_to_one")
    base_rank = pd.DataFrame(columns=["ticker", "baseline_score", "baseline_sector_rank"])
    if baseline_rankings is not None and not baseline_rankings.empty:
        base_columns = [column for column in baseline_rankings.columns if column not in {
            "company", "sector", "as_of_date", "current_price", "close_1y_ago",
            "close_3y_ago", "close_5y_ago", "ath_date", "sector_rank", "method_version",
        }]
        base_rank = baseline_rankings[[*base_columns, "sector_rank"]].rename(columns={
            "yoy_growth": "baseline_yoy_growth",
            "cagr_3y": "baseline_cagr_3y",
            "cagr_5y": "baseline_cagr_5y",
            "days_since_recorded_high": "baseline_days_since_recorded_high",
            "sector_rank": "baseline_sector_rank",
        })
    market = market.merge(base_rank, on="ticker", how="left", validate="one_to_one")
    base_elig = {}
    if baseline_eligibility is not None and not baseline_eligibility.empty:
        base_elig = baseline_eligibility.set_index("ticker").to_dict("index")
    baseline_codes, baseline_reasons = [], []
    for row in market.to_dict("records"):
        known = base_elig.get(row["ticker"])
        if row.get("latest_price") is None or pd.isna(row.get("latest_price")):
            baseline_codes.append("PRICE_UNAVAILABLE")
            baseline_reasons.append(
                "No official exchange trade row exists for this security on the accepted snapshot date; "
                "a latest-prior-trade fallback has not yet been accepted."
            )
        elif known:
            baseline_codes.append(str(known["reason_code"]))
            baseline_reasons.append(str(known["reason"]))
        elif row.get("primary_exchange") == "BSE":
            baseline_codes.append("BSE_CLASSIFICATION_AND_ADJUSTED_HISTORY_PENDING")
            baseline_reasons.append(
                "Exact BSE identity and EOD price are available; official sector classification and "
                "corporate-action-aware adjusted history are not yet accepted for Baseline ranking."
            )
        elif row["classification_status"] != "CLASSIFIED":
            baseline_codes.append("UNCLASSIFIED")
            baseline_reasons.append("Official Sector-tier classification is unavailable.")
        else:
            baseline_codes.append("PRICE_HISTORY_UNAVAILABLE")
            baseline_reasons.append("Prepared five-year provider history is not available in this bundle.")
    market["baseline_reason_code"] = baseline_codes
    market["baseline_reason"] = baseline_reasons
    market["baseline_eligible"] = market["baseline_reason_code"].eq("ELIGIBLE")

    metric_columns: list[str] = []
    v2_rank = pd.DataFrame(columns=["ticker", "research_v2_score", "research_v2_sector_rank"])
    if v2_rankings is not None and not v2_rankings.empty:
        metric_columns = [column for column in v2_rankings.columns if column not in {
            "company", "sector", "ranking_date", "sector_rank", "eligible", "method_version"
        }]
        v2_rank = v2_rankings[["ticker", "sector_rank", *[c for c in metric_columns if c != "ticker"]]].rename(
            columns={"sector_rank": "research_v2_sector_rank"}
        )
    market = market.merge(v2_rank, on="ticker", how="left", validate="one_to_one")
    v2_elig = {}
    if v2_eligibility is not None and not v2_eligibility.empty:
        v2_elig = v2_eligibility.set_index("ticker").to_dict("index")
    v2_codes, v2_reasons = [], []
    for row in market.to_dict("records"):
        ticker = row["ticker"]
        known = v2_elig.get(ticker)
        if row.get("latest_price") is None or pd.isna(row.get("latest_price")):
            v2_codes.append("PRICE_UNAVAILABLE")
            v2_reasons.append(
                "No official exchange trade row exists for this security on the accepted snapshot date; "
                "Research V2 cannot use an unverified substitute price."
            )
        elif known:
            v2_codes.append(str(known["reason_code"]))
            v2_reasons.append(str(known["reason"]))
        elif str(ticker).startswith("BSE-"):
            v2_codes.append("BSE_FUNDAMENTAL_CONTRACT_UNAVAILABLE")
            v2_reasons.append(
                "This exact BSE security has current market evidence but is outside the audited "
                "standalone Research V2 fundamentals contract."
            )
        else:
            v2_codes.append("FUNDAMENTALS_UNAVAILABLE")
            v2_reasons.append("Accepted NSE Audited Standalone Fundamentals v1 inputs are unavailable.")
    market["v2_reason_code"] = v2_codes
    market["v2_reason"] = v2_reasons
    market["v2_eligible"] = market["v2_reason_code"].eq("ELIGIBLE")
    return market.sort_values(["sector", "ticker"], na_position="last", kind="stable").reset_index(drop=True)


def write_live_bundle(
    market: pd.DataFrame,
    output_directory: str | Path,
    *,
    snapshot_metadata: Mapping[str, Any],
    source_files: Mapping[str, str | Path],
    acquisition_started_at: str,
    acquisition_completed_at: str,
    history_attempted: int,
    history_acquired: int,
    history_failed: int,
    history_targeted: int | None = None,
    current_v2_ranking_date: str | None = None,
    frozen_v2_evidence_fingerprint: str | None = None,
    current_v2_additions_fingerprint: str | None = None,
    instrument_exclusions: pd.DataFrame | None = None,
) -> LiveMarketBundle:
    """Write canonical product artifacts atomically and return their validated identity."""

    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=True)
    market_path = root / "live_market.csv"
    temporary = root / "live_market.csv.tmp"
    market.to_csv(temporary, index=False, lineterminator="\n", encoding="utf-8", float_format="%.17g")
    temporary.replace(market_path)
    inventory = [{
        "path": market_path.name, "size": market_path.stat().st_size,
        "sha256": sha256(market_path.read_bytes()).hexdigest(),
    }]
    exclusion_counts: dict[str, int] = {}
    if instrument_exclusions is not None and not instrument_exclusions.empty:
        exclusion_columns = [
            "exchange", "ticker", "company", "series", "isin",
            "ranking_universe_reason_code", "ranking_universe_reason",
            "ranking_universe_contract",
        ]
        exclusions = instrument_exclusions.loc[:, exclusion_columns].copy()
        exclusions = exclusions.sort_values(["exchange", "ticker", "isin"], kind="stable")
        exclusions_path = root / "ranking_universe_exclusions.csv"
        exclusions_tmp = root / "ranking_universe_exclusions.csv.tmp"
        exclusions.to_csv(
            exclusions_tmp, index=False, lineterminator="\n", encoding="utf-8"
        )
        exclusions_tmp.replace(exclusions_path)
        inventory.append({
            "path": exclusions_path.name, "size": exclusions_path.stat().st_size,
            "sha256": sha256(exclusions_path.read_bytes()).hexdigest(),
        })
        exclusion_counts = (
            exclusions["ranking_universe_reason_code"].value_counts()
            .sort_index().astype(int).to_dict()
        )
    fingerprint = sha256(json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    size_counts = {name: int(market["size_segment"].eq(name).sum()) for name in (*SEGMENT_ORDER, "OTHER NSE")}
    if "OTHER BSE" in set(market["size_segment"].dropna().astype(str)):
        size_counts["OTHER BSE"] = int(market["size_segment"].eq("OTHER BSE").sum())
    v2_counts = market["v2_reason_code"].value_counts().sort_index().to_dict()
    manifest = {
        "schema_version": 2, "bundle_version": LIVE_BUNDLE_VERSION,
        "bundle_fingerprint": fingerprint, "files": inventory,
        "universe_source": (
            "NSE Securities available for Equity segment plus exact-ISIN BSE UDiFF traded securities"
            if size_counts.get("OTHER BSE", 0) else "NSE Securities available for Equity segment"
        ),
        "universe_count": len(market),
        "instrument_scope": "Listed ordinary company equity shares only",
        "ranking_universe_contract": (
            ORDINARY_EQUITY_CONTRACT_VERSION if instrument_exclusions is not None else None
        ),
        "ranking_universe_exclusion_count": int(sum(exclusion_counts.values())),
        "ranking_universe_exclusion_counts": exclusion_counts,
        "nse_universe_count": int(market.get("primary_exchange", pd.Series("NSE", index=market.index)).eq("NSE").sum()),
        "bse_only_count": int(market.get("primary_exchange", pd.Series("NSE", index=market.index)).eq("BSE").sum()),
        "excluded_instruments": [
            "mutual fund", "ETF", "government security", "debt instrument",
            "preference share", "REIT", "InvIT", "listed trust unit",
            "rights entitlement", "alternate/DVR security class", "warrant", "SME",
        ],
        "size_membership_source": "Official NSE Indices constituent files",
        "ranked_subset": "NIFTY TOTAL MARKET (Nifty 100 + Midcap 150 + Smallcap 250 + Microcap 250)",
        "fallback_tier_reached": "NIFTY TOTAL MARKET",
        "size_segment_counts": size_counts,
        "classified_count": int(market["classification_status"].eq("CLASSIFIED").sum()),
        "unclassified_count": int(market["classification_status"].ne("CLASSIFIED").sum()),
        "snapshot": dict(snapshot_metadata),
        "price_history": {
            "targeted": history_targeted if history_targeted is not None else int(market["classification_status"].eq("CLASSIFIED").sum()),
            "attempted_this_run": history_attempted, "acquired": history_acquired,
            "failed": history_failed, "cache_ready": history_acquired,
            "provider": "Yahoo Finance through yfinance; exact .NS mapping",
        },
        "baseline_eligible_count": int(market["baseline_eligible"].sum()),
        "research_v2_eligible_count": int(market["v2_eligible"].sum()),
        "research_v2_exclusion_counts": v2_counts,
        "research_v2_contract": "nse_audited_standalone_fundamentals_v1",
        "research_v2_current_ranking_date": current_v2_ranking_date or snapshot_metadata["trade_date"],
        "research_v2_frozen_evidence_fingerprint": frozen_v2_evidence_fingerprint,
        "research_v2_current_additions_fingerprint": current_v2_additions_fingerprint,
        "model_versions": {
            "baseline_v1": "baseline_v1_equal_rank_mean",
            "research_v2": "research_v2_point_in_time_weighted",
        },
        "software_versions": {"stock-ranking-platform": "0.2.0", "pandas": pd.__version__},
        "acquisition_started_at": acquisition_started_at,
        "acquisition_completed_at": acquisition_completed_at,
        "source_files": {name: {"path": Path(value).name, "sha256": sha256(Path(value).read_bytes()).hexdigest()}
                         for name, value in sorted(source_files.items())},
        "separation": "LIVE product provenance; frozen Research Lab fingerprints are not modified.",
    }
    manifest_path = root / "bundle_manifest.json"
    manifest_tmp = root / "bundle_manifest.json.tmp"
    manifest_tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    manifest_tmp.replace(manifest_path)
    return LiveMarketBundle(root.resolve(), market, manifest, fingerprint)


def load_live_market_bundle(path: str | Path) -> LiveMarketBundle:
    """Load a prepared live bundle after validating its canonical fingerprint."""

    root = Path(path).resolve()
    manifest_path = root / "bundle_manifest.json"
    if not root.is_dir() or not manifest_path.is_file():
        raise ValueError("prepared live-market bundle is unavailable")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("bundle_version") not in SUPPORTED_LIVE_BUNDLE_VERSIONS:
        raise ValueError("prepared live-market bundle version is unsupported")
    inventory = manifest.get("files")
    if not isinstance(inventory, list) or not inventory:
        raise ValueError("prepared live-market inventory is invalid")
    for item in inventory:
        relative = Path(str(item.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("prepared live-market inventory path is unsafe")
        target = root / relative
        if not target.is_file() or target.stat().st_size != item.get("size") or sha256(target.read_bytes()).hexdigest() != item.get("sha256"):
            raise ValueError(f"prepared live-market artifact mismatch: {relative}")
    fingerprint = sha256(json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if fingerprint != manifest.get("bundle_fingerprint"):
        raise ValueError("prepared live-market fingerprint mismatch")
    market = pd.read_csv(root / "live_market.csv")
    if market.empty or market["ticker"].duplicated().any():
        raise ValueError("prepared live-market rows must be nonempty and unique")
    return LiveMarketBundle(root, market, manifest, fingerprint)
