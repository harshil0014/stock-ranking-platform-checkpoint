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


LIVE_BUNDLE_VERSION = "all_nse_live_market_v1"
ORDINARY_EQUITY_SERIES = frozenset({"EQ", "BE", "BZ"})
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


def load_official_equity_universe(path: str | Path) -> pd.DataFrame:
    """Load the official NSE equity-segment list and retain ordinary shares only."""

    source = Path(path)
    frame = pd.read_csv(source, encoding="utf-8-sig", skipinitialspace=True)
    frame.columns = frame.columns.astype(str).str.strip()
    frame = _require_columns(frame, UNIVERSE_COLUMNS, "NSE equity universe")
    _text(frame, UNIVERSE_COLUMNS, "NSE equity universe")
    frame = frame.loc[frame["SERIES"].isin(ORDINARY_EQUITY_SERIES)].copy()
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
    }).sort_values("ticker", kind="stable").reset_index(drop=True)


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
        if known:
            baseline_codes.append(str(known["reason_code"]))
            baseline_reasons.append(str(known["reason"]))
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
    for ticker in market["ticker"]:
        known = v2_elig.get(ticker)
        if known:
            v2_codes.append(str(known["reason_code"]))
            v2_reasons.append(str(known["reason"]))
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
    fingerprint = sha256(json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    size_counts = {name: int(market["size_segment"].eq(name).sum()) for name in (*SEGMENT_ORDER, "OTHER NSE")}
    v2_counts = market["v2_reason_code"].value_counts().sort_index().to_dict()
    manifest = {
        "schema_version": 1, "bundle_version": LIVE_BUNDLE_VERSION,
        "bundle_fingerprint": fingerprint, "files": inventory,
        "universe_source": "NSE Securities available for Equity segment",
        "universe_count": len(market), "instrument_scope": "Active NSE main-board ordinary equity shares",
        "excluded_instruments": ["ETF", "mutual fund", "REIT", "InvIT", "debt", "preference share", "warrant", "SME"],
        "size_membership_source": "Official NSE Indices constituent files",
        "ranked_subset": "NIFTY TOTAL MARKET (Nifty 100 + Midcap 150 + Smallcap 250 + Microcap 250)",
        "fallback_tier_reached": "NIFTY TOTAL MARKET",
        "size_segment_counts": size_counts,
        "classified_count": int(market["classification_status"].eq("CLASSIFIED").sum()),
        "unclassified_count": int(market["classification_status"].ne("CLASSIFIED").sum()),
        "snapshot": dict(snapshot_metadata),
        "price_history": {
            "targeted": int(market["classification_status"].eq("CLASSIFIED").sum()),
            "attempted_this_run": history_attempted, "acquired": history_acquired,
            "failed": history_failed, "cache_ready": history_acquired,
            "provider": "Yahoo Finance through yfinance; exact .NS mapping",
        },
        "baseline_eligible_count": int(market["baseline_eligible"].sum()),
        "research_v2_eligible_count": int(market["v2_eligible"].sum()),
        "research_v2_exclusion_counts": v2_counts,
        "research_v2_contract": "nse_audited_standalone_fundamentals_v1",
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
    if manifest.get("bundle_version") != LIVE_BUNDLE_VERSION:
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
