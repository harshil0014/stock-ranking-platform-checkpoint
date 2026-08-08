"""Strict adapter for an official NIFTY constituent and NSE UDiFF snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path, PurePosixPath
import re
from typing import Any
from zipfile import BadZipFile, ZipFile

import numpy as np
import pandas as pd


ADAPTER_VERSION = "nse_nifty_snapshot_v1"
MAX_DECOMPRESSED_CSV_BYTES = 20 * 1024 * 1024

NIFTY_COLUMNS = (
    "Company Name", "Industry", "Symbol", "Series", "ISIN Code",
)
BHAVCOPY_COLUMNS = (
    "TradDt", "Sgmt", "Src", "ISIN", "TckrSymb", "SctySrs",
    "OpnPric", "HghPric", "LwPric", "ClsPric", "LastPric",
    "PrvsClsgPric", "TtlTradgVol", "TtlTrfVal", "TtlNbOfTxsExctd",
    "NewBrdLotQty",
)
CANONICAL_COLUMNS = (
    "trade_date", "ticker", "company", "industry", "series", "isin",
    "open", "high", "low", "close", "last_price", "previous_close",
    "daily_change", "daily_change_pct", "volume", "traded_value",
    "transaction_count", "board_lot_quantity", "source",
)
IDENTITY_COLUMNS = ("Symbol", "Series", "ISIN Code")
BHAV_IDENTITY_COLUMNS = ("TckrSymb", "SctySrs", "ISIN")
PRICE_MAP = {
    "OpnPric": "open",
    "HghPric": "high",
    "LwPric": "low",
    "ClsPric": "close",
    "LastPric": "last_price",
    "PrvsClsgPric": "previous_close",
}
COUNT_MAP = {
    "TtlTradgVol": "volume",
    "TtlTrfVal": "traded_value",
    "TtlNbOfTxsExctd": "transaction_count",
    "NewBrdLotQty": "board_lot_quantity",
}
SOURCE_DESCRIPTION = (
    "Official supplied NIFTY constituent file + "
    "NSE CM-UDiFF Common Bhavcopy Final"
)
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True, slots=True)
class NSESnapshotResult:
    snapshot: pd.DataFrame
    provenance: dict[str, Any]


def _require_bytes(value: bytes, label: str) -> bytes:
    if not isinstance(value, bytes) or not value:
        raise ValueError(f"{label} must contain nonempty bytes")
    return value


def _read_csv(data: bytes, label: str) -> pd.DataFrame:
    try:
        frame = pd.read_csv(BytesIO(data), encoding="utf-8-sig")
    except (UnicodeError, pd.errors.ParserError, ValueError) as exc:
        raise ValueError(f"Could not parse {label}: {exc}") from exc
    if frame.empty:
        raise ValueError(f"{label} must contain at least one row")
    return frame


def _safe_inner_csv(archive_bytes: bytes) -> tuple[str, bytes]:
    try:
        with ZipFile(BytesIO(archive_bytes)) as archive:
            candidates = []
            for info in archive.infolist():
                if info.is_dir():
                    continue
                normalized = info.filename.replace("\\", "/")
                path = PurePosixPath(normalized)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or normalized.startswith("/")
                    or re.match(r"^[A-Za-z]:", normalized)
                    or info.flag_bits & 0x1
                ):
                    raise ValueError(
                        f"Unsafe ZIP member name or encryption: {info.filename}"
                    )
                if path.suffix.lower() == ".csv":
                    candidates.append(info)
            if len(candidates) != 1:
                raise ValueError(
                    "Bhavcopy ZIP must contain exactly one CSV file; "
                    f"found {len(candidates)}"
                )
            info = candidates[0]
            if info.file_size <= 0:
                raise ValueError("Bhavcopy ZIP CSV is empty")
            if info.file_size > MAX_DECOMPRESSED_CSV_BYTES:
                raise ValueError(
                    "Bhavcopy ZIP CSV exceeds the 20 MiB decompressed limit"
                )
            content = archive.read(info)
    except BadZipFile as exc:
        raise ValueError("Bhavcopy upload is not a valid ZIP archive") from exc
    if not content:
        raise ValueError("Bhavcopy ZIP CSV is empty")
    return info.filename, content


def _require_columns(
    frame: pd.DataFrame, required: tuple[str, ...], label: str
) -> pd.DataFrame:
    missing = [name for name in required if name not in frame.columns]
    if missing:
        raise ValueError(
            f"{label} missing required columns: " + ", ".join(missing)
        )
    return frame.loc[:, list(required)].copy()


def _normalize_text(
    frame: pd.DataFrame, columns: tuple[str, ...], label: str
) -> None:
    for column in columns:
        if frame[column].isna().any():
            raise ValueError(f"{label}.{column} must not contain missing values")
        frame[column] = frame[column].astype(str).str.strip()
        if frame[column].eq("").any():
            raise ValueError(f"{label}.{column} must not contain blank values")


def _validate_nifty(data: bytes) -> pd.DataFrame:
    frame = _require_columns(
        _read_csv(data, "NIFTY constituent CSV"), NIFTY_COLUMNS,
        "NIFTY constituent CSV",
    )
    _normalize_text(frame, NIFTY_COLUMNS, "NIFTY constituent CSV")
    duplicates = frame.duplicated(list(IDENTITY_COLUMNS), keep=False)
    if duplicates.any():
        raise ValueError(
            "NIFTY constituent CSV contains duplicate "
            "(Symbol, Series, ISIN Code) identities"
        )
    frame["_constituent_order"] = np.arange(len(frame), dtype="int64")
    return frame


def _parse_trade_dates(frame: pd.DataFrame) -> str:
    if frame["TradDt"].isna().any():
        raise ValueError("Bhavcopy.TradDt must not contain missing values")
    raw = frame["TradDt"].astype(str).str.strip()
    if (~raw.str.fullmatch(ISO_DATE)).any():
        raise ValueError("Bhavcopy.TradDt must use ISO YYYY-MM-DD format")
    try:
        dates = pd.to_datetime(raw, format="%Y-%m-%d", errors="raise")
    except ValueError as exc:
        raise ValueError("Bhavcopy.TradDt contains an invalid calendar date") from exc
    unique = dates.dt.strftime("%Y-%m-%d").unique().tolist()
    if len(unique) != 1:
        raise ValueError("Bhavcopy must contain exactly one trading date")
    frame["TradDt"] = dates
    return unique[0]


def _numeric(
    frame: pd.DataFrame, columns: tuple[str, ...], label: str
) -> None:
    for column in columns:
        try:
            values = pd.to_numeric(frame[column], errors="raise").astype(float)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label}.{column} must be numeric") from exc
        if not np.isfinite(values.to_numpy()).all():
            raise ValueError(f"{label}.{column} must contain finite values")
        frame[column] = values


def parse_nse_snapshot(
    nifty_csv_bytes: bytes,
    bhavcopy_zip_bytes: bytes,
    *,
    nifty_filename: str,
    bhavcopy_filename: str,
) -> NSESnapshotResult:
    """Parse, validate, and join one official supplied NSE/NIFTY snapshot."""

    nifty_bytes = _require_bytes(nifty_csv_bytes, "NIFTY constituent CSV")
    zip_bytes = _require_bytes(bhavcopy_zip_bytes, "Bhavcopy ZIP")
    nifty = _validate_nifty(nifty_bytes)
    inner_name, bhav_csv = _safe_inner_csv(zip_bytes)
    raw_bhav = _read_csv(bhav_csv, "NSE bhavcopy CSV")
    bhav_row_count = len(raw_bhav)
    bhav = _require_columns(raw_bhav, BHAVCOPY_COLUMNS, "NSE bhavcopy CSV")
    for column in ("Sgmt", "Src", *BHAV_IDENTITY_COLUMNS):
        bhav[column] = bhav[column].astype("string").str.strip()
    trade_date = _parse_trade_dates(bhav)

    key_names = list(BHAV_IDENTITY_COLUMNS)
    nifty_keys = nifty.loc[:, list(IDENTITY_COLUMNS)].rename(columns={
        "Symbol": "TckrSymb", "Series": "SctySrs", "ISIN Code": "ISIN",
    })
    relevant = bhav.merge(
        nifty_keys.drop_duplicates(), on=key_names, how="inner",
        validate="many_to_one",
    )
    _normalize_text(
        relevant,
        ("Sgmt", "Src", *BHAV_IDENTITY_COLUMNS),
        "Matched bhavcopy",
    )
    duplicated_matches = relevant.duplicated(key_names, keep=False)
    if duplicated_matches.any():
        raise ValueError(
            "NSE bhavcopy contains duplicate matches for a NIFTY identity"
        )

    joined = nifty.merge(
        bhav,
        left_on=list(IDENTITY_COLUMNS),
        right_on=key_names,
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    missing = joined.loc[joined["_merge"].ne("both"), "Symbol"].tolist()
    if missing:
        raise ValueError(
            f"NSE bhavcopy is missing {len(missing)} NIFTY constituent(s): "
            + ", ".join(missing)
        )
    if not joined["Sgmt"].eq("CM").all():
        raise ValueError("Matched bhavcopy rows must have Sgmt=CM")
    if not joined["Src"].eq("NSE").all():
        raise ValueError("Matched bhavcopy rows must have Src=NSE")

    numeric_columns = tuple(PRICE_MAP) + tuple(COUNT_MAP)
    _numeric(joined, numeric_columns, "Matched bhavcopy")
    if (joined[["OpnPric", "HghPric", "LwPric", "ClsPric"]] < 0).any().any():
        raise ValueError("Matched bhavcopy OHLC prices must not be negative")
    if (joined["ClsPric"] <= 0).any():
        raise ValueError("Matched bhavcopy close prices must be positive")
    if (joined[["LastPric", "PrvsClsgPric"]] < 0).any().any():
        raise ValueError(
            "Matched bhavcopy last and previous-close prices must not be negative"
        )
    if (joined[list(COUNT_MAP)] < 0).any().any():
        raise ValueError(
            "Matched bhavcopy volume, value, transaction, and lot fields "
            "must not be negative"
        )
    if (joined["HghPric"] < joined["LwPric"]).any():
        raise ValueError("Matched bhavcopy high price must be at least low price")

    zero_previous = joined["PrvsClsgPric"].eq(0)
    daily_change_pct = pd.Series(np.nan, index=joined.index, dtype="float64")
    nonzero_previous = ~zero_previous
    daily_change_pct.loc[nonzero_previous] = (
        joined.loc[nonzero_previous, "ClsPric"]
        / joined.loc[nonzero_previous, "PrvsClsgPric"]
        - 1
    ) * 100
    result = pd.DataFrame({
        "trade_date": joined["TradDt"].dt.strftime("%Y-%m-%d"),
        "ticker": joined["Symbol"],
        "company": joined["Company Name"],
        "industry": joined["Industry"],
        "series": joined["Series"],
        "isin": joined["ISIN Code"],
        **{output: joined[source] for source, output in PRICE_MAP.items()},
        "daily_change": joined["ClsPric"] - joined["PrvsClsgPric"],
        "daily_change_pct": daily_change_pct,
        **{output: joined[source] for source, output in COUNT_MAP.items()},
        "source": SOURCE_DESCRIPTION,
        "_constituent_order": joined["_constituent_order"],
    })
    for column in ("volume", "transaction_count", "board_lot_quantity"):
        values = result[column]
        if not np.equal(values, np.floor(values)).all():
            raise ValueError(f"Matched bhavcopy {column} must be whole numbers")
        result[column] = values.astype("int64")
    result = (
        result.sort_values("_constituent_order", kind="mergesort")
        .drop(columns="_constituent_order")
        .loc[:, list(CANONICAL_COLUMNS)]
        .reset_index(drop=True)
    )
    warnings = [
        "This is a one-day market snapshot imported from supplied local files.",
        "No live retrieval was performed.",
        "This snapshot alone is not sufficient for YoY, 3Y CAGR, 5Y CAGR, "
        "or historical-high recency.",
        "This snapshot alone is not sufficient for Research V2 historical "
        "point-in-time prices and fundamentals.",
    ]
    if zero_previous.any():
        warnings.append(
            f"{int(zero_previous.sum())} row(s) had previous_close=0; "
            "daily_change_pct is blank for those rows."
        )
    provenance = {
        "data_mode": "REAL CURRENT SNAPSHOT",
        "trade_date": trade_date,
        "constituent_count": len(nifty),
        "matched_count": len(result),
        "missing_count": 0,
        "duplicate_match_count": 0,
        "nifty_source_filename": Path(nifty_filename).name,
        "nse_source_filename": Path(bhavcopy_filename).name,
        "nifty_file_sha256": sha256(nifty_bytes).hexdigest(),
        "nse_zip_sha256": sha256(zip_bytes).hexdigest(),
        "inner_csv_filename": inner_name,
        "nifty_row_count": len(nifty),
        "bhavcopy_row_count": bhav_row_count,
        "relevant_bhavcopy_row_count": len(relevant),
        "adapter_version": ADAPTER_VERSION,
        "schema_columns": list(CANONICAL_COLUMNS),
        "source_label": SOURCE_DESCRIPTION,
        "validation_warnings": warnings,
        "ranking_available": False,
    }
    return NSESnapshotResult(result, provenance)


def load_nse_snapshot(
    nifty_csv_path: str | Path,
    bhavcopy_zip_path: str | Path,
) -> NSESnapshotResult:
    """Load an official supplied snapshot directly from two local files."""

    nifty_path = Path(nifty_csv_path)
    bhav_path = Path(bhavcopy_zip_path)
    if not nifty_path.is_file():
        raise ValueError(f"NIFTY constituent CSV does not exist: {nifty_path}")
    if not bhav_path.is_file():
        raise ValueError(f"NSE bhavcopy ZIP does not exist: {bhav_path}")
    return parse_nse_snapshot(
        nifty_path.read_bytes(),
        bhav_path.read_bytes(),
        nifty_filename=nifty_path.name,
        bhavcopy_filename=bhav_path.name,
    )
